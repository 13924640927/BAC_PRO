# ============================================================
# STATE SAMPLER
# ------------------------------------------------------------
# Role:
#   Massive STATE sampling & aggregation engine.
#   Produces raw STATE statistics for downstream EV extraction.
#
# Guarantees:
#   - Sampling logic, trigger timing, STATE_KEY logic LOCKED.
#   - No EV computation.
#   - No per-snapshot storage.
#   - Incremental UPSERT into premax_snapshot_state (STATE statistics).
#   - Natural resume support via aggregation + run checkpoint.
#
# Notes:
#   - This file is derived from snapshot_run_patched.py.
#   - Only the storage layer for STATE aggregation is adapted.
# ============================================================

# pipeline/snapshot_run.py
from __future__ import annotations
import hashlib
import argparse
import secrets
import time
from typing import List, Dict, Any, Union, Optional, Tuple
import os
import sys

# Ensure project ROOT (BAC_PRO/) is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
    

class StateStatsWriter:
    """
    STATE statistics writer (raw material layer).

    - Buffer + flush to DB
    - state_hash = sha256(state_key) hex (64 chars)  ✅ avoids 'Data too long'
    - Writes only columns that MUST exist:
        state_hash, cur_side, cur_len, hist_b_json, hist_p_json,
        cnt, sum_hist_hb, sum_hist_hp, created_at, updated_at
      ✅ avoids 'Unknown column n_b_win'
    """

    def __init__(self, db_cfg):
        import pymysql
        self.conn = pymysql.connect(
            host=db_cfg.host,
            user=db_cfg.user,
            password=db_cfg.password,
            database=db_cfg.database,
            autocommit=True,
            charset="utf8mb4",
        )
        self.buffer = {}  # state_hash -> row dict

        self.sql = """
        INSERT INTO premax_snapshot_state (
            state_hash,
            cur_side, cur_len,
            hist_b_json, hist_p_json,
            cnt, sum_hist_hb, sum_hist_hp,
            created_at, updated_at
        ) VALUES (
            %(state_hash)s,
            %(cur_side)s, %(cur_len)s,
            %(hist_b_json)s, %(hist_p_json)s,
            %(cnt)s, %(sum_hist_hb)s, %(sum_hist_hp)s,
            NOW(), NOW()
        )
        ON DUPLICATE KEY UPDATE
            cnt         = cnt + VALUES(cnt),
            sum_hist_hb = sum_hist_hb + VALUES(sum_hist_hb),
            sum_hist_hp = sum_hist_hp + VALUES(sum_hist_hp),
            updated_at  = NOW()
        """

    def add_state(
        self,
        state_key,
        cur_side,
        cur_len,
        hist_b_json,
        hist_p_json,
        hist_hb,
        hist_hp,
    ):
        state_hash = hashlib.sha256(state_key.encode("utf-8")).hexdigest()

        d = self.buffer.get(state_hash)
        if d is None:
            d = {
                "state_hash": state_hash,
                "cur_side": cur_side,
                "cur_len": cur_len,
                "hist_b_json": hist_b_json,
                "hist_p_json": hist_p_json,
                "cnt": 0,
                "sum_hist_hb": 0,
                "sum_hist_hp": 0,
            }
            self.buffer[state_hash] = d

        d["cnt"] += 1
        d["sum_hist_hb"] += int(hist_hb)
        d["sum_hist_hp"] += int(hist_hp)

    def flush_states(self):
        if not self.buffer:
            return
        with self.conn.cursor() as cur:
            for row in self.buffer.values():
                cur.execute(self.sql, row)
        self.buffer.clear()

    def close(self):
        try:
            self.flush_states()
        finally:
            try:
                self.conn.close()
            except Exception:
                pass
            
            
            



from core.deal_adapter import deal_hand_stream
from core.streak_engine import StreakEngine, StreakEvent, ShoeEndEvent
from core.snapshot_engine import (
    SnapshotEngine,
    SnapshotConfig,
    HistoryState,
    build_state_key,
    SnapshotAggregator,
    SnapshotRunStats,
    canonical_hist_json,
)


