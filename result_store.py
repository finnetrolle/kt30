"""
File-based result storage with TTL cleanup.
Replaces in-memory dictionary to support multi-worker deployments and persistence.
"""
import os
import json
import time
import logging
import threading
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Default TTL: 24 hours
DEFAULT_TTL_SECONDS = 24 * 60 * 60
# Cleanup interval: every 30 minutes
CLEANUP_INTERVAL_SECONDS = 30 * 60


class ResultStore:
    """File-based storage for analysis results with automatic TTL cleanup.
    
    Each result is stored as a separate JSON file in the results directory.
    This supports multi-worker deployments (Gunicorn) and survives restarts.
    """
    
    def __init__(self, storage_dir: str = "results_data", ttl_seconds: int = DEFAULT_TTL_SECONDS):
        """Initialize the result store.
        
        Args:
            storage_dir: Directory to store result files
            ttl_seconds: Time-to-live for results in seconds
        """
        self.storage_dir = Path(storage_dir)
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._ensure_storage_dir()
        self._start_cleanup_thread()
        logger.info(f"ResultStore initialized: dir={storage_dir}, ttl={ttl_seconds}s")
    
    def _ensure_storage_dir(self):
        """Create storage directory if it doesn't exist."""
        if not self.storage_dir.exists():
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created results storage directory: {self.storage_dir}")
    
    def _start_cleanup_thread(self):
        """Start background thread for periodic cleanup of expired results."""
        def cleanup_loop():
            while True:
                time.sleep(CLEANUP_INTERVAL_SECONDS)
                try:
                    self.cleanup_expired()
                except Exception as e:
                    logger.error(f"Error during cleanup: {e}")
        
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
        logger.info("Started background cleanup thread")
    
    def _get_filepath(self, result_id: str) -> Path:
        """Get file path for a result ID.
        
        Args:
            result_id: Unique result identifier
            
        Returns:
            Path to the result file
        """
        # Sanitize result_id to prevent path traversal
        safe_id = result_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self.storage_dir / f"{safe_id}.json"
    
    def save(self, result_id: str, data: Dict[str, Any]) -> bool:
        """Save a result to storage.
        
        Args:
            result_id: Unique result identifier
            data: Result data dictionary
            
        Returns:
            True if saved successfully
        """
        try:
            filepath = self._get_filepath(result_id)
            
            # Add metadata for TTL management
            stored_data = {
                "_stored_at": time.time(),
                "_result_id": result_id,
                **data
            }
            
            temp_path = filepath.with_suffix(".tmp")
            with self._lock:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(stored_data, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, filepath)
            
            logger.info(f"Result saved: {result_id} -> {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save result {result_id}: {e}")
            return False
    
    def get(self, result_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a result from storage.
        
        Args:
            result_id: Unique result identifier
            
        Returns:
            Result data dictionary or None if not found/expired
        """
        try:
            filepath = self._get_filepath(result_id)
            
            if not filepath.exists():
                logger.debug(f"Result not found: {result_id}")
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                stored_data = json.load(f)
            
            # Check TTL
            stored_at = stored_data.get("_stored_at", 0)
            if time.time() - stored_at > self.ttl_seconds:
                logger.info(f"Result expired: {result_id}")
                self._delete_file(filepath)
                return None
            
            # Remove internal metadata before returning
            result = {k: v for k, v in stored_data.items() if not k.startswith("_")}
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted result file for {result_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to read result {result_id}: {e}")
            return None
    
    def delete(self, result_id: str) -> bool:
        """Delete a result from storage.
        
        Args:
            result_id: Unique result identifier
            
        Returns:
            True if deleted successfully
        """
        filepath = self._get_filepath(result_id)
        return self._delete_file(filepath)
    
    def _delete_file(self, filepath: Path) -> bool:
        """Delete a file safely.
        
        Args:
            filepath: Path to file to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            if filepath.exists():
                filepath.unlink()
                logger.debug(f"Deleted result file: {filepath}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete {filepath}: {e}")
            return False
    
    def cleanup_expired(self) -> int:
        """Remove all expired results.
        
        Returns:
            Number of expired results removed
        """
        removed = 0
        try:
            for filepath in self.storage_dir.glob("*.json"):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        stored_data = json.load(f)
                    
                    stored_at = stored_data.get("_stored_at", 0)
                    if time.time() - stored_at > self.ttl_seconds:
                        self._delete_file(filepath)
                        removed += 1
                except Exception:
                    # If we can't read the file, it's probably corrupted — remove it
                    self._delete_file(filepath)
                    removed += 1
            
            if removed > 0:
                logger.info(f"Cleanup: removed {removed} expired results")
                
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        
        return removed
    
    def count(self) -> int:
        """Get the number of stored results.
        
        Returns:
            Number of result files
        """
        return len(list(self.storage_dir.glob("*.json")))

    def list_recent(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Return recent non-expired stored results ordered by save time.

        Args:
            limit: Maximum number of results to return

        Returns:
            Stored result dictionaries including internal metadata fields
        """
        entries: list[Dict[str, Any]] = []

        try:
            for filepath in self.storage_dir.glob("*.json"):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        stored_data = json.load(f)

                    stored_at = stored_data.get("_stored_at", 0)
                    if time.time() - stored_at > self.ttl_seconds:
                        self._delete_file(filepath)
                        continue

                    entries.append(stored_data)
                except Exception:
                    self._delete_file(filepath)

            entries.sort(key=lambda item: float(item.get("_stored_at", 0) or 0), reverse=True)
        except Exception as e:
            logger.error(f"Failed to list recent results: {e}")
            return []

        if limit > 0:
            return entries[:limit]
        return entries


# Global instance — shared across the application
_store_instance: Optional[ResultStore] = None


def get_result_store(storage_dir: str = "results_data", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> ResultStore:
    """Get or create the global ResultStore instance.
    
    Args:
        storage_dir: Directory to store result files
        ttl_seconds: Time-to-live for results in seconds
        
    Returns:
        ResultStore instance
    """
    global _store_instance
    if (
        _store_instance is None or
        str(_store_instance.storage_dir) != str(Path(storage_dir)) or
        _store_instance.ttl_seconds != ttl_seconds
    ):
        _store_instance = ResultStore(storage_dir=storage_dir, ttl_seconds=ttl_seconds)
    return _store_instance
