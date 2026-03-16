# pipeline/deal_trace_audit.py
from __future__ import annotations

import hashlib
from typing import Optional, List, Dict, Any

from dealer.baccarat_dealer import ShoeFactory
from core.deal_adapter import deal_hand_stream
from core.deal_monitor import DealAuditConfig, DealMonitor


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def results_hash_for_shoe(*, shoe_id: int, seed: int, decks: int, cut_cards: int) -> str:
    # 对逐手 result 做 hash（不存全量 events）
    h = hashlib.sha256()
    for e in deal_hand_stream(shoe_id=shoe_id, seed=seed, decks=decks, cut_cards=cut_cards):
        if e.get("is_shoe_end"):
            break
        h.update(e["result"].encode("utf-8"))
    return h.hexdigest()


def audit_one_shoe(
    *,
    shoe_id: int = 1,
    seed: Optional[int] = 123,
    decks: int = 8,
    cut_cards: int = 14,
    verbose: bool = True,
):
    factory = ShoeFactory(decks=decks)

    # 原牌（未洗牌）
    unshuffled: List[str] = []
    for _ in range(decks):
        unshuffled.extend(factory.create_deck())

    # 洗牌（同 seed 两次生成，做可复现断言）
    shuffled_1 = list(factory.create_shoe(seed=seed))
    shuffled_2 = list(factory.create_shoe(seed=seed))

    # monitor
    mon = DealMonitor(
        DealAuditConfig(
            verbose=verbose,
            trace_first_n_hands=10,
            record_cards=True,
            assert_hand_sequence=True,
            assert_tie_push_logic=True,
        )
    )

    mon.on_shoe_start(
        shoe_id=shoe_id,
        seed=seed,
        unshuffled_cards=unshuffled,
        shuffled_cards=shuffled_1,
    )

    # ✅ 断言 1：洗牌可复现（同 seed）
    if sha256_str("\n".join(shuffled_1)) != sha256_str("\n".join(shuffled_2)):
        raise AssertionError("Shuffle determinism failed: same seed produced different shuffle order")

    # ✅ 断言 2：发牌过程可复现（同 seed，两次结果序列 hash 一致）
    rh1 = results_hash_for_shoe(shoe_id=shoe_id, seed=seed, decks=decks, cut_cards=cut_cards)
    rh2 = results_hash_for_shoe(shoe_id=shoe_id, seed=seed, decks=decks, cut_cards=cut_cards)
    if rh1 != rh2:
        raise AssertionError(f"Deal determinism failed: results hash mismatch {rh1} != {rh2}")

    if verbose:
        print(f"[determinism] shuffle=OK, deal_results_hash={rh1}")

    # 正式发牌：走 deal_adapter（输出 hand-stream，供 monitor 审计）
    for e in deal_hand_stream(shoe_id=shoe_id, seed=seed, decks=decks, cut_cards=cut_cards):
        if e.get("is_shoe_end"):
            mon.on_shoe_end(e)
        else:
            mon.on_hand(e)

    summary = mon.report()
    print("\n=== AUDIT SUMMARY ===")
    print(summary)


if __name__ == "__main__":
    audit_one_shoe(shoe_id=1, seed=123, decks=8, cut_cards=14, verbose=True)