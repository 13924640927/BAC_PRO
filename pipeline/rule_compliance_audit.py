# pipeline/rule_compliance_audit.py
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional, Dict, Any

from dealer.baccarat_dealer import BaccaratDealer
from core.deal_adapter import deal_hand_stream


MIN_CARDS_PER_HAND = 6  # 一手最多用 6 张（双方都补）


@dataclass
class AuditStats:
    shoes_checked: int = 0
    hands_checked: int = 0
    tie_checked: int = 0
    natural_checked: int = 0
    player_draw_checked: int = 0
    banker_draw_checked: int = 0
    shoe_end_checked: int = 0


def _assert(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def audit_rules(
    *,
    shoes: int,
    seed_start: int,
    cut_cards: int,
    fail_fast: bool = True,
    quiet: bool = False,
) -> AuditStats:
    """
    规则合规审计（纯验证，不建模）
    - 逐手复算 Natural / 闲补牌 / 庄补牌是否应发生，并与实际动作比对
    - 检查 Tie push 语义
    - 检查 shoe_end 合理性（cards_left < max(cut_cards, 6)）
    - 检查 hand_id 连续性
    """
    dealer = BaccaratDealer()
    stats = AuditStats()

    for i in range(shoes):
        shoe_id = i + 1
        seed = seed_start + i

        last_hand_id = 0
        seen_end = False

        try:
            for e in deal_hand_stream(shoe_id=shoe_id, seed=seed, cut_cards=cut_cards, audit=True):
                # --- shoe end ---
                if e.get("is_shoe_end"):
                    seen_end = True
                    stats.shoe_end_checked += 1

                    meta = e.get("meta", {})
                    cards_left = meta.get("cards_left")
                    if cards_left is not None:
                        _assert(
                            cards_left < max(cut_cards, MIN_CARDS_PER_HAND),
                            f"[SHOE_END INVALID] shoe={shoe_id} seed={seed} cards_left={cards_left} "
                            f"expected < {max(cut_cards, MIN_CARDS_PER_HAND)}"
                        )
                    break

                # --- hand event ---
                stats.hands_checked += 1

                # hand_id sequence
                hid = int(e["hand_id"])
                _assert(
                    hid == last_hand_id + 1,
                    f"[HAND_ID SEQ BROKEN] shoe={shoe_id} seed={seed} last={last_hand_id} current={hid}"
                )
                last_hand_id = hid

                meta: Dict[str, Any] = e.get("meta") or {}
                _assert(meta != {}, f"[MISSING META] shoe={shoe_id} seed={seed} hand={hid} (need audit=True meta)")

                # Tie push logic
                if e["result"] == "T":
                    stats.tie_checked += 1
                    _assert(
                        e["banker_profit"] == 0.0 and e["player_profit"] == 0.0 and e["tie_profit"] == 8.0,
                        f"[TIE PUSH VIOLATION] shoe={shoe_id} seed={seed} hand={hid} event={e}"
                    )

                # Recompute initial values from init cards
                p_init = meta["player_init_cards"]
                b_init = meta["banker_init_cards"]
                p_init_v = dealer.calculate_hand_value(p_init)
                b_init_v = dealer.calculate_hand_value(b_init)

                should_natural = (p_init_v >= 8 or b_init_v >= 8)
                stats.natural_checked += 1
                _assert(
                    bool(meta["is_natural"]) == should_natural,
                    f"[NATURAL MISMATCH] shoe={shoe_id} seed={seed} hand={hid} "
                    f"p_init_v={p_init_v} b_init_v={b_init_v} should={should_natural} meta={meta}"
                )

                # Natural => no draws
                if should_natural:
                    _assert(
                        meta["player_drew"] is False and meta["banker_drew"] is False,
                        f"[NATURAL DRAW ERROR] shoe={shoe_id} seed={seed} hand={hid} meta={meta}"
                    )
                    continue

                # Player draw rule: <= 5 draw
                should_player_draw = dealer.player_draw(p_init_v)
                stats.player_draw_checked += 1
                _assert(
                    bool(meta["player_drew"]) == should_player_draw,
                    f"[PLAYER DRAW MISMATCH] shoe={shoe_id} seed={seed} hand={hid} "
                    f"p_init_v={p_init_v} should={should_player_draw} meta={meta}"
                )

                # Banker draw rule uses banker initial value + player_third_value (None if player stands)
                ptv = meta.get("player_third_value", None)
                should_banker_draw = dealer.banker_draw(b_init_v, ptv)
                stats.banker_draw_checked += 1
                _assert(
                    bool(meta["banker_drew"]) == should_banker_draw,
                    f"[BANKER DRAW MISMATCH] shoe={shoe_id} seed={seed} hand={hid} "
                    f"b_init_v={b_init_v} ptv={ptv} should={should_banker_draw} meta={meta}"
                )

            _assert(seen_end, f"[NO SHOE_END] shoe={shoe_id} seed={seed} ended without shoe_end event")

        except AssertionError as ex:
            if not quiet:
                print("\n=== RULE AUDIT FAIL ===")
                print(str(ex))
                print(f"shoe_id={shoe_id} seed={seed} last_hand_id={last_hand_id}")
            if fail_fast:
                raise
            # fail_fast=False: continue to next shoe

        stats.shoes_checked += 1
        if (not quiet) and (stats.shoes_checked % 1000 == 0):
            print(f"[progress] shoes_checked={stats.shoes_checked:,} hands_checked={stats.hands_checked:,}")

    if not quiet:
        print("\n=== RULE AUDIT PASS ===")
        print(
            f"shoes={stats.shoes_checked:,}, hands={stats.hands_checked:,}, "
            f"tie={stats.tie_checked:,}, natural={stats.natural_checked:,}, "
            f"player_draw_checks={stats.player_draw_checked:,}, banker_draw_checks={stats.banker_draw_checked:,}, "
            f"shoe_end_checks={stats.shoe_end_checked:,}"
        )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Rule compliance audit for BAC dealer/adapter (pure verification)")
    parser.add_argument("--shoes", type=int, default=100, help="number of shoes to audit")
    parser.add_argument("--seed_start", type=int, default=1000, help="starting seed")
    parser.add_argument("--cut_cards", type=int, default=14, help="cut-card threshold")
    parser.add_argument("--fail_fast", action="store_true", help="stop immediately on first failure")
    parser.add_argument("--quiet", action="store_true", help="less output (only final summary unless fail)")

    args = parser.parse_args()

    audit_rules(
        shoes=args.shoes,
        seed_start=args.seed_start,
        cut_cards=args.cut_cards,
        fail_fast=args.fail_fast,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()