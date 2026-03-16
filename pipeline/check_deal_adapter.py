# pipeline/check_deal_adapter.py
from collections import Counter, defaultdict
from math import sqrt
from typing import List, Dict

from core.deal_adapter import deal_hand_stream


def collect_hands(
    *,
    num_shoes: int,
    seed_start: int = 1000,
) -> Dict:
    """
    跑多个 shoe，收集 hand-stream
    """
    all_results = []
    shoe_lengths = []

    for i in range(num_shoes):
        shoe_id = i + 1
        seed = seed_start + i

        hand_count = 0
        for e in deal_hand_stream(shoe_id=shoe_id, seed=seed):
            if "is_shoe_end" in e:
                shoe_lengths.append(hand_count)
            else:
                all_results.append(e["result"])
                hand_count += 1

    return {
        "results": all_results,
        "shoe_lengths": shoe_lengths,
        "num_hands": len(all_results),
        "num_shoes": num_shoes,
    }


def check_distribution(results: List[str]):
    counter = Counter(results)
    total = len(results)

    dist = {k: v / total for k, v in counter.items()}

    # 理论值（8 副牌长期）
    theory = {
        "B": 0.4586,
        "P": 0.4462,
        "T": 0.0952,
    }

    print("\n=== Distribution Check ===")
    for k in ["B", "P", "T"]:
        obs = dist.get(k, 0)
        exp = theory[k]
        # 3-sigma 区间
        sigma = sqrt(exp * (1 - exp) / total)
        ok = abs(obs - exp) <= 3 * sigma
        print(
            f"{k}: observed={obs:.4%}, "
            f"expected={exp:.4%}, "
            f"±3σ={3*sigma:.4%} -> {'OK' if ok else 'FAIL'}"
        )


def check_shoe_lengths(shoe_lengths: List[int]):
    avg = sum(shoe_lengths) / len(shoe_lengths)
    min_len = min(shoe_lengths)
    max_len = max(shoe_lengths)

    print("\n=== Shoe Length Check ===")
    print(f"Shoes: {len(shoe_lengths)}")
    print(f"Avg hands/shoe: {avg:.2f}")
    print(f"Min hands: {min_len}")
    print(f"Max hands: {max_len}")

    if min_len < 50 or max_len > 90:
        print("⚠️  WARNING: abnormal shoe length detected")
    else:
        print("OK")


def check_push_logic(num_shoes: int = 50):
    """
    确认 Tie 不污染 B/P
    """
    for e in deal_hand_stream(shoe_id=999, seed=999):
        if e.get("result") == "T":
            assert e["banker_profit"] == 0.0
            assert e["player_profit"] == 0.0
            assert e["tie_profit"] == 8.0
    print("\n=== Push Logic Check === OK")


if __name__ == "__main__":
    data = collect_hands(num_shoes=200)

    check_distribution(data["results"])
    check_shoe_lengths(data["shoe_lengths"])
    check_push_logic()