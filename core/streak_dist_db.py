#BAC_PRO/core/streak_dist_db.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple, Any, Optional

import pymysql


@dataclass
class DBConfig:
    host: str = "localhost"
    user: str = "root"
    password: str = ""
    database: str = "BAC_PRO"
    port: int = 3306
    charset: str = "utf8mb4"


class StreakDistDB:
    """
    - streak_dist_len: per (run_id, side, is_censored, len) counts via UPSERT
    - streak_dist_run: run progress + cumulative totals (absolute values)
    """
    def __init__(self, cfg: DBConfig, *, autocommit: bool = False):
        self.cfg = cfg
        self.conn = pymysql.connect(
            host=cfg.host,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            port=cfg.port,
            charset=cfg.charset,
            autocommit=autocommit,
        )
        # buffer key: (side, is_censored, len) -> cnt_increment
        self.buf: Dict[Tuple[str, int, int], int] = {}

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def add_len(self, *, side: str, is_censored: int, length: int, inc: int = 1):
        key = (side, is_censored, int(length))
        self.buf[key] = self.buf.get(key, 0) + int(inc)

    def flush_len(self, *, run_id: str):
        if not self.buf:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for (side, is_censored, length), inc in self.buf.items():
            rows.append((run_id, side, is_censored, length, inc, now))

        sql = """
        INSERT INTO streak_dist_len
          (run_id, side, is_censored, len, cnt, updated_at)
        VALUES
          (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          cnt = cnt + VALUES(cnt),
          updated_at = VALUES(updated_at);
        """
        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)
        self.conn.commit()
        self.buf.clear()

    def upsert_run(
        self,
        *,
        run_id: str,
        mode: str,
        master_seed: int,
        params: dict,
        shoes_target: int,
        shoes_done: int,
        raw_b: int,
        raw_p: int,
        raw_t: int,
        censored_streaks: int,
        censored_b_hands: int,
        censored_p_hands: int,
        finished: bool,
    ):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        params_json = json.dumps(params, separators=(",", ":"), sort_keys=True)

        sql = """
        INSERT INTO streak_dist_run
          (run_id, mode, master_seed, params_json, shoes_target, shoes_done,
           raw_b, raw_p, raw_t, censored_streaks, censored_b_hands, censored_p_hands,
           started_at, updated_at, finished_at)
        VALUES
          (%s, %s, %s, CAST(%s AS JSON), %s, %s,
           %s, %s, %s, %s, %s, %s,
           %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          shoes_done = VALUES(shoes_done),
          raw_b = VALUES(raw_b),
          raw_p = VALUES(raw_p),
          raw_t = VALUES(raw_t),
          censored_streaks = VALUES(censored_streaks),
          censored_b_hands = VALUES(censored_b_hands),
          censored_p_hands = VALUES(censored_p_hands),
          updated_at = VALUES(updated_at),
          finished_at = VALUES(finished_at);
        """

        finished_at = now if finished else None
        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run_id, mode, master_seed, params_json, shoes_target, shoes_done,
                    raw_b, raw_p, raw_t, censored_streaks, censored_b_hands, censored_p_hands,
                    now, now, finished_at
                ),
            )
        self.conn.commit()

    def load_run(self, run_id: str) -> Tuple[int, int, int, Dict[str, Any], Dict[str, int]]:
        """
        Returns:
          master_seed, shoes_done, shoes_target, params_dict, totals_dict
        totals_dict keys:
          raw_b, raw_p, raw_t, censored_streaks, censored_b_hands, censored_p_hands
        """
        sql = """
        SELECT master_seed, shoes_done, shoes_target, params_json,
               raw_b, raw_p, raw_t, censored_streaks, censored_b_hands, censored_p_hands
        FROM streak_dist_run
        WHERE run_id = %s
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (run_id,))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"run_id not found: {run_id}")

        (
            master_seed, shoes_done, shoes_target, params_json,
            raw_b, raw_p, raw_t, censored_streaks, censored_b_hands, censored_p_hands
        ) = row

        return (
            int(master_seed),
            int(shoes_done),
            int(shoes_target),
            json.loads(params_json),
            {
                "raw_b": int(raw_b),
                "raw_p": int(raw_p),
                "raw_t": int(raw_t),
                "censored_streaks": int(censored_streaks),
                "censored_b_hands": int(censored_b_hands),
                "censored_p_hands": int(censored_p_hands),
            },
        )