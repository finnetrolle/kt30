"""
Per-run artifact storage for uploaded files, logs, and intermediate results.
"""
import json
import logging
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _timestamp_utc() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _safe_component(value: str, fallback: str = "file") -> str:
    """Sanitize a path component for filesystem use."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._")
    return cleaned or fallback


class RunArtifacts:
    """Filesystem-backed artifact store for a single uploaded file run."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @classmethod
    def create_for_upload(
        cls,
        root_dir: str,
        run_id: str,
        original_filename: str,
        source_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "RunArtifacts":
        """Create a run directory and copy the uploaded file into it."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_name = Path(original_filename or source_path).name
        safe_stem = _safe_component(Path(source_name).stem, fallback="upload")
        base_dir = Path(root_dir) / f"{timestamp}_{run_id}_{safe_stem}"
        instance = cls(base_dir)
        copied_source = instance.copy_source_file(source_path, source_name)
        instance.write_json(
            "run_meta.json",
            {
                "run_id": run_id,
                "original_filename": original_filename,
                "created_at": _timestamp_utc(),
                "source_copy": copied_source,
                **(metadata or {})
            }
        )
        return instance

    def _resolve_path(self, relative_path: str) -> Path:
        """Resolve and prepare a path inside the artifact directory."""
        path = self.base_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _atomic_write(self, path: Path, content: str):
        """Write a file atomically."""
        temp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_path, path)

    def copy_source_file(self, source_path: str, filename: Optional[str] = None) -> str:
        """Copy the uploaded source file into the run directory."""
        source_name = Path(filename or source_path).name
        safe_name = _safe_component(source_name, fallback="source")
        target = self._resolve_path(f"source/{safe_name}")
        with self._lock:
            shutil.copy2(source_path, target)
        logger.info("Copied uploaded file into run directory: %s", target)
        return str(target.relative_to(self.base_dir))

    def write_json(self, relative_path: str, payload: Any):
        """Write JSON into a file inside the run directory."""
        path = self._resolve_path(relative_path)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        with self._lock:
            self._atomic_write(path, serialized)

    def write_text(self, relative_path: str, content: str):
        """Write plain text into a file inside the run directory."""
        path = self._resolve_path(relative_path)
        with self._lock:
            self._atomic_write(path, content)

    def append_jsonl(self, relative_path: str, payload: Dict[str, Any]):
        """Append one JSON record as a line."""
        path = self._resolve_path(relative_path)
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")

    def record_progress_event(self, event: Dict[str, Any]):
        """Append a progress event to the run logs."""
        self.append_jsonl(
            "progress_events.ndjson",
            {
                "logged_at": _timestamp_utc(),
                **event
            }
        )

    def record_llm_call(self, payload: Dict[str, Any]):
        """Append an LLM interaction to the run logs."""
        self.append_jsonl(
            "llm_calls.ndjson",
            {
                "logged_at": _timestamp_utc(),
                **payload
            }
        )

    def record_intermediate(self, stage: str, payload: Any):
        """Append an intermediate result snapshot to the run logs."""
        self.append_jsonl(
            "intermediate_results.ndjson",
            {
                "logged_at": _timestamp_utc(),
                "stage": stage,
                "payload": payload
            }
        )


def cleanup_expired_runs(root_dir: str, retention_seconds: int) -> int:
    """Remove run artifact directories older than the retention window."""
    if retention_seconds <= 0:
        return 0

    root_path = Path(root_dir)
    if not root_path.exists():
        return 0

    removed = 0
    cutoff = datetime.now(timezone.utc).timestamp() - retention_seconds

    for child in root_path.iterdir():
        if not child.is_dir():
            continue

        try:
            mtime = child.stat().st_mtime
        except OSError as exc:
            logger.warning("Could not stat artifact directory %s: %s", child, exc)
            continue

        if mtime >= cutoff:
            continue

        try:
            shutil.rmtree(child)
            removed += 1
        except OSError as exc:
            logger.warning("Could not remove artifact directory %s: %s", child, exc)

    if removed:
        logger.info("Removed %s expired artifact directories from %s", removed, root_path)

    return removed
