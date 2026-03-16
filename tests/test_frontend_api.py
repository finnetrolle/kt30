import io
import tempfile
import time
import unittest
import types
import sys
import os
from pathlib import Path
from unittest import mock

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
from job_queue import get_job_queue
from progress_tracker import get_progress_store
from result_store import get_result_store


class AuthFrontendApiConfig(TestingConfig):
    SECRET_KEY = "test-secret-key"
    APP_AUTH_PASSWORD = "topsecret"


class FrontendApiAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base_dir = self.temp_dir.name

        class LocalAuthFrontendApiConfig(AuthFrontendApiConfig):
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
            FRONTEND_DIST_DIR = f"{base_dir}/frontend_dist"
            SERVE_FRONTEND_BUILD = True

        frontend_dist = Path(LocalAuthFrontendApiConfig.FRONTEND_DIST_DIR)
        frontend_dist.mkdir(parents=True, exist_ok=True)
        (frontend_dist / "index.html").write_text("<html><body>frontend app</body></html>", encoding="utf-8")
        self.app = create_app(LocalAuthFrontendApiConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_session_endpoint_reports_unauthenticated_user(self):
        response = self.client.get("/api/auth/session")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["auth_enabled"])
        self.assertFalse(payload["authenticated"])
        self.assertTrue(payload["csrf_token"])

    def test_api_login_requires_csrf(self):
        response = self.client.post("/api/auth/login", json={"password": "topsecret"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "CSRF validation failed")

    def test_api_login_and_logout_flow(self):
        csrf_response = self.client.get("/api/auth/csrf")
        csrf_token = csrf_response.get_json()["csrf_token"]

        login_response = self.client.post(
            "/api/auth/login",
            json={"password": "topsecret"},
            headers={"X-CSRF-Token": csrf_token}
        )

        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.get_json()
        self.assertTrue(login_payload["success"])
        self.assertTrue(login_payload["authenticated"])

        logout_response = self.client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": csrf_token}
        )

        self.assertEqual(logout_response.status_code, 200)
        logout_payload = logout_response.get_json()
        self.assertTrue(logout_payload["success"])
        self.assertFalse(logout_payload["authenticated"])
        self.assertNotEqual(logout_payload["csrf_token"], csrf_token)

    def test_frontend_app_route_is_accessible_before_login(self):
        response = self.client.get("/app/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn("frontend app", response.get_data(as_text=True))
        response.close()

    def test_root_redirects_to_standalone_login_when_auth_is_required(self):
        response = self.client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/app/login")
        response.close()

    def test_legacy_login_route_redirects_to_standalone_login(self):
        response = self.client.get("/login", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/app/login")
        response.close()


class FrontendApiConfig(TestingConfig):
    SECRET_KEY = "test-secret-key"


class FrontendApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base_dir = self.temp_dir.name

        class LocalFrontendApiConfig(FrontendApiConfig):
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
            FRONTEND_DIST_DIR = f"{base_dir}/frontend_dist"
            SERVE_FRONTEND_BUILD = True

        self.config = LocalFrontendApiConfig
        frontend_dist = Path(LocalFrontendApiConfig.FRONTEND_DIST_DIR)
        (frontend_dist / "assets").mkdir(parents=True, exist_ok=True)
        (frontend_dist / "index.html").write_text("<html><body>frontend shell</body></html>", encoding="utf-8")
        (frontend_dist / "assets" / "app.js").write_text("console.log('frontend');", encoding="utf-8")
        self.app = create_app(LocalFrontendApiConfig)
        self.client = self.app.test_client()
        self.progress_store = get_progress_store(
            storage_root=LocalFrontendApiConfig.PROGRESS_STORAGE_DIR,
            ttl_seconds=LocalFrontendApiConfig.PROGRESS_TTL_SECONDS
        )
        self.job_queue = get_job_queue(LocalFrontendApiConfig.JOB_QUEUE_DB_PATH)
        self.result_store = get_result_store(
            storage_dir=LocalFrontendApiConfig.RESULTS_STORAGE_DIR,
            ttl_seconds=LocalFrontendApiConfig.RESULT_TTL_SECONDS
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _csrf_token(self) -> str:
        response = self.client.get("/api/auth/csrf")
        self.assertEqual(response.status_code, 200)
        return response.get_json()["csrf_token"]

    def test_api_upload_alias_exists(self):
        response = self.client.post(
            "/api/uploads",
            headers={"X-CSRF-Token": self._csrf_token()}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "No file provided")

    def test_api_upload_queues_artifact_source_path_and_closes_upload(self):
        with mock.patch("werkzeug.datastructures.FileStorage.close", autospec=True) as close_mock:
            response = self.client.post(
                "/api/uploads",
                data={
                    "file": (io.BytesIO(b"PK\x03\x04demo docx payload"), "ТЗ 4. - .docx")
                },
                content_type="multipart/form-data",
                headers={"X-CSRF-Token": self._csrf_token()}
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["task_id"])

        job = self.job_queue.get(payload["task_id"])
        self.assertIsNotNone(job)
        self.assertTrue(os.path.isabs(job["payload"]["filepath"]))
        self.assertIn("/analysis_runs/", job["payload"]["filepath"])
        self.assertTrue(job["payload"]["filepath"].endswith("/source/4._-_.docx"))
        self.assertTrue(os.path.isabs(job["payload"]["upload_filepath"]))
        self.assertIn("/uploads/", job["payload"]["upload_filepath"])
        self.assertTrue(os.path.exists(job["payload"]["filepath"]))
        close_mock.assert_called()

    def test_api_progress_alias_streams_existing_events(self):
        tracker = self.progress_store.create("task-1")
        tracker.complete("/results/result-1", "result-1")

        response = self.client.get("/api/tasks/task-1/events")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/event-stream")
        payload = response.get_data(as_text=True)
        self.assertIn("event: complete", payload)
        self.assertIn('"result_id": "result-1"', payload)

    def test_api_results_returns_headless_view_model(self):
        self.result_store.save(
            "result-1",
            {
                "filename": "demo.docx",
                "timestamp": "2026-03-14T10:00:00",
                "result": {
                    "wbs": {
                        "phases": []
                    }
                },
                "usage": {
                    "llm_profile": "default"
                },
                "metadata": {},
                "token_usage": {}
            }
        )

        response = self.client.get("/api/results/result-1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["result_id"], "result-1")
        self.assertEqual(payload["links"]["self"], "/api/results/result-1")
        self.assertEqual(payload["links"]["excel_export"], "/api/results/result-1/export.xlsx")
        self.assertEqual(payload["links"]["frontend_html"], "/app/results/result-1")
        self.assertIn("project_info", payload["result"])
        self.assertEqual(payload["result"]["project_info"]["calculated_duration_days"], 0)
        self.assertEqual(payload["result"]["dependencies_matrix"], [])

    def test_api_results_history_returns_recent_entries(self):
        self.result_store.save(
            "result-1",
            {
                "filename": "first.docx",
                "timestamp": "2026-03-14T10:00:00",
                "result": {
                    "project_info": {
                        "project_name": "First project",
                        "description": "First stored result",
                        "complexity_level": "low"
                    },
                    "wbs": {
                        "phases": []
                    }
                },
                "usage": {},
                "metadata": {},
                "token_usage": {
                    "totals": {
                        "total_tokens": 100
                    },
                    "request_count": 1
                }
            }
        )
        time.sleep(0.01)
        self.result_store.save(
            "result-2",
            {
                "filename": "second.docx",
                "timestamp": "2026-03-14T11:00:00",
                "result": {
                    "project_info": {
                        "project_name": "Second project",
                        "description": "Second stored result",
                        "complexity_level": "medium"
                    },
                    "wbs": {
                        "phases": []
                    }
                },
                "usage": {},
                "metadata": {},
                "token_usage": {
                    "totals": {
                        "total_tokens": 200
                    },
                    "request_count": 2
                }
            }
        )

        response = self.client.get("/api/results")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["scope"], "history")
        self.assertEqual([item["result_id"] for item in payload["items"]], ["result-2", "result-1"])
        self.assertEqual(payload["items"][0]["project_name"], "Second project")
        self.assertEqual(payload["items"][0]["links"]["frontend_html"], "/app/results/result-2")
        self.assertEqual(payload["items"][1]["filename"], "first.docx")

    def test_frontend_app_serves_index_and_assets(self):
        root_response = self.client.get("/app")
        history_response = self.client.get("/app/results")
        route_response = self.client.get("/app/results/result-1")
        asset_response = self.client.get("/app/assets/app.js")

        self.assertEqual(root_response.status_code, 200)
        self.assertIn("frontend shell", root_response.get_data(as_text=True))
        self.assertEqual(history_response.status_code, 200)
        self.assertIn("frontend shell", history_response.get_data(as_text=True))
        self.assertEqual(route_response.status_code, 200)
        self.assertIn("frontend shell", route_response.get_data(as_text=True))
        self.assertEqual(asset_response.status_code, 200)
        self.assertEqual(asset_response.get_data(as_text=True), "console.log('frontend');")
        root_response.close()
        history_response.close()
        route_response.close()
        asset_response.close()

    def test_root_and_legacy_results_redirect_to_standalone_frontend(self):
        root_response = self.client.get("/", follow_redirects=False)
        results_response = self.client.get("/results/result-1", follow_redirects=False)

        self.assertEqual(root_response.status_code, 302)
        self.assertEqual(root_response.headers["Location"], "/app/")
        self.assertEqual(results_response.status_code, 302)
        self.assertEqual(results_response.headers["Location"], "/app/results/result-1")
        root_response.close()
        results_response.close()


if __name__ == "__main__":
    unittest.main()
