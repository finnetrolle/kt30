"""
SQLite-backed fixed-window rate limiter for multi-worker Flask deployments.
"""
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict


class SQLiteRateLimiter:
    """Fixed-window rate limiter persisted in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _initialize(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limit_counters (
                    scope TEXT NOT NULL,
                    rate_key TEXT NOT NULL,
                    bucket_start INTEGER NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY(scope, rate_key, bucket_start)
                )
                """
            )

    def check(self, scope: str, rate_key: str, limit: int, window_seconds: int) -> Dict[str, int | bool]:
        """Consume one hit and return whether the request is allowed."""
        if limit <= 0 or window_seconds <= 0:
            return {"allowed": True, "remaining": limit, "reset_at": int(time.time())}

        now = int(time.time())
        bucket_start = now - (now % window_seconds)
        reset_at = bucket_start + window_seconds

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT count
                FROM rate_limit_counters
                WHERE scope = ? AND rate_key = ? AND bucket_start = ?
                """,
                (scope, rate_key, bucket_start)
            ).fetchone()

            current_count = int(row["count"]) if row else 0
            allowed = current_count < limit
            new_count = current_count + 1 if allowed else current_count

            if row:
                if allowed:
                    conn.execute(
                        """
                        UPDATE rate_limit_counters
                        SET count = ?
                        WHERE scope = ? AND rate_key = ? AND bucket_start = ?
                        """,
                        (new_count, scope, rate_key, bucket_start)
                    )
            elif allowed:
                conn.execute(
                    """
                    INSERT INTO rate_limit_counters(scope, rate_key, bucket_start, count)
                    VALUES (?, ?, ?, 1)
                    """,
                    (scope, rate_key, bucket_start)
                )

            conn.execute("COMMIT")

        remaining = max(0, limit - new_count)
        return {
            "allowed": allowed,
            "remaining": remaining,
            "reset_at": reset_at
        }

    def cleanup(self, retention_seconds: int = 24 * 60 * 60) -> int:
        """Delete expired buckets."""
        cutoff = int(time.time()) - retention_seconds
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM rate_limit_counters WHERE bucket_start < ?",
                (cutoff,)
            )
        return result.rowcount


_rate_limiter_instance: SQLiteRateLimiter | None = None


def get_rate_limiter(db_path: str) -> SQLiteRateLimiter:
    """Get or create the rate limiter singleton."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None or os.fspath(_rate_limiter_instance.db_path) != os.fspath(Path(db_path)):
        _rate_limiter_instance = SQLiteRateLimiter(db_path)
    return _rate_limiter_instance
