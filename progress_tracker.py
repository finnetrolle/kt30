"""
Thread-safe progress tracker for streaming agent activity to the frontend via SSE.
"""
import threading
import time
import queue
import logging
from typing import Optional, Dict, Any
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


class ProgressTracker:
    """Thread-safe progress tracker for a single analysis task.
    
    Stores progress events that can be consumed by an SSE endpoint.
    Each event has a type, message, and optional metadata.
    """
    
    def __init__(self, task_id: str, run_artifacts: Optional[RunArtifacts] = None):
        self.task_id = task_id
        self.run_artifacts = run_artifacts
        self.events: queue.Queue = queue.Queue()
        self.created_at = time.time()
        self._completed = False
        self._error = False
        self._lock = threading.Lock()
        self._current_stage_id = 0
        self._current_stage_message = ""
        self._stage_usage: Dict[int, Dict[str, Any]] = {}
        self._overall_usage = _empty_usage()
        self._request_count = 0
    
    @property
    def is_finished(self) -> bool:
        return self._completed or self._error
    
    def emit(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit a progress event.
        
        Args:
            event_type: Type of event (stage, agent, info, success, error)
            message: Human-readable message
            data: Optional additional data
        """
        event = {
            "type": event_type,
            "message": message,
            "timestamp": time.time(),
            "data": data or {}
        }
        self.events.put(event)
        if self.run_artifacts:
            self.run_artifacts.record_progress_event(event)
        logger.debug(f"[ProgressTracker:{self.task_id}] {event_type}: {message}")

    @property
    def artifacts_dir(self) -> Optional[str]:
        """Return the filesystem path of the current run artifact directory."""
        if not self.run_artifacts:
            return None
        return str(self.run_artifacts.base_dir)

    def record_intermediate(self, stage: str, payload: Any):
        """Persist an intermediate result if artifact storage is available."""
        if self.run_artifacts:
            self.run_artifacts.record_intermediate(stage, payload)

    def record_llm_call(self, payload: Dict[str, Any]):
        """Persist an LLM interaction if artifact storage is available."""
        if self.run_artifacts:
            self.run_artifacts.record_llm_call(payload)

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
        """Get next event, blocking up to timeout seconds.
        
        Args:
            timeout: Max seconds to wait
            
        Returns:
            Event dict or None if timeout
        """
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None


class ProgressTrackerStore:
    """Global store for active progress trackers."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._trackers: Dict[str, ProgressTracker] = {}
                    cls._instance._store_lock = threading.Lock()
        return cls._instance
    
    def create(self, task_id: str, run_artifacts: Optional[RunArtifacts] = None) -> ProgressTracker:
        """Create a new progress tracker for a task."""
        tracker = ProgressTracker(task_id, run_artifacts=run_artifacts)
        with self._store_lock:
            self._trackers[task_id] = tracker
        return tracker
    
    def get(self, task_id: str) -> Optional[ProgressTracker]:
        """Get a progress tracker by task ID."""
        with self._store_lock:
            return self._trackers.get(task_id)
    
    def remove(self, task_id: str):
        """Remove a progress tracker."""
        with self._store_lock:
            self._trackers.pop(task_id, None)
    
    def cleanup(self, max_age_seconds: float = 3600):
        """Remove old trackers."""
        now = time.time()
        with self._store_lock:
            expired = [
                tid for tid, t in self._trackers.items()
                if now - t.created_at > max_age_seconds
            ]
            for tid in expired:
                del self._trackers[tid]


def get_progress_store() -> ProgressTrackerStore:
    """Get the global progress tracker store singleton."""
    return ProgressTrackerStore()
