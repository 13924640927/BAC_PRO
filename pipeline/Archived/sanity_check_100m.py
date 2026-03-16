# pipeline/sanity_check_100m.py
from __future__ import annotations

import argparse
from collections import deque
from math import sqrt
from typing import Deque, Tuple

from core.deal_adapter import deal_hand_stream

# ===== Engine baseline (theory) you specified =====
THEORY = {"B": 0.458597, "P": 0.446247, "T": 0.095152}

# Trend window in "number of checkpoints"
TREND_N_DEFAULT = 20  # trend = current - N checkpoints ago


def run_sanity_check(
    *,
    total_shoes: int,
    checkpoint: int,
    trend_n: int,
):
    total_hands = 0
    cnt_B = 0
    cnt_P = 0
    cnt_T = 0

    min_hands = 10**9
    max_hands = 0
    sum_hands = 0

    # store per-checkpoint (pB, pP, pT)
    hist: Deque[Tuple[float, float, float]] = deque(maxlen=trend_n + 1)

    for shoe_id in range(1, total_shoes + 1):
        hand_count = 0

        for e in deal_hand_stream(shoe_id=shoe_id, seed=shoe_id):
            if e.get("is_shoe_end"):
                break

            total_hands += 1
            hand_count += 1

            r = e["result"]
            if r == "B":
                cnt_B += 1
            elif r == "P":
                cnt_P += 1
            else:
                cnt_T += 1

        if hand_count < min_hands:
            min_hands = hand_count
        if hand_count > max_hands:
            max_hands = hand_count
        sum_hands += hand_count

        if shoe_id % checkpoint == 0:
            print_checkpoint(
                shoe_id=shoe_id,
                total_hands=total_hands,
                cnt_B=cnt_B,
                cnt_P=cnt_P,
                cnt_T=cnt_T,
                min_hands=min_hands,
                max_hands=max_hands,
                sum_hands=sum_hands,
                hist=hist,
                trend_n=trend_n,
                final=False,
            )

    print("\n=== FINAL SUMMARY ===")
    print_checkpoint(
        shoe_id=shoe_id,
        total_hands=total_hands,
        cnt_B=cnt_B,
        cnt_P=cnt_P,
        cnt_T=cnt_T,
        min_hands=min_hands,
        max_hands=max_hands,
        sum_hands=sum_hands,
        hist=hist,
        trend_n=trend_n,
        final=True,
    )


def print_checkpoint(
    *,
    shoe_id: int,
    total_hands: int,
    cnt_B: int,
    cnt_P: int,
    cnt_T: int,
    min_hands: int,
    max_hands: int,
    sum_hands: int,
    hist: Deque[Tuple[float, float, float]],
    trend_n: int,
    final: bool,
):
    pB = cnt_B / total_hands
    pP = cnt_P / total_hands
    pT = cnt_T / total_hands

    avg_hands = sum_hands / shoe_id
    tag = "FINAL" if final else f"@ shoe {shoe_id:,}"

    # record to history per checkpoint
    hist.append((pB, pP, pT))

    # deviation vs engine baseline (your THEORY)
    dB = pB - THEORY["B"]
    dP = pP - THEORY["P"]
    dT = pT - THEORY["T"]

    # trend over last N checkpoints: current - N checkpoints ago
    trendB = trendP = trendT = None
    if len(hist) >= trend_n + 1:
        oldB, oldP, oldT = hist[0]
        trendB = pB - oldB
        trendP = pP - oldP
        trendT = pT - oldT

    # 3-sigma scale (using THEORY probabilities as noise scale)
    def three_sigma(p: float) -> float:
        return 3.0 * sqrt(p * (1.0 - p) / total_hands)

    sB = three_sigma(THEORY["B"])
    sP = three_sigma(THEORY["P"])
    sT = three_sigma(THEORY["T"])

    print(f"\n[{tag}]")
    print(f"Total shoes: {shoe_id:,}")
    print(f"Total hands: {total_hands:,}")
    print(f"B/P/T: {pB:.6f} / {pP:.6f} / {pT:.6f}")
    print(f"Hands/shoe avg/min/max: {avg_hands:.2f} / {min_hands} / {max_hands}")

    print("Deviation vs ENGINE BASELINE (THEORY):")
    print(f"  B: {dB:+.6e}  (3σ≈{sB:.6e})")
    print(f"  P: {dP:+.6e}  (3σ≈{sP:.6e})")
    print(f"  T: {dT:+.6e}  (3σ≈{sT:.6e})")

    if trendB is None:
        print(f"Trend over last N checkpoints: N={trend_n} (warming up: need {trend_n+1} checkpoints)")
    else:
        print(f"Trend over last N checkpoints: N={trend_n}")
        print(f"  B: {trendB:+.6e}  P: {trendP:+.6e}  T: {trendT:+.6e}")


def main():
    parser = argparse.ArgumentParser(description="BPT sanity check (pure verification, no modeling)")
    parser.add_argument("--shoes", type=int, default=1_000_000, help="number of shoes")
    parser.add_argument("--checkpoint", type=int, default=100_000, help="checkpoint interval (shoes)")
    parser.add_argument("--trend_n", type=int, default=TREND_N_DEFAULT, help="trend window in number of checkpoints")
    args = parser.parse_args()

    run_sanity_check(
        total_shoes=args.shoes,
        checkpoint=args.checkpoint,
        trend_n=args.trend_n,
    )


if __name__ == "__main__":
    main()