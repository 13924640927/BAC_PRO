# -*- coding: utf-8 -*-
"""
查询加速的版本

STEP4 = STEP3 + PREMAX (严格复用 core/snapshot_engine.py 口径)
- UI 不改（SBI 在右侧；PREMAX & BET 在 BIG ROAD 下方）
- APP 端：每发一手牌都用 (SIDE, STREAK_LEN, SNAPSHOT) 形成 state_key
- 历史 snapshot 的统计与采样口径一致：只统计真实出现的 streak 长度，不扫描补全
"""

import os
import sys
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Iterator, List, Optional, Tuple
import secrets

from PIL import Image, ImageTk

# ---- path bootstrap: allow "from core.xxx import ..." ----
APP_DIR = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(APP_DIR, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.deal_adapter import deal_hand_stream  # ✅ only source of truth (do not modify dealing rules)

# ✅ PREMAX core (固定位置：core/snapshot_engine.py)
from core.snapshot_engine import SnapshotConfig, HistoryState, build_state_key

# =========================
# STEP6 ADD: DB adapter layer (PREMAX EV query + bet logging)
# =========================
try:
    # New EV-SIG (fast)
    from core.db_adapter import query_premax_ev_sig as query_premax_ev
    from core.db_adapter import insert_bet_log  # STEP6 ADD
except Exception:
    try:
        # Old EV (legacy)
        from core.db_adapter import query_premax_ev, insert_bet_log  # STEP6 ADD
    except Exception:
        query_premax_ev = None  # type: ignore
        insert_bet_log = None  # type: ignore


# =========================
# PREMAX snapshot helpers (do NOT modify core/snapshot_engine.py)
# =========================
def _ge_to_exact_hist(ge: Dict[str, int], hist_min: int, hist_max: int) -> Dict[str, int]:
    """Keep GE(>=k) buckets as-is (APP/样品口径要求：统计为 >=k 的次数).
    We only normalize keys/values and apply HIST_MIN/HIST_MAX filtering.
    Any k < hist_min is dropped; any k > hist_max is ignored (core通常不会产生).
    """
    out: Dict[str, int] = {}
    for k, v in (ge or {}).items():
        try:
            kk = int(k)
            vv = int(v)
        except Exception:
            continue
        if kk < hist_min:
            continue
        if kk > hist_max:
            continue
        out[str(kk)] = vv
    return out


def _ge_to_real_end_lengths(ge: Dict[str, int], hist_min: int, hist_max: int) -> Dict[str, int]:
    """From GE(>=k) buckets, keep only lengths that actually occurred as streak end lengths.
    A length k is considered 'occurred' if ge[k] > ge[k+1] (or ge[k] > 0 when k+1 missing).
    Values are kept as ge[k] (GE-count at that threshold), per your required HB/HP value meaning.
    Also applies HIST_MIN/HIST_MAX filtering, and caps any length > hist_max into hist_max.
    """
    if not ge:
        return {}
    # normalize and cap keys
    tmp: Dict[int, int] = {}
    for k, v in ge.items():
        try:
            kk = int(k)
            vv = int(v)
        except Exception:
            continue
        if kk < hist_min:
            continue
        if kk > hist_max:
            kk = hist_max
        tmp[kk] = max(tmp.get(kk, 0), vv)
    if not tmp:
        return {}
    out: Dict[str, int] = {}
    ks = sorted(tmp.keys())
    for k in ks:
        v = tmp.get(k, 0)
        next_v = tmp.get(k + 1, 0)
        if v > next_v:
            out[str(k)] = v
    return out

# =========================
# Baccarat helpers
# =========================
def baccarat_point(card: str) -> int:
    """
    Returns baccarat point for a single card:
      A=1, 2-9=face value, 10/J/Q/K=0
    """
    if not card:
        return 0
    s = str(card).strip()
    if " of " in s:
        rank = s.split(" of ", 1)[0].strip()
    else:
        rank = s[:-1] if len(s) >= 2 else s

    r = rank.upper()
    if r in ("A", "ACE"):
        return 1
    if r in ("K", "KING", "Q", "QUEEN", "J", "JACK", "10"):
        return 0
    try:
        v = int(r)
        if v >= 10:
            return 0
        return v
    except Exception:
        return 0


def baccarat_value(cards: List[str]) -> int:
    total = 0
    for c in cards or []:
        total += baccarat_point(c)
    return total % 10


def _safe_float(v, default=0.0):
    try:
        x = float(v)
        if x != x or x in (float("inf"), float("-inf")):
            return default
        return x
    except Exception:
        return default


def _fmt_money(x: float) -> str:
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "$0.00"


# =========================
# Assets
# =========================
def detect_img_dir() -> str:
    cands = [
        os.path.join(APP_DIR, "PIC", "CARDS_PNG"),
        os.path.join(ROOT, "app", "PIC", "CARDS_PNG"),
        os.path.join(ROOT, "PIC", "CARDS_PNG"),
    ]
    for p in cands:
        if os.path.isdir(p):
            return p
    return ""


IMG_DIR = detect_img_dir()
RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS

RANK_MAP = {
    "Ace": "A", "King": "K", "Queen": "Q", "Jack": "J",
    "10": "10", "9": "9", "8": "8", "7": "7", "6": "6", "5": "5", "4": "4", "3": "3", "2": "2",
    "A": "A", "K": "K", "Q": "Q", "J": "J",
}
SUIT_MAP = {
    "Hearts": "H", "Diamonds": "D", "Clubs": "C", "Spades": "S",
    "Heart": "H", "Diamond": "D", "Club": "C", "Spade": "S"
}


def card_to_png_filename(card: str) -> Optional[str]:
    if not card:
        return None
    s = str(card).strip()
    raw = s.replace(".png", "").replace(".PNG", "")

    if len(raw) in (2, 3) and raw[-1].upper() in ("H", "D", "C", "S"):
        return f"{raw[:-1]}{raw[-1].upper()}.png"

    if " of " in s:
        rank, _, suit = s.partition(" of ")
        rank = rank.strip()
        suit = suit.strip()
        r = RANK_MAP.get(rank)
        su = SUIT_MAP.get(suit)
        if r and su:
            return f"{r}{su}.png"
    return None


# =========================
# UI: Card Board (STEP2 locked layout)
# =========================
class CardBoard(tk.Canvas):
    def __init__(self, master):
        self.board_h = 240  # UI: reduce green card area height (~3 text lines)
        super().__init__(master, width=920, height=self.board_h, bg="#2E7D32", highlightthickness=0)
        self.card_w, self.card_h = 92, 132
        self.refs: List[ImageTk.PhotoImage] = []
        self.cache: Dict[Tuple[str, bool], ImageTk.PhotoImage] = {}
        self.draw_bg()

    def draw_bg(self):
        self.delete("all")
        self.create_text(240, 28, text="BANKER", fill="white", font=("Helvetica", 20, "bold"))
        self.create_text(680, 28, text="PLAYER", fill="white", font=("Helvetica", 20, "bold"))
        self.result_text_id = self.create_text(460, 28, text="", fill="#FFFFFF", font=("Helvetica", 20, "bold"))

    def set_result_text(self, r: str):
        if r == "B":
            self.itemconfig(self.result_text_id, text="BANKER WINS", fill="#FFEBEE")
        elif r == "P":
            self.itemconfig(self.result_text_id, text="PLAYER WINS", fill="#E3F2FD")
        elif r == "T":
            self.itemconfig(self.result_text_id, text="TIE", fill="#2E7D32")
        else:
            self.itemconfig(self.result_text_id, text="", fill="#FFFFFF")

    def _load_photo(self, card: str, rotate: bool) -> Optional[ImageTk.PhotoImage]:
        key = (card, rotate)
        if key in self.cache:
            return self.cache[key]

        fn = card_to_png_filename(card)
        if not fn or not IMG_DIR:
            return None
        path = os.path.join(IMG_DIR, fn)
        if not os.path.exists(path):
            return None

        img = Image.open(path).resize((self.card_w, self.card_h), RESAMPLE)
        if rotate:
            img = img.transpose(Image.ROTATE_90)
        ph = ImageTk.PhotoImage(img)
        self.cache[key] = ph
        return ph

    def _draw_card_or_fallback(self, x: int, y: int, card: str, rotate: bool):
        ph = self._load_photo(card, rotate)
        if ph is not None:
            self.refs.append(ph)
            self.create_image(x, y, anchor="nw", image=ph)
        else:
            self.create_rectangle(x, y, x + self.card_w, y + self.card_h, outline="#FFFFFF", width=2)
            self.create_text(
                x + self.card_w // 2, y + self.card_h // 2,
                text=str(card), fill="#FFFFFF", font=("Helvetica", 10), width=self.card_w - 10
            )

    def show(
        self,
        banker: List[str],
        player: List[str],
        *,
        banker_value: Optional[int] = None,
        player_value: Optional[int] = None,
        result: str = ""
    ):
        self.refs.clear()
        self.draw_bg()
        self.set_result_text(result)

        # keep 6 cards centered vertically in the green area
        y_main = max(40, int((self.board_h - self.card_h)/2))
        y_third = y_main + 18
        banker_pos = [(150, y_main), (270, y_main), (20, y_third)]
        player_pos = [(560, y_main), (680, y_main), (770, y_third)]

        for i, card in enumerate((banker or [])[:3]):
            x, y = banker_pos[i]
            self._draw_card_or_fallback(x, y, card, rotate=(i == 2))

        for i, card in enumerate((player or [])[:3]):
            x, y = player_pos[i]
            self._draw_card_or_fallback(x, y, card, rotate=(i == 2))
        # UI: place BANKER/PLAYER value text under the INITIAL 2 vertical cards of each side (no overlap, keep fix6 layout)
        # Keep green area size unchanged; cards remain centered. Only move the value labels.
        label_y = y_main + self.card_h + 10  # below the two vertical cards
        # centers between the first two vertical cards (B: idx 0/1, P: idx 0/1)
        b_center = int(((banker_pos[0][0] + self.card_w / 2) + (banker_pos[1][0] + self.card_w / 2)) / 2)
        p_center = int(((player_pos[0][0] + self.card_w / 2) + (player_pos[1][0] + self.card_w / 2)) / 2)

        if banker_value is not None:
            self.create_text(
                b_center,
                label_y,
                text=f"BANKER={banker_value}",
                fill="#B71C1C",  # red
                font=("Helvetica", 14, "bold"),
                anchor="n",
            )

        if player_value is not None:
            self.create_text(
                p_center,
                label_y,
                text=f"PLAYER={player_value}",
                fill="#0D47A1",  # blue
                font=("Helvetica", 14, "bold"),
                anchor="n",
            )



# =========================
# STEP2: 6-row STREAK board (locked)
# =========================
class StreakBoard(tk.Canvas):
    def __init__(self, master, width=980, height=165, cell=20):
        super().__init__(
            master,
            width=width,
            height=height,
            bg="#F5F5F5",
            highlightthickness=1,
            highlightbackground="#DDDDDD",
        )
        self.width = width
        self.height = height
        self.rows = 6
        self.cell = int(cell)
        self.pad_x = 10
        self.pad_y = 30
        self.dot_r = max(6, self.cell // 2 - 2)
        self.visible_cols = max(8, (self.width - self.pad_x * 2) // self.cell)

        self.grid: Dict[Tuple[int, int], Dict[str, int]] = {}

        self.last_bp_side: Optional[str] = None
        self.cur_col = 0
        self.cur_row = 0
        self.base_col = 0
        self.last_cell: Optional[Tuple[int, int]] = None

        # per-shoe result counters (reset on new_shoe)
        self.count_B = 0
        self.count_P = 0
        self.count_T = 0

        self._draw_header()

    def _draw_header(self):
        self.delete("all")
        # Title
        self.create_text(10, 10, anchor="nw", text="BIG ROAD", fill="#333333", font=("Helvetica", 12, "bold"))

        # Counters (B / P / T) shown on the header row
        y = 16
        r = min(8, self.dot_r)
        font_dot = ("Helvetica", 10, "bold")
        font_cnt = ("Helvetica", 12, "bold")

        def draw_counter(xc: int, color: str, letter: str, count: int):
            self.create_oval(xc - r, y - r, xc + r, y + r, fill=color, outline="#333333", width=1)
            self.create_text(xc, y, text=letter, fill="white", font=font_dot)
            self.create_text(xc + r + 8, 10, anchor="nw", text=str(int(count)), fill="#333333", font=font_cnt)

        # spacing: dot + count, then ~2 "spaces" gap
        x0 = 140
        step = 120
        draw_counter(x0 + 0 * step, "#D32F2F", "B", getattr(self, "count_B", 0))
        draw_counter(x0 + 1 * step, "#1976D2", "P", getattr(self, "count_P", 0))
        draw_counter(x0 + 2 * step, "#2E7D32", "T", getattr(self, "count_T", 0))

    def reset(self):
        self.grid.clear()
        self.last_bp_side = None
        self.cur_col = 0
        self.cur_row = 0
        self.base_col = 0
        self.last_cell = None
        self.count_B = 0
        self.count_P = 0
        self.count_T = 0
        self._draw_header()

    def _is_occupied(self, col: int, row: int) -> bool:
        return (col, row) in self.grid

    def _place_cell(self, col: int, row: int, side: str):
        self.grid[(col, row)] = {"side": side, "tie": 0}
        self.last_cell = (col, row)
        self.cur_col = col
        self.cur_row = row

    def _overlay_tie(self):
        if self.last_cell and self.last_cell in self.grid:
            self.grid[self.last_cell]["tie"] += 1

    def push_result(self, result: str):
        # Update per-shoe counters
        if result == "T":
            self.count_T = int(getattr(self, "count_T", 0)) + 1
            self._overlay_tie()
            self.redraw()
            return

        if result == "B":
            self.count_B = int(getattr(self, "count_B", 0)) + 1
        elif result == "P":
            self.count_P = int(getattr(self, "count_P", 0)) + 1
        else:
            return

        if self.last_bp_side is None:
            self.last_bp_side = result
            self.base_col = 0
            r = 0
            while r < self.rows and self._is_occupied(0, r):
                r += 1
            if r >= self.rows:
                self.base_col = 1
                r = 0
            self._place_cell(self.base_col, r, result)
            self.redraw()
            return

        if result == self.last_bp_side:
            down_r = self.cur_row + 1
            if down_r < self.rows and not self._is_occupied(self.cur_col, down_r):
                self._place_cell(self.cur_col, down_r, result)
            else:
                c = self.cur_col + 1
                while self._is_occupied(c, self.cur_row):
                    c += 1
                self._place_cell(c, self.cur_row, result)
            self.redraw()
            return

        self.last_bp_side = result
        start_c = self.base_col + 1
        c = start_c
        while True:
            r = 0
            while r < self.rows and self._is_occupied(c, r):
                r += 1
            if r < self.rows:
                break
            c += 1
        self.base_col = c
        self._place_cell(c, r, result)
        self.redraw()

    def redraw(self):
        self._draw_header()
        if not self.grid:
            return

        max_col = max(c for (c, _r) in self.grid.keys())
        start_col = max(0, max_col - self.visible_cols + 1)

        gx0, gy0 = self.pad_x, self.pad_y
        gx1 = self.pad_x + self.visible_cols * self.cell
        gy1 = self.pad_y + self.rows * self.cell

        for r in range(self.rows + 1):
            y = gy0 + r * self.cell
            self.create_line(gx0, y, gx1, y, fill="#E6E6E6")
        for c in range(self.visible_cols + 1):
            x = gx0 + c * self.cell
            self.create_line(x, gy0, x, gy1, fill="#E6E6E6")

        for (col, row), info in sorted(self.grid.items(), key=lambda x: (x[0][0], x[0][1])):
            if col < start_col:
                continue
            vis_c = col - start_col
            if vis_c >= self.visible_cols:
                continue

            cx = gx0 + vis_c * self.cell + self.cell // 2
            cy = gy0 + row * self.cell + self.cell // 2

            side = info["side"]
            tie = int(info["tie"])

            fill = "#D32F2F" if side == "B" else "#1976D2"
            outline = "#333333"

            self.create_oval(
                cx - self.dot_r, cy - self.dot_r,
                cx + self.dot_r, cy + self.dot_r,
                fill=fill, outline=outline, width=1
            )
            if tie > 0:
                self.create_text(
                    cx, cy, text="T", fill="#2E7D32",
                    font=("Helvetica", max(10, self.cell // 2), "bold")
                )


# =========================
# STEP3: SBI model (rank 1..9 only, ignore 0)
# =========================
try:
    from SBI_FULL_MODEL import FullSBIModel  # type: ignore
except Exception:
    class FullSBIModel:  # type: ignore
        def __init__(self, total_decks: int = 8):
            self.total_decks = total_decks
            base = total_decks * 4
            self.rank_counts = {r: base for r in range(1, 10)}
            self.accum_rank_usage = {r: 0 for r in range(1, 10)}
            self.cards_dealt = 0

        def on_card_dealt(self, rank: int) -> None:
            if 1 <= rank <= 9:
                self.rank_counts[rank] = max(0, self.rank_counts.get(rank, 0) - 1)
                self.accum_rank_usage[rank] = self.accum_rank_usage.get(rank, 0) + 1
                self.cards_dealt += 1

        def bias_label(self) -> str:
            return "Neutral"

        def ev_p(self) -> float:
            return 0.0

        def ev_b_comm(self) -> float:
            return 0.0


# =========================
# Shoe session (deal adapter stream)
# =========================
class ShoeSession:
    def __init__(self, cut_cards: int = 14, decks: int = 8):
        self.cut_cards = cut_cards
        self.decks = decks
        self.shoe_id = 0
        self.seed: Optional[int] = None
        self.it: Optional[Iterator[Dict[str, Any]]] = None
        self.last_hand_id: int = 0

    def new_shoe(self):
        self.shoe_id += 1
        self.last_hand_id = 0
        self.seed = secrets.randbits(64)
        self.it = iter(
            deal_hand_stream(
                shoe_id=self.shoe_id,
                seed=self.seed,
                decks=self.decks,
                cut_cards=self.cut_cards,
                audit=True,
            )
        )


# =========================
# APP (STEP4)
# =========================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BACARRAT PRO — THE EDGE ENGINE")  # STEP6 CHANGE
        self.geometry("1240x940")
        self.minsize(1200, 900)

        # ===== main layout =====
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=8)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        right = ttk.Frame(main, width=260)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        # --- left: CardBoard + StreakBoard ---
        self.board = CardBoard(left)
        self.board.pack(pady=(0, 8))

        self.streak_board = StreakBoard(left, width=980, cell=20)
        self.streak_board.pack(pady=(0, 6))

        # --- left: PREMAX panel (under BIG ROAD) ---
        self.premax_box = ttk.LabelFrame(left, text="PREMAX SETTING")
        self.premax_box.pack(fill="x", pady=(0, 8))

        # controls row
        row1 = ttk.Frame(self.premax_box)
        row1.pack(fill="x", padx=10, pady=(8, 6))

        ttk.Label(row1, text="HIST MIN").grid(row=0, column=0, sticky="w")
        self.hist_min_var = tk.StringVar(value="3")
        ttk.Entry(row1, textvariable=self.hist_min_var, width=8).grid(row=0, column=1, padx=(6, 18))

        ttk.Label(row1, text="HIST MAX").grid(row=0, column=2, sticky="w")
        self.hist_max_var = tk.StringVar(value="15")
        ttk.Entry(row1, textvariable=self.hist_max_var, width=8).grid(row=0, column=3, padx=(6, 18))

        ttk.Label(row1, text="STREAK MIN").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.cur_min_var = tk.StringVar(value="3")
        ttk.Entry(row1, textvariable=self.cur_min_var, width=8).grid(row=1, column=1, padx=(6, 18), pady=(6, 0))

        ttk.Label(row1, text="STREAK MAX").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.cur_max_var = tk.StringVar(value="99")
        ttk.Entry(row1, textvariable=self.cur_max_var, width=8).grid(row=1, column=3, padx=(6, 18), pady=(6, 0))

        self.btn_apply = ttk.Button(row1, text="Apply", command=self._premax_apply)
        self.btn_apply.grid(row=0, column=4, rowspan=2, padx=(20, 8), ipadx=18)

        # EV output (move to Apply right side)
        self.ev_out = ttk.Label(row1, text="PREMAX(EDGE) ", anchor="w")
        self.ev_out.grid(row=0, column=5, rowspan=2, sticky="w", padx=(10, 0))

        # --- left: BET & STRATEGY (STEP5) ---
        self.bet_box = ttk.LabelFrame(left, text="BET & STRATEGY")
        self.bet_box.pack(fill="both", expand=True)
        self._bet_init_ui()

        # --- right: STATUS ---
        status_box = ttk.LabelFrame(right, text="STATUS")
        status_box.pack(fill="x", pady=(0, 10))
        self.status = ttk.Label(status_box, text="", anchor="w", justify="left", wraplength=260, font=("Helvetica", 10))
        self.status.pack(fill="x", padx=8, pady=8)

        # --- right: CONTROL ---
        ctrl_box = ttk.LabelFrame(right, text="CONTROL")
        ctrl_box.pack(fill="x", pady=(0, 10))
        ttk.Button(ctrl_box, text="Deal One", command=self.deal_one).pack(fill="x", padx=8, pady=(8, 6))
        ttk.Button(ctrl_box, text="New Shoe", command=self.new_shoe).pack(fill="x", padx=8, pady=(0, 8))

        # --- right: SBI (STEP3) ---
        self.sbi_box = ttk.LabelFrame(right, text="SBI")
        self.sbi_box.pack(fill="both", expand=True, pady=(0, 10))

        hdr = ttk.Frame(self.sbi_box)
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(hdr, text="Rank", width=6).grid(row=0, column=0, sticky="w")
        ttk.Label(hdr, text="Dealt", width=7).grid(row=0, column=1, sticky="w")
        ttk.Label(hdr, text="Remain", width=7).grid(row=0, column=2, sticky="w")

        self._lbl_dealt: Dict[int, ttk.Label] = {}
        self._lbl_remain: Dict[int, ttk.Label] = {}
        grid = ttk.Frame(self.sbi_box)
        grid.pack(fill="x", padx=8)

        for r in range(1, 10):
            ttk.Label(grid, text=str(r), width=6).grid(row=r, column=0, sticky="w", pady=1)
            ld = ttk.Label(grid, text="0", width=7)
            lr = ttk.Label(grid, text="0", width=7)
            ld.grid(row=r, column=1, sticky="w")
            lr.grid(row=r, column=2, sticky="w")
            self._lbl_dealt[r] = ld
            self._lbl_remain[r] = lr

        sep = ttk.Separator(self.sbi_box, orient="horizontal")
        sep.pack(fill="x", padx=8, pady=8)

        self.lbl_bias = ttk.Label(self.sbi_box, text="Bias: -", font=("Helvetica", 12, "bold"))
        self.lbl_bias.pack(anchor="w", padx=8, pady=(0, 4))

        self.lbl_ev = ttk.Label(self.sbi_box, text="SBI_SBI_EV_P: -   SBI_SBI_EV_B: -", font=("Helvetica", 10))
        self.lbl_ev.pack(anchor="w", padx=8, pady=(0, 8))

        # ===== session & SBI model =====
        self.session = ShoeSession(cut_cards=14, decks=8)
        self.session.new_shoe()
        self.sbi_model = FullSBIModel(total_decks=8)

        # ===== PREMAX runtime state =====
        self.premax_cfg = SnapshotConfig(cur_min=3, cur_max=99, hist_min=3, hist_max=15, debug=False)
        self.hist_state = HistoryState()  # ✅ 不带 cfg（严格按 core 口径）
        self.cur_streak_side: Optional[str] = None
        self.cur_streak_len: int = 0

        # STEP6 ADD: last PREMAX EV row from DB (used for UI display and bet logging)
        self.last_premax_ev_row: Optional[Dict[str, Any]] = None
        self.last_premax_query_args: Optional[Tuple[str, int, Dict[str, int], Dict[str, int]]] = None
        self.bet_ev_row: Optional[Dict[str, Any]] = None  # captured at Confirm Bet time

        # ===== fixed LOGO bottom-right =====
        self._logo_ref: Optional[ImageTk.PhotoImage] = None
        logo_path = os.path.join(APP_DIR, "PIC", "ME.PNG")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).convert("RGBA")
                img = img.resize((188, 188), RESAMPLE)
                self._logo_ref = ImageTk.PhotoImage(img)
                self.logo_label = tk.Label(self, image=self._logo_ref, borderwidth=0, highlightthickness=0)
                self.logo_label.place(relx=1.0, rely=1.0, anchor="se", x=-45, y=-22)
            except Exception:
                pass

        self._update_status(msg="ready")
        self._refresh_sbi_panel()

    def _update_status(self, msg: str = ""):
        full = f"shoe={self.session.shoe_id} hand={self.session.last_hand_id}  {msg}".strip()
        try:
            self.status.config(text=full)
        except Exception:
            pass
        # Also print + append to a local log so errors never get “lost”
        try:
            print(full)
        except Exception:
            pass
        try:
            with open("premax_step6_status.log", "a", encoding="utf-8") as f:
                f.write(full + "\n")
        except Exception:
            pass


    # STEP6 DEBUG: print detailed traces without overwriting status label
    def _debug_log(self, msg: str = ""):
        line = msg
        try:
            print(line)
        except Exception:
            pass
        try:
            with open("premax_step6_debug.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    # === STEP3: update SBI display (1..9) ===
    def _refresh_sbi_panel(self):
        for r in range(1, 10):
            dealt = int(getattr(self.sbi_model, "accum_rank_usage", {}).get(r, 0))
            remain = int(getattr(self.sbi_model, "rank_counts", {}).get(r, 0))
            self._lbl_dealt[r].config(text=str(dealt))
            self._lbl_remain[r].config(text=str(remain))

        try:
            bias = self.sbi_model.bias_label()
            evp = self.sbi_model.ev_p()
            evb = self.sbi_model.ev_b_comm()
            self.lbl_bias.config(text=f"Bias: {bias}")
            self.lbl_ev.config(text=f"SBI_EV_P: {evp:+.6f}   SBI_EV_B: {evb:+.6f}")
        except Exception:
            self.lbl_bias.config(text="Bias: -")
            self.lbl_ev.config(text="SBI_SBI_EV_P: -   SBI_SBI_EV_B: -")

    # =========================
    # PREMAX
    # =========================
    def _premax_apply(self):
        # SnapshotConfig 是 frozen dataclass → 必须重建
        try:
            hist_min = int(self.hist_min_var.get())
            hist_max = int(self.hist_max_var.get())
            cur_min = int(self.cur_min_var.get())
            cur_max = int(self.cur_max_var.get())
        except Exception:
            return

        if hist_min < 1:
            hist_min = 1
        if hist_max < hist_min:
            hist_max = hist_min
        if cur_min < 1:
            cur_min = 1
        if cur_max < cur_min:
            cur_max = cur_min

        self.premax_cfg = SnapshotConfig(
            cur_min=cur_min,
            cur_max=cur_max,
            hist_min=hist_min,
            hist_max=hist_max,
            debug=False,
        )

        # UI 不显示 debug 信息（只保留 EV 文本）
        self.ev_out.config(text="PREMAX(EDGE) -")  # STEP6 CHANGE



    def _premax_reset_ev_display(self):
        """Reset PREMAX EV hint bar to its initial state.

        Prevents stale EV from being displayed when the current hand no longer
        satisfies the snapshot trigger conditions.
        """
        try:
            self.ev_out.config(text="PREMAX(EDGE) -")
        except Exception:
            # UI may not be ready during early init
            pass


    def _premax_on_bp_result(self, side: str):
        # If this hand is not a B/P outcome (e.g. tie), PREMAX snapshot should not be active.
        if side not in ("B", "P"):
            self._premax_reset_ev_display()
            return
        """
        APP 端每手牌都执行一次：
        - 仅 B/P 影响 streak
        - 掉头时把上一条 streak 写入 HistoryState（采样口径）
        - 然后用当前 (side, cur_len, hist_snapshot) 形成 state_key
        - 只有当 cur_len 落在 cfg.cur_min..cfg.cur_max 才触发（打印 / 未来查库）
        """
        if side not in ("B", "P"):
            return

        # init
        if self.cur_streak_side is None:
            self.cur_streak_side = side
            self.cur_streak_len = 1
        else:
            if side == self.cur_streak_side:
                self.cur_streak_len += 1
            else:
                # side flip → push previous streak into history (采样口径一致)
                try:
                    self.hist_state.apply_streak_to_history(self.cur_streak_side, int(self.cur_streak_len), self.premax_cfg)
                except Exception:
                    print(f"[PREMAX] WARN: history push failed (side={self.cur_streak_side}, len={self.cur_streak_len})")

                # start new streak
                self.cur_streak_side = side
                self.cur_streak_len = 1

        # build state for APP: each new hand once streak_len reaches CUR_MIN; lengths >= CUR_MAX are merged into CUR_MAX
        if self.cur_streak_len < self.premax_cfg.cur_min:
            self._premax_reset_ev_display()
            return

        eff_cur_len = self.premax_cfg.cur_max if self.cur_streak_len >= self.premax_cfg.cur_max else self.cur_streak_len

        try:
            ge_B, ge_P = self.hist_state.clone_key_material()
            # IMPORTANT: core stores GE(>=k). For APP/DB params we keep only REAL occurred end-length keys (样品口径：只保留实际出现过的长度)
            hist_B = _ge_to_real_end_lengths(ge_B, self.premax_cfg.hist_min, self.premax_cfg.hist_max)
            hist_P = _ge_to_real_end_lengths(ge_P, self.premax_cfg.hist_min, self.premax_cfg.hist_max)

            # Gate: when HIST_MIN is set high (e.g. 6~15), the history snapshot (HB/HP)
            # stays empty early in the shoe. In that case we should NOT trigger a PREMAX
            # lookup using HB={}, HP={}, because it violates the user's "photo conditions".
            # Only start querying once at least one history bucket exists within [hist_min, hist_max].
            if (self.premax_cfg.hist_min is not None and int(self.premax_cfg.hist_min) > 1) and (not hist_B) and (not hist_P):
                self._premax_reset_ev_display()
                return

            key = build_state_key(
                cur_side=self.cur_streak_side,
                cur_len=int(eff_cur_len),
                hist_B=hist_B,
                hist_P=hist_P,
            )
            print(f"[PREMAX] STATE_KEY = {key}")

            # STEP6 CHANGE: query PREMAX EV from DB and surface DB errors
            ev_row = None
            if query_premax_ev is not None:
                try:
                    # STEP6 DEBUG: log exact lookup keys (raw)
                    try:
                        self._debug_log(
                            "PREMAX_EV_QUERY raw: "
                            f"cur_side={self.cur_streak_side!r} "
                            f"cur_len={int(eff_cur_len)!r} "
                            f"hist_b_json(len)={len(str(hist_B))} val={str(hist_B)[:200]!r} "
                            f"hist_p_json(len)={len(str(hist_P))} val={str(hist_P)[:200]!r}"
                        )
                    except Exception:
                        pass

                    ev_row, n_matches, db_err = query_premax_ev(
                        cur_side=self.cur_streak_side,
                        cur_len=int(eff_cur_len),
                        hist_b_json=hist_B,
                        hist_p_json=hist_P,
                    )

                    # STEP6 DEBUG: log DB return
                    try:
                        self._debug_log(f"PREMAX_EV_RESULT n_matches={n_matches} row={ev_row} err={db_err}")
                    except Exception:
                        pass



                    # STEP6 FINAL: duplicates / no-hit handling
                    if (not db_err) and (n_matches > 1):
                        try:
                            self._update_status(
                                f"PREMAX EV duplicate rows: {n_matches} (side={self.cur_streak_side} len={int(eff_cur_len)})"
                            )
                        except Exception:
                            pass

                    if db_err:
                        try:
                            self._update_status(db_err)
                        except Exception:
                            pass
                except Exception as e:
                    try:
                        self._update_status(f'DB EV query exception: {e}')
                    except Exception:
                        pass
                    ev_row = None

            self.last_premax_ev_row = ev_row
            self.last_premax_query_args = (self.cur_streak_side, int(eff_cur_len), hist_B, hist_P)

            if ev_row:
                try:
                    self.ev_out.config(
                        text=(
                            f"PREMAX(EDGE)  SIDE: {self.cur_streak_side}  EV_cut: {float(ev_row.get('ev_cut', 0.0)):+.6f}  "
                            f"EV_cont: {float(ev_row.get('ev_continue', 0.0)):+.6f}  "
                            f"best: {str(ev_row.get('best_action', '-'))}  "
                            f"edge: {float(ev_row.get('edge', 0.0)):+.6f}"
                        )
                    )
                except Exception:
                    self.ev_out.config(text="PREMAX(EDGE): (db row found)")
            else:
                self.ev_out.config(text="PREMAX(EDGE):  N/A")
        except Exception:
            # keep console clean; only valid STATE_KEY is printed
            return

    # =========================
    # Shoe control
    # =========================
    def new_shoe(self):
        self.session.new_shoe()
        self.board.show([], [], banker_value=None, player_value=None, result="")
        self.streak_board.reset()

        self.sbi_model = FullSBIModel(total_decks=8)

        # reset PREMAX runtime
        self.hist_state = HistoryState()
        self.cur_streak_side = None
        self.cur_streak_len = 0

        self.ev_out.config(text="PREMAX(EDGE) -")  # STEP6 CHANGE
        self.last_premax_ev_row = None  # STEP6 ADD
        self.last_premax_query_args = None  # STEP6 ADD
        self.bet_ev_row = None  # STEP6 ADD


        # STEP5 BET: reset per-shoe log & cumulative
        self.running_pnl = 0.0
        try:
            self._bet_clear_log()
        except Exception:
            pass
        try:
            self._bet_reset_inputs_only()
        except Exception:
            pass

        self._update_status("new_shoe")
        self._refresh_sbi_panel()

    def deal_one(self):
        if self.session.it is None:
            self._update_status("ERROR: iterator None")
            return

        steps = 0
        while True:
            steps += 1
            if steps > 5000:
                self._update_status("ERROR: no hand event found")
                return

            try:
                e = next(self.session.it)
            except StopIteration:
                self._update_status("STOPITER — click New Shoe")
                return

            if e.get("is_shoe_end"):
                self._update_status("SHOE END — click New Shoe")
                return

            if "hand_id" in e:
                break

        meta = e.get("meta") or {}
        player_cards = list(meta.get("player_cards") or [])
        banker_cards = list(meta.get("banker_cards") or [])

        self.session.last_hand_id = int(e.get("hand_id") or 0)
        r = e.get("result")  # "B"/"P"/"T"

        self.last_result = r  # STEP5: expose last result for betting

        cards_left = meta.get("cards_left")
        extra = f"cards_left={cards_left}" if cards_left is not None else ""
        self._update_status(extra)

        banker_value = meta.get("banker_value")
        player_value = meta.get("player_value")
        if banker_value is None:
            banker_value = baccarat_value(banker_cards)
        if player_value is None:
            player_value = baccarat_value(player_cards)

        # STEP3: update SBI model by all dealt cards in this hand (ignore 0)
        for c in (banker_cards + player_cards):
            pt = baccarat_point(c)
            if 1 <= pt <= 9:
                self.sbi_model.on_card_dealt(pt)
        self._refresh_sbi_panel()

        # STEP2: draw table
        self.board.show(
            banker_cards,
            player_cards,
            banker_value=int(banker_value),
            player_value=int(player_value),
            result=str(r or "")
        )

        # STEP2: update BIG ROAD
        if r in ("B", "P", "T"):
            self.streak_board.push_result(r)

        # STEP4 PREMAX: only B/P affect streak space; T ignored for state updates
        if r in ("B", "P"):
            self._premax_on_bp_result(r)


        # STEP5 BET: settle/log after each hand
        self._bet_after_hand()


# =========================
# STEP5: BET (manual) + per-shoe log
# =========================
def _bet_init_ui(self):
    # init state vars
    self.bet_confirmed = False
    self.bet_base = tk.StringVar(value="100")
    self.bet_side = tk.StringVar(value="")
    self.bet_mult = tk.StringVar(value="1")  # default = 1
    self.running_pnl = 0.0

    # clear placeholder / any existing children
    for w in list(self.bet_box.winfo_children()):
        try:
            w.destroy()
        except Exception:
            pass

    # input row (keep behavior)
    row = ttk.Frame(self.bet_box)
    row.pack(fill="x", padx=10, pady=(8, 8))

    ttk.Label(row, text="Base").pack(side="left")
    ttk.Entry(row, textvariable=self.bet_base, width=7).pack(side="left", padx=(6, 14))

    ttk.Label(row, text="Side").pack(side="left")
    ttk.Radiobutton(row, text="B", variable=self.bet_side, value="B").pack(side="left", padx=(6, 0))
    ttk.Radiobutton(row, text="P", variable=self.bet_side, value="P").pack(side="left", padx=(6, 14))

    ttk.Label(row, text="Mult").pack(side="left")
    ttk.Entry(row, textvariable=self.bet_mult, width=7).pack(side="left", padx=(6, 16))

    ttk.Button(row, text="Confirm Bet", command=self._bet_confirm).pack(side="left", padx=(0, 10))
    ttk.Button(row, text="Reset", command=self._bet_reset_manual).pack(side="left")

    # confirm indicator moved into the same row to save vertical space
    root_bg = self.cget("background")
    self.lbl_confirm = tk.Label(
        row, text="", fg="#1b5e20", bg=root_bg, font=("Helvetica", 10, "bold")
    )
    self.lbl_confirm.pack(side="left", padx=(14, 0))


    # output table
    out_wrap = ttk.Frame(self.bet_box)
    out_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 14))

    cols = ("hand", "bet_side", "win_side", "bet", "wl", "cum")
    self.bet_tv = ttk.Treeview(out_wrap, columns=cols, show="headings", height=5)

    headings = {
        "hand": "Hand#",
        "bet_side": "Bet Side",
        "win_side": "Win Side",
        "bet": "Bet Amount",
        "wl": "Win/Loss",
        "cum": "Cumulative",
    }
    for c in cols:
        self.bet_tv.heading(c, text=headings[c])

    self.bet_tv.column("hand", width=70, anchor="center")
    self.bet_tv.column("bet_side", width=80, anchor="center")
    self.bet_tv.column("win_side", width=80, anchor="center")
    self.bet_tv.column("bet", width=120, anchor="e")
    self.bet_tv.column("wl", width=120, anchor="e")
    self.bet_tv.column("cum", width=130, anchor="e")

    ys = ttk.Scrollbar(out_wrap, orient="vertical", command=self.bet_tv.yview)
    self.bet_tv.configure(yscrollcommand=ys.set)

    self.bet_tv.grid(row=0, column=0, sticky="nsew")
    ys.grid(row=0, column=1, sticky="ns")

    out_wrap.rowconfigure(0, weight=1)
    out_wrap.columnconfigure(0, weight=1)

def _bet_confirm(self):
    if self.bet_side.get() in ("B", "P") and _safe_float(self.bet_mult.get(), 0.0) > 0:
        self.bet_confirmed = True
        self.bet_ev_row = getattr(self, 'last_premax_ev_row', None)  # STEP6 ADD
        try:
            self.lbl_confirm.config(text="BET CONFIRMED - next hand only")
        except Exception:
            pass

def _bet_reset_inputs_only(self):
    self.bet_confirmed = False
    self.bet_ev_row = None  # STEP6 ADD
    self.bet_side.set("")
    self.bet_mult.set("1")
    try:
        self.lbl_confirm.config(text="")
    except Exception:
        pass

def _bet_reset_manual(self):
    # manual reset: inputs only (log clears on New Shoe)
    self._bet_reset_inputs_only()

def _bet_clear_log(self):
    try:
        for iid in self.bet_tv.get_children():
            self.bet_tv.delete(iid)
    except Exception:
        pass

def _bet_append_row(self, hand_no, bet_side, win_side, bet_amount, pnl, cum):
    try:
        self.bet_tv.insert(
            "",
            "end",
            values=(
                str(hand_no),
                bet_side or "-",
                win_side or "-",
                _fmt_money(bet_amount),
                _fmt_money(pnl),
                _fmt_money(cum),
            ),
        )
        self.bet_tv.see(self.bet_tv.get_children()[-1])
    except Exception:
        pass

def _bet_after_hand(self):
    # called after each deal_one
    hand_no = int(getattr(getattr(self, "session", None), "last_hand_id", 0) or 0)
    win_side = getattr(self, "last_result", None)

    bet_amount = 0.0
    pnl = 0.0
    bet_side = None

    auto_side = self.bet_side.get()
    auto_mult = _safe_float(self.bet_mult.get(), 0.0)
    auto_base = _safe_float(self.bet_base.get(), 0.0)
    auto_ready = (auto_side in ("B","P") and auto_mult > 0 and auto_base > 0)

    # STEP6 FIX: if user picked B/P and amount>0, treat as confirmed even if they forgot to click Confirm
    if (self.bet_confirmed or auto_ready) and win_side in ("B", "P", "T"):
        base = _safe_float(self.bet_base.get(), 100.0)
        mult = _safe_float(self.bet_mult.get(), 1.0)
        bet_amount = base * mult
        bet_side = self.bet_side.get()

        # STEP6 FIX: surface whether bet was auto-inferred (no Confirm click)
        if (not self.bet_confirmed) and auto_ready:
            try:
                self._update_status("BET AUTO-ARMED (no Confirm click) — logged for this hand")
            except Exception:
                pass

        if win_side == "T":
            pnl = 0.0
        elif win_side == bet_side:
            pnl = bet_amount * (0.95 if win_side == "B" else 1.0)
        else:
            pnl = -bet_amount

        self.running_pnl += pnl

        # STEP6 CHANGE: write bet log to DB and surface DB errors (no silent fail)
        if insert_bet_log is not None and bet_side in ('B', 'P'):
            shoe_id = str(getattr(getattr(self, 'session', None), 'shoe_id', ''))
            try:
                db_err = insert_bet_log(
                    shoe_id=shoe_id,
                    hand_id=hand_no,
                    bet_side=bet_side,
                    bet_amount=float(bet_amount),
                    ev_row=(self.bet_ev_row or {'ev_cut': None, 'ev_continue': None, 'best_action': None, 'edge': None}),
                    result=('T' if win_side == 'T' else ('WIN' if win_side == bet_side else 'LOSS')),
                    pnl=float(pnl),
                )
                if db_err:
                    try:
                        self._update_status(db_err)
                    except Exception:
                        pass
            except Exception as e:
                try:
                    self._update_status(f'DB bet_log exception: {e}')
                except Exception:
                    pass

    self._bet_append_row(hand_no, bet_side, win_side, bet_amount, pnl, self.running_pnl)

    # strict one-hand reset after this hand
    self._bet_reset_inputs_only()



# =========================
# STEP5: bind betting helpers as App methods (single-file wiring)
# =========================
App._bet_init_ui = _bet_init_ui
App._bet_confirm = _bet_confirm
App._bet_reset_inputs_only = _bet_reset_inputs_only
App._bet_reset_manual = _bet_reset_manual
App._bet_clear_log = _bet_clear_log
App._bet_append_row = _bet_append_row
App._bet_after_hand = _bet_after_hand

if __name__ == "__main__":
    App().mainloop()