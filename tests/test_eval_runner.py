import json
import tempfile
import unittest
from pathlib import Path

from agent_eval import (
    attach_llm_judge_results,
    build_trace_judge_payload,
    evaluate_case,
    load_analysis_runs,
    load_cases_file,
    summarize_evaluations,
)


def _base_payload(total_hours: int = 180, confidence: float = 0.82) -> dict:
    return {
        "result": {
            "project_info": {
                "project_name": "Demo API",
                "project_type": "API сервис",
                "complexity_level": "Высокий",
                "total_estimated_hours": total_hours,
            },
            "wbs": {
                "phases": [
                    {
                        "name": "Разработка",
                        "estimated_hours": total_hours - 40,
                        "work_packages": [
                            {
                                "name": "API логика",
                                "requirement_ids": ["FR-1", "FR-2"],
                                "tasks": [
                                    {"name": "Реализовать аутентификацию", "requirement_ids": ["FR-1"]},
                                    {"name": "Добавить аудит операций", "requirement_ids": ["FR-2"]},
                                ],
                            }
                        ],
                    },
                    {
                        "name": "Тестирование",
                        "estimated_hours": 20,
                        "work_packages": [
                            {
                                "name": "API тесты",
                                "requirement_ids": ["FR-1", "FR-2"],
                                "tasks": [
                                    {"name": "Проверить безопасность", "requirement_ids": ["FR-1"]},
                                    {"name": "Проверить аудит", "requirement_ids": ["FR-2"]},
                                ],
                            }
                        ],
                    },
                    {
                        "name": "Развертывание",
                        "estimated_hours": 20,
                        "work_packages": [
                            {
                                "name": "Релиз",
                                "requirement_ids": ["FR-1", "FR-2"],
                                "tasks": [
                                    {"name": "Подготовить релиз", "requirement_ids": ["FR-1", "FR-2"]},
                                ],
                            }
                        ],
                    },
                ]
            },
        },
        "metadata": {
            "min_confidence_score": 0.7,
            "requirements_coverage": {
                "total": 2,
                "covered": 2,
                "covered_by_ids": 2,
                "covered_by_name_fallback": 0,
                "uncovered": [],
                "coverage_matrix": [
                    {
                        "requirement_id": "FR-1",
                        "requirement_name": "Аутентификация",
                        "covered": True,
                        "covered_by_ids": True,
                        "covered_by_name_fallback": False,
                    },
                    {
                        "requirement_id": "FR-2",
                        "requirement_name": "Аудит операций",
                        "covered": True,
                        "covered_by_ids": True,
                        "covered_by_name_fallback": False,
                    },
                ],
            },
        },
        "validation": {
            "confidence_score": confidence,
        },
    }


