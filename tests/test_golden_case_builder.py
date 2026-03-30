import json
import tempfile
import unittest
from pathlib import Path

from agent_eval import (
    build_golden_case_from_payload,
    load_result_payload_from_source,
    upsert_golden_case_file,
)


def _payload(total_hours: int = 240, confidence: float = 0.81) -> dict:
    return {
        "result": {
            "project_info": {
                "project_name": "Customer Portal",
                "project_type": "Веб-приложение",
                "complexity_level": "Средний",
                "total_estimated_hours": total_hours,
            },
            "wbs": {
                "phases": [
                    {
                        "name": "Планирование и анализ",
                        "estimated_hours": 30,
                        "work_packages": [
                            {
                                "name": "Уточнение требований",
                                "requirement_ids": ["FR-10", "FR-11"],
                                "tasks": [
                                    {"name": "Уточнить роли пользователей", "requirement_ids": ["FR-10"]},
                                    {"name": "Уточнить сценарии заявок", "requirement_ids": ["FR-11"]},
                                ],
                            }
                        ],
                    },
                    {
                        "name": "Разработка",
                        "estimated_hours": total_hours - 70,
                        "work_packages": [
                            {
                                "name": "Личный кабинет",
                                "requirement_ids": ["FR-10", "FR-11", "FR-12"],
                                "tasks": [
                                    {"name": "Сделать профиль", "requirement_ids": ["FR-10"]},
                                    {"name": "Сделать заявки", "requirement_ids": ["FR-11"]},
                                    {"name": "Сделать уведомления", "requirement_ids": ["FR-12"]},
                                ],
                            }
                        ],
                    },
                    {
                        "name": "Тестирование",
                        "estimated_hours": 25,
                        "work_packages": [
                            {
                                "name": "Функциональные тесты",
                                "requirement_ids": ["FR-10", "FR-11", "FR-12"],
                                "tasks": [
                                    {"name": "Проверить профиль", "requirement_ids": ["FR-10"]},
                                    {"name": "Проверить заявки", "requirement_ids": ["FR-11"]},
                                    {"name": "Проверить уведомления", "requirement_ids": ["FR-12"]},
                                ],
                            }
                        ],
                    },
                    {
                        "name": "Развертывание",
                        "estimated_hours": 15,
                        "work_packages": [
                            {
                                "name": "Публикация",
                                "requirement_ids": ["FR-10", "FR-11", "FR-12"],
                                "tasks": [
                                    {"name": "Подготовить релиз", "requirement_ids": ["FR-10", "FR-11", "FR-12"]},
                                ],
                            }
                        ],
                    },
                ]
            },
        },
        "metadata": {
            "min_confidence_score": 0.75,
            "requirements_coverage": {
                "total": 3,
                "covered": 3,
                "covered_by_ids": 3,
                "covered_by_name_fallback": 0,
                "uncovered": [],
                "coverage_matrix": [
                    {
                        "requirement_id": "FR-10",
                        "requirement_name": "Профиль",
                        "covered": True,
                        "covered_by_ids": True,
                        "covered_by_name_fallback": False,
                    },
                    {
                        "requirement_id": "FR-11",
                        "requirement_name": "Заявки",
                        "covered": True,
                        "covered_by_ids": True,
                        "covered_by_name_fallback": False,
                    },
                    {
                        "requirement_id": "FR-12",
                        "requirement_name": "Уведомления",
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


class GoldenCaseBuilderTests(unittest.TestCase):
    def test_load_result_payload_from_directory_and_file(self):
        payload = _payload()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            run_dir = temp_path / "analysis_runs" / "portal-run"
            run_dir.mkdir(parents=True, exist_ok=True)
            result_file = run_dir / "final_result.json"

            with open(result_file, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            with open(run_dir / "llm_calls.ndjson", "w", encoding="utf-8") as handle:
                handle.write("{}\n")

            loaded_from_dir = load_result_payload_from_source(str(run_dir))
            loaded_from_file = load_result_payload_from_source(str(result_file))

            self.assertEqual(loaded_from_dir["trace_dir"], str(run_dir))
            self.assertEqual(loaded_from_file["trace_dir"], str(run_dir))
            self.assertEqual(
                loaded_from_dir["payload"]["result"]["project_info"]["project_name"],
                "Customer Portal",
            )
            self.assertEqual(
                loaded_from_file["payload"]["result"]["project_info"]["project_name"],
                "Customer Portal",
            )

    def test_build_golden_case_from_payload_seeds_expected_fields(self):
        case = build_golden_case_from_payload(
            _payload(total_hours=240, confidence=0.81),
            case_id="portal-case",
            source="analysis_runs/portal-run/final_result.json",
            trace_dir="analysis_runs/portal-run",
            total_hours_tolerance=0.1,
            max_requirements=2,
        )

        self.assertEqual(case["case_id"], "portal-case")
        self.assertEqual(case["expected"]["project_type"], "Веб-приложение")
        self.assertEqual(case["expected"]["complexity_level"], "Средний")
        self.assertEqual(case["expected"]["total_hours_range"], [216, 264])
        self.assertEqual(case["expected"]["required_requirement_ids"], ["FR-10", "FR-11"])
        self.assertEqual(case["trace_dir"], "analysis_runs/portal-run")
        self.assertEqual(case["seeded_from"], "analysis_runs/portal-run/final_result.json")
        self.assertEqual(case["expected"]["min_confidence_score"], 0.75)
        self.assertEqual(len(case["notes"]), 2)

    def test_upsert_golden_case_file_inserts_and_replaces(self):
        case = build_golden_case_from_payload(_payload(), case_id="portal-case")
        case_replacement = build_golden_case_from_payload(
            _payload(total_hours=260),
            case_id="portal-case",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cases_file = Path(temp_dir) / "golden_cases.json"

            first = upsert_golden_case_file(str(cases_file), case)
            self.assertEqual(first["action"], "inserted")
            self.assertEqual(first["cases_count"], 1)

            with self.assertRaises(ValueError):
                upsert_golden_case_file(str(cases_file), case)

            second = upsert_golden_case_file(
                str(cases_file),
                case_replacement,
                replace_existing=True,
            )
            self.assertEqual(second["action"], "replaced")
            self.assertEqual(second["cases_count"], 1)

            with open(cases_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)

            self.assertEqual(payload["cases"][0]["expected"]["total_hours_range"], [221, 299])


if __name__ == "__main__":
    unittest.main()
