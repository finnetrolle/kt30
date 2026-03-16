import tempfile
import time
import unittest

from job_queue import get_job_queue, JobStatus


class JobQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.queue = get_job_queue(f"{self.temp_dir.name}/job_queue.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_enqueue_and_lease_job(self):
        self.queue.enqueue("task-1", {"task_id": "task-1", "filename": "demo.docx"})
        leased = self.queue.lease_next_job("worker-1", stale_after_seconds=60)

        self.assertIsNotNone(leased)
        self.assertEqual(leased["task_id"], "task-1")
        self.assertEqual(leased["status"], JobStatus.RUNNING)

    def test_cancel_queued_job_immediately(self):
        self.queue.enqueue("task-2", {"task_id": "task-2"})
        job = self.queue.request_cancel("task-2")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JobStatus.CANCELED)

    def test_mark_job_succeeded(self):
        self.queue.enqueue("task-3", {"task_id": "task-3"})
        self.queue.lease_next_job("worker-1", stale_after_seconds=60)
        self.queue.mark_succeeded("task-3", result_id="result-3")
        job = self.queue.get("task-3")

        self.assertEqual(job["status"], JobStatus.SUCCEEDED)
        self.assertEqual(job["result_id"], "result-3")

    def test_touch_prevents_running_job_from_being_requeued_as_stale(self):
        self.queue.enqueue("task-4", {"task_id": "task-4"})
        self.queue.lease_next_job("worker-1", stale_after_seconds=60)

        with self.queue._connect() as conn:
            conn.execute(
                "UPDATE jobs SET updated_at = ? WHERE task_id = ?",
                (time.time() - 120, "task-4")
            )

        self.queue.touch("task-4")
        requeued = self.queue.requeue_stale_jobs(stale_after_seconds=60)
        job = self.queue.get("task-4")

        self.assertEqual(requeued, 0)
        self.assertEqual(job["status"], JobStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