def _ge_to_real_end_lengths(ge: Dict[str, int], hist_min: int, hist_max: int) -> Dict[str, int]:
    """Convert GE(>=k) histogram into 'real end-length' keys to match APP口径.

    GE form means buckets store counts for "streak length >= k".
    APP expects to keep only lengths that actually occurred as streak END lengths,
    defined by ge[k] > ge[k+1] (or ge[k] > 0 when k+1 missing).
    Values are kept as ge[k], consistent with existing APP implementation.
    Keys are filtered to [hist_min, hist_max] and any key > hist_max is capped to hist_max.
    """
    if not ge:
        return {}
    tmp: Dict[int, int] = {}
    for k, v in ge.items():
        try:
            kk = int(k)
            vv = int(v)
        except Exception:
            continue
        if kk < hist_min:
            continue
        if kk > hist_max:
            kk = hist_max
        tmp[kk] = max(tmp.get(kk, 0), vv)
    if not tmp:
        return {}
    out: Dict[str, int] = {}
    for k in sorted(tmp.keys()):
        v = tmp.get(k, 0)
        next_v = tmp.get(k + 1, 0)
        if v > next_v:
            out[str(k)] = v
    return out



# ----------------------------
# utils
# ----------------------------
def _clip(seq: List[str], max_len: int) -> str:
    if len(seq) <= max_len:
        return "".join(seq)
    return "".join(seq[:max_len]) + f"...(+{len(seq) - max_len} hands)"


def _print_shoe_block(
    *,
    shoe_id: int,
    seed: int,
    hands_dealt: int,
    raw: List[str],
    notie: List[str],
    events: List[Union[StreakEvent, ShoeEndEvent]],
    snapshots: List[Dict[str, Any]],
    max_hands_print: int,
):
    print(f"\n=== SHOE TRACE #{shoe_id} ===")
    print(f"  meta: seed={seed} hands_dealt={hands_dealt} raw_len={len(raw)} notie_len={len(notie)}")

    print(f"  RAW(BPT)   : {_clip(raw, max_hands_print)}")
    print(f"  NoTie(BP)  : {_clip(notie, max_hands_print)}")

    streak_tokens: List[str] = []
    for ev in events:
        if isinstance(ev, StreakEvent):
            tok = f"{ev.side}{ev.length}"
            if ev.end_reason == "SHOE_END":
                tok += "(censored)"
            streak_tokens.append(tok)
    print(f"  STREAKS    : " + (", ".join(streak_tokens) if streak_tokens else "(none)"))

    print("  STREAK EVENTS:")
    for ev in events:
        if isinstance(ev, StreakEvent):
            print(f"    - StreakEvent(idx={ev.streak_idx}, side={ev.side}, len={ev.length}, end={ev.end_reason})")
        else:
            print(f"    - ShoeEndEvent(shoe_id={ev.shoe_id}, hands_dealt={ev.hands_dealt})")

    print("  SNAPSHOTS:")
    if not snapshots:
        print("    (none)")
    else:
        for s in snapshots:
            hb = s["hist_B"]
            hp = s["hist_P"]
            print(
                f"    - idx={s['streak_idx']} cur=({s['cur_side']},{s['cur_len']}) "
                f"hist_hB={s['hist_hB']} hist_hP={s['hist_hP']} "
                f"HB={hb} HP={hp}"
            )

    print(f"=== END SHOE #{shoe_id} ===")
    print("-" * 100)


