"""
Durable SQLite-backed job queue for long-running analysis tasks.
"""
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class JobStatus:
    """Canonical job status values."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class JobQueue:
    """SQLite-backed queue with leasing semantics for worker processes."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
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
                CREATE TABLE IF NOT EXISTS jobs (
                    task_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    result_id TEXT,
                    worker_id TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_heartbeats (
                    worker_id TEXT PRIMARY KEY,
                    updated_at REAL NOT NULL
                )
                """
            )

    def enqueue(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new queued job."""
        now = time.time()
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs (
                    task_id, payload_json, status, error, result_id, worker_id,
                    cancel_requested, created_at, updated_at, started_at, finished_at
                ) VALUES (?, ?, ?, NULL, NULL, NULL, 0, ?, ?, NULL, NULL)
                """,
                (task_id, serialized, JobStatus.QUEUED, now, now)
            )
        return self.get(task_id)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one job by task id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE task_id = ?",
                (task_id,)
            ).fetchone()
        return self._row_to_job(row)

    def list_jobs(self, statuses: Optional[list[str]] = None, limit: int = 100) -> list[Dict[str, Any]]:
        """Fetch jobs ordered for operator-facing dashboards."""
        query = [
            "SELECT * FROM jobs"
        ]
        params: list[Any] = []

        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query.append(f"WHERE status IN ({placeholders})")
            params.extend(statuses)

        query.append(
            """
            ORDER BY
                CASE status
                    WHEN 'running' THEN 0
                    WHEN 'queued' THEN 1
                    ELSE 2
                END,
                COALESCE(started_at, created_at) DESC,
                updated_at DESC
            """
        )

        if limit > 0:
            query.append("LIMIT ?")
            params.append(limit)

        with self._connect() as conn:
            rows = conn.execute("\n".join(query), params).fetchall()

        return [self._row_to_job(row) for row in rows if row is not None]

    def lease_next_job(self, worker_id: str, stale_after_seconds: int) -> Optional[Dict[str, Any]]:
        """Lease the next available job for processing."""
        self.requeue_stale_jobs(stale_after_seconds)
        now = time.time()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT task_id
                FROM jobs
                WHERE status = ? AND cancel_requested = 0
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (JobStatus.QUEUED,)
            ).fetchone()

            if row is None:
                conn.execute("COMMIT")
                return None

            task_id = row["task_id"]
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, worker_id = ?, started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (JobStatus.RUNNING, worker_id, now, now, task_id, JobStatus.QUEUED)
            )
            conn.execute("COMMIT")

        return self.get(task_id)

    def touch(self, task_id: str):
        """Update the job heartbeat timestamp."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET updated_at = ? WHERE task_id = ?",
                (time.time(), task_id)
            )

    def mark_succeeded(self, task_id: str, result_id: Optional[str] = None):
        """Mark a job as succeeded."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, result_id = ?, error = NULL, updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (JobStatus.SUCCEEDED, result_id, now, now, task_id)
            )

    def mark_failed(self, task_id: str, error: str):
        """Mark a job as failed."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, error = ?, updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (JobStatus.FAILED, error, now, now, task_id)
            )

    def mark_canceled(self, task_id: str, error: str = "Задача отменена"):
        """Mark a job as canceled."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, error = ?, cancel_requested = 1, updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (JobStatus.CANCELED, error, now, now, task_id)
            )

    def request_cancel(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Request job cancellation.

        Queued jobs are canceled immediately.
        Running jobs receive a cooperative cancellation flag.
        """
        job = self.get(task_id)
        if not job:
            return None

        status = job["status"]
        now = time.time()

        with self._connect() as conn:
            if status == JobStatus.QUEUED:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = ?, error = ?, cancel_requested = 1, updated_at = ?, finished_at = ?
                    WHERE task_id = ?
                    """,
                    (JobStatus.CANCELED, "Задача отменена пользователем", now, now, task_id)
                )
            elif status == JobStatus.RUNNING:
                conn.execute(
                    "UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE task_id = ?",
                    (now, task_id)
                )

        return self.get(task_id)

    def is_cancel_requested(self, task_id: str) -> bool:
        """Check whether cancellation was requested for a job."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM jobs WHERE task_id = ?",
                (task_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def requeue_stale_jobs(self, stale_after_seconds: int) -> int:
        """Move stale running jobs back to the queue."""
        if stale_after_seconds <= 0:
            return 0

        cutoff = time.time() - stale_after_seconds
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE jobs
                SET status = ?, worker_id = NULL, updated_at = ?, error = ?
                WHERE status = ? AND updated_at < ? AND cancel_requested = 0
                """,
                (
                    JobStatus.QUEUED,
                    time.time(),
                    "Job requeued after stale worker lease",
                    JobStatus.RUNNING,
                    cutoff
                )
            )
        if result.rowcount:
            logger.warning("Requeued %s stale jobs", result.rowcount)
        return result.rowcount

    def cleanup_old_jobs(self, retention_seconds: int) -> int:
        """Delete finished jobs older than the retention window."""
        if retention_seconds <= 0:
            return 0

        cutoff = time.time() - retention_seconds
        with self._connect() as conn:
            result = conn.execute(
                """
                DELETE FROM jobs
                WHERE status IN (?, ?, ?) AND finished_at IS NOT NULL AND finished_at < ?
                """,
                (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED, cutoff)
            )
        return result.rowcount

    def heartbeat(self, worker_id: str):
        """Update a worker heartbeat timestamp."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO worker_heartbeats(worker_id, updated_at)
                VALUES (?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (worker_id, time.time())
            )

    def get_worker_health(self, stale_after_seconds: int) -> Dict[str, Any]:
        """Return a summary of worker heartbeats."""
        cutoff = time.time() - stale_after_seconds
        with self._connect() as conn:
            healthy_count = conn.execute(
                "SELECT COUNT(*) AS total FROM worker_heartbeats WHERE updated_at >= ?",
                (cutoff,)
            ).fetchone()["total"]
            total_count = conn.execute(
                "SELECT COUNT(*) AS total FROM worker_heartbeats"
            ).fetchone()["total"]
        return {
            "healthy_workers": healthy_count,
            "known_workers": total_count
        }

    def _row_to_job(self, row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None

        payload = json.loads(row["payload_json"])
        return {
            "task_id": row["task_id"],
            "payload": payload,
            "status": row["status"],
            "error": row["error"],
            "result_id": row["result_id"],
            "worker_id": row["worker_id"],
            "cancel_requested": bool(row["cancel_requested"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"]
        }


_job_queue_instance: Optional[JobQueue] = None


def get_job_queue(db_path: str) -> JobQueue:
    """Get or create the global job queue singleton."""
    global _job_queue_instance
    if _job_queue_instance is None or os.fspath(_job_queue_instance.db_path) != os.fspath(Path(db_path)):
        _job_queue_instance = JobQueue(db_path)
    return _job_queue_instance
