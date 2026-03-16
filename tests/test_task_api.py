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
from progress_tracker import get_progress_store
from result_store import get_result_store


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
        self.progress_store = get_progress_store(
            storage_root=LocalTaskApiConfig.PROGRESS_STORAGE_DIR,
            ttl_seconds=LocalTaskApiConfig.PROGRESS_TTL_SECONDS
        )
        self.result_store = get_result_store(
            storage_dir=LocalTaskApiConfig.RESULTS_STORAGE_DIR,
            ttl_seconds=LocalTaskApiConfig.RESULT_TTL_SECONDS
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_task_status_returns_queued_job(self):
        self.job_queue.enqueue("task-1", {"task_id": "task-1", "filename": "demo.docx"})
        tracker = self.progress_store.create("task-1")
        tracker.stage("⏳ Задача поставлена в очередь")

        response = self.client.get("/api/tasks/task-1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["task_id"], "task-1")
        self.assertEqual(payload["status"], JobStatus.QUEUED)
        self.assertEqual(payload["filename"], "demo.docx")
        self.assertEqual(payload["current_stage"], "⏳ Задача поставлена в очередь")
        self.assertEqual(payload["payload"]["filename"], "demo.docx")

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

    def test_list_active_tasks_returns_dashboard_view_model(self):
        self.job_queue.enqueue(
            "task-running",
            {"task_id": "task-running", "filename": "spec-a.docx", "file_size": 2048}
        )
        running_tracker = self.progress_store.create("task-running")
        running_tracker.stage("Парсинг документа...")
        running_tracker.usage("planner", {"prompt_tokens": 12, "completion_tokens": 8})
        self.job_queue.lease_next_job("worker-1", stale_after_seconds=60)

        self.job_queue.enqueue(
            "task-queued",
            {"task_id": "task-queued", "filename": "spec-b.pdf", "file_size": 1024}
        )
        queued_tracker = self.progress_store.create("task-queued")
        queued_tracker.stage("⏳ Задача поставлена в очередь")

        self.job_queue.enqueue("task-finished", {"task_id": "task-finished", "filename": "done.docx"})
        self.job_queue.mark_succeeded("task-finished", result_id="result-1")
        self.result_store.save(
            "result-1",
            {
                "filename": "done.docx",
                "timestamp": "2026-03-16T12:00:00Z",
                "result": {"wbs": {"phases": []}},
                "usage": {},
                "metadata": {},
                "token_usage": {}
            }
        )

        response = self.client.get("/api/tasks")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["scope"], "active")
        self.assertEqual(payload["counts"]["total"], 2)
        self.assertEqual(payload["counts"]["running"], 1)
        self.assertEqual(payload["counts"]["queued"], 1)

        items = {item["task_id"]: item for item in payload["items"]}
        self.assertEqual(set(items.keys()), {"task-running", "task-queued"})
        self.assertEqual(items["task-running"]["status"], JobStatus.RUNNING)
        self.assertEqual(items["task-running"]["filename"], "spec-a.docx")
        self.assertEqual(items["task-running"]["current_stage"], "Парсинг документа...")
        self.assertEqual(items["task-running"]["total_tokens"], 20)
        self.assertEqual(items["task-running"]["request_count"], 1)
        self.assertEqual(items["task-running"]["worker_id"], "worker-1")
        self.assertEqual(items["task-queued"]["status"], JobStatus.QUEUED)
        self.assertEqual(items["task-queued"]["filename"], "spec-b.pdf")
        self.assertEqual(len(payload["recent_results"]), 1)
        self.assertEqual(payload["recent_results"][0]["task_id"], "task-finished")
        self.assertEqual(payload["recent_results"][0]["result_id"], "result-1")

    def test_ready_is_green_when_worker_heartbeat_exists(self):
        self.job_queue.heartbeat("worker-1")

        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["checks"]["worker_available"])


if __name__ == "__main__":
    unittest.main()
