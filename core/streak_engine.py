# core/streak_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal, Iterator, Union

from core.deal_adapter import deal_hand_stream

Side = Literal["B", "P"]
EndReason = Literal["RESULT_FLIP", "SHOE_END"]


@dataclass(frozen=True)
class StreakEvent:
    """
    A completed streak inside a shoe.
    NOTE:
      - RESULT_FLIP: valid streak (ended by opposite side)
      - SHOE_END: censored streak (ended by shoe end)
    """
    shoe_id: int
    streak_idx: int          # index among streak events emitted within shoe
    side: Side
    length: int              # real final length (L_final)
    end_reason: EndReason    # RESULT_FLIP or SHOE_END


@dataclass(frozen=True)
class ShoeEndEvent:
    """
    Explicit shoe end marker event.
    Useful for snapshot/prod progress tracking & resuming.
    """
    shoe_id: int
    hands_dealt: int


Event = Union[StreakEvent, ShoeEndEvent]


class StreakEngine:
    """
    STREAK ENGINE (Mode B, Fact Layer)
    ----------------------------------
    - T is ignored (does not increment, does not break)
    - streaks only on B/P
    - emits streak on flip (RESULT_FLIP)
    - emits last streak on shoe end (SHOE_END)  <-- IMPORTANT: snapshot decides whether to use it
    - optionally emits ShoeEndEvent for lifecycle clarity
    """

    def __init__(self, emit_shoe_end_event: bool = True):
        self.emit_shoe_end_event = emit_shoe_end_event

        # current streak state
        self._cur_side: Optional[Side] = None
        self._cur_len: int = 0

        # streak index within current shoe (counts emitted streak events)
        self._streak_idx: int = 0

    def _emit_current_if_any(self, *, shoe_id: int, end_reason: EndReason) -> Optional[StreakEvent]:
        if self._cur_side is None or self._cur_len <= 0:
            return None
        evt = StreakEvent(
            shoe_id=shoe_id,
            streak_idx=self._streak_idx,
            side=self._cur_side,
            length=self._cur_len,
            end_reason=end_reason,
        )
        self._streak_idx += 1
        return evt

    def _start_new(self, side: Side) -> None:
        self._cur_side = side
        self._cur_len = 1

    def _reset_shoe(self) -> None:
        self._cur_side = None
        self._cur_len = 0
        self._streak_idx = 0

    def consume_result(self, *, shoe_id: int, result: str) -> Optional[StreakEvent]:
        """
        Consume one hand result.
        Returns a StreakEvent ONLY when a streak completes by RESULT_FLIP.
        """
        if result == "T":
            # Mode B: ignore T completely
            return None
        if result not in ("B", "P"):
            raise ValueError(f"Unknown result: {result}")

        side: Side = result  # type: ignore

        if self._cur_side is None:
            self._start_new(side)
            return None

        if side == self._cur_side:
            self._cur_len += 1
            return None

        # flip -> emit previous streak as RESULT_FLIP, then start new
        evt = self._emit_current_if_any(shoe_id=shoe_id, end_reason="RESULT_FLIP")
        self._start_new(side)
        return evt

    def close_shoe(self, *, shoe_id: int, hands_dealt: int) -> Iterator[Event]:
        """
        Called when shoe ends.
        Emits the last streak with end_reason=SHOE_END (censored),
        then optionally emits ShoeEndEvent.
        """
        last_evt = self._emit_current_if_any(shoe_id=shoe_id, end_reason="SHOE_END")
        if last_evt is not None:
            yield last_evt

        if self.emit_shoe_end_event:
            yield ShoeEndEvent(shoe_id=shoe_id, hands_dealt=hands_dealt)

        self._reset_shoe()

    def run(
        self,
        *,
        shoes: int,
        seed_start: int = 1,
        decks: int = 8,
        cut_cards: int = 14,
    ) -> Iterator[Event]:
        """
        Run N shoes: call deal_adapter -> dealer, and yield streak events (and optional shoe_end events).
        """
        for i in range(shoes):
            shoe_id = i + 1
            seed = seed_start + i

            hands_dealt = 0

            for e in deal_hand_stream(shoe_id=shoe_id, seed=seed, decks=decks, cut_cards=cut_cards):
                if e.get("is_shoe_end"):
                    hands_dealt = int(e.get("hands_dealt", hands_dealt))
                    # shoe end: emit last streak as SHOE_END (censored), and shoe_end marker
                    yield from self.close_shoe(shoe_id=shoe_id, hands_dealt=hands_dealt)
                    break

                hands_dealt += 1
                evt = self.consume_result(shoe_id=shoe_id, result=e["result"])
                if evt is not None:
                    yield evt