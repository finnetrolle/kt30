"""
Worker runtime for processing queued analysis jobs.
"""
import logging
import socket
import threading
import time
import uuid
from typing import Optional

from analysis_jobs import process_analysis_job
from config import Config
from job_queue import get_job_queue
from progress_tracker import get_progress_store
from result_store import get_result_store

logger = logging.getLogger(__name__)


class JobWorker:
    """Polls the durable job queue and processes analysis jobs."""

    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.job_queue = get_job_queue(Config.JOB_QUEUE_DB_PATH)
        self.progress_store = get_progress_store(
            storage_root=Config.PROGRESS_STORAGE_DIR,
            ttl_seconds=Config.PROGRESS_TTL_SECONDS
        )
        self.result_store = get_result_store(
            storage_dir=Config.RESULTS_STORAGE_DIR,
            ttl_seconds=Config.RESULT_TTL_SECONDS
        )
        self.poll_interval_seconds = Config.WORKER_POLL_INTERVAL_SECONDS
        self.stale_after_seconds = Config.JOB_STALE_AFTER_SECONDS
        self.job_retention_seconds = Config.JOB_RETENTION_SECONDS
        self._stop_event = threading.Event()

    def stop(self):
        """Request the worker loop to stop."""
        self._stop_event.set()

    def run_once(self) -> bool:
        """Lease and process at most one job."""
        self.job_queue.heartbeat(self.worker_id)
        self.job_queue.cleanup_old_jobs(self.job_retention_seconds)

        job = self.job_queue.lease_next_job(self.worker_id, self.stale_after_seconds)
        if not job:
            return False

        logger.info("Worker %s processing task %s", self.worker_id, job["task_id"])
        process_analysis_job(job, self.result_store, self.progress_store, self.job_queue)
        return True

    def run_forever(self):
        """Run the worker loop until stopped."""
        logger.info("Worker %s started", self.worker_id)
        while not self._stop_event.is_set():
            processed = self.run_once()
            if not processed:
                self._stop_event.wait(self.poll_interval_seconds)
        logger.info("Worker %s stopped", self.worker_id)

    def start_in_background(self) -> threading.Thread:
        """Launch the worker loop in a daemon thread."""
        thread = threading.Thread(target=self.run_forever, name=f"job-worker-{self.worker_id}", daemon=True)
        thread.start()
        return thread
