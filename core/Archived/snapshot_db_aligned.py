# core/snapshot_db.py
# Snapshot DB Writer (RUN-AWARE, PARAMS-AWARE)
# Compatible with new schema:
#   PRIMARY KEY (run_id, state_hash)

import json
import hashlib
import pymysql
from datetime import datetime
from typing import Dict


# =========================
# Helpers
# =========================

def _canonical_json(obj: dict) -> str:
    """Canonical JSON (sorted keys, compact)"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def params_hash(params_json: dict) -> str:
    return sha256_hex(_canonical_json(params_json))

class DBConfig:
    def __init__(self, user, password, db_name, host="localhost", port=3306):
        self.user = user
        self.password = password
        self.db_name = db_name
        self.host = host
        self.port = port
# =========================
# Snapshot DB Writer
# =========================

class SnapshotDBWriter:
    def __init__(
        self,
        *,
        db_host: str,
        db_user: str,
        db_password: str,
        db_name: str,
        run_id: str,
        params: dict,
    ):
        self.run_id = run_id
        self.params = params
        self.params_hash = params_hash(params)

        self.conn = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            autocommit=False,
            charset="utf8mb4",
        )

        self._ensure_run_row()

    # -------------------------
    # Run table
    # -------------------------

    def _ensure_run_row(self):
        """
        Create run row if not exists.
        If exists, verify params_hash consistency.
        """
        now = datetime.utcnow()

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT params_hash
                FROM premax_snapshot_run
                WHERE run_id = %s
                """,
                (self.run_id,),
            )
            row = cur.fetchone()

            if row is None:
                # create new run
                cur.execute(
                    """
                    INSERT INTO premax_snapshot_run (
                        run_id, mode,
                        master_seed,
                        params_json, params_hash,
                        shoes_target,
                        shoes_done, snapshots_done, states_touched,
                        started_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 0, %s, %s)
                    """,
                    (
                        self.run_id,
                        self.params.get("mode", "PROD"),
                        self.params["master_seed"],
                        json.dumps(self.params),
                        self.params_hash,
                        (self.params.get("shoes_target") or self.params.get("shoes_target_total")),
                        now,
                        now,
                    ),
                )
                self.conn.commit()
            else:
                # resume: verify params_hash
                if row[0] != self.params_hash:
                    raise RuntimeError(
                        f"[FATAL] Run params mismatch for run_id={self.run_id}\n"
                        f"DB params_hash={row[0]}\n"
                        f"CLI params_hash={self.params_hash}"
                    )

    def update_run_checkpoint(
        self,
        *,
        shoes_done: int,
        snapshots_done: int,
        states_touched: int,
        finished: bool = False,
    ):
        now = datetime.utcnow()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE premax_snapshot_run
                SET
                    shoes_done=%s,
                    snapshots_done=%s,
                    states_touched=%s,
                    updated_at=%s,
                    finished_at=%s
                WHERE run_id=%s
                """,
                (
                    shoes_done,
                    snapshots_done,
                    states_touched,
                    now,
                    now if finished else None,
                    self.run_id,
                ),
            )
        self.conn.commit()

    # -------------------------
    # State UPSERT
    # -------------------------

    def upsert_states(self, states: Dict[str, dict]):
        """
        states:
          state_hash -> {
            cur_side, cur_len,
            hist_b_json, hist_p_json,
            cnt, sum_hist_hb, sum_hist_hp
          }
        """
        now = datetime.utcnow()

        sql = """
        INSERT INTO premax_snapshot_state (
            run_id, params_hash,
            cur_min, cur_max, hist_min, hist_max,
            state_hash,
            cur_side, cur_len,
            hist_b_json, hist_p_json,
            cnt, sum_hist_hb, sum_hist_hp,
            created_at, updated_at
        )
        VALUES (
            %s, %s,
            %s, %s, %s, %s,
            %s,
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s
        )
        ON DUPLICATE KEY UPDATE
            cnt = cnt + VALUES(cnt),
            sum_hist_hb = sum_hist_hb + VALUES(sum_hist_hb),
            sum_hist_hp = sum_hist_hp + VALUES(sum_hist_hp),
            updated_at = VALUES(updated_at)
        """

        with self.conn.cursor() as cur:
            for state_hash, s in states.items():
                cur.execute(
                    sql,
                    (
                        self.run_id,
                        self.params_hash,
                        self.params["cur_min"],
                        self.params["cur_max"],
                        self.params["hist_min"],
                        self.params["hist_max"],
                        state_hash,
                        s["cur_side"],
                        s["cur_len"],
                        json.dumps(s["hist_b"]),
                        json.dumps(s["hist_p"]),
                        s["cnt"],
                        s["sum_hist_hb"],
                        s["sum_hist_hp"],
                        now,
                        now,
                    ),
                )

        self.conn.commit()

    def close(self):
        self.conn.close()