# core/deal_adapter.py
from typing import Dict, Generator, Optional

from dealer.baccarat_dealer import BaccaratDealer, ShoeFactory


PAYOUT = {
    "B": {"banker_profit": 0.95, "player_profit": -1.0, "tie_profit": 0.0},
    "P": {"banker_profit": -1.0, "player_profit": 1.0, "tie_profit": 0.0},
    "T": {"banker_profit": 0.0, "player_profit": 0.0, "tie_profit": 8.0},
}


def deal_hand_stream(
    *,
    shoe_id: int,
    seed: Optional[int] = None,
    decks: int = 8,
    cut_cards: int = 14,
    audit: bool = False,   # ✅ 新增
) -> Generator[Dict, None, None]:
    """
    唯一发牌入口
    - audit=False：生产模式（定型 hand-stream）
    - audit=True ：审计模式（附加 meta，不影响发牌）
    """

    factory = ShoeFactory(decks=decks)
    shoe = factory.create_shoe(seed=seed)

    dealer = BaccaratDealer()
    hand_id = 0

    MIN_CARDS_PER_HAND = 6

    while len(shoe) >= max(cut_cards, MIN_CARDS_PER_HAND):
        hand_id += 1

        # 发一手（返回 HandOutcome）
        outcome = dealer.deal_one_hand(shoe)

        payout = PAYOUT[outcome.winner]

        event = {
            "shoe_id": shoe_id,
            "hand_id": hand_id,
            "result": outcome.winner,
            "banker_profit": payout["banker_profit"],
            "player_profit": payout["player_profit"],
            "tie_profit": payout["tie_profit"],
        }

        # ===== 审计模式：附加 meta =====
        if audit:
            event["meta"] = {
                # 初始两张
                "player_init_cards": list(outcome.player_cards[:2]),
                "banker_init_cards": list(outcome.banker_cards[:2]),

                # 最终牌面
                "player_cards": list(outcome.player_cards),
                "banker_cards": list(outcome.banker_cards),

                # 第三张信息
                "player_third": outcome.player_third,
                "banker_third": outcome.banker_third,
                "player_third_value": outcome.player_third_value,

                # 行为标记
                "is_natural": outcome.is_natural,
                "player_drew": outcome.player_drew,
                "banker_drew": outcome.banker_drew,

                # 鞋状态
                "cards_left": len(shoe),
            }

        yield event

    # shoe end
    yield {
        "shoe_id": shoe_id,
        "is_shoe_end": True,
        "hands_dealt": hand_id,
        **(
            {"meta": {"cards_left": len(shoe)}} if audit else {}
        ),
    }