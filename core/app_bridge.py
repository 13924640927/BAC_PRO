# core/app_bridge.py
# Robust Bridge: Desktop APP -> BAC_PRO internal dealer + snapshot (GE history)
# Works even if BaccaratDealer has:
#   - __init__() with no args
#   - NO new_shoe() method
# Strategy:
#   - new shoe => recreate dealer instance + best-effort init hooks
#   - deal_one_hand => accept dict/object returns

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, List, Literal, Any
import secrets
import time

Side = Literal["B", "P"]
Result = Literal["B", "P", "T"]

from dealer.baccarat_dealer import BaccaratDealer
from core.snapshot_engine import SnapshotConfig, HistoryState, build_state_key


# ----------------------------
# Snapshot tracker (online)
# ----------------------------
@dataclass
class _OnlineStreak:
    side: Optional[Side] = None
    length: int = 0


class PremaxSnapshotTracker:
    """
    Online snapshot tracker:
      - T does not enter streak
      - snapshot only when a streak ends by RESULT_FLIP
      - last streak at shoe end is censored: no snapshot, not added to history
      - history buckets are GE(>=k) (HistoryState implements GE)
    """
    def __init__(self, cfg: SnapshotConfig):
        self.cfg = cfg
        self.hist = HistoryState()
        self.cur = _OnlineStreak()
        self.snapshots: List[Dict] = []
        self.streak_idx = -1

    def reset_for_new_shoe(self):
        self.hist = HistoryState()
        self.cur = _OnlineStreak()
        self.snapshots.clear()
        self.streak_idx = -1

    def _finalize_streak_result_flip(self, shoe_no: int):
        if self.cur.side is None or self.cur.length <= 0:
            return

        self.streak_idx += 1
        L_final = int(self.cur.length)
        side = self.cur.side

        if L_final >= self.cfg.cur_min:
            cur_len = self.cfg.cur_max if L_final >= self.cfg.cur_max else L_final
            hB, hP = self.hist.clone_key_material()
            state_key = build_state_key(cur_side=side, cur_len=cur_len, hist_B=hB, hist_P=hP)
            self.snapshots.append({
                "shoe_no": shoe_no,
                "streak_idx": self.streak_idx,
                "cur_side": side,
                "cur_len": cur_len,
                "hist_hB": self.hist.hist_hB,
                "hist_hP": self.hist.hist_hP,
                "hist_B": hB,   # GE buckets
                "hist_P": hP,   # GE buckets
                "state_key": state_key,
            })

        # update history after snapshot
        self.hist.apply_streak_to_history(side, L_final, self.cfg)
        self.cur = _OnlineStreak()

    def on_hand_result(self, shoe_no: int, result_side: Result):
        if result_side == "T":
            return

        side: Side = result_side

        if self.cur.side is None:
            self.cur.side = side
            self.cur.length = 1
            return

        if side == self.cur.side:
            self.cur.length += 1
        else:
            self._finalize_streak_result_flip(shoe_no)
            self.cur.side = side
            self.cur.length = 1

    def on_shoe_end(self):
        # last streak is censored: do not snapshot and do not add to history
        self.cur = _OnlineStreak()


# ----------------------------
# Dealer compatibility helpers
# ----------------------------
def _call_first_existing(obj: Any, method_names: List[str], *args, **kwargs) -> bool:
    """
    Try calling the first existing callable method in method_names.
    Return True if a call happened, else False.
    """
    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                fn(*args, **kwargs)
                return True
            except TypeError:
                # signature mismatch; try no-arg fallback for init-like methods
                try:
                    fn()
                    return True
                except Exception:
                    continue
            except Exception:
                continue
    return False


def _normalize_result(res: Any) -> Optional[str]:
    if res is None:
        return None
    if isinstance(res, str):
        r = res.strip()
        if r in ("B", "P", "T"):
            return r
        up = r.upper()
        if up in ("BANKER", "B"):
            return "B"
        if up in ("PLAYER", "P"):
            return "P"
        if up in ("TIE", "T"):
            return "T"
    return None


def _extract_outcome(outcome: Any) -> Dict[str, Any]:
    """
    Normalize dealer outcome into:
      {player_cards, banker_cards, winner}
    Supports dict, dataclass-like, or object with attrs.
    """
    if outcome is None:
        return {}

    if isinstance(outcome, dict):
        pcs = outcome.get("player_cards") or outcome.get("player") or outcome.get("P")
        bcs = outcome.get("banker_cards") or outcome.get("banker") or outcome.get("B")
        res = outcome.get("result") or outcome.get("winner") or outcome.get("result_side")
        return {"player_cards": pcs, "banker_cards": bcs, "winner": _normalize_result(res)}

    # object / dataclass
    pcs = getattr(outcome, "player_cards", None) or getattr(outcome, "player", None)
    bcs = getattr(outcome, "banker_cards", None) or getattr(outcome, "banker", None)
    res = getattr(outcome, "result", None) or getattr(outcome, "winner", None) or getattr(outcome, "result_side", None)
    return {"player_cards": pcs, "banker_cards": bcs, "winner": _normalize_result(res)}


