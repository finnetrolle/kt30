"""
SQLite-backed liveness/readiness probe for the worker process.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time


def _resolve_db_path() -> str:
    runtime_dir = os.getenv("RUNTIME_DIR", "runtime")
    return os.getenv("JOB_QUEUE_DB_PATH", os.path.join(runtime_dir, "job_queue.sqlite3"))


def main() -> int:
    db_path = _resolve_db_path()
    worker_id = os.getenv("WORKER_ID", "").strip()
    stale_after = int(os.getenv("WORKER_HEALTHCHECK_TTL_SECONDS", os.getenv("JOB_STALE_AFTER_SECONDS", "1800")))
    cutoff = time.time() - stale_after

    if not os.path.exists(db_path):
        print(f"worker healthcheck database missing: {db_path}")
        return 1

    query = "SELECT updated_at FROM worker_heartbeats WHERE updated_at >= ? ORDER BY updated_at DESC LIMIT 1"
    params: tuple[object, ...] = (cutoff,)

    if worker_id:
        query = "SELECT updated_at FROM worker_heartbeats WHERE worker_id = ? AND updated_at >= ? LIMIT 1"
        params = (worker_id, cutoff)

    try:
        connection = sqlite3.connect(db_path, timeout=5)
        row = connection.execute(query, params).fetchone()
        connection.close()
    except sqlite3.Error as exc:
        print(f"worker healthcheck query failed: {exc}")
        return 1

    if not row:
        target = worker_id or "any worker"
        print(f"worker unhealthy: no fresh heartbeat for {target}")
        return 1

    print("worker healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
