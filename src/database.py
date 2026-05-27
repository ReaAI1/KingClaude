"""
Aurentis AI — SQLite persistence layer.
Optional Supabase sync for cloud access across devices.
"""
import json
import logging
import sqlite3
import time
import threading
from typing import Any, List, Optional

log = logging.getLogger("aurentis.db")


class Database:
    def __init__(self, path: str = "aurentis.db"):
        self._path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup()
        log.info("Database ready: %s", path)

    def _setup(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           REAL,
                coin         TEXT,
                side         TEXT,
                size         REAL,
                entry        REAL,
                exit         REAL,
                pnl          REAL,
                fees         REAL,
                pnl_pct      REAL,
                reason       TEXT,
                duration_min REAL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                ts    REAL,
                value REAL,
                cash  REAL,
                realized REAL
            );
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                val TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_trades_ts    ON trades(ts);
            CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
        """)
        self._conn.commit()

    # ── KV store ──────────────────────────────────────────────────────────────
    def set(self, key: str, value: str):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, value))
            self._conn.commit()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT val FROM kv WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    # ── Trades ────────────────────────────────────────────────────────────────
    def insert_trade(self, coin, side, size, entry, exit_p, pnl, fees, pnl_pct, reason, dur):
        with self._lock:
            self._conn.execute(
                "INSERT INTO trades "
                "(ts,coin,side,size,entry,exit,pnl,fees,pnl_pct,reason,duration_min) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), coin, side, size, entry, exit_p, pnl, fees, pnl_pct, reason, dur),
            )
            self._conn.commit()

    def recent_trades(self, n: int = 50) -> List[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT coin,side,size,entry,exit,pnl,pnl_pct,reason,duration_min "
                "FROM trades ORDER BY ts DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def all_trades(self) -> List[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM trades ORDER BY ts ASC").fetchall()
        return [dict(r) for r in rows]

    # ── Snapshots ─────────────────────────────────────────────────────────────
    def insert_snapshot(self, value: float, cash: float, realized: float):
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots VALUES (?,?,?,?)",
                (time.time(), value, cash, realized),
            )
            self._conn.commit()

    def recent_snapshots(self, n: int = 288) -> List[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, value, cash, realized FROM snapshots "
                "ORDER BY ts DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def equity_curve(self, hours: int = 24) -> List[dict]:
        since = time.time() - hours * 3600
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, value FROM snapshots WHERE ts > ? ORDER BY ts ASC",
                (since,)
            ).fetchall()
        return [{"ts": r["ts"], "value": r["value"]} for r in rows]

    # ── Stats ─────────────────────────────────────────────────────────────────
    def trade_stats(self) -> dict:
        rows = self.all_trades()
        if not rows:
            return {}
        wins   = [r for r in rows if r["pnl"] > 0]
        losses = [r for r in rows if r["pnl"] <= 0]
        return {
            "total":    len(rows),
            "wins":     len(wins),
            "losses":   len(losses),
            "win_rate": len(wins) / len(rows) * 100 if rows else 0,
            "total_pnl": sum(r["pnl"] for r in rows),
        }