class AgentEvalRunnerTests(unittest.TestCase):
    def test_evaluate_case_passes_for_expected_range_and_requirements(self):
        expected = {
            "project_type": "API сервис",
            "complexity_level": "Высокий",
            "total_hours_range": [120, 560],
            "required_requirement_ids": ["FR-1", "FR-2"],
            "required_phase_names": ["Разработка", "Тестирование"],
            "min_confidence_score": 0.7,
            "min_total_score": 75,
        }

        evaluation = evaluate_case(
            _base_payload(),
            case_id="demo",
            source="memory",
            expected=expected,
        )

        self.assertTrue(evaluation["passed"])
        self.assertGreaterEqual(evaluation["score"], 75)

    def test_evaluate_case_fails_when_requirement_and_range_are_wrong(self):
        payload = _base_payload(total_hours=900, confidence=0.4)
        payload["metadata"]["requirements_coverage"]["covered_by_ids"] = 1
        payload["metadata"]["requirements_coverage"]["covered"] = 1
        payload["metadata"]["requirements_coverage"]["coverage_matrix"][1]["covered"] = False
        payload["metadata"]["requirements_coverage"]["coverage_matrix"][1]["covered_by_ids"] = False
        payload["metadata"]["requirements_coverage"]["uncovered"] = ["Аудит операций"]

        expected = {
            "project_type": "API сервис",
            "complexity_level": "Высокий",
            "total_hours_range": [120, 560],
            "required_requirement_ids": ["FR-1", "FR-2"],
            "required_phase_names": ["Разработка", "Тестирование"],
            "min_confidence_score": 0.7,
            "min_total_score": 75,
        }

        evaluation = evaluate_case(
            payload,
            case_id="demo-fail",
            source="memory",
            expected=expected,
        )

        self.assertFalse(evaluation["passed"])
        self.assertLess(evaluation["score"], 75)

    def test_load_cases_and_analysis_runs(self):
        payload = _base_payload()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cases_path = temp_path / "cases.json"
            runs_path = temp_path / "analysis_runs" / "run-1"
            runs_path.mkdir(parents=True, exist_ok=True)

            with open(cases_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "cases": [
                            {
                                "case_id": "demo",
                                "expected": {
                                    "required_requirement_ids": ["FR-1"],
                                },
                                "result": payload,
                            }
                        ]
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )

            with open(runs_path / "final_result.json", "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            with open(runs_path / "llm_calls.ndjson", "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "agent": "Планировщик WBS",
                    "status": "success",
                    "attempt": 1,
                    "elapsed_seconds": 1.25,
                    "messages": [
                        {"role": "system", "content": "Ты планировщик"},
                        {"role": "user", "content": "Построй WBS по API"},
                    ],
                    "response": "{\"ok\":true}",
                }, ensure_ascii=False) + "\n")
            with open(runs_path / "intermediate_results.ndjson", "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "stage": "planning_started",
                    "payload": {"compact_analysis": {"project_info": {"project_name": "Demo API"}}},
                }, ensure_ascii=False) + "\n")
            with open(runs_path / "progress_events.ndjson", "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "type": "agent",
                    "message": "📤 Планировщик WBS: запрос отправлен",
                    "data": {"agent": "Планировщик WBS", "llm_event": "request_started"},
                }, ensure_ascii=False) + "\n")

            loaded_cases = load_cases_file(str(cases_path))
            loaded_runs = load_analysis_runs(str(temp_path / "analysis_runs"))
            summary = summarize_evaluations([
                evaluate_case(loaded_cases[0]["payload"], case_id=loaded_cases[0]["case_id"]),
                evaluate_case(loaded_runs[0]["payload"], case_id=loaded_runs[0]["case_id"]),
            ])

            self.assertEqual(len(loaded_cases), 1)
            self.assertEqual(len(loaded_runs), 1)
            self.assertEqual(loaded_runs[0]["case_id"], "run-1")
            self.assertEqual(len(loaded_runs[0]["trace"]["llm_calls"]), 1)
            self.assertEqual(len(loaded_runs[0]["trace"]["intermediate_results"]), 1)
            self.assertEqual(summary["cases"], 2)
            self.assertEqual(summary["judged_cases"], 0)

    def test_build_trace_judge_payload_compacts_artifacts(self):
        evaluation = evaluate_case(_base_payload(), case_id="demo-trace", source="memory")
        trace_bundle = {
            "trace_dir": "analysis_runs/demo-trace",
            "llm_calls": [
                {
                    "agent": "Аналитик ТЗ",
                    "status": "success",
                    "attempt": 1,
                    "elapsed_seconds": 2.5,
                    "stage_message": "📋 Этап 1/6: Анализ технического задания",
                    "messages": [
                        {"role": "system", "content": "Ты аналитик."},
                        {"role": "user", "content": "Разбери требования к API и аудиту."},
                    ],
                    "response": "{\"functional_requirements\":[]}",
                },
                {
                    "agent": "Планировщик WBS",
                    "status": "error",
                    "error_type": "json_parse",
                    "attempt": 2,
                    "elapsed_seconds": 3.75,
                    "messages": [
                        {"role": "system", "content": "Ты планировщик."},
                        {"role": "user", "content": "Построй WBS."},
                    ],
                    "error": "broken json",
                },
            ],
            "intermediate_results": [
                {"stage": "planning_started", "payload": {}},
                {"stage": "wbs_completed", "payload": {}},
            ],
            "progress_events": [
                {"type": "stage", "message": "📐 Этап 3/6: Создание Work Breakdown Structure", "data": {}},
                {"type": "agent", "message": "📤 Планировщик WBS: запрос отправлен", "data": {"llm_event": "request_started"}},
            ],
        }

        payload = build_trace_judge_payload(evaluation, trace_bundle)

        self.assertEqual(payload["trace_summary"]["llm_call_count"], 2)
        self.assertEqual(payload["trace_summary"]["status_counts"]["success"], 1)
        self.assertEqual(payload["trace_summary"]["status_counts"]["error"], 1)
        self.assertEqual(payload["llm_call_examples"][0]["agent"], "Планировщик WBS")
        self.assertIn("traceability", {check["name"] for check in payload["deterministic_eval"]["checks"]})

    def test_attach_llm_judge_results_skips_when_trace_missing(self):
        evaluation = evaluate_case(_base_payload(), case_id="no-trace", source="memory")
        evaluations = attach_llm_judge_results(
            [evaluation],
            [{"case_id": "no-trace", "source": "memory", "payload": _base_payload(), "trace": {}}],
            max_cases=1,
        )

        self.assertTrue(evaluations[0]["llm_judge"]["skipped"])
        self.assertEqual(evaluations[0]["combined_score"], evaluations[0]["score"])


if __name__ == "__main__":
    unittest.main()
