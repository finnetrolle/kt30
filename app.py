"""
Flask backend application for Technical Specification Analyzer.
"""
import copy
import hmac
import os
import json
import logging
import re
import secrets
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, send_file, send_from_directory, session, Response
from werkzeug.utils import secure_filename
from config import Config, get_active_config_class
from excel_export import export_wbs_to_excel, calculate_project_duration_with_parallel, build_dependencies_matrix
from result_store import get_result_store
from progress_tracker import get_progress_store
from run_artifacts import RunArtifacts, cleanup_expired_runs
from wbs_utils import canonicalize_wbs_result, has_legacy_root_phases, recover_wbs_from_artifacts
from job_queue import get_job_queue, JobStatus
from rate_limiter import get_rate_limiter
from job_worker import JobWorker


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def _close_uploaded_file(uploaded_file, request_id: str):
    """Close the upload stream promptly so background workers can reopen the file safely."""
    close = getattr(uploaded_file, 'close', None)
    if not callable(close):
        return

    try:
        close()
    except Exception as close_error:
        logger.warning("[%s] Failed to close uploaded file stream: %s", request_id, close_error)


def _save_uploaded_file(uploaded_file, upload_folder: str, saved_filename: str, request_id: str) -> tuple[str, int]:
    """Persist the upload and return an absolute path plus file size."""
    upload_dir = os.path.abspath(upload_folder)
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.abspath(os.path.join(upload_dir, saved_filename))

    logger.info("[%s] Saving file to: %s", request_id, filepath)
    try:
        uploaded_file.save(filepath)
    finally:
        # Embedded workers can start immediately after enqueueing; close the upload stream first
        # so parsers like python-docx do not hit a locked file on Windows/dev setups.
        _close_uploaded_file(uploaded_file, request_id)

    with open(filepath, 'rb'):
        pass

    file_size = os.path.getsize(filepath)
    logger.info("[%s] File saved successfully. Size: %s bytes", request_id, file_size)
    return filepath, file_size


