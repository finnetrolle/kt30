import unittest

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
        return validator

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


if __name__ == "__main__":
    unittest.main()
