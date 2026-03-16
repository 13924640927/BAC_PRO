# core/deal_monitor.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _sha256_of_cards(cards: List[str]) -> str:
    h = hashlib.sha256()
    for c in cards:
        h.update(c.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


@dataclass
class DealAuditConfig:
    # 是否输出/记录详细 trace（逐手/逐张）
    verbose: bool = True

    # 只采样前 N 手牌（避免输出过大）
    trace_first_n_hands: int = 5

    # 是否记录牌面（审计时很有用；长跑时应关闭）
    record_cards: bool = True

    # 断言：同一 shoe 不能 hand_id 重复/跳号
    assert_hand_sequence: bool = True

    # 断言：Tie 时 push 逻辑正确（B/P 主注为 0，tie_profit=8）
    assert_tie_push_logic: bool = True


@dataclass
class DealAuditState:
    shoe_id: Optional[int] = None
    seed: Optional[int] = None

    # 原牌/洗牌摘要（hash）
    unshuffled_hash: Optional[str] = None
    shuffled_hash: Optional[str] = None

    # 运行统计
    hands_dealt: int = 0
    cnt_B: int = 0
    cnt_P: int = 0
    cnt_T: int = 0

    # 鞋内手序检查
    last_hand_id: int = 0

    # trace 采样
    traces: List[Dict[str, Any]] = field(default_factory=list)

    def summarize(self) -> Dict[str, Any]:
        total = self.hands_dealt if self.hands_dealt else 1
        return {
            "shoe_id": self.shoe_id,
            "seed": self.seed,
            "unshuffled_hash": self.unshuffled_hash,
            "shuffled_hash": self.shuffled_hash,
            "hands_dealt": self.hands_dealt,
            "BPT": {
                "B": self.cnt_B,
                "P": self.cnt_P,
                "T": self.cnt_T,
                "B_ratio": self.cnt_B / total,
                "P_ratio": self.cnt_P / total,
                "T_ratio": self.cnt_T / total,
            },
            "trace_samples": self.traces,
        }


class DealMonitor:
    """
    监测器：接收 deal_adapter / dealer 发来的事件，做审计与断言。
    不改发牌，不参与逻辑。
    """

    def __init__(self, cfg: DealAuditConfig):
        self.cfg = cfg
        self.state = DealAuditState()

    # ---------- 生命周期事件 ----------
    def on_shoe_start(
        self,
        *,
        shoe_id: int,
        seed: Optional[int],
        unshuffled_cards: Optional[List[str]] = None,
        shuffled_cards: Optional[List[str]] = None,
    ):
        self.state = DealAuditState(shoe_id=shoe_id, seed=seed)

        if unshuffled_cards is not None:
            self.state.unshuffled_hash = _sha256_of_cards(unshuffled_cards)
            if self.cfg.verbose:
                print(f"[shoe_start] shoe_id={shoe_id} seed={seed} unshuffled_hash={self.state.unshuffled_hash}")

        if shuffled_cards is not None:
            self.state.shuffled_hash = _sha256_of_cards(shuffled_cards)
            if self.cfg.verbose:
                print(f"[shoe_start] shoe_id={shoe_id} seed={seed} shuffled_hash={self.state.shuffled_hash}")

    def on_hand(self, event: Dict[str, Any]):
        """
        event: 来自 deal_adapter 的 hand event（你定型的 hand-stream）
        """
        if self.cfg.assert_hand_sequence:
            hid = int(event["hand_id"])
            if hid != self.state.last_hand_id + 1:
                raise AssertionError(f"hand_id sequence broken: last={self.state.last_hand_id}, current={hid}")
            self.state.last_hand_id = hid

        r = event["result"]
        self.state.hands_dealt += 1
        if r == "B":
            self.state.cnt_B += 1
        elif r == "P":
            self.state.cnt_P += 1
        else:
            self.state.cnt_T += 1

        if self.cfg.assert_tie_push_logic and r == "T":
            if not (event["banker_profit"] == 0.0 and event["player_profit"] == 0.0 and event["tie_profit"] == 8.0):
                raise AssertionError(f"Tie push logic violated: {event}")

        # 采样 trace
        if self.cfg.verbose and self.state.hands_dealt <= self.cfg.trace_first_n_hands:
            # 仅记录小样本，避免爆输出
            sample = {k: event.get(k) for k in ["shoe_id", "hand_id", "result", "banker_profit", "player_profit", "tie_profit"]}
            # 可选：如果 adapter 给了 meta/cards，也可一并记
            if self.cfg.record_cards:
                meta = event.get("meta")
                if meta:
                    sample["meta"] = meta
            self.state.traces.append(sample)
            print(f"[hand] {sample}")

    def on_shoe_end(self, event: Dict[str, Any]):
        if self.cfg.verbose:
            print(f"[shoe_end] {event}")

    def report(self) -> Dict[str, Any]:
        return self.state.summarize()