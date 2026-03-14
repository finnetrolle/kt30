import tempfile
import unittest
import types
import sys
import os

os.environ.setdefault("APP_ENV", "testing")

sys.modules.setdefault(
    "document_parser",
    types.SimpleNamespace(parse_document=lambda *_args, **_kwargs: {})
)
sys.modules.setdefault(
    "openai_client",
    types.SimpleNamespace(analyze_specification=lambda *_args, **_kwargs: {"success": False, "error": "stub"})
)
sys.modules.setdefault(
    "excel_export",
    types.SimpleNamespace(
        export_wbs_to_excel=lambda *_args, **_kwargs: (_args, "stub.xlsx"),
        calculate_project_duration_with_parallel=lambda *_args, **_kwargs: {
            "total_days": 0,
            "total_weeks": 0,
            "phase_durations": {}
        },
        build_dependencies_matrix=lambda *_args, **_kwargs: []
    )
)

from app import create_app
from config import TestingConfig
from job_queue import get_job_queue, JobStatus


class TaskApiConfig(TestingConfig):
    SECRET_KEY = "test-secret-key"


class TaskApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base_dir = self.temp_dir.name

        class LocalTaskApiConfig(TaskApiConfig):
            RUNTIME_DIR = f"{base_dir}/runtime"
            UPLOAD_FOLDER = f"{base_dir}/uploads"
            ARTIFACTS_ROOT = f"{base_dir}/analysis_runs"
            RESULTS_STORAGE_DIR = f"{base_dir}/results_data"
            PROGRESS_STORAGE_DIR = f"{base_dir}/progress_data"
            JOB_QUEUE_DB_PATH = f"{base_dir}/runtime/job_queue.sqlite3"
            RATE_LIMIT_DB_PATH = f"{base_dir}/runtime/rate_limits.sqlite3"
            RESULT_TTL_SECONDS = 60
            PROGRESS_TTL_SECONDS = 60
            ARTIFACT_RETENTION_SECONDS = 60
            JOB_RETENTION_SECONDS = 60

        self.app = create_app(LocalTaskApiConfig)
        self.client = self.app.test_client()
        self.job_queue = get_job_queue(LocalTaskApiConfig.JOB_QUEUE_DB_PATH)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_task_status_returns_queued_job(self):
        self.job_queue.enqueue("task-1", {"task_id": "task-1", "filename": "demo.docx"})

        response = self.client.get("/api/tasks/task-1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["task_id"], "task-1")
        self.assertEqual(payload["status"], JobStatus.QUEUED)

    def test_cancel_endpoint_marks_job_canceled(self):
        self.job_queue.enqueue("task-2", {"task_id": "task-2"})
        self.client.get("/")

        with self.client.session_transaction() as session:
            csrf_token = session["_csrf_token"]

        response = self.client.post(
            "/api/tasks/task-2/cancel",
            data={"csrf_token": csrf_token}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], JobStatus.CANCELED)
        self.assertEqual(self.job_queue.get("task-2")["status"], JobStatus.CANCELED)

    def test_ready_is_green_when_worker_heartbeat_exists(self):
        self.job_queue.heartbeat("worker-1")

        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["checks"]["worker_available"])


if __name__ == "__main__":
    unittest.main()
