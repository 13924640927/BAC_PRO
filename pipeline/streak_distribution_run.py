#BAC_PRO/pipeline/streak_distribution_run.py

from __future__ import annotations

import argparse
import secrets
import time
from collections import defaultdict
from typing import Dict, Tuple, Optional

from core.deal_adapter import deal_hand_stream
from core.streak_engine import StreakEngine, StreakEvent
from core.streak_dist_db import DBConfig, StreakDistDB


def _compute_ge_from_eq(eq: Dict[int, int]) -> Dict[int, int]:
    """
    Given exact counts per length: eq[L] = count(len==L),
    return ge[L] = count(len>=L).
    """
    if not eq:
        return {}
    max_len = max(eq.keys())
    running = 0
    ge = {}
    for L in range(max_len, 0, -1):
        running += eq.get(L, 0)
        if running > 0:
            ge[L] = running
    return ge


def _resolve_master_seed(prod_master_seed: Optional[int]) -> int:
    return int(prod_master_seed) if prod_master_seed is not None else secrets.randbits(64)


def main():
    p = argparse.ArgumentParser(description="STREAK Distribution Runner (10^9 shoes capable, DB + resume)")

    p.add_argument("--mode", choices=["PROD"], default="PROD")

    # New run target
    p.add_argument("--shoes", type=int, default=100)

    # dealing params
    p.add_argument("--decks", type=int, default=8)
    p.add_argument("--cut_cards", type=int, default=14)

    # checkpoint every N shoes
    p.add_argument("--checkpoint", type=int, default=10000)

    # DB
    p.add_argument("--db_host", type=str, default="localhost")
    p.add_argument("--db_user", type=str, default="root")
    p.add_argument("--db_password", type=str, default="holybaby")
    p.add_argument("--db_name", type=str, default="BAC_PRO")

    # run id control
    p.add_argument("--run_id", type=str, default=None)
    p.add_argument("--resume_run_id", type=str, default=None)

    # seed control
    p.add_argument("--prod_master_seed", type=int, default=None, help="optional pin for reproducibility")

    # buffer flush (unique (side,censored,len) keys are small, but we still flush on checkpoint)
    p.add_argument("--flush_each_checkpoint", action="store_true", help="flush len table at every checkpoint (recommended)")

    # reporting
    p.add_argument("--report_top_len", type=int, default=30, help="print eq/ge up to this len each checkpoint")

    args = p.parse_args()

    db = StreakDistDB(DBConfig(
        host=args.db_host,
        user=args.db_user,
        password=args.db_password,
        database=args.db_name,
    ))

    # ----------------------------
    # RESUME or NEW RUN
    # ----------------------------
    if args.resume_run_id:
        run_id = args.resume_run_id
        master_seed0, shoes_done0, shoes_target0, params0, totals0 = db.load_run(run_id)
        if shoes_done0 >= shoes_target0:
            print(f"[RESUME] run already finished: run_id={run_id} shoes_done={shoes_done0:,} shoes_target={shoes_target0:,}")
            db.close()
            return

        print("\n=== RESUME STREAK RUN ===")
        print(f"run_id={run_id}")
        print(f"master_seed={master_seed0}")
        print(f"shoes_done={shoes_done0:,} / shoes_target={shoes_target0:,}")
        print(f"start_seed = master_seed + shoes_done = {master_seed0 + shoes_done0}")

        master_seed = master_seed0
        shoes_target = shoes_target0
        shoes_done = shoes_done0

        raw_b = totals0["raw_b"]
        raw_p = totals0["raw_p"]
        raw_t = totals0["raw_t"]
        censored_streaks = totals0["censored_streaks"]
        censored_b_hands = totals0["censored_b_hands"]
        censored_p_hands = totals0["censored_p_hands"]

        start_seed = master_seed + shoes_done
        shoes_to_run = shoes_target - shoes_done

    else:
        if args.run_id is None:
            run_id = f"STREAK_{int(time.time())}_{secrets.randbits(32):08x}"
        else:
            run_id = args.run_id

        master_seed = _resolve_master_seed(args.prod_master_seed)
        shoes_target = int(args.shoes)
        shoes_done = 0

        raw_b = raw_p = raw_t = 0
        censored_streaks = 0
        censored_b_hands = censored_p_hands = 0

        start_seed = master_seed
        shoes_to_run = shoes_target

        print("\n=== NEW STREAK RUN ===")
        print(f"run_id={run_id}")
        print(f"master_seed={master_seed}  (random if not pinned)")
        print("per-shoe seed = master_seed + shoe_index")

    params = {
        "decks": args.decks,
        "cut_cards": args.cut_cards,
        "seed_policy": "master_seed + shoe_index",
        "streak_mode": "B/P only (T ignored, does not break/increment)",
        "valid_streak": "RESULT_FLIP",
        "censored_streak": "SHOE_END (last streak of shoe)",
        "distributions": "eq(len) and ge(len) computed from eq at reporting time",
    }

    # write run header (or refresh on resume)
    db.upsert_run(
        run_id=run_id,
        mode="PROD",
        master_seed=master_seed,
        params=params,
        shoes_target=shoes_target,
        shoes_done=shoes_done,
        raw_b=raw_b,
        raw_p=raw_p,
        raw_t=raw_t,
        censored_streaks=censored_streaks,
        censored_b_hands=censored_b_hands,
        censored_p_hands=censored_p_hands,
        finished=False,
    )

    # ----------------------------
    # Main loop: deal -> streak -> stats -> DB
    # ----------------------------
    se = StreakEngine(emit_shoe_end_event=True)

    # in-memory exact distributions for checkpoint report only (not required for DB correctness)
    # key: (side, is_censored) -> dict[len] = cnt
    eq_dist: Dict[Tuple[str, int], Dict[int, int]] = {
        ("B", 0): defaultdict(int),
        ("P", 0): defaultdict(int),
        ("B", 1): defaultdict(int),
        ("P", 1): defaultdict(int),
    }

    checkpoint = int(args.checkpoint)
    report_top = int(args.report_top_len)

    for i in range(shoes_to_run):
        shoe_id = shoes_done + 1  # global shoe counter for this run
        seed = start_seed + i

        # collect raw B/P/T + feed streak engine
        hands_dealt = 0

        # IMPORTANT: StreakEngine is per-shoe streaming; we must reset internal state per shoe.
        # Our StreakEngine implementation emits events; to keep it safe, we use consume_result and close_shoe explicitly per shoe.
        # (We don't use se.run() here so we can count raw B/P/T precisely.)
        for e in deal_hand_stream(shoe_id=shoe_id, seed=seed, decks=args.decks, cut_cards=args.cut_cards):
            if e.get("is_shoe_end"):
                break
            hands_dealt += 1
            r = e["result"]
            if r == "B":
                raw_b += 1
            elif r == "P":
                raw_p += 1
            else:
                raw_t += 1

            ev = se.consume_result(shoe_id=shoe_id, result=r)
            if isinstance(ev, StreakEvent):
                # valid streak ends only when flip happens
                if ev.end_reason == "RESULT_FLIP":
                    db.add_len(side=ev.side, is_censored=0, length=ev.length, inc=1)
                    eq_dist[(ev.side, 0)][ev.length] += 1

        # close shoe -> censored last streak + shoe_end marker
        for ev in se.close_shoe(shoe_id=shoe_id, hands_dealt=hands_dealt):
            if isinstance(ev, StreakEvent) and ev.end_reason == "SHOE_END":
                # censored distribution
                db.add_len(side=ev.side, is_censored=1, length=ev.length, inc=1)
                eq_dist[(ev.side, 1)][ev.length] += 1

                censored_streaks += 1
                if ev.side == "B":
                    censored_b_hands += ev.length
                else:
                    censored_p_hands += ev.length

        shoes_done += 1

        # checkpoint
        if checkpoint > 0 and (shoes_done % checkpoint == 0):
            # flush len dist
            if args.flush_each_checkpoint:
                db.flush_len(run_id=run_id)

            # update run
            db.upsert_run(
                run_id=run_id,
                mode="PROD",
                master_seed=master_seed,
                params=params,
                shoes_target=shoes_target,
                shoes_done=shoes_done,
                raw_b=raw_b,
                raw_p=raw_p,
                raw_t=raw_t,
                censored_streaks=censored_streaks,
                censored_b_hands=censored_b_hands,
                censored_p_hands=censored_p_hands,
                finished=False,
            )

            # compute “censored 后 B/P”
            post_b = raw_b - censored_b_hands
            post_p = raw_p - censored_p_hands

            # checkpoint report (eq + ge for each)
            print(f"\n[@ checkpoint shoes_done={shoes_done:,}/{shoes_target:,}]")
            print(f"raw B/P/T: {raw_b:,} / {raw_p:,} / {raw_t:,}")
            print(f"censored streaks: {censored_streaks:,}  censored_hands B/P: {censored_b_hands:,} / {censored_p_hands:,}")
            print(f"post-censored B/P (raw - censored_last_streak_hands): {post_b:,} / {post_p:,}")

            for side in ("B", "P"):
                for is_c in (0, 1):
                    tag = "VALID" if is_c == 0 else "CENSORED"
                    eq = eq_dist[(side, is_c)]
                    ge = _compute_ge_from_eq(eq)

                    # print up to report_top
                    print(f"\n{tag} {side} streak dist (eq & ge, show len<= {report_top}):")
                    for L in range(1, report_top + 1):
                        eqv = eq.get(L, 0)
                        gev = ge.get(L, 0)
                        if eqv == 0 and gev == 0:
                            continue
                        print(f"  len={L:>2}: eq={eqv:,}  ge={gev:,}")

    # final flush
    db.flush_len(run_id=run_id)

    # final run update
    finished = (shoes_done >= shoes_target)
    db.upsert_run(
        run_id=run_id,
        mode="PROD",
        master_seed=master_seed,
        params=params,
        shoes_target=shoes_target,
        shoes_done=shoes_done,
        raw_b=raw_b,
        raw_p=raw_p,
        raw_t=raw_t,
        censored_streaks=censored_streaks,
        censored_b_hands=censored_b_hands,
        censored_p_hands=censored_p_hands,
        finished=finished,
    )

    post_b = raw_b - censored_b_hands
    post_p = raw_p - censored_p_hands

    print("\n=== FINAL SUMMARY ===")
    print(f"run_id={run_id}")
    print(f"shoes_done={shoes_done:,} / shoes_target={shoes_target:,} master_seed={master_seed}")
    print(f"raw B/P/T: {raw_b:,} / {raw_p:,} / {raw_t:,}")
    print(f"censored streaks: {censored_streaks:,}  censored_hands B/P: {censored_b_hands:,} / {censored_p_hands:,}")
    print(f"post-censored B/P: {post_b:,} / {post_p:,}")

    db.close()


if __name__ == "__main__":
    main()