# ----------------------------
# TEST mode: grouped blocks + in-memory aggregation
# ----------------------------
def _run_test_with_grouped_shoes(
    *,
    shoes: int,
    seed_start: int,
    decks: int,
    cut_cards: int,
    cfg: SnapshotConfig,
    max_hands_print: int,
) -> Tuple[SnapshotRunStats, SnapshotAggregator]:
    stats = SnapshotRunStats()
    agg = SnapshotAggregator()
    se = StreakEngine(emit_shoe_end_event=True)

    for i in range(shoes):
        shoe_id = i + 1
        seed = seed_start + i  # TEST deterministic

        raw: List[str] = []
        hands_dealt = 0
        for e in deal_hand_stream(shoe_id=shoe_id, seed=seed, decks=decks, cut_cards=cut_cards):
            if e.get("is_shoe_end"):
                hands_dealt = int(e.get("hands_dealt", hands_dealt))
                break
            hands_dealt += 1
            raw.append(e["result"])

        notie = [x for x in raw if x != "T"]

        events: List[Union[StreakEvent, ShoeEndEvent]] = []
        for r in raw:
            evt = se.consume_result(shoe_id=shoe_id, result=r)
            if evt is not None:
                events.append(evt)
        events.extend(list(se.close_shoe(shoe_id=shoe_id, hands_dealt=hands_dealt)))

        hist = HistoryState()
        shoe_snapshots: List[Dict[str, Any]] = []

        for ev in events:
            if isinstance(ev, ShoeEndEvent):
                stats.shoes_done += 1
                continue

            sev: StreakEvent = ev  # type: ignore
            stats.streak_events_seen += 1

            if sev.end_reason == "SHOE_END":
                continue

            L_final = sev.length

            # Runner snapshot decision is event-driven (turn point only), NOT a scan over lengths.
            # L_final is the JUST-ENDED streak length.
            # - If L_final < cur_min: ignore (no snapshot), but still advance history.
            # - Otherwise: emit exactly one snapshot; the state parameter uses L_param=min(L_final, cur_max).
            if L_final < cfg.cur_min:
                hist.apply_streak_to_history(sev.side, L_final, cfg)
                continue

            cur_len = cfg.cur_max if L_final >= cfg.cur_max else L_final
            cur_side = sev.side

            ge_B, ge_P = hist.clone_key_material()
            hist_min = int(getattr(cfg, 'hist_min', getattr(cfg, 'cur_min', 3)))
            hist_max = int(getattr(cfg, 'hist_max', getattr(cfg, 'cur_max', 10)))
            hB = _ge_to_real_end_lengths(ge_B, hist_min, hist_max)
            hP = _ge_to_real_end_lengths(ge_P, hist_min, hist_max)
            state_key = build_state_key(cur_side=cur_side, cur_len=cur_len, hist_B=hB, hist_P=hP)

            agg.add_state(state_key, hist.hist_hB, hist.hist_hP)
            stats.snapshots_emitted += 1

            shoe_snapshots.append(
                {
                    "shoe_id": shoe_id,
                    "streak_idx": sev.streak_idx,
                    "cur_side": cur_side,
                    "cur_len": cur_len,
                    "hist_hB": hist.hist_hB,
                    "hist_hP": hist.hist_hP,
                    "hist_B": hB,
                    "hist_P": hP,
                    "state_key": state_key,
                }
            )

            hist.apply_streak_to_history(sev.side, L_final, cfg)

        _print_shoe_block(
            shoe_id=shoe_id,
            seed=seed,
            hands_dealt=hands_dealt,
            raw=raw,
            notie=notie,
            events=events,
            snapshots=shoe_snapshots,
            max_hands_print=max_hands_print,
        )

    return stats, agg


# ----------------------------
# PROD mode: stream -> DB UPSERT
# ----------------------------
def _resolve_prod_master_seed(prod_master_seed: Optional[int]) -> int:
    if prod_master_seed is not None:
        return int(prod_master_seed)
    return secrets.randbits(64)