# ----------------------------
# BAC_PRO Engine Wrapper for APP
# ----------------------------
class BACProEngineWrapper:
    """
    UI-facing engine with stable API:
      - new_shoe()
      - deal_one_hand() -> dict with player_cards/banker_cards/winner/hand_no/shoe_no
    Backend:
      - BaccaratDealer from BAC_PRO (whatever its API is)
      - Snapshot tracker based on BAC_PRO snapshot rules (GE history)
    PROD policy:
      - seed=None => random shoe, not intended to repeat
    """
    def __init__(
        self,
        *,
        decks: int = 8,
        cut_cards: int = 14,
        cur_min: int = 3,
        cur_max: int = 15,
        hist_min: int = 3,
        hist_max: int = 15,
        seed: Optional[int] = None,  # None=PROD random
    ):
        self.decks = decks
        self.cut_cards = cut_cards
        self.seed = seed

        self.shoe_no = 0
        self.hand_index = 0
        self._shoe_counter = 0

        self.snapshot_cfg = SnapshotConfig(
            cur_min=cur_min, cur_max=cur_max,
            hist_min=hist_min, hist_max=hist_max,
            debug=False,
        )
        self.snapshot_tracker = PremaxSnapshotTracker(self.snapshot_cfg)

        # create first shoe
        self.dealer = None
        self.new_shoe()

    def _next_shoe_seed(self) -> int:
        self._shoe_counter += 1
        if self.seed is not None:
            return int(self.seed) + int(self._shoe_counter)
        # random 64-bit seed
        r = secrets.randbits(64)
        t = time.time_ns() & ((1 << 64) - 1)
        return (r ^ t ^ (self._shoe_counter << 1)) & ((1 << 64) - 1)

    def _create_dealer(self):
        """
        Create BaccaratDealer with best-effort parameter passing.
        Many BAC_PRO versions use no-arg constructor, so we accept that.
        """
        shoe_seed = self._next_shoe_seed()

        # Try common constructor signatures
        try:
            d = BaccaratDealer(decks=self.decks, cut_cards=self.cut_cards, seed=shoe_seed)
            return d, shoe_seed
        except TypeError:
            d = BaccaratDealer()
            # best-effort set attrs if present
            for k, v in (("decks", self.decks), ("cut_cards", self.cut_cards), ("seed", shoe_seed)):
                if hasattr(d, k):
                    try:
                        setattr(d, k, v)
                    except Exception:
                        pass
            return d, shoe_seed

    def _init_shoe_best_effort(self, dealer: Any, shoe_seed: int):
        """
        If dealer has an explicit shoe init method, call it.
        Otherwise assume dealer is ready after construction.
        """
        # Common method names across versions
        init_names = [
            "new_shoe",
            "reset_shoe",
            "init_shoe",
            "build_shoe",
            "prepare_shoe",
            "shuffle",
            "shuffle_and_cut",
        ]

        # Try passing params; fallback handled inside _call_first_existing
        called = _call_first_existing(
            dealer,
            init_names,
            decks=self.decks,
            cut_cards=self.cut_cards,
            seed=shoe_seed,
        )

        # If nothing called, that's OK: dealer might already be initialized in __init__()
        return called

    def new_shoe(self):
        # New shoe => recreate dealer (guarantees compatibility when dealer has no new_shoe())
        self.dealer, shoe_seed = self._create_dealer()
        self._init_shoe_best_effort(self.dealer, shoe_seed)

        self.hand_index = 0
        self.shoe_no += 1
        self.snapshot_tracker.reset_for_new_shoe()

    def deal_one_hand(self) -> Optional[Dict]:
        """
        Deal one hand via BAC_PRO dealer.
        Return None when shoe ends.
        """
        if self.dealer is None:
            self.new_shoe()

        if not hasattr(self.dealer, "deal_one_hand") or not callable(getattr(self.dealer, "deal_one_hand")):
            raise RuntimeError("BaccaratDealer has no deal_one_hand() method")

        outcome_raw = self.dealer.deal_one_hand()

        # Shoe end convention: None indicates end
        if outcome_raw is None:
            self.snapshot_tracker.on_shoe_end()
            return None

        self.hand_index += 1
        out = _extract_outcome(outcome_raw)

        winner = out.get("winner")
        if winner in ("B", "P", "T"):
            self.snapshot_tracker.on_hand_result(self.shoe_no, winner)

        return {
            "player_cards": out.get("player_cards"),
            "banker_cards": out.get("banker_cards"),
            "winner": winner,
            "hand_no": self.hand_index,
            "shoe_no": self.shoe_no,
            # optional
            "snapshots": self.snapshot_tracker.snapshots,
        }