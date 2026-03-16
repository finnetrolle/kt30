"""
Shared analysis job processing logic for web and worker runtimes.
"""
import logging
import os
import threading
from datetime import datetime
from typing import Dict, Any, Optional

from config import Config
from document_parser import parse_document
from openai_client import analyze_specification
from result_store import ResultStore
from progress_tracker import ProgressTrackerStore
from job_queue import JobQueue
from wbs_utils import canonicalize_wbs_result

logger = logging.getLogger(__name__)


class AnalysisJobCanceled(Exception):
    """Raised when a queued or running analysis job is canceled."""


def _cleanup_uploaded_file(filepath: str, request_id: str):
    """Remove the temporary uploaded file if it still exists."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            logger.info("[%s] Cleaned up uploaded file", request_id)
    except Exception as cleanup_error:
        logger.warning("[%s] Failed to cleanup file: %s", request_id, cleanup_error)


def process_analysis_job(
    job: Dict[str, Any],
    result_store: ResultStore,
    progress_store: ProgressTrackerStore,
    job_queue: JobQueue
) -> None:
    """Process one analysis job end-to-end."""
    task_id = job["task_id"]
    payload = job["payload"]
    filepath = payload["filepath"]
    upload_filepath = payload.get("upload_filepath", filepath)
    filename = payload["filename"]
    unique_id = payload["unique_id"]
    request_id = payload["request_id"]

    tracker = progress_store.get(task_id)
    heartbeat_stop = threading.Event()
    heartbeat_interval_seconds = min(30.0, max(5.0, Config.JOB_STALE_AFTER_SECONDS / 3))

    def ensure_not_canceled():
        job_queue.touch(task_id)
        if job_queue.is_cancel_requested(task_id):
            raise AnalysisJobCanceled("Задача отменена пользователем")

    def keep_job_alive():
        """Refresh the durable lease while long-running analysis is still active."""
        while not heartbeat_stop.wait(heartbeat_interval_seconds):
            try:
                job_queue.touch(task_id)
            except Exception as heartbeat_error:
                logger.warning("[%s] Failed to refresh job heartbeat for %s: %s", request_id, task_id, heartbeat_error)

    heartbeat_thread = threading.Thread(
        target=keep_job_alive,
        name=f"job-heartbeat-{task_id}",
        daemon=True
    )
    heartbeat_thread.start()

    try:
        ensure_not_canceled()
        if tracker:
            tracker.stage("📄 Парсинг документа...")
        logger.info("[%s] Starting document parsing...", request_id)
        document_content = parse_document(filepath)
        text_length = len(document_content["raw_text"])
        sections_count = len(document_content["structure"].get("sections", []))
        tables_count = len(document_content.get("tables", []))
        logger.info("[%s] Document parsed successfully:", request_id)
        logger.info("[%s]   - Text length: %s characters", request_id, text_length)
        logger.info("[%s]   - Sections found: %s", request_id, sections_count)
        logger.info("[%s]   - Tables found: %s", request_id, tables_count)

        if tracker:
            tracker.write_json_artifact("parsed_document.json", document_content)
            tracker.info(
                f"📄 Документ разобран: {text_length} символов, {sections_count} секций, {tables_count} таблиц"
            )

        analysis_text = document_content["raw_text"]
        if document_content["structure"]["sections"]:
            analysis_text += "\n\nОглавление документа:\n"
            for section in document_content["structure"]["sections"]:
                indent = "  " * (section["level"] - 1)
                analysis_text += f"{indent}{section['title']}\n"

        if tracker:
            tracker.write_text_artifact("analysis_input.txt", analysis_text)
            tracker.record_intermediate(
                "document_prepared_for_analysis",
                {
                    "text_length": len(analysis_text),
                    "sections_count": sections_count,
                    "tables_count": tables_count
                }
            )

        ensure_not_canceled()
        if tracker:
            tracker.stage("🤖 Запуск мульти-агентного анализа...")
        logger.info("[%s] Starting OpenAI analysis...", request_id)
        logger.info("[%s]   - API Base: %s", request_id, Config.OPENAI_API_BASE)
        logger.info("[%s]   - Model: %s", request_id, Config.OPENAI_MODEL)

        result = analyze_specification(analysis_text, request_id=request_id, progress_tracker=tracker)
        if not result["success"]:
            logger.error("[%s] OpenAI analysis failed: %s", request_id, result["error"])
            if tracker:
                tracker.write_json_artifact("analysis_error.json", result)
                tracker.error(f"Ошибка анализа: {result['error']}")
            job_queue.mark_failed(task_id, result["error"])
            return

        logger.info("[%s] OpenAI analysis completed successfully", request_id)
        if "usage" in result:
            logger.info("[%s] Token usage: %s", request_id, result["usage"])

        token_usage = result.get("metadata", {}).get("token_usage", {})
        normalized_result = canonicalize_wbs_result(result.get("data", {}))

        result_id = unique_id
        timestamp = datetime.now().isoformat()
        result_store.save(result_id, {
            "filename": filename,
            "timestamp": timestamp,
            "result": normalized_result,
            "usage": result.get("usage", {}),
            "metadata": result.get("metadata", {}),
            "agent_conversation": result.get("agent_conversation", []),
            "token_usage": token_usage,
            "artifacts_dir": tracker.artifacts_dir if tracker else None
        })

        if tracker:
            tracker.write_json_artifact("final_result.json", {
                "filename": filename,
                "timestamp": timestamp,
                "result": normalized_result,
                "usage": result.get("usage", {}),
                "metadata": result.get("metadata", {}),
                "agent_conversation": result.get("agent_conversation", []),
                "token_usage": token_usage,
                "result_id": result_id,
                "artifacts_dir": tracker.artifacts_dir
            })

        frontend_route_prefix = Config.FRONTEND_ROUTE_PREFIX.strip('/') or 'app'
        redirect_url = f"/{frontend_route_prefix}/results/{result_id}"
        if tracker:
            tracker.complete(redirect_url, result_id, {
                "artifacts_dir": tracker.artifacts_dir if tracker else None
            })
        job_queue.mark_succeeded(task_id, result_id=result_id)

    except AnalysisJobCanceled as canceled_error:
        logger.warning("[%s] Job canceled: %s", request_id, canceled_error)
        if tracker:
            tracker.error(str(canceled_error))
        job_queue.mark_canceled(task_id, str(canceled_error))
    except PermissionError as error:
        logger.exception("[%s] Permission error during background processing: %s", request_id, error)
        if tracker:
            tracker.write_json_artifact("background_error.json", {
                "error": str(error),
                "request_id": request_id,
                "analysis_filepath": filepath,
                "upload_filepath": upload_filepath
            })
            tracker.error(
                "Нет доступа к файлу для анализа. "
                f"Источник: {filepath}"
            )
        job_queue.mark_failed(task_id, str(error))
    except Exception as error:
        logger.exception("[%s] Unexpected error during background processing: %s", request_id, error)
        if tracker:
            tracker.write_json_artifact("background_error.json", {
                "error": str(error),
                "request_id": request_id,
                "analysis_filepath": filepath,
                "upload_filepath": upload_filepath
            })
            tracker.error(f"Непредвиденная ошибка: {str(error)}")
        job_queue.mark_failed(task_id, str(error))
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1.0)
        _cleanup_uploaded_file(upload_filepath, request_id)