def _run_prod_to_db(
    *,
    shoes: int,
    master_seed: int,
    decks: int,
    cut_cards: int,
    cfg: SnapshotConfig,
    checkpoint_shoes: int,
    flush_states_every: int,
    db_host: str,
    db_user: str,
    db_password: str,
    db_name: str,
    run_id: str,
    shoes_done_base: int,
    shoes_target_total: int,
):
    from core.snapshot_db import DBConfig, SnapshotDBWriter

    writer = SnapshotDBWriter(DBConfig(host=db_host, user=db_user, password=db_password, database=db_name))
    state_writer = StateStatsWriter(DBConfig(host=db_host, user=db_user, password=db_password, database=db_name))

    params = {
        "cur_min": cfg.cur_min,
        "cur_max": cfg.cur_max,
        "hist_min": cfg.hist_min,
        "hist_max": cfg.hist_max,
        "decks": decks,
        "cut_cards": cut_cards,
        "seed_policy": "PROD master_seed + shoe_index (global), resume supported",
    }

    shoes_done = shoes_done_base
    snapshots_done = 0
    states_touched = 0

    streak_engine = StreakEngine(emit_shoe_end_event=True)
    hist = HistoryState()

    # init/update run row
    writer.upsert_run_checkpoint(
        run_id=run_id,
        mode="PROD",
        master_seed=master_seed - shoes_done_base,  # store ORIGINAL master_seed
        params=params,
        shoes_target=shoes_target_total,
        shoes_done=shoes_done,
        snapshots_done=0,
        states_touched=0,
        finished=False,
    )

    def flush_states(force: bool = False):
        nonlocal states_touched
        if force or (len(state_writer.buffer) >= flush_states_every):
            states_touched += len(state_writer.buffer)
            state_writer.flush_states()

    try:
        for ev in streak_engine.run(shoes=shoes, seed_start=master_seed, decks=decks, cut_cards=cut_cards):
            if isinstance(ev, ShoeEndEvent):
                shoes_done += 1
                hist = HistoryState()

                if checkpoint_shoes and (shoes_done % checkpoint_shoes == 0):
                    flush_states(force=True)
                    writer.upsert_run_checkpoint(
                        run_id=run_id,
                        mode="PROD",
                        master_seed=master_seed - shoes_done_base,
                        params=params,
                        shoes_target=shoes_target_total,
                        shoes_done=shoes_done,
                        snapshots_done=snapshots_done,
                        states_touched=states_touched,
                        finished=False,
                    )
                    print(
                        f"[PROD checkpoint] shoes_done={shoes_done:,}/{shoes_target_total:,} "
                        f"snapshots={snapshots_done:,} buffered_states={len(state_writer.buffer):,}"
                    )
                continue

            sev: StreakEvent = ev  # type: ignore

            if sev.end_reason == "SHOE_END":
                continue

            L_final = sev.length

            # Runner snapshot decision is event-driven (turn point only), NOT a scan over lengths.
            # L_final is the JUST-ENDED streak length.
            # - If L_final < cur_min: ignore (no snapshot), but still advance history.
            # - Otherwise: emit exactly one snapshot; the state parameter uses L_param=min(L_final, cur_max).
            if L_final < cfg.cur_min:
                hist.apply_streak_to_history(sev.side, L_final, cfg)
                continue

            cur_len = cfg.cur_max if L_final >= cfg.cur_max else L_final
            cur_side = sev.side
            ge_B, ge_P = hist.clone_key_material()
            hist_min = int(getattr(cfg, 'hist_min', getattr(cfg, 'cur_min', 3)))
            hist_max = int(getattr(cfg, 'hist_max', getattr(cfg, 'cur_max', 10)))
            hB = _ge_to_real_end_lengths(ge_B, hist_min, hist_max)
            hP = _ge_to_real_end_lengths(ge_P, hist_min, hist_max)
            state_key = build_state_key(cur_side=cur_side, cur_len=cur_len, hist_B=hB, hist_P=hP)

            hb_json = canonical_hist_json(hB)
            hp_json = canonical_hist_json(hP)

            state_writer.add_state(
                state_key=state_key,
                cur_side=cur_side,
                cur_len=cur_len,
                hist_b_json=hb_json,
                hist_p_json=hp_json,
                hist_hb=hist.hist_hB,
                hist_hp=hist.hist_hP,
            )
            snapshots_done += 1

            hist.apply_streak_to_history(sev.side, L_final, cfg)

            flush_states(force=False)

        flush_states(force=True)

        finished = (shoes_done >= shoes_target_total)
        writer.upsert_run_checkpoint(
            run_id=run_id,
            mode="PROD",
            master_seed=master_seed - shoes_done_base,
            params=params,
            shoes_target=shoes_target_total,
            shoes_done=shoes_done,
            snapshots_done=snapshots_done,
            states_touched=states_touched,
            finished=finished,
        )
        print(f"[PROD done] shoes_done={shoes_done:,} snapshots={snapshots_done:,} states_touched={states_touched:,}")

    finally:
        state_writer.close()
    writer.close()


