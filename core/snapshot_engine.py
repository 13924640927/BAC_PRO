# core/snapshot_engine.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional, Literal, Iterable, Union

from core.streak_engine import StreakEngine, StreakEvent, ShoeEndEvent

Side = Literal["B", "P"]


# ----------------------------
# Config
# ----------------------------
@dataclass(frozen=True)
class SnapshotConfig:
    # CUR (snapshot emission gate)
    cur_min: int = 3
    cur_max: int = 15

    # HIST (history inclusion + capping)
    hist_min: int = 3
    hist_max: int = 15

    # runtime
    debug: bool = False


# ----------------------------
# Canonicalization helpers
# ----------------------------
def canonical_hist_json(hist: Dict[str, int]) -> str:
    """
    Stable JSON string for dict[str,int] with numeric-sorted keys.
    Keys are expected like "3","4",...,"15".
    """
    if not hist:
        return "{}"
    # numeric sort
    items = sorted(hist.items(), key=lambda kv: int(kv[0]))
    return json.dumps({k: int(v) for k, v in items}, separators=(",", ":"), ensure_ascii=False)


def build_state_key(*, cur_side: Side, cur_len: int, hist_B: Dict[str, int], hist_P: Dict[str, int]) -> str:
    """
    State key MUST be deterministic.
    In this GE version, hist_B/hist_P are already GE buckets:
      key "k" means count(len >= k) within history (after HIST_MIN filter, capped by HIST_MAX).
    """
    hb = canonical_hist_json(hist_B)
    hp = canonical_hist_json(hist_P)
    return f"{cur_side}|{cur_len}|HB={hb}|HP={hp}"


# ----------------------------
# History state (GE-based)
# ----------------------------
@dataclass
class HistoryState:
    """
    Online-maintained history BEFORE current streak.

    IMPORTANT: This version stores GE(>=k) buckets directly:
      - For each history streak with eff_len:
          for k in [hist_min .. eff_len]: GE[k] += 1
      - Buckets are capped by hist_max via eff_len=min(real_len, hist_max).
      - Streaks with real_len < hist_min are ignored entirely (no bucket, no hands).
      - hands accumulation uses eff_len (cap after hist_max).
    """
    hist_B: Dict[str, int] = field(default_factory=dict)  # GE buckets for Banker side
    hist_P: Dict[str, int] = field(default_factory=dict)  # GE buckets for Player side
    hist_hB: int = 0  # cap'ed hands sum inside history (B)
    hist_hP: int = 0  # cap'ed hands sum inside history (P)

    def clone_key_material(self) -> Tuple[Dict[str, int], Dict[str, int]]:
        # return shallow copies (dict is small)
        return dict(self.hist_B), dict(self.hist_P)

    def apply_streak_to_history(self, side: Side, real_len: int, cfg: SnapshotConfig) -> None:
        """
        Update history with one completed streak (RESULT_FLIP only; caller must enforce).
        GE buckets: for k in [HIST_MIN..eff_len], +1
        hands: +eff_len on the corresponding side
        """
        if real_len < cfg.hist_min:
            return

        eff_len = cfg.hist_max if real_len >= cfg.hist_max else real_len

        # hands accumulation (cap after HIST_MAX)
        if side == "B":
            self.hist_hB += eff_len
            target = self.hist_B
        else:
            self.hist_hP += eff_len
            target = self.hist_P

        # GE buckets: count len >= k
        # keys are strings "3","4",...,"HIST_MAX"
        for k in range(cfg.hist_min, eff_len + 1):
            ks = str(k)
            target[ks] = target.get(ks, 0) + 1


# ----------------------------
# Run stats + Aggregator
# ----------------------------
@dataclass
class SnapshotRunStats:
    shoes_done: int = 0
    streak_events_seen: int = 0
    snapshots_emitted: int = 0


