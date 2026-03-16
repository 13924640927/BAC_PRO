# -*- coding: utf-8 -*-
"""
core/db_adapter.py  (STEP6 EV MATCH FIX + BET LOG)

Goals:
- EV lookup MUST match the exact JSON string format produced by core.snapshot_engine.canonical_hist_json
  and stored in premax_snapshot_state / premax_state_ev by your sampling + stored procedure.
- Provide duplicate detection (n_matches > 1) and clear error messages.
- Provide bet_log insertion.

Public API:
- query_premax_ev(cur_side, cur_len, hist_b_json, hist_p_json) -> (row|None, n_matches:int, err|None)
- insert_bet_log(...)
"""

from __future__ import annotations
import hashlib
import os
import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector.errors import PoolError

# IMPORTANT: ensure we use the SAME canonicalization as the sampler (state_sampler.py)
try:
    from core.snapshot_engine import canonical_hist_json
except Exception:
    canonical_hist_json = None  # type: ignore

DB_CONFIG = {
    "host": os.getenv("BAC_DB_HOST", "localhost"),
    "user": os.getenv("BAC_DB_USER", "root"),
    "password": os.getenv("BAC_DB_PASS", "holybaby"),
    "database": os.getenv("BAC_DB_NAME", "BAC_PRO"),
    "autocommit": True,
}

_POOL: Optional[MySQLConnectionPool] = None


def init_pool(pool_size: int = 5) -> None:
    global _POOL
    if _POOL is None:
        _POOL = MySQLConnectionPool(pool_name="bac_pro_pool", pool_size=pool_size, **DB_CONFIG)


def get_conn():
    if _POOL is None:
        init_pool()
    return _POOL.get_connection()  # type: ignore


def _canon_json(x: Any) -> str:
    """Return canonical JSON string that matches canonical_hist_json used by sampling."""
    # sampler stores {} for empty; keep consistent
    if x is None or x == "":
        return "{}"

    # If python dict/list/etc: prefer canonical_hist_json if available
    if not isinstance(x, str):
        if canonical_hist_json is not None:
            try:
                return canonical_hist_json(x)  # type: ignore
            except Exception:
                pass
        # fallback: still canonicalize deterministically
        try:
            return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            return str(x)

    # string path
    s = x.strip()

    # If it's a python repr like "{'1': 1}", normalize it
    # 1) try strict json
    try:
        obj = json.loads(s)
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        pass

    # 2) try relaxed: replace single quotes with double quotes
    try:
        obj = json.loads(s.replace("'", '"'))
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        # as last resort, return trimmed string (but this may not match DB)
        return s


def query_premax_ev(
    cur_side: str,
    cur_len: int,
    hist_b_json: Any,
    hist_p_json: Any,
) -> Tuple[Optional[Dict[str, Any]], int, Optional[str]]:
    """
    Exact match against premax_state_ev.

    Matching keys:
      cur_side, cur_len, hist_b_json, hist_p_json

    Returns:
      (row, n_matches, err)

    Notes:
    - n_matches > 1 indicates duplicate rows for the same key (shouldn't happen if you enforce uniqueness).
    - We LIMIT 2 for speed but still detect duplicates.
    """
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor(dictionary=True)

        sql = """
        SELECT
          ev_cut,
          ev_continue,
          best_action,
          edge
        FROM premax_state_ev
        WHERE
          cur_side = %s
          AND cur_len = %s
          AND hist_b_json = CAST(%s AS JSON)
          AND hist_p_json = CAST(%s AS JSON)
        LIMIT 2;
        """

        hb = _canon_json(hist_b_json)
        hp = _canon_json(hist_p_json)

        cur.execute(sql, (str(cur_side), int(cur_len), hb, hp))
        rows = cur.fetchall() or []
        n_matches = len(rows)
        row = rows[0] if n_matches >= 1 else None
        return row, n_matches, None

    except PoolError as e:
        return None, 0, f"MySQL pool error (EV query): {e}"
    except Error as e:
        return None, 0, f"MySQL query error (EV): {e}"
    except Exception as e:
        return None, 0, f"EV query exception: {e}"
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()  # return to pool
        except Exception:
            pass
        
def query_premax_ev_sig(cur_side, cur_len, hist_b_json, hist_p_json):
    conn = None
    cur = None
    try:
        hb = _canon_json(hist_b_json)
        hp = _canon_json(hist_p_json)

        conn = get_conn()
        cur = conn.cursor(dictionary=True)

        sql = """
        SELECT
          best_action, edge, ev_cut, ev_continue,
          n_eq, n_gt, n_ge,
          p_cut, p_continue,
          updated_at
        FROM BAC_PRO.premax_state_ev_sig
        WHERE cur_side = %s
          AND cur_len  = %s
          AND hist_sig = SHA2(
              CONCAT(
                CAST(CAST(%s AS JSON) AS CHAR),
                '|',
                CAST(CAST(%s AS JSON) AS CHAR)
              ),
              256
          )
        LIMIT 1
        """

        cur.execute(sql, (str(cur_side), int(cur_len), hb, hp))
        row = cur.fetchone()

        return (row, 1 if row else 0, None)

    except Exception as e:
        return (None, 0, f"DB_ERR: {e}")

    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
        
def insert_bet_log(
    shoe_id: str,
    hand_id: int,
    bet_side: str,
    bet_amount: float,
    ev_row: Optional[Dict[str, Any]],
    result: str,
    pnl: float,
) -> Optional[str]:
    """Insert one row into bet_log. Returns err string or None."""
    conn = None
    cur = None
    try:
        if not ev_row:
            ev_row = {"ev_cut": None, "ev_continue": None, "best_action": None, "edge": None}

        conn = get_conn()
        cur = conn.cursor()

        sql = """
        INSERT INTO bet_log (
            ts,
            shoe_id,
            hand_id,
            bet_side,
            bet_amount,
            ev_cut,
            ev_continue,
            best_action,
            edge,
            result,
            pnl
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """

        cur.execute(
            sql,
            (
                datetime.now(),
                str(shoe_id),
                int(hand_id),
                str(bet_side),
                float(bet_amount),
                ev_row.get("ev_cut"),
                ev_row.get("ev_continue"),
                ev_row.get("best_action"),
                ev_row.get("edge"),
                str(result),
                float(pnl),
            ),
        )

        try:
            conn.commit()
        except Exception:
            pass

        return None

    except PoolError as e:
        return f"MySQL pool error (bet_log): {e}"
    except Error as e:
        return f"MySQL bet_log insert error: {e}"
    except Exception as e:
        return f"bet_log insert exception: {e}"
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
