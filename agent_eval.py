"""
Offline evaluation helpers for agent-generated WBS results.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

STANDARD_PHASES = [
    "Планирование и анализ",
    "Проектирование",
    "Разработка",
    "Тестирование",
    "Развертывание",
]


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_key(value: Any) -> str:
    return _normalize_space(value).lower()


def _truncate_text(value: Any, limit: int = 240) -> str:
    text = _normalize_space(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _safe_ratio(numerator: float, denominator: float, default: float = 1.0) -> float:
    if denominator <= 0:
        return default
    return max(0.0, min(1.0, numerator / denominator))


def _range_score(value: float, min_value: Optional[float], max_value: Optional[float]) -> float:
    if value <= 0:
        return 0.0
    if min_value is None and max_value is None:
        return 1.0
    if min_value is not None and value < min_value:
        return max(0.0, 1.0 - ((min_value - value) / max(min_value, 1.0)))
    if max_value is not None and value > max_value:
        return max(0.0, 1.0 - ((value - max_value) / max(max_value, 1.0)))
    return 1.0


def _keyword_match(reference: str, candidates: Iterable[str]) -> bool:
    tokens = [
        token for token in re.findall(r"[a-zA-Zа-яА-Я0-9]+", _normalize_key(reference))
        if len(token) > 3
    ]
    if not tokens:
        return False
    haystack = " ".join(_normalize_key(candidate) for candidate in candidates)
    matched = sum(1 for token in tokens if token in haystack)
    return _safe_ratio(matched, len(tokens), default=0.0) >= 0.5


def _extract_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    result = raw_payload.get("result") or raw_payload.get("data") or raw_payload
    metadata = raw_payload.get("metadata", {}) if isinstance(raw_payload.get("metadata", {}), dict) else {}
    validation = raw_payload.get("validation")
    return {
        "result": result if isinstance(result, dict) else {},
        "metadata": metadata,
        "validation": validation if isinstance(validation, dict) else {},
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def load_trace_bundle(trace_dir: str) -> Dict[str, Any]:
    """Load trace artifacts from one analysis run directory."""
    base_dir = Path(trace_dir)
    llm_calls = _read_jsonl(base_dir / "llm_calls.ndjson")
    intermediate_results = _read_jsonl(base_dir / "intermediate_results.ndjson")
    progress_events = _read_jsonl(base_dir / "progress_events.ndjson")
    return {
        "trace_dir": str(base_dir),
        "llm_calls": llm_calls,
        "intermediate_results": intermediate_results,
        "progress_events": progress_events,
    }


def _collect_result_stats(result: Dict[str, Any]) -> Dict[str, Any]:
    phases = result.get("wbs", {}).get("phases", []) or []
    phase_names: List[str] = []
    all_names: List[str] = []
    work_packages = 0
    work_packages_with_requirement_ids = 0
    work_packages_with_tasks = 0
    tasks = 0
    tasks_with_requirement_ids = 0
    explicit_requirement_ids = set()

    for phase in phases:
        phase_name = _normalize_space(phase.get("name"))
        if phase_name:
            phase_names.append(phase_name)
            all_names.append(phase_name)

        for work_package in phase.get("work_packages", []) or []:
            work_packages += 1
            wp_name = _normalize_space(work_package.get("name"))
            if wp_name:
                all_names.append(wp_name)

            wp_requirement_ids = {
                _normalize_space(req_id)
                for req_id in work_package.get("requirement_ids", []) or []
                if _normalize_space(req_id)
            }
            if wp_requirement_ids:
                work_packages_with_requirement_ids += 1
                explicit_requirement_ids.update(wp_requirement_ids)

            wp_tasks = work_package.get("tasks", []) or []
            if wp_tasks:
                work_packages_with_tasks += 1

            for task in wp_tasks:
                tasks += 1
                task_name = _normalize_space(task.get("name"))
                if task_name:
                    all_names.append(task_name)

                task_requirement_ids = {
                    _normalize_space(req_id)
                    for req_id in task.get("requirement_ids", []) or []
                    if _normalize_space(req_id)
                }
                if task_requirement_ids:
                    tasks_with_requirement_ids += 1
                    explicit_requirement_ids.update(task_requirement_ids)

    project_info = result.get("project_info", {}) or {}
    total_hours = float(project_info.get("total_estimated_hours", 0) or 0)
    if total_hours <= 0:
        total_hours = sum(float(phase.get("estimated_hours", 0) or 0) for phase in phases)

    return {
        "phase_names": phase_names,
        "all_names": all_names,
        "work_packages": work_packages,
        "work_packages_with_requirement_ids": work_packages_with_requirement_ids,
        "work_packages_with_tasks": work_packages_with_tasks,
        "tasks": tasks,
        "tasks_with_requirement_ids": tasks_with_requirement_ids,
        "explicit_requirement_ids": explicit_requirement_ids,
        "total_hours": total_hours,
        "project_type": _normalize_space(project_info.get("project_type")),
        "complexity_level": _normalize_space(project_info.get("complexity_level")),
    }


def _expected_requirement_coverage(
    expected: Dict[str, Any],
    coverage_matrix: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> Dict[str, Any]:
    required_ids = [
        _normalize_space(req_id)
        for req_id in expected.get("required_requirement_ids", []) or []
        if _normalize_space(req_id)
    ]
    required_names = [
        _normalize_space(name)
        for name in expected.get("required_requirement_names", []) or []
        if _normalize_space(name)
    ]
    if not required_ids and not required_names:
        return {
            "score": None,
            "passed": None,
            "details": {}
        }

    matrix_by_id = {
        _normalize_space(item.get("requirement_id")): item
        for item in coverage_matrix
        if _normalize_space(item.get("requirement_id"))
    }

    explicit_matches = sum(
        1 for requirement_id in required_ids
        if (
            bool(matrix_by_id[requirement_id].get("covered_by_ids"))
            if requirement_id in matrix_by_id
            else requirement_id in stats["explicit_requirement_ids"]
        )
    )
    name_matches = sum(
        1 for requirement_name in required_names
        if _keyword_match(requirement_name, stats["all_names"])
    )
    total_expected = len(required_ids) + len(required_names)
    score = _safe_ratio(explicit_matches + name_matches, total_expected, default=0.0)
    return {
        "score": score,
        "passed": score >= 1.0,
        "details": {
            "required_requirement_ids": required_ids,
            "required_requirement_names": required_names,
            "matched_requirement_ids": explicit_matches,
            "matched_requirement_names": name_matches,
        }
    }


def evaluate_case(
    raw_payload: Dict[str, Any],
    *,
    case_id: str = "",
    source: str = "",
    expected: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Evaluate one result payload against deterministic rubric checks."""
    expected = expected or {}
    payload = _extract_payload(raw_payload)
    result = payload["result"]
    metadata = payload["metadata"]
    validation = payload["validation"]
    stats = _collect_result_stats(result)

    coverage_meta = metadata.get("requirements_coverage", {}) if isinstance(metadata.get("requirements_coverage", {}), dict) else {}
    coverage_matrix = coverage_meta.get("coverage_matrix", []) if isinstance(coverage_meta.get("coverage_matrix", []), list) else []
    total_requirements = int(coverage_meta.get("total", 0) or 0)
    covered_by_ids = int(coverage_meta.get("covered_by_ids", 0) or 0)
    covered_total = int(coverage_meta.get("covered", 0) or 0)

    explicit_traceability_ratio = (
        _safe_ratio(covered_by_ids, total_requirements, default=0.0)
        if total_requirements > 0
        else _safe_ratio(
            stats["tasks_with_requirement_ids"] + stats["work_packages_with_requirement_ids"],
            stats["tasks"] + stats["work_packages"],
            default=0.0
        )
    )
    total_coverage_ratio = (
        _safe_ratio(covered_total, total_requirements, default=0.0)
        if total_requirements > 0
        else explicit_traceability_ratio
    )
    required_coverage = _expected_requirement_coverage(expected, coverage_matrix, stats)
    traceability_score = required_coverage["score"]
    if traceability_score is None:
        traceability_score = (explicit_traceability_ratio * 0.7) + (total_coverage_ratio * 0.3)

    expected_total_range = expected.get("total_hours_range", []) or []
    min_total = float(expected_total_range[0]) if len(expected_total_range) >= 1 else None
    max_total = float(expected_total_range[1]) if len(expected_total_range) >= 2 else None
    estimate_score = _range_score(stats["total_hours"], min_total, max_total)
    estimate_pass = estimate_score >= 1.0 if min_total is not None or max_total is not None else stats["total_hours"] > 0

    confidence_target = float(
        expected.get("min_confidence_score")
        or metadata.get("min_confidence_score")
        or 0.7
    )
    raw_confidence = float(validation.get("confidence_score", 0) or 0)
    confidence_score = (
        min(1.0, raw_confidence / max(confidence_target, 0.01))
        if raw_confidence > 0
        else 0.0
    )
    confidence_pass = raw_confidence >= confidence_target if raw_confidence > 0 else False

    required_phase_names = [
        _normalize_space(name)
        for name in expected.get("required_phase_names", []) or []
        if _normalize_space(name)
    ]
    if required_phase_names:
        matched_phases = sum(
            1 for phase_name in required_phase_names
            if _normalize_key(phase_name) in {_normalize_key(value) for value in stats["phase_names"]}
        )
        phase_score = _safe_ratio(matched_phases, len(required_phase_names), default=0.0)
        phase_pass = phase_score >= 1.0
    else:
        phase_score = _safe_ratio(len(stats["phase_names"]), 3, default=0.0)
        phase_pass = len(stats["phase_names"]) >= 3

    structure_components = [
        _safe_ratio(stats["work_packages_with_requirement_ids"], stats["work_packages"], default=0.0),
        _safe_ratio(stats["tasks_with_requirement_ids"], stats["tasks"], default=0.0),
        _safe_ratio(stats["work_packages_with_tasks"], stats["work_packages"], default=0.0),
    ]
    structure_score = sum(structure_components) / len(structure_components) if structure_components else 0.0
    structure_pass = structure_score >= 0.8

    expected_project_type = _normalize_space(expected.get("project_type"))
    expected_complexity = _normalize_space(expected.get("complexity_level"))
    project_type_pass = not expected_project_type or stats["project_type"] == expected_project_type
    complexity_pass = not expected_complexity or stats["complexity_level"] == expected_complexity
    type_score = 1.0 if project_type_pass else 0.0
    complexity_score = 1.0 if complexity_pass else 0.0

    checks = [
        {
            "name": "traceability",
            "weight": 0.35,
            "score": traceability_score,
            "passed": traceability_score >= float(expected.get("min_traceability_coverage", 0.8)),
            "details": {
                "explicit_traceability_ratio": explicit_traceability_ratio,
                "total_coverage_ratio": total_coverage_ratio,
                **required_coverage["details"],
            },
        },
        {
            "name": "estimate_range",
            "weight": 0.25,
            "score": estimate_score,
            "passed": estimate_pass,
            "details": {
                "total_hours": stats["total_hours"],
                "expected_range": [min_total, max_total],
            },
        },
        {
            "name": "confidence",
            "weight": 0.20,
            "score": confidence_score,
            "passed": confidence_pass,
            "details": {
                "confidence_score": raw_confidence,
                "target": confidence_target,
            },
        },
        {
            "name": "phase_coverage",
            "weight": 0.10,
            "score": phase_score,
            "passed": phase_pass,
            "details": {
                "phase_names": stats["phase_names"],
                "required_phase_names": required_phase_names,
            },
        },
        {
            "name": "structure",
            "weight": 0.10,
            "score": structure_score,
            "passed": structure_pass,
            "details": {
                "work_packages": stats["work_packages"],
                "work_packages_with_requirement_ids": stats["work_packages_with_requirement_ids"],
                "work_packages_with_tasks": stats["work_packages_with_tasks"],
                "tasks": stats["tasks"],
                "tasks_with_requirement_ids": stats["tasks_with_requirement_ids"],
            },
        },
    ]

    if expected_project_type:
        checks.append({
            "name": "project_type_match",
            "weight": 0.0,
            "score": type_score,
            "passed": project_type_pass,
            "details": {
                "actual": stats["project_type"],
                "expected": expected_project_type,
            },
        })
    if expected_complexity:
        checks.append({
            "name": "complexity_match",
            "weight": 0.0,
            "score": complexity_score,
            "passed": complexity_pass,
            "details": {
                "actual": stats["complexity_level"],
                "expected": expected_complexity,
            },
        })

    weighted_score = round(sum(check["weight"] * check["score"] for check in checks) * 100, 1)
    hard_fail = any(
        (check["name"] in {"traceability", "project_type_match", "complexity_match"} and not check["passed"])
        for check in checks
        if check["weight"] == 0.0 or check["name"] == "traceability"
    )
    passed = weighted_score >= float(expected.get("min_total_score", 75.0)) and not hard_fail

    return {
        "case_id": case_id,
        "source": source,
        "score": weighted_score,
        "passed": passed,
        "checks": checks,
        "summary": {
            "project_type": stats["project_type"],
            "complexity_level": stats["complexity_level"],
            "total_hours": stats["total_hours"],
            "explicit_traceability_ratio": round(explicit_traceability_ratio, 3),
            "total_coverage_ratio": round(total_coverage_ratio, 3),
            "confidence_score": raw_confidence,
            "phase_count": len(stats["phase_names"]),
        },
    }