def create_app(config_class=Config):
    """Create and configure the Flask application.
    
    Args:
        config_class: Configuration class to use
        
    Returns:
        Configured Flask application
    """
    logger.info("Creating Flask application...")

    Config.apply_runtime_overrides(config_class)
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize configuration
    config_class.init_app()
    logger.info("Configuration initialized")

    # File-based result storage with TTL cleanup
    store = get_result_store(
        storage_dir=app.config['RESULTS_STORAGE_DIR'],
        ttl_seconds=app.config['RESULT_TTL_SECONDS']
    )
    progress_store = get_progress_store(
        storage_root=app.config['PROGRESS_STORAGE_DIR'],
        ttl_seconds=app.config['PROGRESS_TTL_SECONDS']
    )
    job_queue = get_job_queue(app.config['JOB_QUEUE_DB_PATH'])
    rate_limiter = get_rate_limiter(app.config['RATE_LIMIT_DB_PATH'])
    cleanup_expired_runs(
        app.config['ARTIFACTS_ROOT'],
        app.config['ARTIFACT_RETENTION_SECONDS']
    )
    auth_password = app.config['APP_AUTH_PASSWORD']
    frontend_route_prefix = app.config['FRONTEND_ROUTE_PREFIX'].strip('/') or 'app'
    frontend_dist_dir = Path(app.config['FRONTEND_DIST_DIR'])
    frontend_index_file = frontend_dist_dir / 'index.html'

    def _normalize_result_payload(result_id: str, result_data: dict) -> dict:
        """Normalize stored result payloads and recover legacy malformed entries."""
        if not result_data:
            return result_data

        raw_result = result_data.get('result', {})
        normalized_result = canonicalize_wbs_result(raw_result)

        if has_legacy_root_phases(raw_result):
            recovered = recover_wbs_from_artifacts(result_data.get('artifacts_dir'))
            if recovered:
                logger.info("Recovered full WBS from artifacts for result ID: %s", result_id)
                normalized_result = recovered
            else:
                logger.warning("Legacy result detected for %s but artifacts recovery failed", result_id)

        if normalized_result != raw_result:
            updated = dict(result_data)
            updated['result'] = normalized_result
            store.save(result_id, updated)
            return updated

        return result_data

    def _request_json() -> dict:
        """Safely return the current request JSON payload."""
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}

    def _request_value(name: str, default=None):
        """Read a request value from JSON first, then form data."""
        payload = _request_json()
        if name in payload:
            return payload.get(name, default)
        return request.form.get(name, default)

    def _get_csrf_token() -> str:
        """Get or create the current session CSRF token."""
        token = session.get('_csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['_csrf_token'] = token
        return token

    def _validate_csrf() -> bool:
        """Validate the CSRF token from a header or form field."""
        expected_token = session.get('_csrf_token')
        provided_token = request.headers.get('X-CSRF-Token') or _request_value('csrf_token')
        return bool(expected_token and provided_token and hmac.compare_digest(expected_token, provided_token))

    def _is_authenticated_session() -> bool:
        """Check whether the current session is authenticated."""
        if not auth_password:
            return True
        return bool(session.get('authenticated'))

    def _set_authenticated_session():
        """Mark the current session as authenticated."""
        session.permanent = True
        session['authenticated'] = True

    def _clear_authenticated_session():
        """Reset all session state."""
        session.clear()

    def _auth_session_payload() -> dict:
        """Build the auth/session payload used by the standalone frontend."""
        return {
            'auth_enabled': bool(auth_password),
            'authenticated': _is_authenticated_session(),
            'csrf_token': _get_csrf_token(),
            'session_ttl_seconds': int(app.permanent_session_lifetime.total_seconds()),
            'frontend_base_path': f"/{frontend_route_prefix}",
            'frontend_build_available': bool(
                app.config['SERVE_FRONTEND_BUILD'] and frontend_index_file.exists()
            )
        }

    def _standalone_frontend_path(relative_path: str = '') -> str:
        """Build an absolute path for the standalone frontend."""
        cleaned = relative_path.strip('/')
        base_path = f"/{frontend_route_prefix}"
        return f"{base_path}/{cleaned}" if cleaned else f"{base_path}/"

    def _frontend_entry_response(relative_path: str = ''):
        """Redirect the user into the standalone frontend or show a build error."""
        _get_csrf_token()
        if _frontend_build_available():
            return redirect(_standalone_frontend_path(relative_path))

        logger.warning("Standalone frontend build is not available in %s", frontend_dist_dir)
        return render_template(
            'error.html',
            error='Standalone frontend build not found. Run npm install && npm run build in frontend/.'
        ), 404

    def _build_result_view_model(result_id: str, result_data: dict) -> dict:
        """Attach computed fields and useful links to a result payload."""
        normalized_payload = _normalize_result_payload(result_id, result_data)
        if not normalized_payload:
            return normalized_payload

        view_model = copy.deepcopy(normalized_payload)
        result = view_model.setdefault('result', {})
        wbs_data = result.get('wbs', {}) if result else {}

        duration_info = calculate_project_duration_with_parallel(wbs_data)
        dependencies_matrix = build_dependencies_matrix(wbs_data)

        project_info = result.setdefault('project_info', {})
        project_info['calculated_duration_days'] = duration_info['total_days']
        project_info['calculated_duration_weeks'] = duration_info['total_weeks']
        result['dependencies_matrix'] = dependencies_matrix
        view_model['execution_trace'] = _build_execution_trace(
            view_model.get('artifacts_dir'),
            view_model.get('token_usage')
        )

        view_model['result_id'] = result_id
        view_model['calculated_duration'] = duration_info
        view_model['links'] = {
            'self': f"/api/results/{result_id}",
            'legacy_html': f"/results/{result_id}",
            'excel_export': f"/api/results/{result_id}/export.xlsx",
            'legacy_excel_export': f"/export/excel/{result_id}",
            'frontend_html': _standalone_frontend_path(f"results/{result_id}")
        }

        return view_model

    def _build_result_history_entry(stored_result: dict) -> dict | None:
        """Build a lightweight summary row for the results history page."""
        result_id = stored_result.get('_result_id')
        if not result_id:
            return None

        view_model = _build_result_view_model(result_id, {
            key: value for key, value in stored_result.items() if not str(key).startswith('_')
        })
        if not view_model:
            return None

        project_info = view_model.get('result', {}).get('project_info', {})
        return {
            'result_id': result_id,
            'stored_at': stored_result.get('_stored_at'),
            'timestamp': view_model.get('timestamp'),
            'filename': view_model.get('filename'),
            'project_name': project_info.get('project_name'),
            'description': project_info.get('description'),
            'complexity_level': project_info.get('complexity_level'),
            'calculated_duration': view_model.get('calculated_duration'),
            'token_usage': view_model.get('token_usage'),
            'links': view_model.get('links')
        }

    def _build_task_view_model(job: dict, include_payload: bool = False) -> dict:
        """Attach operator-focused metadata to a durable job record."""
        payload = job.get('payload') or {}
        tracker = progress_store.get(job['task_id'])
        tracker_state = tracker.get_persisted_state() if tracker else {}
        overall_usage = tracker_state.get('overall_usage') or {}

        view_model = {
            'task_id': job['task_id'],
            'status': job['status'],
            'error': job.get('error'),
            'result_id': job.get('result_id'),
            'worker_id': job.get('worker_id'),
            'cancel_requested': bool(job.get('cancel_requested')),
            'created_at': job.get('created_at'),
            'updated_at': job.get('updated_at'),
            'started_at': job.get('started_at'),
            'finished_at': job.get('finished_at'),
            'filename': payload.get('filename'),
            'file_size': payload.get('file_size'),
            'request_id': payload.get('request_id'),
            'current_stage': tracker_state.get('current_stage_message'),
            'current_stage_id': tracker_state.get('current_stage_id'),
            'request_count': int(tracker_state.get('request_count', 0) or 0),
            'total_tokens': int(overall_usage.get('total_tokens', 0) or 0),
            'artifacts_dir': tracker_state.get('artifacts_dir') or payload.get('artifacts_dir')
        }

        if include_payload:
            view_model['payload'] = payload

        return view_model

    def _coerce_artifacts_dir(artifacts_dir: str | None) -> Path | None:
        """Return a safe artifact directory path only when it exists."""
        if not artifacts_dir:
            return None

        try:
            candidate = Path(artifacts_dir)
            if candidate.is_dir():
                return candidate
        except (OSError, TypeError, ValueError):
            return None

        return None

    def _read_artifact_jsonl(artifacts_dir: str | None, filename: str, limit: int | None = None) -> list[dict]:
        """Read JSONL records from a run artifact file."""
        base_dir = _coerce_artifacts_dir(artifacts_dir)
        if not base_dir:
            return []

        path = base_dir / filename
        if not path.exists():
            return []

        records = []
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            logger.warning("Failed to read artifact log %s: %s", path, exc)
            return []

        if limit is not None and len(records) > limit:
            return records[-limit:]
        return records

    def _extract_message_text(message: object) -> str:
        """Extract human-readable text from a Chat Completions message payload."""
        if isinstance(message, str):
            return message

        if isinstance(message, list):
            parts = []
            for item in message:
                if isinstance(item, dict):
                    if isinstance(item.get('text'), str):
                        parts.append(item['text'])
                    elif item.get('type') == 'text' and isinstance(item.get('content'), str):
                        parts.append(item['content'])
            return "\n".join(parts)

        return ""

    def _truncate_text(value: str, limit: int = 160) -> str:
        """Normalize and truncate free text for UI-safe summaries."""
        cleaned = " ".join(str(value or "").strip().split())
        return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"

    def _extract_named_context(prompt_text: str, block_name: str) -> str | None:
        """Best-effort extract a named object from embedded JSON context."""
        pattern = rf'"{re.escape(block_name)}"\s*:\s*\{{.*?"name"\s*:\s*"([^"]+)"'
        match = re.search(pattern, prompt_text, flags=re.DOTALL)
        if match:
            return _truncate_text(match.group(1), 100)
        return None

    def _summarize_llm_prompt(agent_name: str, prompt_text: str) -> str:
        """Convert a raw prompt into a short description of the request purpose."""
        text = str(prompt_text or "").replace("\r", "\n")
        if not text.strip():
            return f"{agent_name}: LLM-вызов"

        if "Детализируй пакет работ" in text:
            package_name = _extract_named_context(text, "work_package")
            return (
                f"Детализация пакета работ «{package_name}» в задачи"
                if package_name
                else "Детализация пакета работ в задачи"
            )

        if "phase_plan" in text or "каркас WBS" in text or "стандартные фазы" in text:
            return "Формирование каркаса WBS по фазам и пакетам работ"

        if "validate" in agent_name.lower() or "валидатор" in agent_name.lower():
            return "Проверка структуры, оценок и связности WBS"

        if "analyst" in agent_name.lower() or "аналит" in agent_name.lower():
            return "Извлечение требований, рисков и ограничений из документа"

        if "planner" in agent_name.lower() or "планиров" in agent_name.lower():
            return "Построение и уточнение структуры WBS"

        if "stabilizer" in agent_name.lower() or "стабилиз" in agent_name.lower():
            return "Стабилизация и согласование финального варианта WBS"

        cut_markers = ("\n\nКонтекст:", "\nКонтекст:", "\n\nТехническое задание:", "\nТехническое задание:", "\n\nJSON:")
        for marker in cut_markers:
            if marker in text:
                text = text.split(marker, 1)[0]
                break

        for line in text.splitlines():
            cleaned = _truncate_text(line, 140)
            if cleaned and not cleaned.startswith(("{", "[", "\"")):
                return cleaned

        return f"{agent_name}: LLM-вызов"

    def _summarize_llm_call(raw_call: dict, index: int) -> dict:
        """Return a compact LLM call summary safe for the UI."""
        agent_name = str(raw_call.get('agent') or 'LLM')
        prompt_text = ""
        for message in reversed(raw_call.get('messages', []) if isinstance(raw_call.get('messages'), list) else []):
            if isinstance(message, dict) and message.get('role') == 'user':
                prompt_text = _extract_message_text(message.get('content'))
                if prompt_text:
                    break

        usage = raw_call.get('usage') if isinstance(raw_call.get('usage'), dict) else {}
        summary = {
            'index': index,
            'agent': agent_name,
            'description': _summarize_llm_prompt(agent_name, prompt_text),
            'status': raw_call.get('status') or 'unknown',
            'attempt': int(raw_call.get('attempt', 1) or 1),
            'model': raw_call.get('model'),
            'elapsed_seconds': raw_call.get('elapsed_seconds'),
            'usage': {
                'prompt_tokens': int(usage.get('prompt_tokens', 0) or 0),
                'completion_tokens': int(usage.get('completion_tokens', 0) or 0),
                'total_tokens': int(usage.get('total_tokens', 0) or 0)
            },
            'stage_id': raw_call.get('stage_id'),
            'stage_message': raw_call.get('stage_message'),
            'error': _truncate_text(str(raw_call.get('error', '') or ''), 180) if raw_call.get('error') else None,
            'error_type': raw_call.get('error_type')
        }
        return summary

    def _build_execution_trace(artifacts_dir: str | None, token_usage: dict | None) -> dict:
        """Build a compact, UI-friendly execution trace from run artifacts."""
        llm_calls_raw = _read_artifact_jsonl(artifacts_dir, 'llm_calls.ndjson')
        progress_events = _read_artifact_jsonl(artifacts_dir, 'progress_events.ndjson', limit=120)
        token_usage = token_usage if isinstance(token_usage, dict) else {}
        stage_entries = token_usage.get('stages', []) if isinstance(token_usage.get('stages'), list) else []
        stage_map: dict[int, dict] = {}

        for stage in stage_entries:
            if not isinstance(stage, dict):
                continue
            stage_id = int(stage.get('stage_id', 0) or 0)
            if stage_id <= 0:
                continue
            usage = stage.get('usage') if isinstance(stage.get('usage'), dict) else {}
            stage_map[stage_id] = {
                'stage_id': stage_id,
                'message': stage.get('message') or f'Этап {stage_id}',
                'usage': {
                    'prompt_tokens': int(usage.get('prompt_tokens', 0) or 0),
                    'completion_tokens': int(usage.get('completion_tokens', 0) or 0),
                    'total_tokens': int(usage.get('total_tokens', 0) or 0)
                },
                'request_count': int(stage.get('request_count', 0) or 0),
                'llm_calls': []
            }

        uncategorized_calls = []
        for index, raw_call in enumerate(llm_calls_raw, start=1):
            if not isinstance(raw_call, dict):
                continue
            call_summary = _summarize_llm_call(raw_call, index)
            stage_id = int(call_summary.get('stage_id', 0) or 0)
            if stage_id > 0:
                stage_bucket = stage_map.setdefault(
                    stage_id,
                    {
                        'stage_id': stage_id,
                        'message': call_summary.get('stage_message') or f'Этап {stage_id}',
                        'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                        'request_count': 0,
                        'llm_calls': []
                    }
                )
                stage_bucket['llm_calls'].append(call_summary)
            else:
                uncategorized_calls.append(call_summary)

        recent_events = [
            {
                'type': event.get('type'),
                'message': event.get('message'),
                'timestamp': event.get('timestamp')
            }
            for event in progress_events
            if isinstance(event, dict)
        ]

        stages = [stage_map[key] for key in sorted(stage_map)]
        return {
            'available': bool(stages or uncategorized_calls or recent_events),
            'artifacts_dir': artifacts_dir,
            'llm_call_count': len(llm_calls_raw),
            'error_count': sum(1 for call in llm_calls_raw if isinstance(call, dict) and call.get('status') == 'error'),
            'progress_event_count': len(progress_events),
            'stages': stages,
            'uncategorized_calls': uncategorized_calls,
            'recent_events': recent_events[-20:]
        }

    def _build_progress_snapshot(task_id: str, job: dict | None = None) -> dict | None:
        """Return a durable progress snapshot for polling and page reload recovery."""
        tracker = progress_store.get(task_id)
        if not tracker:
            return None

        tracker_state = tracker.get_persisted_state()
        events, _offset = tracker.read_events_since(0)
        overall_usage = tracker_state.get('overall_usage') if isinstance(tracker_state.get('overall_usage'), dict) else {}
        worker_health = job_queue.get_worker_health(app.config['JOB_STALE_AFTER_SECONDS'])
        worker_available = app.config['EMBEDDED_WORKER_ENABLED'] or worker_health['healthy_workers'] > 0

        return {
            'task_id': task_id,
            'status': job.get('status') if job else None,
            'current_stage': tracker_state.get('current_stage_message'),
            'current_stage_id': tracker_state.get('current_stage_id'),
            'request_count': int(tracker_state.get('request_count', 0) or 0),
            'overall_usage': {
                'prompt_tokens': int(overall_usage.get('prompt_tokens', 0) or 0),
                'completion_tokens': int(overall_usage.get('completion_tokens', 0) or 0),
                'total_tokens': int(overall_usage.get('total_tokens', 0) or 0)
            },
            'stage_usage': tracker_state.get('stage_usage', []),
            'events': events[-120:],
            'completed': bool(tracker_state.get('completed', False)),
            'error': bool(tracker_state.get('error', False)),
            'artifacts_dir': tracker_state.get('artifacts_dir'),
            'worker_available': bool(worker_available),
            'worker_health': worker_health
        }

    def _build_compact_progress_snapshot(snapshot: dict, event_limit: int = 12) -> dict:
        """Return a lighter snapshot variant for browser-compatibility mode."""
        compact_events = []
        worker_health = snapshot.get('worker_health') if isinstance(snapshot.get('worker_health'), dict) else {}
        allowed_keys = {
            'agent',
            'model',
            'worker_id',
            'attempt',
            'elapsed_seconds',
            'queue_wait_seconds',
            'retry_in_seconds',
            'request_id',
            'max_tokens',
            'temperature',
            'llm_event'
        }
        for event in snapshot.get('events', [])[-event_limit:]:
            if not isinstance(event, dict):
                continue

            data = event.get('data') if isinstance(event.get('data'), dict) else {}
            compact_data = {key: data[key] for key in allowed_keys if key in data}

            if isinstance(data.get('usage'), dict):
                usage = data['usage']
                compact_data['usage'] = {
                    'prompt_tokens': int(usage.get('prompt_tokens', 0) or 0),
                    'completion_tokens': int(usage.get('completion_tokens', 0) or 0),
                    'total_tokens': int(usage.get('total_tokens', 0) or 0)
                }

            if isinstance(data.get('worker_health'), dict):
                worker_health = data['worker_health']
                compact_data['worker_health'] = {
                    'healthy_workers': int(worker_health.get('healthy_workers', 0) or 0),
                    'known_workers': int(worker_health.get('known_workers', 0) or 0)
                }

            compact_events.append({
                'type': event.get('type'),
                'message': event.get('message'),
                'timestamp': event.get('timestamp'),
                'data': compact_data
            })

        return {
            **snapshot,
            'events': compact_events,
            'stage_usage': [],
            'worker_health': {
                'healthy_workers': int(worker_health.get('healthy_workers', 0) or 0),
                'known_workers': int(worker_health.get('known_workers', 0) or 0)
            }
        }

    def _frontend_build_available() -> bool:
        """Return whether the built standalone frontend is available for serving."""
        return bool(app.config['SERVE_FRONTEND_BUILD'] and frontend_index_file.exists())

    def _has_valid_file_signature(uploaded_file) -> bool:
        """Validate the uploaded file signature against the claimed extension."""
        extension = uploaded_file.filename.rsplit('.', 1)[1].lower()
        header = uploaded_file.stream.read(8)
        uploaded_file.stream.seek(0)

        if extension == 'pdf':
            return header.startswith(b'%PDF-')

        if extension == 'docx':
            return header.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'))

        return False

    @app.context_processor
    def inject_template_globals():
        """Expose security-related values to templates."""
        return {
            'csrf_token': _get_csrf_token()
        }

    @app.before_request
    def protect_csrf():
        """Protect unsafe requests against CSRF."""
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None

        if request.endpoint in ('health', 'ready', 'static'):
            return None

        if not _validate_csrf():
            logger.warning("CSRF validation failed for endpoint %s", request.endpoint)
            return jsonify({'error': 'CSRF validation failed', 'status': 400}), 400

        return None

    @app.after_request
    def add_security_headers(response):
        """Attach a basic hardening header set to every response."""
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
        )
        if app.config['ENV_NAME'] == 'production' and request.is_secure:
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response

    rate_limit_rules = {
        'login': (5, 60),
        'api_login': (5, 60),
        'upload_file': (10, 60),
        'progress_stream': (120, 60),
        'cancel_task': (20, 60)
    }

    @app.before_request
    def enforce_rate_limits():
        """Rate limit sensitive endpoints across workers."""
        rule = rate_limit_rules.get(request.endpoint)
        if not rule:
            return None

        remote_addr = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
        rate_key = remote_addr.split(',')[0].strip()
        limit, window = rule
        result = rate_limiter.check(request.endpoint, rate_key, limit, window)

        if not result["allowed"]:
            response = jsonify({'error': 'Rate limit exceeded', 'status': 429})
            response.status_code = 429
            response.headers['Retry-After'] = str(max(1, result["reset_at"] - int(time.time())))
            return response

        return None

    # Optional authentication middleware
    if auth_password:
        logger.info("Authentication is ENABLED (APP_AUTH_PASSWORD is set)")
        
        @app.before_request
        def check_auth():
            """Check authentication for all routes except health and login."""
            if request.method == 'OPTIONS':
                return None

            # Skip auth for health check and static files
            if request.endpoint in (
                'health',
                'ready',
                'login',
                'static',
                'frontend_app',
                'api_auth_session',
                'api_auth_csrf',
                'api_login',
                'api_logout'
            ):
                return None
            
            if not _is_authenticated_session():
                if request.endpoint == 'index':
                    return redirect(_standalone_frontend_path('login'))
                if request.endpoint == 'results':
                    return redirect(_standalone_frontend_path('login'))
                return jsonify({'error': 'Authentication required', 'status': 401}), 401
        
        @app.route('/login', methods=['GET', 'POST'])
        def login():
            """Compatibility route that forwards users into the standalone frontend."""
            if request.method == 'GET':
                return _frontend_entry_response('login')

            password = _request_value('password', '')
            if hmac.compare_digest(password, auth_password):
                _set_authenticated_session()
                logger.info("User authenticated successfully")
                return redirect(_standalone_frontend_path())
            else:
                logger.warning("Failed authentication attempt")
                return redirect(f"{_standalone_frontend_path('login')}?legacyError=invalid-password")

        @app.route('/logout', methods=['POST'])
        def logout():
            """Clear the current authenticated session."""
            _clear_authenticated_session()
            logger.info("User logged out")
            return redirect(_standalone_frontend_path('login'))
    else:
        logger.info("Authentication is DISABLED (APP_AUTH_PASSWORD not set)")

    @app.route('/api/auth/session', methods=['GET'])
    def api_auth_session():
        """Return the current auth/session state for the standalone frontend."""
        return jsonify(_auth_session_payload())

    @app.route('/api/auth/csrf', methods=['GET'])
    def api_auth_csrf():
        """Return a CSRF token and ensure a session exists."""
        return jsonify({'csrf_token': _get_csrf_token()})

    @app.route('/api/auth/login', methods=['POST'])
    def api_login():
        """Authenticate the current session for API clients."""
        if not auth_password:
            return jsonify({'success': True, **_auth_session_payload()})

        password = _request_value('password', '')
        if hmac.compare_digest(password, auth_password):
            _set_authenticated_session()
            logger.info("API user authenticated successfully")
            return jsonify({'success': True, **_auth_session_payload()})

        logger.warning("Failed API authentication attempt")
        return jsonify({'error': 'Неверный пароль', 'status': 401}), 401

    @app.route('/api/auth/logout', methods=['POST'])
    def api_logout():
        """Clear the current authenticated session for API clients."""
        _clear_authenticated_session()
        logger.info("API user logged out")
        return jsonify({'success': True, **_auth_session_payload()})
    
    @app.route('/')
    def index():
        """Redirect the primary entry point into the standalone frontend."""
        logger.info("Redirecting root request into standalone frontend")
        return _frontend_entry_response()

    @app.route(f'/{frontend_route_prefix}')
    @app.route(f'/{frontend_route_prefix}/')
    @app.route(f'/{frontend_route_prefix}/<path:asset_path>')
    def frontend_app(asset_path: str = ''):
        """Serve the built standalone frontend with SPA fallback."""
        if not _frontend_build_available():
            return _frontend_entry_response()

        requested_path = asset_path.strip('/')
        if requested_path and '.' in Path(requested_path).name:
            candidate = frontend_dist_dir / requested_path
            if candidate.exists() and candidate.is_file():
                return send_from_directory(frontend_dist_dir, requested_path, conditional=True)

        return send_from_directory(frontend_dist_dir, 'index.html', conditional=True)
    
    @app.route('/api/uploads', methods=['POST'])
    @app.route('/upload', methods=['POST'])
    def upload_file():
        """Handle file upload — starts background processing and returns task_id."""
        request_id = str(uuid.uuid4())[:8]
        logger.info(f"[{request_id}] Starting file upload process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            logger.warning(f"[{request_id}] No file provided in request")
            return jsonify({'error': 'No file provided', 'status': 400}), 400
        
        file = request.files['file']
        logger.info(f"[{request_id}] Received file: {file.filename}")
        
        # Check if file was selected
        if file.filename == '':
            logger.warning(f"[{request_id}] No file selected")
            return jsonify({'error': 'No file selected', 'status': 400}), 400
        
        # Check file extension
        if not config_class.allowed_file(file.filename):
            logger.warning(f"[{request_id}] Invalid file type: {file.filename}")
            return jsonify({'error': 'Invalid file type. Please upload a .docx or .pdf file', 'status': 400}), 400

        if not _has_valid_file_signature(file):
            logger.warning(f"[{request_id}] File signature mismatch: {file.filename}")
            return jsonify({'error': 'File content does not match the selected extension', 'status': 400}), 400
        
        try:
            # Generate unique filename
            filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            task_id = str(uuid.uuid4())[:12]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            saved_filename = f"{timestamp}_{unique_id}_{filename}"
            filepath, file_size = _save_uploaded_file(
                file,
                app.config['UPLOAD_FOLDER'],
                saved_filename,
                request_id
            )
            
            artifacts = RunArtifacts.create_for_upload(
                app.config['ARTIFACTS_ROOT'],
                unique_id,
                filename,
                filepath,
                metadata={
                    "task_id": task_id,
                    "request_id": request_id,
                    "saved_upload_path": filepath,
                    "saved_filename": saved_filename,
                    "file_size": file_size
                }
            )
            analysis_filepath = artifacts.source_copy_path or filepath

            # Create progress tracker
            tracker = progress_store.create(task_id, run_artifacts=artifacts)
            tracker.info(f"📁 Файл «{filename}» загружен ({file_size} байт)")
            tracker.record_intermediate(
                "upload_saved",
                {
                    "filename": filename,
                    "saved_filename": saved_filename,
                    "file_size": file_size,
                    "request_id": request_id,
                    "task_id": task_id,
                    "saved_upload_path": filepath,
                    "analysis_source_path": analysis_filepath,
                    "artifacts_dir": tracker.artifacts_dir
                }
            )

            tracker.stage("⏳ Задача поставлена в очередь")
            worker_health = job_queue.get_worker_health(app.config['JOB_STALE_AFTER_SECONDS'])
            tracker.info(
                "⏳ Анализ будет запущен worker-процессом",
                {
                    "request_id": request_id,
                    "filename": filename,
                    "file_size": file_size,
                    "worker_health": worker_health,
                    "worker_available": bool(
                        app.config['EMBEDDED_WORKER_ENABLED'] or worker_health['healthy_workers'] > 0
                    )
                }
            )
            job_queue.enqueue(task_id, {
                "task_id": task_id,
                "filepath": analysis_filepath,
                "upload_filepath": filepath,
                "filename": filename,
                "file_size": file_size,
                "unique_id": unique_id,
                "request_id": request_id,
                "artifacts_dir": tracker.artifacts_dir
            })

            logger.info(f"[{request_id}] Job queued successfully, task_id: {task_id}")
            
            # Return task_id for SSE subscription
            return jsonify({
                'success': True,
                'task_id': task_id
            })
            
        except Exception as e:
            logger.exception(f"[{request_id}] Unexpected error during upload: {str(e)}")
            if 'filepath' in locals() and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            return jsonify({'error': str(e), 'status': 500}), 500
    
    @app.route('/api/tasks/<task_id>/events')
    @app.route('/progress/<task_id>')
    def progress_stream(task_id):
        """SSE endpoint for streaming progress events.
        
        Args:
            task_id: Task ID to stream progress for
        """
        tracker = progress_store.get(task_id)
        if not tracker:
            return jsonify({'error': 'Task not found', 'status': 404}), 404
        
        def generate():
            """Generate SSE events from the persisted progress log."""
            offset = 0
            last_keepalive = 0.0

            while True:
                events, offset = tracker.read_events_since(offset)

                if events:
                    for event in events:
                        event_data = json.dumps(event, ensure_ascii=False)
                        yield f"event: {event['type']}\ndata: {event_data}\n\n"

                        if event['type'] in ('complete', 'error'):
                            progress_store.remove(task_id)
                            return

                    continue

                tracker.refresh_state()
                now = time.time()
                if now - last_keepalive >= 15:
                    yield ": keepalive\n\n"
                    last_keepalive = now

                time.sleep(0.5)
        
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )

    @app.route('/api/tasks/<task_id>')
    def task_status(task_id):
        """Return the durable status of a queued or running task."""
        job = job_queue.get(task_id)
        if not job:
            return jsonify({'error': 'Task not found', 'status': 404}), 404
        return jsonify(_build_task_view_model(job, include_payload=True))

    @app.route('/api/tasks/<task_id>/progress')
    def task_progress_snapshot(task_id):
        """Return persisted task events and token stats for polling clients."""
        job = job_queue.get(task_id)
        tracker = progress_store.get(task_id)
        if not job and not tracker:
            return jsonify({'error': 'Task not found', 'status': 404}), 404

        snapshot = _build_progress_snapshot(task_id, job=job or {})
        if not snapshot:
            return jsonify({'error': 'Task not found', 'status': 404}), 404
        compact_mode = request.args.get('compact', '').strip().lower() in ('1', 'true', 'yes')
        if compact_mode:
            snapshot = _build_compact_progress_snapshot(snapshot)
        return jsonify(snapshot)

    @app.route('/api/tasks')
    def list_active_tasks():
        """Return all active background jobs for the operator dashboard."""
        jobs = job_queue.list_jobs(
            statuses=[JobStatus.QUEUED, JobStatus.RUNNING],
            limit=200
        )
        items = [_build_task_view_model(job) for job in jobs]
        recent_results = []

        for job in job_queue.list_jobs(statuses=[JobStatus.SUCCEEDED], limit=20):
            result_id = job.get('result_id')
            if not result_id or not store.get(result_id):
                continue
            recent_results.append(_build_task_view_model(job))

        return jsonify({
            'scope': 'active',
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'counts': {
                'total': len(items),
                'queued': sum(1 for item in items if item['status'] == JobStatus.QUEUED),
                'running': sum(1 for item in items if item['status'] == JobStatus.RUNNING),
                'cancel_requested': sum(1 for item in items if item['cancel_requested'])
            },
            'items': items,
            'recent_results': recent_results
        })

    @app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
    def cancel_task(task_id):
        """Request cancellation for a queued or running task."""
        job = job_queue.request_cancel(task_id)
        if not job:
            return jsonify({'error': 'Task not found', 'status': 404}), 404

        if job['status'] == JobStatus.CANCELED:
            tracker = progress_store.get(task_id)
            if tracker:
                tracker.error("Задача отменена пользователем")
            return jsonify({'success': True, 'status': JobStatus.CANCELED})

        if job['status'] == JobStatus.RUNNING:
            return jsonify({'success': True, 'status': 'cancel_requested'}), 202

        return jsonify({'success': True, 'status': job['status']})
    
    @app.route('/results/<result_id>')
    def results(result_id):
        """Compatibility route that forwards result links into the standalone frontend."""
        logger.info("Redirecting legacy results page for ID %s into standalone frontend", result_id)
        return _frontend_entry_response(f"results/{result_id}")
    
    @app.route('/api/results/<result_id>')
    def api_results(result_id):
        """API endpoint to get results as JSON."""
        logger.info(f"API request for results ID: {result_id}")
        result_data = _build_result_view_model(result_id, store.get(result_id))
        
        if not result_data:
            logger.warning(f"API: Result not found for ID: {result_id}")
            return jsonify({'error': 'Result not found', 'status': 404}), 404
        
        return jsonify(result_data)

    @app.route('/api/results')
    def api_results_history():
        """Return recent stored results for the standalone frontend history page."""
        entries = []
        for stored_result in store.list_recent(limit=50):
            entry = _build_result_history_entry(stored_result)
            if entry:
                entries.append(entry)

        return jsonify({
            'scope': 'history',
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'items': entries
        })
    
    @app.route('/api/results/<result_id>/export.xlsx')
    @app.route('/export/excel/<result_id>')
    def export_excel(result_id):
        """Export WBS results as Excel file."""
        logger.info(f"Excel export request for results ID: {result_id}")
        result_data = _normalize_result_payload(result_id, store.get(result_id))
        
        if not result_data:
            logger.warning(f"Excel export: Result not found for ID: {result_id}")
            return jsonify({'error': 'Result not found', 'status': 404}), 404
        
        try:
            excel_file, filename = export_wbs_to_excel(result_data['result'])
            logger.info(f"Excel export successful for ID: {result_id}")
            
            return send_file(
                excel_file,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )
        except Exception as e:
            logger.exception(f"Excel export failed for ID: {result_id}: {str(e)}")
            return jsonify({'error': f'Failed to generate Excel: {str(e)}', 'status': 500}), 500
    
    @app.route('/health')
    def health():
        """Health check endpoint."""
        worker_health = job_queue.get_worker_health(app.config['JOB_STALE_AFTER_SECONDS'])
        return jsonify({
            'status': 'healthy',
            'environment': app.config['ENV_NAME'],
            'auth_enabled': bool(app.config['APP_AUTH_PASSWORD']),
            'workers': worker_health
        })

    @app.route('/ready')
    def ready():
        """Readiness endpoint with basic dependency checks."""
        required_dirs = {
            'runtime': app.config['RUNTIME_DIR'],
            'uploads': app.config['UPLOAD_FOLDER'],
            'artifacts': app.config['ARTIFACTS_ROOT'],
            'progress': app.config['PROGRESS_STORAGE_DIR'],
            'results': app.config['RESULTS_STORAGE_DIR']
        }
        checks = {
            name: os.path.isdir(path)
            for name, path in required_dirs.items()
        }
        checks['job_queue_db'] = os.path.exists(app.config['JOB_QUEUE_DB_PATH'])
        checks['rate_limit_db'] = os.path.exists(app.config['RATE_LIMIT_DB_PATH'])
        worker_health = job_queue.get_worker_health(app.config['JOB_STALE_AFTER_SECONDS'])
        checks['worker_available'] = (
            app.config['EMBEDDED_WORKER_ENABLED'] or worker_health['healthy_workers'] > 0
        )
        status_code = 200 if all(checks.values()) else 503
        return jsonify({
            'status': 'ready' if status_code == 200 else 'degraded',
            'checks': checks,
            'workers': worker_health
        }), status_code
    
    @app.errorhandler(413)
    def too_large(e):
        """Handle file too large error."""
        logger.warning(f"File too large error: {e}")
        return jsonify({'error': 'File is too large. Maximum size is 16MB', 'status': 413}), 413

    @app.errorhandler(500)
    def server_error(e):
        """Handle server error."""
        logger.error(f"Server error: {e}")
        return jsonify({'error': 'Internal server error', 'status': 500}), 500

    if app.config['EMBEDDED_WORKER_ENABLED'] and not app.config.get('TESTING', False):
        embedded_worker = JobWorker(worker_id=f"embedded-{os.getpid()}-{uuid.uuid4().hex[:6]}")
        embedded_worker.start_in_background()
        app.extensions['embedded_worker'] = embedded_worker
        logger.info("Embedded job worker started")
    
    logger.info("Flask application created successfully")
    return app


# Create application instance
app = create_app(get_active_config_class())


if __name__ == '__main__':
    logger.info("Starting development server on http://0.0.0.0:8000")
    app.run(debug=True, host='0.0.0.0', port=8000)