class SnapshotAggregator:
    """
    In-memory state aggregator (useful for TEST).
    For PROD DB mode, you typically won't use this and will UPSERT into DB instead.
    """
    def __init__(self):
        # state_key -> (cnt, sum_hist_hB, sum_hist_hP)
        self.states: Dict[str, Tuple[int, int, int]] = {}

    def add_state(self, state_key: str, hist_hB: int, hist_hP: int) -> None:
        cnt, shb, shp = self.states.get(state_key, (0, 0, 0))
        self.states[state_key] = (cnt + 1, shb + int(hist_hB), shp + int(hist_hP))


# ----------------------------
# Snapshot engine
# ----------------------------
class SnapshotEngine:
    """
    Consume a streak event stream and emit snapshot states.

    Snapshot emission rule (your finalized version):
      - Only for RESULT_FLIP streaks (valid streaks)
      - Exclude SHOE_END streak (censored last streak): no snapshot, not added to history
      - Each valid streak produces at most ONE snapshot:
          - if L_final < CUR_MIN: skip snapshot (but may enter history if >= HIST_MIN)
          - else: snapshot with cur_len = min(L_final, CUR_MAX)
      - Snapshot uses history BEFORE adding current streak.
      - After snapshot decision, add the streak to history (GE buckets) if it passes HIST_MIN.
    """
    def __init__(self, cfg: SnapshotConfig):
        self.cfg = cfg

    def run_streak_events(
        self,
        events: Iterable[Union[StreakEvent, ShoeEndEvent]],
    ) -> Tuple[SnapshotRunStats, SnapshotAggregator]:
        run_stats = SnapshotRunStats()
        agg = SnapshotAggregator()

        hist = HistoryState()

        for ev in events:
            if isinstance(ev, ShoeEndEvent):
                run_stats.shoes_done += 1
                hist = HistoryState()  # reset per shoe
                continue

            sev: StreakEvent = ev
            run_stats.streak_events_seen += 1

            # Exclude censored last streak completely
            if sev.end_reason == "SHOE_END":
                if self.cfg.debug:
                    print(f"[censored streak] shoe={sev.shoe_id} idx={sev.streak_idx} side={sev.side} len={sev.length}")
                continue

            # Only RESULT_FLIP streaks should arrive here; still keep it robust
            if sev.end_reason != "RESULT_FLIP":
                continue

            L_final = int(sev.length)

            # CUR_MIN gate: too short => no snapshot, but may still affect history (via HIST_MIN)
            if L_final < self.cfg.cur_min:
                hist.apply_streak_to_history(sev.side, L_final, self.cfg)
                continue

            cur_len = self.cfg.cur_max if L_final >= self.cfg.cur_max else L_final
            cur_side: Side = sev.side

            # Build state from history BEFORE adding current streak
            hB, hP = hist.clone_key_material()
            state_key = build_state_key(cur_side=cur_side, cur_len=cur_len, hist_B=hB, hist_P=hP)

            agg.add_state(state_key, hist.hist_hB, hist.hist_hP)
            run_stats.snapshots_emitted += 1

            if self.cfg.debug:
                print(
                    f"[snapshot] shoe={sev.shoe_id} streak_idx={sev.streak_idx} cur=({cur_side},{cur_len}) "
                    f"hist_hB={hist.hist_hB} hist_hP={hist.hist_hP} state={state_key[:140]}..."
                )

            # AFTER snapshot, update history with this completed streak
            hist.apply_streak_to_history(sev.side, L_final, self.cfg)

        return run_stats, agg

    def run_from_dealer(
        self,
        *,
        shoes: int,
        seed_start: int,
        decks: int = 8,
        cut_cards: int = 14,
    ) -> Tuple[SnapshotRunStats, SnapshotAggregator]:
        """
        Convenience: deal -> streak engine -> snapshot engine
        (Used mainly for TEST / quick checks)
        """
        streak_engine = StreakEngine(emit_shoe_end_event=True)
        events = streak_engine.run(shoes=shoes, seed_start=seed_start, decks=decks, cut_cards=cut_cards)
        return self.run_streak_events(events)