def summarize_evaluations(evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not evaluations:
        return {
            "cases": 0,
            "passed": 0,
            "failed": 0,
            "average_score": 0.0,
        }

    passed = sum(1 for evaluation in evaluations if evaluation["passed"])
    return {
        "cases": len(evaluations),
        "passed": passed,
        "failed": len(evaluations) - passed,
        "average_score": round(
            sum(float(evaluation.get("score", 0) or 0) for evaluation in evaluations) / len(evaluations),
            1
        ),
        "judged_cases": sum(
            1 for evaluation in evaluations
            if evaluation.get("llm_judge", {}).get("success")
        ),
        "average_combined_score": round(
            sum(
                float(evaluation.get("combined_score", evaluation.get("score", 0)) or 0)
                for evaluation in evaluations
            ) / len(evaluations),
            1
        ),
    }


def _extract_user_prompt(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user":
            return _truncate_text(message.get("content", ""), limit=220)
    return ""


def _extract_system_prompt(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "system":
            return _truncate_text(message.get("content", ""), limit=180)
    return ""


def _compact_llm_call(call: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "agent": _normalize_space(call.get("agent")),
        "status": _normalize_space(call.get("status")),
        "error_type": _normalize_space(call.get("error_type")),
        "attempt": int(call.get("attempt", 0) or 0),
        "elapsed_seconds": float(call.get("elapsed_seconds", 0) or 0),
        "stage_message": _truncate_text(call.get("stage_message", ""), limit=140),
        "system_prompt_preview": _extract_system_prompt(call.get("messages", [])),
        "user_prompt_preview": _extract_user_prompt(call.get("messages", [])),
        "response_preview": _truncate_text(
            call.get("response")
            or call.get("raw_response")
            or call.get("error"),
            limit=220,
        ),
    }


def build_trace_judge_payload(
    evaluation: Dict[str, Any],
    trace_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a compact trace payload for optional LLM judging."""
    llm_calls = trace_bundle.get("llm_calls", []) if isinstance(trace_bundle.get("llm_calls", []), list) else []
    intermediate_results = (
        trace_bundle.get("intermediate_results", [])
        if isinstance(trace_bundle.get("intermediate_results", []), list)
        else []
    )
    progress_events = (
        trace_bundle.get("progress_events", [])
        if isinstance(trace_bundle.get("progress_events", []), list)
        else []
    )

    agent_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    error_type_counts: Dict[str, int] = {}
    for call in llm_calls:
        agent_name = _normalize_space(call.get("agent")) or "unknown"
        status = _normalize_space(call.get("status")) or "unknown"
        error_type = _normalize_space(call.get("error_type")) or "none"
        agent_counts[agent_name] = agent_counts.get(agent_name, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
        error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1

    compact_calls = [
        _compact_llm_call(call)
        for call in sorted(
            llm_calls,
            key=lambda item: (
                0 if _normalize_space(item.get("status")) != "success" else 1,
                -float(item.get("elapsed_seconds", 0) or 0),
            ),
        )[:8]
    ]

    stage_counts: Dict[str, int] = {}
    for row in intermediate_results:
        stage_name = _normalize_space(row.get("stage")) or "unknown"
        stage_counts[stage_name] = stage_counts.get(stage_name, 0) + 1

    progress_highlights = []
    for event in progress_events:
        event_type = _normalize_space(event.get("type")) or "unknown"
        message = _truncate_text(event.get("message", ""), limit=180)
        data = event.get("data", {}) if isinstance(event.get("data", {}), dict) else {}
        if (
            event_type in {"stage", "error"}
            or data.get("llm_event")
            or "quality gate" in message.lower()
            or "ошибка" in message.lower()
        ):
            progress_highlights.append({
                "type": event_type,
                "message": message,
                "agent": _normalize_space(data.get("agent")),
                "llm_event": _normalize_space(data.get("llm_event")),
            })
        if len(progress_highlights) >= 10:
            break

    return {
        "case_id": evaluation.get("case_id", ""),
        "deterministic_eval": {
            "score": evaluation.get("score"),
            "passed": evaluation.get("passed"),
            "summary": evaluation.get("summary", {}),
            "checks": [
                {
                    "name": check.get("name"),
                    "score": check.get("score"),
                    "passed": check.get("passed"),
                }
                for check in evaluation.get("checks", [])
            ],
        },
        "trace_summary": {
            "trace_dir": trace_bundle.get("trace_dir", ""),
            "llm_call_count": len(llm_calls),
            "intermediate_result_count": len(intermediate_results),
            "progress_event_count": len(progress_events),
            "agent_counts": agent_counts,
            "status_counts": status_counts,
            "error_type_counts": error_type_counts,
            "stage_counts": stage_counts,
        },
        "llm_call_examples": compact_calls,
        "progress_highlights": progress_highlights,
    }


def _parse_json_blob(text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def judge_trace_with_llm(
    evaluation: Dict[str, Any],
    trace_bundle: Dict[str, Any],
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Run an optional LLM judge over compact trace artifacts."""
    llm_calls = trace_bundle.get("llm_calls", []) if isinstance(trace_bundle.get("llm_calls", []), list) else []
    intermediate_results = (
        trace_bundle.get("intermediate_results", [])
        if isinstance(trace_bundle.get("intermediate_results", []), list)
        else []
    )
    progress_events = (
        trace_bundle.get("progress_events", [])
        if isinstance(trace_bundle.get("progress_events", []), list)
        else []
    )
    if not llm_calls and not intermediate_results and not progress_events:
        return {
            "success": False,
            "skipped": True,
            "reason": "no_trace_bundle",
        }

    from config import Config
    from openai import OpenAI

    judge_model = model or Config.OPENAI_MODEL
    client = OpenAI(
        api_key=api_key or Config.OPENAI_API_KEY or "not-needed",
        base_url=base_url or Config.OPENAI_API_BASE,
        timeout=180.0,
    )
    payload = build_trace_judge_payload(evaluation, trace_bundle)

    system_prompt = """Ты строгий judge trace-ов мульти-агентной системы оценки проектов.

Оцени не только итоговый результат, но и качество процесса.
Возвращай ТОЛЬКО JSON.

Шкалы 0-100:
- grounding_to_requirements
- traceability_discipline
- estimation_calibration
- repair_loop_effectiveness
- robustness_and_reliability

Pass=true только если общий score >= 75 и нет критических провалов в grounding_to_requirements или traceability_discipline.

Формат:
{
  "score": 0,
  "passed": false,
  "category_scores": {
    "grounding_to_requirements": 0,
    "traceability_discipline": 0,
    "estimation_calibration": 0,
    "repair_loop_effectiveness": 0,
    "robustness_and_reliability": 0
  },
  "strengths": [],
  "findings": [],
  "risks": [],
  "reasoning_summary": ""
}"""
    user_message = (
        "Оцени следующий trace bundle. "
        "Опирайся только на факты из payload, не выдумывай детали.\n\n"
        f"Payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    request = {
        "model": judge_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": 1400,
    }

    try:
        response = client.chat.completions.create(
            response_format={"type": "json_object"},
            **request,
        )
    except Exception:
        response = client.chat.completions.create(**request)

    content = response.choices[0].message.content or "{}"
    judge_payload = _parse_json_blob(content)
    if not judge_payload:
        return {
            "success": False,
            "error": "judge_response_parse_failed",
            "raw_response": content,
            "model": judge_model,
        }

    judge_score = float(judge_payload.get("score", 0) or 0)
    judge_passed = bool(
        judge_payload.get("passed", False)
        or (
            judge_score >= 75
            and float(judge_payload.get("category_scores", {}).get("grounding_to_requirements", 0) or 0) >= 60
            and float(judge_payload.get("category_scores", {}).get("traceability_discipline", 0) or 0) >= 60
        )
    )

    return {
        "success": True,
        "model": judge_model,
        "score": judge_score,
        "passed": judge_passed,
        "category_scores": judge_payload.get("category_scores", {}),
        "strengths": judge_payload.get("strengths", []),
        "findings": judge_payload.get("findings", []),
        "risks": judge_payload.get("risks", []),
        "reasoning_summary": judge_payload.get("reasoning_summary", ""),
        "payload": payload,
    }


def attach_llm_judge_results(
    evaluations: List[Dict[str, Any]],
    entries: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_cases: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Attach optional LLM judge results to deterministic evaluations."""
    judged = 0
    for evaluation, entry in zip(evaluations, entries):
        trace_bundle = entry.get("trace") if isinstance(entry.get("trace"), dict) else {}
        if max_cases is not None and judged >= max_cases:
            evaluation["llm_judge"] = {
                "success": False,
                "skipped": True,
                "reason": "max_cases_reached",
            }
            evaluation["combined_score"] = evaluation.get("score", 0)
            evaluation["combined_passed"] = evaluation.get("passed", False)
            continue

        judge_result = judge_trace_with_llm(
            evaluation,
            trace_bundle,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        evaluation["llm_judge"] = judge_result
        if judge_result.get("success"):
            judged += 1
            evaluation["combined_score"] = round(
                (float(evaluation.get("score", 0) or 0) * 0.7) +
                (float(judge_result.get("score", 0) or 0) * 0.3),
                1
            )
            evaluation["combined_passed"] = bool(
                evaluation.get("passed", False) and judge_result.get("passed", False)
            )
        else:
            evaluation["combined_score"] = evaluation.get("score", 0)
            evaluation["combined_passed"] = evaluation.get("passed", False)

    return evaluations


def load_cases_file(path: str) -> List[Dict[str, Any]]:
    """Load golden cases from a JSON file."""
    file_path = Path(path)
    with open(file_path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if isinstance(raw, dict) and isinstance(raw.get("cases"), list):
        cases = raw["cases"]
    elif isinstance(raw, list):
        cases = raw
    else:
        cases = [raw]

    loaded_cases = []
    for index, case in enumerate(cases, start=1):
        case_id = _normalize_space(case.get("case_id")) or f"case-{index}"
        result_payload = case.get("result")
        result_file = case.get("result_file")
        if result_payload is None and result_file:
            resolved_path = (file_path.parent / result_file).resolve()
            with open(resolved_path, "r", encoding="utf-8") as handle:
                result_payload = json.load(handle)

        trace_bundle = case.get("trace") if isinstance(case.get("trace"), dict) else {}
        trace_file = case.get("trace_file")
        trace_dir = case.get("trace_dir")
        if not trace_bundle and trace_file:
            resolved_trace_path = (file_path.parent / trace_file).resolve()
            with open(resolved_trace_path, "r", encoding="utf-8") as handle:
                loaded_trace = json.load(handle)
            trace_bundle = loaded_trace if isinstance(loaded_trace, dict) else {}
        if not trace_bundle and trace_dir:
            resolved_trace_dir = (file_path.parent / trace_dir).resolve()
            trace_bundle = load_trace_bundle(str(resolved_trace_dir))

        loaded_cases.append({
            "case_id": case_id,
            "source": str(result_file or file_path),
            "expected": case.get("expected", {}) if isinstance(case.get("expected", {}), dict) else {},
            "payload": result_payload if isinstance(result_payload, dict) else {},
            "trace": trace_bundle,
        })

    return loaded_cases


def load_analysis_runs(root_dir: str) -> List[Dict[str, Any]]:
    """Load completed analysis run artifacts from analysis_runs."""
    root = Path(root_dir)
    loaded_runs = []
    for final_result_path in sorted(root.rglob("final_result.json")):
        with open(final_result_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        loaded_runs.append({
            "case_id": final_result_path.parent.name,
            "source": str(final_result_path),
            "expected": {},
            "payload": payload if isinstance(payload, dict) else {},
            "trace": load_trace_bundle(str(final_result_path.parent)),
        })
    return loaded_runs


def load_result_payload_from_source(source_path: str) -> Dict[str, Any]:
    """Load one result payload from a file or analysis run directory."""
    path = Path(source_path)
    trace_dir = ""
    if path.is_dir():
        payload_path = path / "final_result.json"
        trace_dir = str(path)
    else:
        payload_path = path
        if path.name == "final_result.json":
            trace_dir = str(path.parent)
        elif (path.parent / "llm_calls.ndjson").exists():
            trace_dir = str(path.parent)

    with open(payload_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return {
        "payload": payload if isinstance(payload, dict) else {},
        "source": str(payload_path),
        "trace_dir": trace_dir,
    }


def build_golden_case_from_payload(
    raw_payload: Dict[str, Any],
    *,
    case_id: str,
    source: str = "",
    trace_dir: str = "",
    total_hours_tolerance: float = 0.15,
    max_requirements: int = 12,
    min_total_score: float = 75.0,
) -> Dict[str, Any]:
    """Build a golden-case draft from a completed result payload."""
    payload = _extract_payload(raw_payload)
    result = payload["result"]
    metadata = payload["metadata"]
    validation = payload["validation"]
    stats = _collect_result_stats(result)
    coverage_meta = metadata.get("requirements_coverage", {}) if isinstance(metadata.get("requirements_coverage", {}), dict) else {}
    coverage_matrix = coverage_meta.get("coverage_matrix", []) if isinstance(coverage_meta.get("coverage_matrix", []), list) else []

    requirement_ids = []
    for item in coverage_matrix:
        requirement_id = _normalize_space(item.get("requirement_id"))
        if not requirement_id:
            continue
        if requirement_id not in requirement_ids:
            requirement_ids.append(requirement_id)
        if len(requirement_ids) >= max_requirements:
            break

    if not requirement_ids:
        requirement_ids = sorted(stats["explicit_requirement_ids"])[:max_requirements]

    total_hours = stats["total_hours"]
    tolerance = max(0.01, float(total_hours_tolerance))
    min_total_hours = max(1, round(total_hours * (1.0 - tolerance)))
    max_total_hours = max(min_total_hours, round(total_hours * (1.0 + tolerance)))

    target_confidence = float(
        metadata.get("min_confidence_score")
        or validation.get("confidence_score")
        or 0.7
    )

    case = {
        "case_id": case_id,
        "expected": {
            "project_type": stats["project_type"],
            "complexity_level": stats["complexity_level"],
            "total_hours_range": [min_total_hours, max_total_hours],
            "required_requirement_ids": requirement_ids,
            "required_phase_names": stats["phase_names"],
            "min_confidence_score": round(target_confidence, 2),
            "min_total_score": min_total_score,
        },
        "result": raw_payload,
        "notes": [
            "REVIEW_REQUIRED: проверь total_hours_range по исходному ТЗ, а не только по текущему результату.",
            "REVIEW_REQUIRED: сократи required_requirement_ids до действительно критичных требований, если список слишком большой.",
        ],
        "seeded_from": source,
    }
    if trace_dir:
        case["trace_dir"] = trace_dir
    return case


def upsert_golden_case_file(
    cases_file: str,
    case: Dict[str, Any],
    *,
    replace_existing: bool = False,
) -> Dict[str, Any]:
    """Insert or replace one case in a golden-case JSON file."""
    file_path = Path(cases_file)
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict) and isinstance(raw.get("cases"), list):
            document = raw
        elif isinstance(raw, list):
            document = {"cases": raw}
        else:
            document = {"cases": []}
    else:
        document = {"cases": []}

    cases = document.get("cases", [])
    case_id = _normalize_space(case.get("case_id"))
    if not case_id:
        raise ValueError("case_id is required")

    existing_index = next(
        (index for index, item in enumerate(cases) if _normalize_space(item.get("case_id")) == case_id),
        None,
    )
    if existing_index is not None and not replace_existing:
        raise ValueError(f"case_id '{case_id}' already exists in {cases_file}")

    if existing_index is not None:
        cases[existing_index] = case
        action = "replaced"
    else:
        cases.append(case)
        action = "inserted"

    document["cases"] = cases
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)

    return {
        "action": action,
        "cases_file": str(file_path),
        "case_id": case_id,
        "cases_count": len(cases),
    }
