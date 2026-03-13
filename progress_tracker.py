"""
Thread-safe progress tracker for streaming agent activity to the frontend via SSE.
"""
import threading
import time
import queue
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Thread-safe progress tracker for a single analysis task.
    
    Stores progress events that can be consumed by an SSE endpoint.
    Each event has a type, message, and optional metadata.
    """
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.events: queue.Queue = queue.Queue()
        self.created_at = time.time()
        self._completed = False
        self._error = False
    
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
        logger.debug(f"[ProgressTracker:{self.task_id}] {event_type}: {message}")
    
    def stage(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit a stage change event (major step)."""
        self.emit("stage", message, data)
    
    def agent(self, agent_name: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit an agent activity event."""
        self.emit("agent", message, {"agent": agent_name, **(data or {})})
    
    def info(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Emit an informational event."""
        self.emit("info", message, data)
    
    def complete(self, redirect_url: str, result_id: str):
        """Emit completion event."""
        self._completed = True
        self.emit("complete", "Анализ завершён", {
            "redirect_url": redirect_url,
            "result_id": result_id
        })
    
    def error(self, message: str):
        """Emit error event."""
        self._error = True
        self.emit("error", message)
    
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
    
    def create(self, task_id: str) -> ProgressTracker:
        """Create a new progress tracker for a task."""
        tracker = ProgressTracker(task_id)
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
