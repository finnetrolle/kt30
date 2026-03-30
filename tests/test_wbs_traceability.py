import unittest

from agents.agent_orchestrator import AgentOrchestrator
from agents.planner_agent import PlannerAgent
from agents.validator_agent import ESTIMATION_RULES, ValidatorAgent


class WBSTraceabilityTests(unittest.TestCase):
    def _planner(self) -> PlannerAgent:
        planner = PlannerAgent.__new__(PlannerAgent)
        planner._progress_tracker = None
        return planner

    def _validator(self) -> ValidatorAgent:
        validator = ValidatorAgent.__new__(ValidatorAgent)
        validator.estimation_rules = ESTIMATION_RULES
        validator._progress_tracker = None
        return validator

    def _orchestrator(self) -> AgentOrchestrator:
        return AgentOrchestrator.__new__(AgentOrchestrator)

    def test_build_wbs_falls_back_to_phase_requirements_for_missing_traceability(self):
        planner = self._planner()
        analysis = {
            "project_info": {"project_name": "Demo"},
            "functional_requirements": [
                {
                    "id": "FR-1",
                    "name": "Интеграция API",
                    "category": "Backend",
                    "description": "Сервис должен обмениваться данными по API.",
                }
            ],
        }
        skeleton = {
            "phase_plan": [
                {
                    "name": "Разработка",
                    "description": "Реализация",
                    "work_packages": [
                        {
                            "name": "Интеграционный блок",
                            "description": "Реализация интеграции",
                            "requirement_ids": [],
                            "deliverables": [],
                            "skills_required": ["Backend Developer"],
                        }
                    ],
                }
            ]
        }
        generated_tasks = {
            "интеграционный блок": {
                "tasks": [
                    {
                        "name": "Реализовать API",
                        "description": "Добавить вызовы внешнего сервиса",
                        "requirement_ids": [],
                        "estimated_hours": 16,
                        "skills_required": ["Backend Developer"],
                        "depends_on": [],
                        "can_start_parallel": False,
                    }
                ],
                "deliverables": [],
                "skills_required": ["Backend Developer"],
            }
        }

        result = planner._build_wbs_from_skeleton(analysis, skeleton, generated_tasks)
        wp = result["wbs"]["phases"][0]["work_packages"][0]
        task = wp["tasks"][0]

        self.assertEqual(wp["requirement_ids"], ["FR-1"])
        self.assertEqual(task["requirement_ids"], ["FR-1"])

    def test_planner_validation_rejects_tasks_outside_parent_requirements(self):
        planner = self._planner()
        wbs = {
            "wbs": {
                "phases": [
                    {
                        "id": "1",
                        "work_packages": [
                            {
                                "id": "1.1",
                                "requirement_ids": ["FR-1"],
                                "tasks": [
                                    {"id": "1.1.1", "requirement_ids": ["FR-2"]},
                                ],
                            }
                        ],
                    }
                ]
            }
        }

        validation = planner.validate_wbs(wbs)

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any("references requirements outside work package" in issue for issue in validation["issues"])
        )

    def test_validator_normalize_enforces_parent_subset_and_inherits_missing_ids(self):
        validator = self._validator()
        wbs = {
            "project_info": {"total_estimated_hours": 0},
            "wbs": {
                "phases": [
                    {
                        "id": "1",
                        "estimated_hours": 0,
                        "work_packages": [
                            {
                                "id": "1.1",
                                "estimated_hours": 0,
                                "requirement_ids": ["FR-1"],
                                "tasks": [
                                    {
                                        "id": "1.1.1",
                                        "name": "Реализация",
                                        "estimated_hours": 8,
                                        "requirement_ids": ["FR-2", "FR-1"],
                                    },
                                    {
                                        "id": "1.1.2",
                                        "name": "Проверка",
                                        "estimated_hours": 8,
                                        "requirement_ids": [],
                                    },
                                ],
                            }
                        ],
                    }
                ]
            },
        }

        normalized = validator.normalize_wbs(wbs)
        tasks = normalized["wbs"]["phases"][0]["work_packages"][0]["tasks"]

        self.assertEqual(tasks[0]["requirement_ids"], ["FR-1"])
        self.assertEqual(tasks[1]["requirement_ids"], ["FR-1"])
        self.assertEqual(normalized["wbs"]["phases"][0]["work_packages"][0]["estimated_hours"], 16)

    def test_orchestrator_coverage_uses_requirement_ids_before_name_fallback(self):
        orchestrator = self._orchestrator()
        analysis = {
            "functional_requirements": [
                {"id": "FR-1", "name": "Авторизация пользователей"},
                {"id": "FR-2", "name": "Аудит действий пользователей"},
            ]
        }
        wbs = {
            "wbs": {
                "phases": [
                    {
                        "name": "Разработка",
                        "work_packages": [
                            {
                                "id": "1.1",
                                "name": "Модуль авторизации",
                                "requirement_ids": ["FR-1"],
                                "tasks": [
                                    {
                                        "id": "1.1.1",
                                        "name": "Реализовать login/logout",
                                        "requirement_ids": ["FR-1"],
                                    }
                                ],
                            },
                            {
                                "id": "1.2",
                                "name": "Журналирование событий",
                                "requirement_ids": [],
                                "tasks": [
                                    {
                                        "id": "1.2.1",
                                        "name": "Настроить аудит действий пользователей",
                                        "requirement_ids": [],
                                    }
                                ],
                            },
                        ],
                    }
                ]
            }
        }

        coverage = orchestrator._check_requirements_coverage(analysis, wbs)

        self.assertEqual(coverage["total"], 2)
        self.assertEqual(coverage["covered_count"], 2)
        self.assertEqual(coverage["covered_count_by_ids"], 1)
        self.assertEqual(coverage["covered_count_by_name_fallback"], 1)
        self.assertEqual(coverage["uncovered"], [])

        coverage_by_requirement = {
            item["requirement_id"]: item for item in coverage["coverage_matrix"]
        }
        self.assertTrue(coverage_by_requirement["FR-1"]["covered_by_ids"])
        self.assertFalse(coverage_by_requirement["FR-1"]["covered_by_name_fallback"])
        self.assertFalse(coverage_by_requirement["FR-2"]["covered_by_ids"])
        self.assertTrue(coverage_by_requirement["FR-2"]["covered_by_name_fallback"])

    def test_validator_flags_total_hours_outside_project_baseline_range(self):
        validator = self._validator()
        tasks = [
            {"id": "1.1.1", "name": "API backend task 1", "estimated_hours": 75, "requirement_ids": ["FR-1"]},
            {"id": "1.1.2", "name": "API backend task 2", "estimated_hours": 75, "requirement_ids": ["FR-1"]},
            {"id": "1.1.3", "name": "API backend task 3", "estimated_hours": 75, "requirement_ids": ["FR-1"]},
            {"id": "1.1.4", "name": "API backend task 4", "estimated_hours": 75, "requirement_ids": ["FR-1"]},
        ]
        wbs = {
            "project_info": {
                "project_name": "Payments API",
                "project_type": "API сервис",
                "complexity_level": "Высокий",
                "total_estimated_hours": 900,
            },
            "wbs": {
                "phases": [
                    {
                        "id": "1",
                        "name": "Планирование",
                        "duration": "38 дней",
                        "estimated_hours": 300,
                        "work_packages": [
                            {"id": "1.1", "name": "План", "estimated_hours": 300, "requirement_ids": ["FR-1"], "tasks": tasks}
                        ],
                    },
                    {
                        "id": "2",
                        "name": "Разработка",
                        "duration": "38 дней",
                        "estimated_hours": 300,
                        "work_packages": [
                            {"id": "2.1", "name": "Реализация", "estimated_hours": 300, "requirement_ids": ["FR-1"], "tasks": tasks}
                        ],
                    },
                    {
                        "id": "3",
                        "name": "Тестирование",
                        "duration": "38 дней",
                        "estimated_hours": 300,
                        "work_packages": [
                            {"id": "3.1", "name": "Проверка", "estimated_hours": 300, "requirement_ids": ["FR-1"], "tasks": tasks}
                        ],
                    },
                ]
            },
        }

        result = validator.validate_wbs(wbs)

        self.assertTrue(
            any(
                "outside expected range" in issue["message"]
                for issue in result.issues + result.warnings
            )
        )
        self.assertLess(result.confidence_score, 0.9)


if __name__ == "__main__":
    unittest.main()
