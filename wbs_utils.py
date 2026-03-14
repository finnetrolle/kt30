"""
Utilities for normalizing and recovering WBS result payloads.
"""
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def has_legacy_root_phases(result: Optional[Dict[str, Any]]) -> bool:
    """Return True when phases are stored at the root instead of under wbs."""
    return isinstance(result, dict) and "wbs" not in result and isinstance(result.get("phases"), list)


def canonicalize_wbs_result(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize result payloads to the canonical schema with wbs.phases."""
    if not isinstance(result, dict):
        return {}

    normalized = deepcopy(result)
    root_phases = normalized.get("phases")
    wbs_section = normalized.get("wbs")

    if isinstance(wbs_section, dict):
        if "phases" not in wbs_section and isinstance(root_phases, list):
            normalized["wbs"] = dict(wbs_section)
            normalized["wbs"]["phases"] = root_phases
            normalized.pop("phases", None)
        return normalized

    if isinstance(root_phases, list):
        normalized["wbs"] = {"phases": root_phases}
        normalized.pop("phases", None)

    return normalized


def recover_wbs_from_artifacts(artifacts_dir: Optional[str]) -> Optional[Dict[str, Any]]:
    """Recover the last full WBS snapshot from run artifacts if available."""
    if not artifacts_dir:
        return None

    intermediate_path = Path(artifacts_dir) / "intermediate_results.ndjson"
    if not intermediate_path.exists():
        return None

    recovered = None

    try:
        with open(intermediate_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue

                entry = json.loads(line)
                stage = entry.get("stage", "")
                payload = entry.get("payload", {})
                if not stage.endswith(":wbs_completed"):
                    continue

                candidate = payload.get("wbs")
                if isinstance(candidate, dict):
                    recovered = canonicalize_wbs_result(candidate)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to recover WBS from artifacts %s: %s", artifacts_dir, exc)
        return None

    return recovered
