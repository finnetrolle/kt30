"""
Dedicated worker process entrypoint for queued analysis jobs.
"""
import logging
import os
import signal
import sys

from config import Config, get_active_config_class
from job_worker import JobWorker


logger = logging.getLogger(__name__)


def main() -> int:
    config_class = get_active_config_class()
    Config.apply_runtime_overrides(config_class)
    config_class.init_app()

    worker = JobWorker(worker_id=os.getenv("WORKER_ID"))

    def shutdown(_signum, _frame):
        logger.info("Shutdown signal received, stopping worker")
        worker.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
