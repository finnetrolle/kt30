"""
Thread-safe and filesystem-backed progress tracking for long-running analysis tasks.
"""
import json
import logging
import queue
import shutil
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from run_artifacts import RunArtifacts

logger = logging.getLogger(__name__)


def _empty_usage() -> Dict[str, int]:
    """Create an empty token usage bucket."""
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    }


def _normalize_usage(usage: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Normalize token usage payload to integer counters."""
    usage = usage or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", 0) or 0)

    if total_tokens == 0 and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens
    }


def _merge_usage(target: Dict[str, int], delta: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Add one token usage payload into another."""
    normalized = _normalize_usage(delta)
    target["prompt_tokens"] += normalized["prompt_tokens"]
    target["completion_tokens"] += normalized["completion_tokens"]
    target["total_tokens"] += normalized["total_tokens"]
    return target


def _preview_text(value: Any, limit: int = 280) -> str:
    """Return a compact single-line preview for UI-friendly event payloads."""
    if value is None:
        return ""

    if not isinstance(value, str):
        value = str(value)

    normalized = " ".join(value.strip().split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"


class ProgressTracker:
    """Thread-safe progress tracker for a single analysis task.

    Events are stored both in-memory and on disk so SSE consumers can reconnect
    or land on another Gunicorn worker without losing the task stream.
    """

    META_FILENAME = "task_meta.json"
    EVENTS_FILENAME = "events.ndjson"

    def __init__(
        self,
        task_id: str,
        storage_dir: Optional[Path] = None,
        run_artifacts: Optional[RunArtifacts] = None,
        created_at: Optional[float] = None,
        completed: bool = False,
        error: bool = False,
        current_stage_id: int = 0,
        current_stage_message: str = "",
        stage_usage: Optional[List[Dict[str, Any]]] = None,
        overall_usage: Optional[Dict[str, Any]] = None,
        request_count: int = 0,
        persist_on_init: bool = True
    ):
        self.task_id = task_id
        self.run_artifacts = run_artifacts
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.created_at = created_at or time.time()
        self.events: queue.Queue = queue.Queue()
        self._completed = completed
        self._error = error
        self._lock = threading.Lock()
        self._current_stage_id = int(current_stage_id or 0)
        self._current_stage_message = current_stage_message or ""
        self._stage_usage = self._deserialize_stage_usage(stage_usage)
        self._overall_usage = _normalize_usage(overall_usage)
        self._request_count = int(request_count or 0)

        if self.storage_dir:
            self._ensure_storage_dir()
        if self.storage_dir and persist_on_init:
            self._persist_state()

    @classmethod
    def from_existing(cls, task_id: str, storage_dir: Path) -> "ProgressTracker":
        """Create a tracker from persisted state."""
        meta_path = Path(storage_dir) / cls.META_FILENAME
        created_at = time.time()
        completed = False
        error = False
        current_stage_id = 0
        current_stage_message = ""
        stage_usage: List[Dict[str, Any]] = []
        overall_usage = _empty_usage()
        request_count = 0

        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
                created_at = float(meta.get("created_at", created_at))
                completed = bool(meta.get("completed", False))
                error = bool(meta.get("error", False))
                current_stage_id = int(meta.get("current_stage_id", 0) or 0)
                current_stage_message = str(meta.get("current_stage_message", "") or "")
                stage_usage = meta.get("stage_usage", []) if isinstance(meta.get("stage_usage", []), list) else []
                overall_usage = _normalize_usage(meta.get("overall_usage"))
                request_count = int(meta.get("request_count", 0) or 0)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Failed to read progress metadata for %s: %s", task_id, exc)

        return cls(
            task_id=task_id,
            storage_dir=storage_dir,
            created_at=created_at,
            completed=completed,
            error=error,
            current_stage_id=current_stage_id,
            current_stage_message=current_stage_message,
            stage_usage=stage_usage,
            overall_usage=overall_usage,
            request_count=request_count,
            persist_on_init=False
        )

    def _ensure_storage_dir(self) -> None:
        """Recreate the task directory if it was removed while the job is still active."""
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)

    @property
    def meta_path(self) -> Optional[Path]:
        if not self.storage_dir:
            return None
        return self.storage_dir / self.META_FILENAME

    @property
    def events_path(self) -> Optional[Path]:
        if not self.storage_dir:
            return None
        return self.storage_dir / self.EVENTS_FILENAME

    @property
    def is_finished(self) -> bool:
        return self._completed or self._error

    @property
    def artifacts_dir(self) -> Optional[str]:
        """Return the filesystem path of the current run artifact directory."""
        if self.run_artifacts:
            return str(self.run_artifacts.base_dir)

        state = self.get_persisted_state()
        artifacts_dir = state.get("artifacts_dir")
        return str(artifacts_dir) if artifacts_dir else None

    def _state_payload(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "completed": self._completed,
            "error": self._error,
            "current_stage_id": self._current_stage_id,
            "current_stage_message": self._current_stage_message,
            "stage_usage": self._serialize_stage_usage(),
            "overall_usage": dict(self._overall_usage),
            "request_count": self._request_count,
            "artifacts_dir": self.artifacts_dir,
            "updated_at": time.time()
        }

    def _serialize_stage_usage(self) -> List[Dict[str, Any]]:
        return [
            {
                "stage_id": entry["stage_id"],
                "message": entry["message"],
                "usage": dict(entry["usage"]),
                "request_count": entry["request_count"]
            }
            for _, entry in sorted(self._stage_usage.items())
        ]

    def _deserialize_stage_usage(self, stage_usage: Optional[List[Dict[str, Any]]]) -> Dict[int, Dict[str, Any]]:
        restored: Dict[int, Dict[str, Any]] = {}
        for raw_entry in stage_usage or []:
            if not isinstance(raw_entry, dict):
                continue

            stage_id = int(raw_entry.get("stage_id", 0) or 0)
            if stage_id <= 0:
                continue

            restored[stage_id] = {
                "stage_id": stage_id,
                "message": str(raw_entry.get("message", "") or ""),
                "usage": _normalize_usage(raw_entry.get("usage")),
                "request_count": int(raw_entry.get("request_count", 0) or 0)
            }

        return restored

    def _persist_state(self):
        """Persist task metadata atomically."""
        if not self.meta_path:
            return

        payload = self._state_payload()
        for attempt in range(2):
            self._ensure_storage_dir()
            temp_path = self.meta_path.with_suffix(".tmp")
            try:
                with open(temp_path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                temp_path.replace(self.meta_path)
                return
            except FileNotFoundError:
                if attempt == 1:
                    raise

    def refresh_state(self):
        """Refresh completion flags from persisted state."""
        if not self.meta_path or not self.meta_path.exists():
            return

        try:
            with open(self.meta_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self._completed = bool(payload.get("completed", False))
            self._error = bool(payload.get("error", False))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Failed to refresh progress state for %s: %s", self.task_id, exc)

    def get_persisted_state(self) -> Dict[str, Any]:
        """Read the current persisted task metadata."""
        if not self.meta_path or not self.meta_path.exists():
            return {}

        try:
            with open(self.meta_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load task metadata for %s: %s", self.task_id, exc)
            return {}

    def _append_persisted_event(self, event: Dict[str, Any]):
        """Append an event to the persisted NDJSON stream."""
        if not self.events_path:
            return

        line = json.dumps(event, ensure_ascii=False, default=str)
        for attempt in range(2):
            self._ensure_storage_dir()
            try:
                with open(self.events_path, "a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.write("\n")
                return
            except FileNotFoundError:
                if attempt == 1:
                    raise

    def is_expired(self, max_age_seconds: float, now: Optional[float] = None) -> bool:
        """Return True when a finished tracker has been idle beyond retention."""
        if max_age_seconds <= 0:
            return False

        now = time.time() if now is None else now
        state = self.get_persisted_state()
        completed = bool(state.get("completed", self._completed))
        error = bool(state.get("error", self._error))
        if not (completed or error):
            return False

        updated_at = float(state.get("updated_at", self.created_at) or self.created_at)
        return now - updated_at > max_age_seconds

    def read_events_since(self, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """Read persisted events after the provided byte offset."""
        if not self.events_path or not self.events_path.exists():
            return [], offset

        events: List[Dict[str, Any]] = []
        new_offset = offset

        with open(self.events_path, "r", encoding="utf-8") as handle:
            handle.seek(offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                new_offset = handle.tell()
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping malformed progress event for %s: %s", self.task_id, exc)

        return events, new_offset

    def emit(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit and persist a progress event."""
        event = {
            "type": event_type,
            "message": message,
            "timestamp": time.time(),
            "data": data or {}
        }

        with self._lock:
            self.events.put(event)
            self._append_persisted_event(event)
            self._persist_state()

        if self.run_artifacts:
            self.run_artifacts.record_progress_event(event)

        logger.debug("[ProgressTracker:%s] %s: %s", self.task_id, event_type, message)

    def record_intermediate(self, stage: str, payload: Any):
        """Persist an intermediate result if artifact storage is available."""
        if self.run_artifacts:
            self.run_artifacts.record_intermediate(stage, payload)

    def record_llm_call(self, payload: Dict[str, Any]):
        """Persist an LLM interaction if artifact storage is available."""
        if not self.run_artifacts:
            return

        with self._lock:
            enriched_payload = {
                **payload,
                "stage_id": payload.get("stage_id", self._current_stage_id or None),
                "stage_message": payload.get("stage_message", self._current_stage_message or None),
                "progress_request_count": int(payload.get("progress_request_count", self._request_count or 0))
            }

        self.run_artifacts.record_llm_call(enriched_payload)

    def write_json_artifact(self, relative_path: str, payload: Any):
        """Write a JSON artifact for this run."""
        if self.run_artifacts:
            self.run_artifacts.write_json(relative_path, payload)

    def write_text_artifact(self, relative_path: str, content: str):
        """Write a text artifact for this run."""
        if self.run_artifacts:
            self.run_artifacts.write_text(relative_path, content)

    def stage(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit a stage change event (major step)."""
        with self._lock:
            self._current_stage_id += 1
            self._current_stage_message = message
            stage_entry = {
                "stage_id": self._current_stage_id,
                "message": message,
                "usage": _empty_usage(),
                "request_count": 0
            }
            self._stage_usage[self._current_stage_id] = stage_entry
            stage_data = {
                **(data or {}),
                "stage_id": self._current_stage_id,
                "usage": dict(stage_entry["usage"]),
                "request_count": stage_entry["request_count"],
                "overall_usage": dict(self._overall_usage)
            }
        self.emit("stage", message, stage_data)

    def agent(self, agent_name: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit an agent activity event."""
        self.emit("agent", message, {"agent": agent_name, **(data or {})})

    def info(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit an informational event."""
        self.emit("info", message, data)

    def llm_request(
        self,
        agent_name: str,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """Emit a detailed LLM request event for the live progress feed."""
        extra_data = dict(data or {})
        extra_data.pop("system_prompt", None)
        extra_data.pop("prompt", None)
        payload = {
            "agent": agent_name,
            "model": model,
            "llm_event": "request_started",
            "prompt_preview": _preview_text(prompt, limit=480),
            "prompt_characters": len(prompt or ""),
            "system_prompt_preview": _preview_text(system_prompt, limit=280),
            "system_prompt_characters": len(system_prompt or ""),
            **extra_data
        }
        self.emit("agent", f"📤 {agent_name}: запрос отправлен в {model}", payload)

    def llm_response(
        self,
        agent_name: str,
        model: str,
        response_text: str,
        elapsed_seconds: Optional[float] = None,
        usage: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        """Emit a detailed LLM response event for the live progress feed."""
        duration_suffix = f" за {elapsed_seconds:.1f} сек" if elapsed_seconds is not None else ""
        extra_data = dict(data or {})
        extra_data.pop("response_text", None)
        payload = {
            "agent": agent_name,
            "model": model,
            "llm_event": "response_received",
            "response_preview": _preview_text(response_text, limit=480),
            "response_characters": len(response_text or ""),
            "elapsed_seconds": round(elapsed_seconds, 2) if elapsed_seconds is not None else None,
            "usage": _normalize_usage(usage),
            **extra_data
        }
        self.emit("agent", f"📥 {agent_name}: ответ получен от {model}{duration_suffix}", payload)

    def usage(self, agent_name: str, usage: Dict[str, Any], data: Optional[Dict[str, Any]] = None):
        """Emit token usage for the current stage and aggregate totals."""
        normalized = _normalize_usage(usage)
        with self._lock:
            self._request_count += 1
            _merge_usage(self._overall_usage, normalized)

            stage_id = self._current_stage_id if self._current_stage_id > 0 else None
            stage_message = self._current_stage_message or None
            stage_usage = _empty_usage()
            stage_request_count = 0

            if stage_id and stage_id in self._stage_usage:
                stage_entry = self._stage_usage[stage_id]
                _merge_usage(stage_entry["usage"], normalized)
                stage_entry["request_count"] += 1
                stage_usage = dict(stage_entry["usage"])
                stage_request_count = stage_entry["request_count"]

            event_data = {
                "agent": agent_name,
                "usage": normalized,
                "stage_id": stage_id,
                "stage_message": stage_message,
                "stage_usage": stage_usage,
                "stage_request_count": stage_request_count,
                "overall_usage": dict(self._overall_usage),
                "request_count": self._request_count,
                **(data or {})
            }

        self.emit("usage", f"Токены: {agent_name}", event_data)

    def get_usage_summary(self) -> Dict[str, Any]:
        """Return aggregated token usage for the whole task."""
        with self._lock:
            stages = [
                {
                    "stage_id": entry["stage_id"],
                    "message": entry["message"],
                    "usage": dict(entry["usage"]),
                    "request_count": entry["request_count"]
                }
                for _, entry in sorted(self._stage_usage.items())
            ]
            return {
                "totals": dict(self._overall_usage),
                "request_count": self._request_count,
                "stages": stages
            }

    def complete(self, redirect_url: str, result_id: str, data: Optional[Dict[str, Any]] = None):
        """Emit completion event."""
        self._completed = True
        self.emit("complete", "Анализ завершён", {
            "redirect_url": redirect_url,
            "result_id": result_id,
            "usage_summary": self.get_usage_summary(),
            **(data or {})
        })

    def error(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit error event."""
        self._error = True
        self.emit("error", message, {
            "usage_summary": self.get_usage_summary(),
            **(data or {})
        })

    def get_event(self, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Get the next in-memory event for same-process consumers."""
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None


class ProgressTrackerStore:
    """Global store for active progress trackers with disk persistence."""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, storage_root: str = "progress_data", ttl_seconds: float = 3600):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._trackers = {}
                    cls._instance._store_lock = threading.Lock()
                    cls._instance._cleanup_started = False
        return cls._instance

    def __init__(self, storage_root: str = "progress_data", ttl_seconds: float = 3600):
        storage_root_path = Path(storage_root)
        if getattr(self, "storage_root", None) != storage_root_path:
            self._trackers = {}
        self.storage_root = storage_root_path
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        if self._cleanup_started:
            return

        def cleanup_loop():
            while True:
                time.sleep(max(60, int(self.ttl_seconds // 4) or 60))
                try:
                    self.cleanup()
                except Exception as exc:
                    logger.error("Progress cleanup error: %s", exc)

        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
        self._cleanup_started = True

    def _task_dir(self, task_id: str) -> Path:
        safe_task_id = "".join(ch for ch in str(task_id) if ch.isalnum() or ch in ("-", "_"))
        return self.storage_root / safe_task_id

    def create(self, task_id: str, run_artifacts: Optional[RunArtifacts] = None) -> ProgressTracker:
        """Create a new persisted progress tracker for a task."""
        tracker = ProgressTracker(
            task_id=task_id,
            storage_dir=self._task_dir(task_id),
            run_artifacts=run_artifacts
        )
        with self._store_lock:
            self._trackers[task_id] = tracker
        return tracker

    def get(self, task_id: str) -> Optional[ProgressTracker]:
        """Get a progress tracker by task ID, even across workers."""
        with self._store_lock:
            tracker = self._trackers.get(task_id)
            if tracker is not None:
                return tracker

        task_dir = self._task_dir(task_id)
        if not task_dir.exists():
            return None

        tracker = ProgressTracker.from_existing(task_id, task_dir)
        with self._store_lock:
            self._trackers[task_id] = tracker
        return tracker

    def remove(self, task_id: str):
        """Drop a tracker from the in-memory cache only."""
        with self._store_lock:
            self._trackers.pop(task_id, None)

    def cleanup(self, max_age_seconds: Optional[float] = None):
        """Remove old persisted trackers and stale cache entries."""
        max_age = max_age_seconds if max_age_seconds is not None else self.ttl_seconds
        now = time.time()

        with self._store_lock:
            expired_cache = [
                task_id for task_id, tracker in self._trackers.items()
                if tracker.is_expired(max_age, now)
            ]
            for task_id in expired_cache:
                self._trackers.pop(task_id, None)

        for task_dir in self.storage_root.iterdir():
            if not task_dir.is_dir():
                continue

            tracker = ProgressTracker.from_existing(task_dir.name, task_dir)
            if not tracker.is_expired(max_age, now):
                continue

            try:
                shutil.rmtree(task_dir)
            except OSError as exc:
                logger.warning("Failed to remove progress directory %s: %s", task_dir, exc)


def get_progress_store(storage_root: str = "progress_data", ttl_seconds: float = 3600) -> ProgressTrackerStore:
    """Get the global progress tracker store singleton."""
    return ProgressTrackerStore(storage_root=storage_root, ttl_seconds=ttl_seconds)
