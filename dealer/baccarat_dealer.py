# dealer/baccarat_dealer.py
from __future__ import annotations

import random
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class HandOutcome:
    # winner: "B" / "P" / "T"
    winner: str
    player_value: int
    banker_value: int

    # card strings (for audit / trace)
    player_cards: Tuple[str, ...]
    banker_cards: Tuple[str, ...]

    # third card strings (if any)
    player_third: Optional[str]
    banker_third: Optional[str]

    # ===== audit fields (required by rule_compliance_audit) =====
    is_natural: bool
    player_drew: bool
    banker_drew: bool
    player_third_value: Optional[int]


class ShoeFactory:
    """
    负责：建鞋 + 洗牌（可 seed，可复现）
    不负责：任何发牌规则
    """
    suits = ["Hearts", "Diamonds", "Clubs", "Spades"]
    ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

    def __init__(self, decks: int = 8):
        self.decks = decks

    def create_deck(self) -> List[str]:
        return [f"{rank} of {suit}" for suit in self.suits for rank in self.ranks]

    def create_shoe(self, seed: Optional[int] = None) -> Deque[str]:
        shoe: List[str] = []
        for _ in range(self.decks):
            shoe.extend(self.create_deck())

        rng = random.Random(seed)  # ✅ deterministic shuffle
        rng.shuffle(shoe)
        return deque(shoe)


class BaccaratDealer:
    """
    最基础发牌类：严格拷贝你原 BaccaratGame 的发牌规则
    - 点数映射：2-9=自身；10/J/Q/K=0；A=1
    - 闲补牌：<=5 补
    - 庄补牌：完全按你原 banker_draw 的分支逻辑
    - Natural：任一方>=8 直接结算（不补牌）
    - 发牌顺序：闲-庄-闲-庄（严格赌场顺序）
    """

    rank_values: Dict[str, int] = {
        "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
        "10": 0, "J": 0, "Q": 0, "K": 0, "A": 1
    }

    def calculate_hand_value(self, cards: List[str]) -> int:
        return sum(self.rank_values[c.split()[0]] for c in cards) % 10

    def player_draw(self, player_value: int) -> bool:
        # ✅ 完全照抄你原逻辑
        return player_value <= 5

    def banker_draw(self, banker_value: int, player_third_value: Optional[int]) -> bool:
        # ✅ 完全照抄你原逻辑（player_third_value 是点数；None 表示闲不补）
        if banker_value <= 2:
            return True
        if banker_value < 6 and (player_third_value is None):
            return True
        elif banker_value == 3 and (player_third_value is None or player_third_value != 8):
            return True
        elif banker_value == 4 and player_third_value is not None and 2 <= player_third_value <= 7:
            return True
        elif banker_value == 5 and player_third_value is not None and 4 <= player_third_value <= 7:
            return True
        elif banker_value == 6 and player_third_value is not None and player_third_value in [6, 7]:
            return True
        return False

    def determine_winner(self, banker_value: int, player_value: int) -> str:
        if banker_value > player_value:
            return "B"
        elif player_value > banker_value:
            return "P"
        return "T"

    def deal_one_hand(self, shoe: Deque[str]) -> HandOutcome:
        """
        一手完整发牌（含补牌），并返回可审计 outcome。
        不负责 cut-card 停鞋逻辑（由 adapter 控制）。
        """

        # ✅ 严格赌场顺序：闲-庄-闲-庄
        player_cards = [shoe.popleft()]
        banker_cards = [shoe.popleft()]
        player_cards.append(shoe.popleft())
        banker_cards.append(shoe.popleft())

        banker_value = self.calculate_hand_value(banker_cards)
        player_value = self.calculate_hand_value(player_cards)

        # ✅ Natural 8/9：直接结算（不补牌）
        is_natural = (player_value >= 8 or banker_value >= 8)
        if is_natural:
            return HandOutcome(
                winner=self.determine_winner(banker_value, player_value),
                player_value=player_value,
                banker_value=banker_value,
                player_cards=tuple(player_cards),
                banker_cards=tuple(banker_cards),
                player_third=None,
                banker_third=None,
                is_natural=True,
                player_drew=False,
                banker_drew=False,
                player_third_value=None,
            )

        # ---- 非 Natural：进入补牌流程 ----
        player_third: Optional[str] = None
        player_third_value: Optional[int] = None

        # ✅ 记录“闲是否应补牌”
        player_drew = self.player_draw(player_value)
        if player_drew:
            player_third = shoe.popleft()
            player_cards.append(player_third)
            player_value = self.calculate_hand_value(player_cards)
            player_third_value = self.rank_values[player_third.split()[0]]

        # ✅ 记录“庄是否应补牌”（使用初始两张的 banker_value，与原逻辑一致）
        banker_drew = self.banker_draw(banker_value, player_third_value)
        if banker_drew:
            banker_third = shoe.popleft()
            banker_cards.append(banker_third)
            banker_value = self.calculate_hand_value(banker_cards)
        else:
            banker_third = None

        return HandOutcome(
            winner=self.determine_winner(banker_value, player_value),
            player_value=player_value,
            banker_value=banker_value,
            player_cards=tuple(player_cards),
            banker_cards=tuple(banker_cards),
            player_third=player_third,
            banker_third=banker_third,
            is_natural=False,
            player_drew=player_drew,
            banker_drew=banker_drew,
            player_third_value=player_third_value,
        )