# ----------------------------
# main
# ----------------------------
def main():
    p = argparse.ArgumentParser(description="PREMAX Snapshot Runner (TEST grouped audit + PROD DB + RESUME)")

    p.add_argument("--mode", choices=["TEST", "PROD"], default="TEST")
    p.add_argument("--shoes", type=int, default=20)      # for NEW PROD only
    p.add_argument("--seed_start", type=int, default=1)  # TEST only

    p.add_argument("--decks", type=int, default=8)
    p.add_argument("--cut_cards", type=int, default=14)
    p.add_argument("--checkpoint", type=int, default=0)

    p.add_argument("--cur_min", type=int, default=3)
    p.add_argument("--cur_max", type=int, default=12)
    p.add_argument("--hist_min", type=int, default=3)
    p.add_argument("--hist_max", type=int, default=15)

    p.add_argument("--trace_max_hands", type=int, default=200)

    # PROD seed control (new run)
    p.add_argument("--prod_master_seed", type=int, default=None)

    # DB params
    p.add_argument("--run_id", type=str, default=None)
    p.add_argument("--resume_run_id", type=str, default=None, help="resume existing PROD run_id")
    p.add_argument("--db_host", type=str, default="localhost")
    p.add_argument("--db_user", type=str, default="root")
    p.add_argument("--db_password", type=str, default="")
    p.add_argument("--db_name", type=str, default="BAC_PRO")
    p.add_argument("--flush_states_every", type=int, default=50000)

    args = p.parse_args()

    # ------------------------------------------------------------------
    # SNAPSHOT RULES (runner-level; snapshot_engine remains unchanged)
    #
    # 1) Trigger: we only consider a streak when it has JUST ENDED (a turn).
    #    - Ongoing streaks are never snapshotted here.
    #    - The final SHOE_END streak is censored: sev.end_reason == 'SHOE_END' => skip.
    #
    # 2) Eligibility by length (cur_min/cur_max):
    #    - If L_final < cur_min: ignore (no snapshot). We still advance HistoryState.
    #    - If L_final >= cur_min: emit exactly ONE snapshot for this turn.
    #
    # 3) Length bucket / state parameter:
    #    - STREAK_LEN used in the state is L_param = min(L_final, cur_max).
    #      (>= cur_max is grouped into the cur_max bucket.)
    #
    # 4) IMPORTANT CLARIFICATION:
    #    - First occurrence of an eligible length ALSO triggers a snapshot.
    #    - We do NOT scan all lengths in [cur_min, cur_max]. No 'full-range' sweep.
    #    - The 'photo zone' (bucket set) concept is descriptive; it is NOT a prerequisite.
    # ------------------------------------------------------------------

    cfg = SnapshotConfig(
        cur_min=args.cur_min,
        cur_max=args.cur_max,
        hist_min=args.hist_min,
        hist_max=args.hist_max,
        debug=(args.mode == "TEST"),
    )

    if args.mode == "TEST":
        print("\n=== RUN SEED POLICY ===")
        print(f"mode=TEST (deterministic) seed_start={args.seed_start} (seed = seed_start + i)")

        stats, agg = _run_test_with_grouped_shoes(
            shoes=args.shoes,
            seed_start=args.seed_start,
            decks=args.decks,
            cut_cards=args.cut_cards,
            cfg=cfg,
            max_hands_print=args.trace_max_hands,
        )

        print("\n=== SNAPSHOT RUN SUMMARY ===")
        print(f"mode: {args.mode}")
        print(f"shoes_done: {stats.shoes_done:,}")
        print(f"streak_events_seen: {stats.streak_events_seen:,}")
        print(f"snapshots_emitted: {stats.snapshots_emitted:,}")
        print(f"unique_states: {len(agg.states):,}")
        return

    # ----------------------------
    # PROD: NEW RUN or RESUME
    # ----------------------------
    from core.snapshot_db import DBConfig, SnapshotDBWriter

    checkpoint_shoes = args.checkpoint if args.checkpoint else 10000

    # RESUME
    if args.resume_run_id is not None:
        run_id = args.resume_run_id
        writer = SnapshotDBWriter(DBConfig(host=args.db_host, user=args.db_user, password=args.db_password, database=args.db_name))
        master_seed0, shoes_done0, shoes_target0, _params = writer.load_run_for_resume(run_id)
        writer.close()

        if shoes_done0 >= shoes_target0:
            print(f"[RESUME] run_id={run_id} already finished: shoes_done={shoes_done0:,} shoes_target={shoes_target0:,}")
            return

        print("\n=== RESUME RUN ===")
        print(f"run_id={run_id}")
        print(f"master_seed={master_seed0}")
        print(f"shoes_done={shoes_done0:,} / shoes_target={shoes_target0:,}")
        print(f"starting_seed = master_seed + shoes_done = {master_seed0 + shoes_done0}")

        # run remaining shoes only, but maintain global shoes_done in run table
        remaining = shoes_target0 - shoes_done0
        _run_prod_to_db(
            shoes=remaining,
            master_seed=master_seed0 + shoes_done0,
            decks=args.decks,
            cut_cards=args.cut_cards,
            cfg=cfg,
            checkpoint_shoes=checkpoint_shoes,
            flush_states_every=args.flush_states_every,
            db_host=args.db_host,
            db_user=args.db_user,
            db_password=args.db_password,
            db_name=args.db_name,
            run_id=run_id,
            shoes_done_base=shoes_done0,
            shoes_target_total=shoes_target0,
        )
        return

    # NEW RUN
    if args.run_id is None:
        args.run_id = f"PREMAX_{int(time.time())}_{secrets.randbits(32):08x}"
    run_id = args.run_id
    master_seed0 = _resolve_prod_master_seed(args.prod_master_seed)

    print("\n=== NEW PROD RUN ===")
    print(f"run_id={run_id}")
    print(f"master_seed={master_seed0}")
    print("per-shoe seed = master_seed + shoe_index (shoe_index starts at 0)")

    _run_prod_to_db(
        shoes=args.shoes,
        master_seed=master_seed0,
        decks=args.decks,
        cut_cards=args.cut_cards,
        cfg=cfg,
        checkpoint_shoes=checkpoint_shoes,
        flush_states_every=args.flush_states_every,
        db_host=args.db_host,
        db_user=args.db_user,
        db_password=args.db_password,
        db_name=args.db_name,
        run_id=run_id,
        shoes_done_base=0,
        shoes_target_total=args.shoes,
    )


if __name__ == "__main__":
    main()
