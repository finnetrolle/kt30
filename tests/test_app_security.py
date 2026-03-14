import tempfile
import unittest
import types
import sys

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


class SecurityTestConfig(TestingConfig):
    SECRET_KEY = "test-secret-key"
    APP_AUTH_PASSWORD = "topsecret"


class AppSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base_dir = self.temp_dir.name

        class LocalSecurityConfig(SecurityTestConfig):
            UPLOAD_FOLDER = f"{base_dir}/uploads"
            ARTIFACTS_ROOT = f"{base_dir}/analysis_runs"
            RESULTS_STORAGE_DIR = f"{base_dir}/results_data"
            PROGRESS_STORAGE_DIR = f"{base_dir}/progress_data"
            RESULT_TTL_SECONDS = 60
            PROGRESS_TTL_SECONDS = 60
            ARTIFACT_RETENTION_SECONDS = 60

        self.app = create_app(LocalSecurityConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_login_requires_csrf(self):
        response = self.client.post("/login", data={"password": "topsecret"})
        self.assertEqual(response.status_code, 400)

    def test_login_succeeds_with_valid_csrf(self):
        self.client.get("/")

        with self.client.session_transaction() as sess:
            csrf_token = sess["_csrf_token"]

        response = self.client.post(
            "/login",
            data={
                "password": "topsecret",
                "csrf_token": csrf_token
            }
        )

        self.assertEqual(response.status_code, 302)

    def test_production_config_rejects_default_secret(self):
        class BrokenProductionConfig(TestingConfig):
            ENV_NAME = "production"
            DEBUG = False
            SECRET_KEY = "dev-secret-key-change-in-production"

        with self.assertRaises(RuntimeError):
            BrokenProductionConfig.init_app()


if __name__ == "__main__":
    unittest.main()
