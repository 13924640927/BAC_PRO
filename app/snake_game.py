from __future__ import annotations

import os
import random
import sys
import tkinter as tk
from tkinter import ttk
from typing import Optional

APP_DIR = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(APP_DIR, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.snake_logic import (  # noqa: E402
    DIR_DELTAS,
    DIR_DOWN,
    DIR_LEFT,
    DIR_RIGHT,
    DIR_UP,
    SnakeConfig,
    SnakeState,
    create_initial_state,
    step_game,
    toggle_pause,
)


class SnakeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Snake")
        self.resizable(False, False)

        self.config_model = SnakeConfig(cols=20, rows=20)
        self.cell_size = 22
        self.tick_ms = 140
        self.rng = random.Random(42)
        self.state: SnakeState = create_initial_state(self.config_model, rng=self.rng)
        self.pending_direction: Optional[str] = None

        self._build_ui()
        self._bind_keys()
        self._render()
        self.after(self.tick_ms, self._tick)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.grid(row=0, column=0, sticky="nsew")

        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew")
        self.score_var = tk.StringVar(value="Score: 0")
        self.status_var = tk.StringVar(value="Running")
        ttk.Label(header, textvariable=self.score_var).grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.status_var).grid(row=0, column=1, padx=(16, 0), sticky="w")
        ttk.Button(header, text="Pause", command=self._toggle_pause).grid(row=0, column=2, padx=(16, 0))
        ttk.Button(header, text="Restart", command=self._restart).grid(row=0, column=3, padx=(8, 0))

        w = self.config_model.cols * self.cell_size
        h = self.config_model.rows * self.cell_size
        self.canvas = tk.Canvas(root, width=w, height=h, bg="#F5F5F5", highlightthickness=1, highlightbackground="#BDBDBD")
        self.canvas.grid(row=1, column=0, pady=(8, 8))

        controls = ttk.Frame(root)
        controls.grid(row=2, column=0, pady=(4, 0))
        ttk.Button(controls, text="Up", width=8, command=lambda: self._queue_direction(DIR_UP)).grid(row=0, column=1)
        ttk.Button(controls, text="Left", width=8, command=lambda: self._queue_direction(DIR_LEFT)).grid(row=1, column=0, padx=(0, 4))
        ttk.Button(controls, text="Down", width=8, command=lambda: self._queue_direction(DIR_DOWN)).grid(row=1, column=1)
        ttk.Button(controls, text="Right", width=8, command=lambda: self._queue_direction(DIR_RIGHT)).grid(row=1, column=2, padx=(4, 0))

    def _bind_keys(self) -> None:
        for key in ("<Up>", "<Key-w>", "<Key-W>"):
            self.bind(key, lambda _e: self._queue_direction(DIR_UP))
        for key in ("<Down>", "<Key-s>", "<Key-S>"):
            self.bind(key, lambda _e: self._queue_direction(DIR_DOWN))
        for key in ("<Left>", "<Key-a>", "<Key-A>"):
            self.bind(key, lambda _e: self._queue_direction(DIR_LEFT))
        for key in ("<Right>", "<Key-d>", "<Key-D>"):
            self.bind(key, lambda _e: self._queue_direction(DIR_RIGHT))
        self.bind("<space>", lambda _e: self._toggle_pause())
        self.bind("<Key-p>", lambda _e: self._toggle_pause())
        self.bind("<Key-P>", lambda _e: self._toggle_pause())
        self.bind("<Key-r>", lambda _e: self._restart())
        self.bind("<Key-R>", lambda _e: self._restart())

    def _queue_direction(self, direction: str) -> None:
        if direction in DIR_DELTAS:
            self.pending_direction = direction

    def _toggle_pause(self) -> None:
        self.state = toggle_pause(self.state)
        self._render()

    def _restart(self) -> None:
        self.state = create_initial_state(self.config_model, rng=self.rng)
        self.pending_direction = None
        self._render()

    def _tick(self) -> None:
        self.state = step_game(
            self.state,
            self.config_model,
            requested_direction=self.pending_direction,
            rng=self.rng,
        )
        self.pending_direction = None
        self._render()
        self.after(self.tick_ms, self._tick)

    def _render(self) -> None:
        self.canvas.delete("all")
        for x in range(self.config_model.cols):
            for y in range(self.config_model.rows):
                self._draw_cell(x, y, fill="#FAFAFA")

        if self.state.food is not None:
            fx, fy = self.state.food
            self._draw_cell(fx, fy, fill="#E53935")

        for i, (sx, sy) in enumerate(self.state.snake):
            self._draw_cell(sx, sy, fill="#1B5E20" if i == 0 else "#2E7D32")

        self.score_var.set(f"Score: {self.state.score}")
        if self.state.game_over:
            self.status_var.set("Game Over (R to restart)")
        elif self.state.paused:
            self.status_var.set("Paused")
        else:
            self.status_var.set("Running")

    def _draw_cell(self, x: int, y: int, fill: str) -> None:
        x0 = x * self.cell_size
        y0 = y * self.cell_size
        x1 = x0 + self.cell_size
        y1 = y0 + self.cell_size
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="#E0E0E0")


if __name__ == "__main__":
    SnakeApp().mainloop()
