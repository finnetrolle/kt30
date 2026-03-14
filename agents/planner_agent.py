"""
WBS Planner Agent.
Creates Work Breakdown Structure based on analysis from the Analyst Agent.
"""
import copy
import json
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import Config
from wbs_utils import canonicalize_wbs_result

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """Agent responsible for creating Work Breakdown Structure."""

    STANDARD_PHASES = [
        ("Планирование и анализ", "Уточнение объема проекта, декомпозиция требований и план работ."),
        ("Проектирование", "Архитектурное, UX/UI и техническое проектирование решения."),
        ("Разработка", "Реализация функциональных и интеграционных требований."),
        ("Тестирование", "Проверка качества, сценариев использования и нефункциональных требований."),
        ("Развертывание", "Подготовка окружений, релиз и передача в эксплуатацию.")
    ]

    def __init__(self):
        """Initialize the WBS Planner Agent."""
        super().__init__(
            name="Планировщик WBS",
            role="Создает детальную структуру работ (WBS) на основе анализа требований"
        )
        self._estimation_rules = self._load_estimation_rules()

    def _load_estimation_rules(self) -> Dict[str, Any]:
        """Load estimation rules from JSON file."""
        rules_path = Path(__file__).parent.parent / "data" / "estimation_rules.json"
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load estimation rules: {e}")
            return {}

    def _normalize_space(self, value: Any) -> str:
        """Normalize text spacing."""
        return " ".join(str(value or "").strip().split())

    def _truncate(self, value: Any, limit: int = 160) -> str:
        """Truncate long strings for compact prompts."""
        text = self._normalize_space(value)
        return text if len(text) <= limit else text[:limit - 3] + "..."

    def _build_system_prompt(self) -> str:
        """Build the default system prompt for the Planner Agent."""
        return """Ты — опытный проектный менеджер и планировщик разработки ПО.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON.
Не добавляй комментарии и не используй markdown.
Все оценки часов и длительности возвращай числами."""

    def _build_skeleton_system_prompt(self) -> str:
        """Build a compact prompt for phase/work-package planning."""
        phase_lines = "\n".join(f"- {name}: {description}" for name, description in self.STANDARD_PHASES)
        if Config.SMALL_LLM_MODE:
            return f"""Ты планировщик.

Верни только JSON:
- project_info
- phase_plan
- risks
- assumptions
- recommendations

Требования:
- используй только стандартные фазы
- не создавай tasks
- requirement_ids должны ссылаться на FR
- пакеты работ делай короткими
{phase_lines}"""

        return f"""Ты проектный планировщик. Тебе нужно создать компактный каркас WBS без детальных задач.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON.
Верни JSON вида:
{{
  "project_info": {{
    "project_name": "Название проекта",
    "description": "Краткое описание",
    "estimated_duration": "8-16 недель",
    "complexity_level": "Средний"
  }},
  "phase_plan": [
    {{
      "name": "Разработка",
      "description": "Что входит в фазу",
      "work_packages": [
        {{
          "name": "Пакет работ",
          "description": "Краткое описание",
          "requirement_ids": ["FR-1"],
          "dependencies": [],
          "can_start_parallel": false,
          "deliverables": [],
          "skills_required": []
        }}
      ]
    }}
  ],
  "risks": [],
  "assumptions": [],
  "recommendations": [
    {{
      "category": "Процесс",
      "priority": "Средний",
      "recommendation": "Текст рекомендации"
    }}
  ]
}}

Используй только стандартные фазы:
{phase_lines}

Правила:
- requirement_ids должны ссылаться на переданные FR-идентификаторы.
- Каждый пакет работ должен покрывать 1-5 требований или один технический блок.
- Не создавай tasks на этом шаге.
- Все 5 стандартных фаз должны присутствовать.
- Возвращай компактный и практичный план."""

    def _build_tasks_system_prompt(self, template_reference: str) -> str:
        """Build a prompt for generating tasks inside one work package."""
        if Config.SMALL_LLM_MODE:
            return f"""Ты планировщик.

Верни только JSON:
{{
  "tasks": [],
  "deliverables": [],
  "skills_required": []
}}

Правила:
- 2-5 коротких задач
- estimated_hours число
- depends_on только внутри пакета
- без лишнего текста
{template_reference}"""

        return f"""Ты проектный планировщик. Тебе нужно детализировать ОДИН пакет работ.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON.
Верни JSON вида:
{{
  "tasks": [
    {{
      "name": "Название задачи",
      "description": "Краткое описание",
      "estimated_hours": 8,
      "skills_required": ["Backend Developer"],
      "depends_on": [],
      "can_start_parallel": false
    }}
  ],
  "deliverables": [],
  "skills_required": []
}}

Правила:
- Сгенерируй 2-6 атомарных задач.
- estimated_hours должен быть числом в диапазоне 2-80.
- depends_on может ссылаться только на названия задач из того же пакета.
- can_start_parallel=true только если задача реально независима.
- Используй краткие и конкретные формулировки.
{template_reference}"""

    def _build_compact_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Build a compact analysis snapshot for prompts."""
        description_limit = 140 if Config.SMALL_LLM_MODE else 220
        requirement_limit = 90 if Config.SMALL_LLM_MODE else 140
        return {
            "project_info": {
                "project_name": analysis.get("project_info", {}).get("project_name", ""),
                "description": self._truncate(analysis.get("project_info", {}).get("description", ""), description_limit),
                "project_type": analysis.get("project_info", {}).get("project_type", ""),
                "estimated_duration": analysis.get("project_info", {}).get("estimated_duration", ""),
                "complexity_level": analysis.get("project_info", {}).get("complexity_level", "")
            },
            "functional_requirements": [
                {
                    "id": req.get("id", ""),
                    "name": req.get("name", ""),
                    "category": req.get("category", ""),
                    "priority": req.get("priority", ""),
                    "description": self._truncate(req.get("description", ""), requirement_limit)
                }
                for req in analysis.get("functional_requirements", [])
            ],
            "non_functional_requirements": [
                {
                    "id": req.get("id", ""),
                    "name": req.get("name", ""),
                    "category": req.get("category", ""),
                    "description": self._truncate(req.get("description", ""), requirement_limit)
                }
                for req in analysis.get("non_functional_requirements", [])
            ],
            "technical_constraints": analysis.get("technical_constraints", {}),
            "risks": analysis.get("risks", [])[:5],
            "assumptions": analysis.get("assumptions", [])[:10]
        }

    def _guess_phase_for_requirement(self, requirement: Dict[str, Any]) -> str:
        """Map a requirement category to the most likely implementation phase."""
        text = " ".join([
            self._normalize_space(requirement.get("category")),
            self._normalize_space(requirement.get("name")),
            self._normalize_space(requirement.get("description"))
        ]).lower()

        if any(token in text for token in ["ui", "ux", "интерфейс", "экран", "форма", "дизайн"]):
            return "Проектирование"
        if any(token in text for token in ["тест", "qa", "качество"]):
            return "Тестирование"
        if any(token in text for token in ["деплой", "релиз", "развер", "infra", "ci/cd", "docker"]):
            return "Развертывание"
        return "Разработка"

    def _guess_skills(self, text: str) -> List[str]:
        """Guess required skills from a requirement or package description."""
        normalized = self._normalize_space(text).lower()
        skills = []
        if any(token in normalized for token in ["ui", "ux", "интерфейс", "форма", "страница", "дашборд"]):
            skills.append("Frontend Developer")
            skills.append("UI/UX Designer")
        if any(token in normalized for token in ["api", "интеграц", "backend", "сервис", "логика", "данн"]):
            skills.append("Backend Developer")
        if any(token in normalized for token in ["безопас", "rbac", "oauth", "2fa"]):
            skills.append("Security Engineer")
        if any(token in normalized for token in ["база", "sql", "данн", "миграц"]):
            skills.append("Database Engineer")
        if any(token in normalized for token in ["деплой", "docker", "kubernetes", "сервер", "ci/cd"]):
            skills.append("DevOps Engineer")
        if any(token in normalized for token in ["тест", "qa", "качество"]):
            skills.append("QA Engineer")
        if not skills:
            skills.extend(["Backend Developer", "QA Engineer"])

        unique: List[str] = []
        seen = set()
        for skill in skills:
            if skill not in seen:
                unique.append(skill)
                seen.add(skill)
        return unique

    def _build_fallback_skeleton(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Build a deterministic skeleton if the LLM skeleton call fails."""
        requirements = analysis.get("functional_requirements", [])
        by_phase: Dict[str, List[Dict[str, Any]]] = {
            phase_name: [] for phase_name, _ in self.STANDARD_PHASES
        }
        for requirement in requirements:
            by_phase[self._guess_phase_for_requirement(requirement)].append(requirement)

        phase_plan = []
        for phase_name, phase_description in self.STANDARD_PHASES:
            work_packages = []
            if phase_name == "Планирование и анализ":
                work_packages.append({
                    "name": "Анализ требований и границ проекта",
                    "description": "Уточнение состава работ, зависимостей и критериев готовности.",
                    "requirement_ids": [req.get("id") for req in requirements[:6] if req.get("id")],
                    "dependencies": [],
                    "can_start_parallel": False,
                    "deliverables": ["Подтвержденный scope проекта"],
                    "skills_required": ["Business Analyst", "Project Manager"]
                })
            elif phase_name == "Проектирование":
                design_requirements = by_phase.get("Проектирование") or requirements[:4]
                work_packages.append({
                    "name": "Проектирование решения и пользовательских сценариев",
                    "description": "Архитектура, схема данных и дизайн ключевых сценариев.",
                    "requirement_ids": [req.get("id") for req in design_requirements if req.get("id")],
                    "dependencies": ["Анализ требований и границ проекта"],
                    "can_start_parallel": False,
                    "deliverables": ["Архитектурные и UX артефакты"],
                    "skills_required": ["Solution Architect", "UI/UX Designer"]
                })
            elif phase_name == "Разработка":
                grouped: Dict[str, List[Dict[str, Any]]] = {}
                for req in by_phase.get("Разработка", []) or requirements:
                    category = self._normalize_space(req.get("category")) or "Функциональный блок"
                    grouped.setdefault(category, []).append(req)
                for category, items in grouped.items():
                    work_packages.append({
                        "name": f"Реализация блока: {category}",
                        "description": f"Разработка функционала по направлению '{category}'.",
                        "requirement_ids": [req.get("id") for req in items if req.get("id")],
                        "dependencies": ["Проектирование решения и пользовательских сценариев"],
                        "can_start_parallel": len(grouped) > 1,
                        "deliverables": [f"Готовый функционал по блоку '{category}'"],
                        "skills_required": self._guess_skills(" ".join(
                            item.get("name", "") for item in items
                        ))
                    })
            elif phase_name == "Тестирование":
                work_packages.append({
                    "name": "Функциональное и интеграционное тестирование",
                    "description": "Проверка реализованных сценариев, регрессия и дефекты.",
                    "requirement_ids": [req.get("id") for req in requirements if req.get("id")],
                    "dependencies": [wp.get("name") for wp in phase_plan[-1].get("work_packages", [])] if phase_plan else [],
                    "can_start_parallel": False,
                    "deliverables": ["Набор тестовых сценариев и отчет по дефектам"],
                    "skills_required": ["QA Engineer", "Backend Developer"]
                })
            else:
                work_packages.append({
                    "name": "Подготовка релиза и ввод в эксплуатацию",
                    "description": "Сборка, настройка окружений, публикация и передача результатов.",
                    "requirement_ids": [],
                    "dependencies": ["Функциональное и интеграционное тестирование"],
                    "can_start_parallel": False,
                    "deliverables": ["Релиз в целевом окружении", "Эксплуатационная документация"],
                    "skills_required": ["DevOps Engineer", "Project Manager"]
                })

            phase_plan.append({
                "name": phase_name,
                "description": phase_description,
                "work_packages": work_packages
            })

        return {
            "project_info": analysis.get("project_info", {}),
            "phase_plan": phase_plan,
            "risks": analysis.get("risks", [])[:5],
            "assumptions": analysis.get("assumptions", [])[:10],
            "recommendations": [
                {
                    "category": "Процесс",
                    "priority": "Средний",
                    "recommendation": "Уточнить критерии приемки для ключевых функциональных блоков."
                }
            ]
        }

    def _normalize_phase_plan(self, skeleton: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure the skeleton has all standard phases and covered requirements."""
        phases_by_name = {
            self._normalize_space(phase.get("name")): phase
            for phase in skeleton.get("phase_plan", [])
            if self._normalize_space(phase.get("name"))
        }
        fallback = self._build_fallback_skeleton(analysis)
        normalized_phases = []

        for phase_name, phase_description in self.STANDARD_PHASES:
            phase = phases_by_name.get(phase_name) or next(
                (item for item in fallback["phase_plan"] if item.get("name") == phase_name),
                {"name": phase_name, "description": phase_description, "work_packages": []}
            )

            work_packages = []
            for wp in phase.get("work_packages", []):
                name = self._normalize_space(wp.get("name"))
                if not name:
                    continue
                work_packages.append({
                    "name": name,
                    "description": self._normalize_space(wp.get("description")) or name,
                    "requirement_ids": [
                        req_id for req_id in wp.get("requirement_ids", []) if req_id
                    ],
                    "dependencies": self._dedupe_strings(wp.get("dependencies", [])),
                    "can_start_parallel": bool(wp.get("can_start_parallel", False)),
                    "deliverables": self._dedupe_strings(wp.get("deliverables", [])),
                    "skills_required": self._dedupe_strings(wp.get("skills_required", []))
                })

            if not work_packages:
                phase = next(
                    item for item in fallback["phase_plan"] if item.get("name") == phase_name
                )
                work_packages = phase.get("work_packages", [])

            normalized_phases.append({
                "name": phase_name,
                "description": self._normalize_space(phase.get("description")) or phase_description,
                "work_packages": work_packages
            })

        covered = set()
        for phase in normalized_phases:
            for wp in phase["work_packages"]:
                covered.update(wp.get("requirement_ids", []))

        missing_requirements = [
            req for req in analysis.get("functional_requirements", [])
            if req.get("id") and req.get("id") not in covered
        ]
        if missing_requirements:
            dev_phase = next(
                phase for phase in normalized_phases if phase.get("name") == "Разработка"
            )
            for req in missing_requirements:
                dev_phase["work_packages"].append({
                    "name": f"Реализация требования: {req.get('name', req.get('id'))}",
                    "description": self._truncate(req.get("description", req.get("name", "")), 140),
                    "requirement_ids": [req.get("id")],
                    "dependencies": ["Проектирование решения и пользовательских сценариев"],
                    "can_start_parallel": True,
                    "deliverables": [f"Реализовано требование {req.get('id')}"],
                    "skills_required": self._guess_skills(
                        " ".join([req.get("name", ""), req.get("category", ""), req.get("description", "")])
                    )
                })

        skeleton["phase_plan"] = normalized_phases
        if not skeleton.get("project_info"):
            skeleton["project_info"] = analysis.get("project_info", {})
        skeleton["risks"] = skeleton.get("risks") or analysis.get("risks", [])[:5]
        skeleton["assumptions"] = self._dedupe_strings(
            (skeleton.get("assumptions") or []) + (analysis.get("assumptions") or [])
        )[:10]
        skeleton["recommendations"] = skeleton.get("recommendations") or [
            {
                "category": "Процесс",
                "priority": "Средний",
                "recommendation": "Зафиксировать владельцев по интеграциям и приемочным сценариям."
            }
        ]
        return skeleton

    def _dedupe_strings(self, values: List[Any]) -> List[str]:
        """Deduplicate a list of strings preserving order."""
        result = []
        seen = set()
        for value in values:
            normalized = self._normalize_space(value)
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(normalized)
        return result

    def _select_relevant_templates(self, context_text: str, limit: int = 8) -> str:
        """Select a small subset of relevant estimation templates."""
        templates = self._estimation_rules.get("task_templates", {})
        if not templates:
            return ""

        text = self._normalize_space(context_text).lower()
        scored: List[Tuple[int, str]] = []
        fallback: List[str] = []

        for category, tasks in templates.items():
            for task_name, estimation in tasks.items():
                label = f"{category} / {task_name}"
                line = (
                    f"- {label}: {estimation.get('min_hours', 2)}-"
                    f"{estimation.get('max_hours', 80)} ч, типично "
                    f"{estimation.get('typical_hours', 8)} ч"
                )
                tokens = set(re.findall(r"[a-zA-Zа-яА-Я0-9]+", f"{category} {task_name}".lower()))
                score = sum(1 for token in tokens if len(token) > 3 and token in text)
                if score > 0:
                    scored.append((score, line))
                elif task_name in {"CRUD (базовый)", "Интеграция (типовая)", "Integration тесты", "README"}:
                    fallback.append(line)

        lines = [line for _, line in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]
        if len(lines) < limit:
            for line in fallback:
                if line not in lines:
                    lines.append(line)
                if len(lines) >= limit:
                    break

        if not lines:
            return ""
        return "\nОриентиры по трудозатратам:\n" + "\n".join(lines)

    def _build_tasks_message(
        self,
        analysis: Dict[str, Any],
        phase: Dict[str, Any],
        work_package: Dict[str, Any]
    ) -> str:
        """Build a small task-generation prompt for one work package."""
        requirement_ids = set(work_package.get("requirement_ids", []))
        related_requirements = [
            {
                "id": req.get("id", ""),
                "name": req.get("name", ""),
                "category": req.get("category", ""),
                "priority": req.get("priority", ""),
                "description": self._truncate(req.get("description", ""), 140)
            }
            for req in analysis.get("functional_requirements", [])
            if req.get("id") in requirement_ids
        ]
        related_nfr = [
            {
                "name": req.get("name", ""),
                "category": req.get("category", ""),
                "description": self._truncate(req.get("description", ""), 120)
            }
            for req in analysis.get("non_functional_requirements", [])[:5]
        ]

        compact_context = {
            "project": {
                "name": analysis.get("project_info", {}).get("project_name", ""),
                "type": analysis.get("project_info", {}).get("project_type", ""),
                "complexity": analysis.get("project_info", {}).get("complexity_level", "")
            },
            "phase": {
                "name": phase.get("name", ""),
                "description": phase.get("description", "")
            },
            "work_package": {
                "name": work_package.get("name", ""),
                "description": work_package.get("description", ""),
                "dependencies": work_package.get("dependencies", []),
                "deliverables": work_package.get("deliverables", []),
                "skills_required": work_package.get("skills_required", [])
            },
            "requirements": related_requirements,
            "non_functional_requirements": related_nfr,
            "technical_constraints": analysis.get("technical_constraints", {})
        }

        return (
            "Детализируй пакет работ в набор задач.\n\n"
            f"Контекст:\n{json.dumps(compact_context, ensure_ascii=False, indent=2)}\n\n"
            "JSON:"
        )

    def _should_use_llm_for_work_package(self, phase: Dict[str, Any], work_package: Dict[str, Any]) -> bool:
        """Decide whether this package should be delegated to LLM."""
        if not Config.SMALL_LLM_MODE:
            return True
        if not Config.SMALL_LLM_ONLY_DEV_LLM_TASKS:
            return True
        if phase.get("name") != "Разработка":
            return False
        return bool(work_package.get("requirement_ids"))

    def _generate_tasks_for_work_package(
        self,
        analysis: Dict[str, Any],
        phase: Dict[str, Any],
        work_package: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate tasks for a single work package."""
        if not self._should_use_llm_for_work_package(phase, work_package):
            return {
                "success": True,
                "data": self._fallback_tasks_for_work_package(phase, work_package),
                "metadata": {
                    "used_fallback_tasks": True,
                    "reason": "small_llm_policy"
                }
            }

        context_text = " ".join([
            phase.get("name", ""),
            work_package.get("name", ""),
            work_package.get("description", ""),
            " ".join(work_package.get("deliverables", []))
        ])
        template_reference = self._select_relevant_templates(context_text)
        worker = PlannerAgent()
        if self._progress_tracker:
            worker.set_progress_tracker(self._progress_tracker, stream_events=False)
        result = worker.send_message(
            worker._build_tasks_message(analysis, phase, work_package),
            expect_json=True,
            use_history=False,
            max_tokens=Config.WBS_TASKS_MAX_TOKENS,
            temperature=0.0,
            system_prompt=worker._build_tasks_system_prompt(template_reference)
        )
        return result

    def _fallback_tasks_for_work_package(self, phase: Dict[str, Any], work_package: Dict[str, Any]) -> Dict[str, Any]:
        """Create deterministic fallback tasks."""
        skills = work_package.get("skills_required") or self._guess_skills(
            " ".join([phase.get("name", ""), work_package.get("name", ""), work_package.get("description", "")])
        )
        return {
            "tasks": [
                {
                    "name": "Подготовка пакета работ",
                    "description": "Уточнение входных данных, ограничений и подхода к реализации.",
                    "estimated_hours": 4,
                    "skills_required": skills,
                    "depends_on": [],
                    "can_start_parallel": False
                },
                {
                    "name": "Реализация основного объема работ",
                    "description": "Выполнение ключевых работ по пакету.",
                    "estimated_hours": 12,
                    "skills_required": skills,
                    "depends_on": ["Подготовка пакета работ"],
                    "can_start_parallel": False
                },
                {
                    "name": "Проверка и фиксация результата",
                    "description": "Самопроверка, доработка и передача результата.",
                    "estimated_hours": 4,
                    "skills_required": skills,
                    "depends_on": ["Реализация основного объема работ"],
                    "can_start_parallel": False
                }
            ],
            "deliverables": work_package.get("deliverables", []),
            "skills_required": skills
        }

    def _coerce_hours(self, value: Any, default: int = 8) -> int:
        """Coerce LLM output to an integer hour estimate."""
        if isinstance(value, (int, float)):
            return int(round(value))
        text = self._normalize_space(value)
        match = re.search(r"\d+(?:\.\d+)?", text)
        if match:
            try:
                return int(round(float(match.group())))
            except ValueError:
                return default
        return default

    def _build_wbs_from_skeleton(
        self,
        analysis: Dict[str, Any],
        skeleton: Dict[str, Any],
        generated_tasks: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Assemble final WBS from the compact skeleton and task bundles."""
        phases = []
        wp_name_to_id: Dict[str, str] = {}

        for phase_index, phase in enumerate(skeleton.get("phase_plan", []), start=1):
            phase_id = str(phase_index)
            assembled_phase = {
                "id": phase_id,
                "name": phase.get("name", f"Фаза {phase_index}"),
                "description": phase.get("description", ""),
                "duration": 0,
                "estimated_hours": 0,
                "work_packages": []
            }

            for wp_index, wp in enumerate(phase.get("work_packages", []), start=1):
                wp_id = f"{phase_id}.{wp_index}"
                wp_key = wp.get("_key") or self._normalize_space(wp.get("name")).lower()
                task_bundle = generated_tasks.get(wp_key) or self._fallback_tasks_for_work_package(phase, wp)
                tasks_raw = task_bundle.get("tasks", []) or self._fallback_tasks_for_work_package(phase, wp).get("tasks", [])

                task_name_to_id = {}
                assembled_tasks = []
                for task_index, task in enumerate(tasks_raw, start=1):
                    task_id = f"{wp_id}.{task_index}"
                    name = self._normalize_space(task.get("name")) or f"Задача {task_index}"
                    task_hours = max(2, min(80, self._coerce_hours(task.get("estimated_hours", 8))))
                    assembled_task = {
                        "id": task_id,
                        "name": name,
                        "description": self._normalize_space(task.get("description")) or name,
                        "estimated_hours": task_hours,
                        "duration_days": math.ceil(task_hours / 8),
                        "status": "pending",
                        "skills_required": self._dedupe_strings(
                            task.get("skills_required", []) or task_bundle.get("skills_required", []) or wp.get("skills_required", [])
                        ),
                        "dependencies": [],
                        "can_start_parallel": bool(task.get("can_start_parallel", False))
                    }
                    task_name_to_id[name.lower()] = task_id
                    assembled_tasks.append(assembled_task)

                for task, raw in zip(assembled_tasks, tasks_raw):
                    dependencies = []
                    for dep_name in raw.get("depends_on", []):
                        dep_id = task_name_to_id.get(self._normalize_space(dep_name).lower())
                        if dep_id and dep_id != task["id"]:
                            dependencies.append(dep_id)
                    task["dependencies"] = dependencies

                wp_hours = sum(task["estimated_hours"] for task in assembled_tasks)
                assembled_wp = {
                    "id": wp_id,
                    "name": wp.get("name", f"Пакет {wp_id}"),
                    "description": wp.get("description", ""),
                    "estimated_hours": wp_hours,
                    "duration_days": math.ceil(wp_hours / 8),
                    "dependencies": [],
                    "can_start_parallel": bool(wp.get("can_start_parallel", False)),
                    "deliverables": self._dedupe_strings(
                        (task_bundle.get("deliverables") or []) + (wp.get("deliverables") or [])
                    ),
                    "skills_required": self._dedupe_strings(
                        (task_bundle.get("skills_required") or []) + (wp.get("skills_required") or [])
                    ),
                    "_dependencies": wp.get("_dependencies", []),
                    "tasks": assembled_tasks
                }
                wp_name_to_id[self._normalize_space(assembled_wp["name"]).lower()] = wp_id
                assembled_phase["work_packages"].append(assembled_wp)

            for wp in assembled_phase["work_packages"]:
                wp["dependencies"] = [
                    wp_name_to_id[dep.lower()]
                    for dep in wp.get("_dependencies", [])
                    if dep.lower() in wp_name_to_id
                ]
                wp.pop("_dependencies", None)

            assembled_phase["estimated_hours"] = sum(
                wp["estimated_hours"] for wp in assembled_phase["work_packages"]
            )
            assembled_phase["duration"] = math.ceil(assembled_phase["estimated_hours"] / 8)
            phases.append(assembled_phase)

        total_hours = sum(phase["estimated_hours"] for phase in phases)
        project_info = {
            "project_name": skeleton.get("project_info", {}).get(
                "project_name",
                analysis.get("project_info", {}).get("project_name", "Проект")
            ),
            "description": skeleton.get("project_info", {}).get(
                "description",
                analysis.get("project_info", {}).get("description", "")
            ),
            "project_type": skeleton.get("project_info", {}).get(
                "project_type",
                analysis.get("project_info", {}).get("project_type", "")
            ),
            "estimated_duration": f"{max(1, round(total_hours / 40))} недель",
            "complexity_level": skeleton.get("project_info", {}).get(
                "complexity_level",
                analysis.get("project_info", {}).get("complexity_level", "Средний")
            ),
            "total_estimated_hours": total_hours
        }

        risks = []
        for idx, risk in enumerate(skeleton.get("risks", [])[:5], start=1):
            risks.append({
                "id": risk.get("id", f"R-{idx}"),
                "description": risk.get("description", ""),
                "probability": risk.get("probability", "Средняя"),
                "impact": risk.get("impact", "Среднее"),
                "mitigation": risk.get("mitigation", "")
            })

        recommendations = []
        for rec in skeleton.get("recommendations", [])[:5]:
            recommendations.append({
                "category": rec.get("category", "Процесс"),
                "priority": rec.get("priority", "Средний"),
                "recommendation": rec.get("recommendation", "")
            })

        return {
            "project_info": project_info,
            "wbs": {"phases": phases},
            "risks": risks,
            "assumptions": self._dedupe_strings(skeleton.get("assumptions", [])),
            "recommendations": recommendations
        }

    def create_wbs(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create WBS based on the analysis from Analyst Agent."""
        logger.info(f"[{self.name}] Starting WBS creation...")

        compact_analysis = self._build_compact_analysis(analysis)
        self._record_intermediate("planning_started", {"compact_analysis": compact_analysis})
        skeleton_message = (
            "Построй каркас WBS на основе компактного анализа проекта.\n\n"
            f"Анализ:\n{json.dumps(compact_analysis, ensure_ascii=False, indent=2)}\n\n"
            "JSON:"
        )

        skeleton_result = None
        if Config.ENABLE_WBS_SKELETON_LLM:
            skeleton_result = self.send_message(
                skeleton_message,
                expect_json=True,
                use_history=False,
                max_tokens=Config.WBS_SKELETON_MAX_TOKENS,
                temperature=0.0,
                system_prompt=self._build_skeleton_system_prompt()
            )

        if skeleton_result and skeleton_result.get("success"):
            skeleton = skeleton_result["data"]
        else:
            if skeleton_result is not None:
                logger.warning(
                    f"[{self.name}] Skeleton generation failed, using fallback: "
                    f"{skeleton_result.get('error')}"
                )
            else:
                logger.info(f"[{self.name}] LLM skeleton disabled, using deterministic skeleton")
            skeleton = self._build_fallback_skeleton(analysis)

        skeleton = self._normalize_phase_plan(skeleton, analysis)
        self._record_intermediate(
            "skeleton_ready",
            {
                "used_llm_skeleton": bool(skeleton_result and skeleton_result.get("success")),
                "skeleton": skeleton
            }
        )

        if self._progress_tracker:
            total_wp = sum(len(phase.get("work_packages", [])) for phase in skeleton.get("phase_plan", []))
            self._progress_tracker.info(
                f"🧱 Планировщик собрал каркас WBS: {len(skeleton.get('phase_plan', []))} фаз, {total_wp} пакетов работ"
            )

        work_items = []
        for phase in skeleton.get("phase_plan", []):
            for wp in phase.get("work_packages", []):
                key = self._normalize_space(wp.get("name")).lower()
                wp["_key"] = key
                wp["_dependencies"] = self._dedupe_strings(wp.get("dependencies", []))
                work_items.append((phase, wp))

        generated_tasks: Dict[str, Dict[str, Any]] = {}
        llm_task_requests = 0
        fallback_task_packages = 0
        max_workers = max(1, min(Config.LLM_MAX_PARALLEL_REQUESTS, len(work_items) or 1))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._generate_tasks_for_work_package, analysis, phase, wp): wp["_key"]
                for phase, wp in work_items
            }
            for future in as_completed(futures):
                wp_key = futures[future]
                try:
                    result = future.result()
                    if result.get("success"):
                        generated_tasks[wp_key] = result.get("data", {})
                        if result.get("metadata", {}).get("used_fallback_tasks"):
                            fallback_task_packages += 1
                        else:
                            llm_task_requests += 1
                    else:
                        generated_tasks[wp_key] = {}
                        llm_task_requests += 1
                except Exception as exc:
                    logger.exception(f"[{self.name}] Failed to generate tasks for {wp_key}: {exc}")
                    generated_tasks[wp_key] = {}
                    llm_task_requests += 1

        wbs = self._build_wbs_from_skeleton(analysis, skeleton, generated_tasks)
        self._record_intermediate(
            "tasks_generated",
            {
                "generated_tasks": generated_tasks,
                "llm_task_requests": llm_task_requests,
                "fallback_task_packages": fallback_task_packages
            }
        )
        self._record_intermediate(
            "wbs_completed",
            {
                "wbs": wbs,
                "metadata": {
                    "skeleton_phases": len(skeleton.get("phase_plan", [])),
                    "task_generation_requests": llm_task_requests,
                    "fallback_task_packages": fallback_task_packages,
                    "used_llm_skeleton": bool(skeleton_result and skeleton_result.get("success"))
                }
            }
        )

        logger.info(f"[{self.name}] WBS creation completed successfully")
        return {
            "success": True,
            "wbs": wbs,
            "metadata": {
                "skeleton_phases": len(skeleton.get("phase_plan", [])),
                "task_generation_requests": llm_task_requests,
                "fallback_task_packages": fallback_task_packages,
                "used_llm_skeleton": bool(skeleton_result and skeleton_result.get("success"))
            }
        }

    def _compact_wbs_for_review(self, wbs: Dict[str, Any]) -> Dict[str, Any]:
        """Build a compact WBS snapshot for review/refinement prompts."""
        phases = []
        for phase in wbs.get("wbs", {}).get("phases", []):
            phases.append({
                "id": phase.get("id", ""),
                "name": phase.get("name", ""),
                "description": phase.get("description", ""),
                "estimated_hours": phase.get("estimated_hours", 0),
                "work_packages": [
                    {
                        "id": wp.get("id", ""),
                        "name": wp.get("name", ""),
                        "description": wp.get("description", ""),
                        "estimated_hours": wp.get("estimated_hours", 0),
                        "dependencies": wp.get("dependencies", []),
                        "deliverables": wp.get("deliverables", []),
                        "skills_required": wp.get("skills_required", []),
                        "can_start_parallel": wp.get("can_start_parallel", False),
                        "tasks": [
                            {
                                "id": task.get("id", ""),
                                "name": task.get("name", ""),
                                "description": task.get("description", ""),
                                "estimated_hours": task.get("estimated_hours", 0),
                                "skills_required": task.get("skills_required", []),
                                "dependencies": task.get("dependencies", []),
                                "can_start_parallel": task.get("can_start_parallel", False)
                            }
                            for task in wp.get("tasks", [])[:8]
                        ]
                    }
                    for wp in phase.get("work_packages", [])[:8]
                ]
            })
        return {
            "project_info": wbs.get("project_info", {}),
            "wbs": {
                "phases": phases
            },
            "risks": wbs.get("risks", [])[:5],
            "assumptions": wbs.get("assumptions", [])[:10],
            "recommendations": wbs.get("recommendations", [])[:5]
        }

    def _match_existing_item(self, items: List[Dict[str, Any]], candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Find an existing item by ID first, then by normalized name."""
        candidate_id = self._normalize_space(candidate.get("id"))
        if candidate_id:
            for item in items:
                if self._normalize_space(item.get("id")) == candidate_id:
                    return item

        candidate_name = self._normalize_space(candidate.get("name")).lower()
        if candidate_name:
            for item in items:
                if self._normalize_space(item.get("name")).lower() == candidate_name:
                    return item

        return {}

    def _merge_refined_task(
        self,
        current_wp: Dict[str, Any],
        refined_task: Dict[str, Any],
        task_index: int
    ) -> Dict[str, Any]:
        """Merge a refined task into the current detailed task structure."""
        existing = self._match_existing_item(current_wp.get("tasks", []), refined_task)
        merged = copy.deepcopy(existing) if existing else {
            "id": refined_task.get("id", f"{current_wp.get('id', '')}.{task_index}"),
            "name": self._normalize_space(refined_task.get("name")) or f"Задача {task_index}",
            "description": "",
            "estimated_hours": 8,
            "duration_days": 1,
            "status": "pending",
            "skills_required": self._guess_skills(
                " ".join([current_wp.get("name", ""), refined_task.get("name", ""), refined_task.get("description", "")])
            ),
            "dependencies": [],
            "can_start_parallel": False
        }

        if refined_task.get("id"):
            merged["id"] = refined_task["id"]

        name = self._normalize_space(refined_task.get("name"))
        if name:
            merged["name"] = name

        description = self._normalize_space(refined_task.get("description"))
        if description:
            merged["description"] = description
        elif not merged.get("description"):
            merged["description"] = merged.get("name", "")

        if "estimated_hours" in refined_task:
            merged["estimated_hours"] = max(2, min(80, self._coerce_hours(refined_task.get("estimated_hours", 8))))
        else:
            merged["estimated_hours"] = max(2, min(80, self._coerce_hours(merged.get("estimated_hours", 8))))

        if "skills_required" in refined_task:
            merged["skills_required"] = self._dedupe_strings(
                refined_task.get("skills_required", []) or merged.get("skills_required", []) or current_wp.get("skills_required", [])
            )
        elif not merged.get("skills_required"):
            merged["skills_required"] = self._dedupe_strings(
                current_wp.get("skills_required", []) or self._guess_skills(
                    " ".join([current_wp.get("name", ""), merged.get("name", ""), merged.get("description", "")])
                )
            )

        if "dependencies" in refined_task:
            merged["dependencies"] = self._dedupe_strings(refined_task.get("dependencies", []))

        if "can_start_parallel" in refined_task:
            merged["can_start_parallel"] = bool(refined_task.get("can_start_parallel", False))

        merged["duration_days"] = max(1, math.ceil(merged["estimated_hours"] / 8))
        merged.setdefault("status", "pending")
        return merged

    def _merge_refined_work_package(
        self,
        current_phase: Dict[str, Any],
        refined_wp: Dict[str, Any],
        wp_index: int
    ) -> Dict[str, Any]:
        """Merge a refined work package into the current detailed structure."""
        existing = self._match_existing_item(current_phase.get("work_packages", []), refined_wp)
        merged = copy.deepcopy(existing) if existing else {
            "id": refined_wp.get("id", f"{current_phase.get('id', '')}.{wp_index}"),
            "name": self._normalize_space(refined_wp.get("name")) or f"Пакет {wp_index}",
            "description": "",
            "estimated_hours": 0,
            "duration_days": 1,
            "dependencies": [],
            "can_start_parallel": False,
            "deliverables": [],
            "skills_required": self._guess_skills(
                " ".join([current_phase.get("name", ""), refined_wp.get("name", ""), refined_wp.get("description", "")])
            ),
            "tasks": []
        }

        if refined_wp.get("id"):
            merged["id"] = refined_wp["id"]

        name = self._normalize_space(refined_wp.get("name"))
        if name:
            merged["name"] = name

        description = self._normalize_space(refined_wp.get("description"))
        if description:
            merged["description"] = description
        elif not merged.get("description"):
            merged["description"] = merged.get("name", "")

        if "dependencies" in refined_wp:
            merged["dependencies"] = self._dedupe_strings(refined_wp.get("dependencies", []))

        if "can_start_parallel" in refined_wp:
            merged["can_start_parallel"] = bool(refined_wp.get("can_start_parallel", False))

        if "deliverables" in refined_wp:
            merged["deliverables"] = self._dedupe_strings(
                refined_wp.get("deliverables", []) or merged.get("deliverables", [])
            )
        elif not merged.get("deliverables"):
            merged["deliverables"] = [merged.get("name", "Результат пакета работ")]

        if "skills_required" in refined_wp:
            merged["skills_required"] = self._dedupe_strings(
                refined_wp.get("skills_required", []) or merged.get("skills_required", [])
            )
        elif not merged.get("skills_required"):
            merged["skills_required"] = self._guess_skills(
                " ".join([current_phase.get("name", ""), merged.get("name", ""), merged.get("description", "")])
            )

        refined_tasks = refined_wp.get("tasks")
        if isinstance(refined_tasks, list) and refined_tasks:
            merged["tasks"] = [
                self._merge_refined_task(merged, task, task_index)
                for task_index, task in enumerate(refined_tasks, start=1)
                if isinstance(task, dict)
            ]

            existing_tasks = existing.get("tasks", []) if existing else []
            seen_task_ids = {task.get("id") for task in merged["tasks"] if task.get("id")}
            for task in existing_tasks:
                task_id = task.get("id")
                if task_id and task_id not in seen_task_ids:
                    merged["tasks"].append(copy.deepcopy(task))

        if not merged.get("tasks"):
            merged["tasks"] = self._fallback_tasks_for_work_package(current_phase, merged).get("tasks", [])

        if "estimated_hours" in refined_wp:
            merged["estimated_hours"] = max(2, self._coerce_hours(refined_wp.get("estimated_hours", 0), default=0))
        elif merged.get("tasks"):
            merged["estimated_hours"] = sum(task.get("estimated_hours", 0) for task in merged["tasks"])

        if not merged.get("estimated_hours") and merged.get("tasks"):
            merged["estimated_hours"] = sum(task.get("estimated_hours", 0) for task in merged["tasks"])

        merged["duration_days"] = max(1, math.ceil(max(1, merged["estimated_hours"]) / 8))
        return merged

    def _merge_refined_phase(
        self,
        current_wbs: Dict[str, Any],
        refined_phase: Dict[str, Any],
        phase_index: int
    ) -> Dict[str, Any]:
        """Merge a refined phase into the current detailed structure."""
        existing = self._match_existing_item(current_wbs.get("wbs", {}).get("phases", []), refined_phase)
        merged = copy.deepcopy(existing) if existing else {
            "id": refined_phase.get("id", str(phase_index)),
            "name": self._normalize_space(refined_phase.get("name")) or f"Фаза {phase_index}",
            "description": "",
            "duration": 1,
            "estimated_hours": 0,
            "work_packages": []
        }

        if refined_phase.get("id"):
            merged["id"] = refined_phase["id"]

        name = self._normalize_space(refined_phase.get("name"))
        if name:
            merged["name"] = name

        description = self._normalize_space(refined_phase.get("description"))
        if description:
            merged["description"] = description
        elif not merged.get("description"):
            merged["description"] = merged.get("name", "")

        refined_wps = refined_phase.get("work_packages")
        if isinstance(refined_wps, list) and refined_wps:
            merged["work_packages"] = [
                self._merge_refined_work_package(merged, wp, wp_index)
                for wp_index, wp in enumerate(refined_wps, start=1)
                if isinstance(wp, dict)
            ]

            existing_wps = existing.get("work_packages", []) if existing else []
            seen_wp_ids = {wp.get("id") for wp in merged["work_packages"] if wp.get("id")}
            for wp in existing_wps:
                wp_id = wp.get("id")
                if wp_id and wp_id not in seen_wp_ids:
                    merged["work_packages"].append(copy.deepcopy(wp))

        if "estimated_hours" in refined_phase:
            merged["estimated_hours"] = max(8, self._coerce_hours(refined_phase.get("estimated_hours", 0), default=0))
        elif merged.get("work_packages"):
            merged["estimated_hours"] = sum(wp.get("estimated_hours", 0) for wp in merged["work_packages"])

        if not merged.get("estimated_hours") and merged.get("work_packages"):
            merged["estimated_hours"] = sum(wp.get("estimated_hours", 0) for wp in merged["work_packages"])

        merged["duration"] = max(1, math.ceil(max(1, merged["estimated_hours"]) / 8))
        return merged

    def _merge_refined_wbs(self, current_wbs: Dict[str, Any], refined_wbs: Dict[str, Any]) -> Dict[str, Any]:
        """Merge refined WBS data back into the current full structure."""
        current = canonicalize_wbs_result(current_wbs)
        refined = canonicalize_wbs_result(refined_wbs)

        refined_phases = refined.get("wbs", {}).get("phases", [])
        if not refined_phases:
            logger.warning("[%s] Refined WBS has no phases, keeping current structure", self.name)
            return current

        merged = copy.deepcopy(current)
        merged["wbs"] = {"phases": []}
        merged["wbs"]["phases"] = [
            self._merge_refined_phase(current, phase, phase_index)
            for phase_index, phase in enumerate(refined_phases, start=1)
            if isinstance(phase, dict)
        ]

        current_phases = current.get("wbs", {}).get("phases", [])
        seen_phase_ids = {phase.get("id") for phase in merged["wbs"]["phases"] if phase.get("id")}
        for phase in current_phases:
            phase_id = phase.get("id")
            if phase_id and phase_id not in seen_phase_ids:
                merged["wbs"]["phases"].append(copy.deepcopy(phase))

        merged_project_info = copy.deepcopy(current.get("project_info", {}))
        merged_project_info.update(refined.get("project_info", {}))
        merged["project_info"] = merged_project_info
        merged["project_info"]["total_estimated_hours"] = sum(
            phase.get("estimated_hours", 0) for phase in merged["wbs"]["phases"]
        )
        merged["project_info"]["estimated_duration"] = (
            f"{max(1, round(merged['project_info']['total_estimated_hours'] / 40))} недель"
        )

        for field in ("risks", "assumptions", "recommendations"):
            if refined.get(field):
                merged[field] = refined[field]

        return merged

    def refine_wbs(self, current_wbs: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        """Refine the WBS based on feedback."""
        compact_wbs = self._compact_wbs_for_review(current_wbs)
        message = f"""Проверь компактное представление WBS и обратную связь.

Текущий WBS:
{json.dumps(compact_wbs, ensure_ascii=False, indent=2)}

Обратная связь:
{feedback}

Верни полный исправленный WBS JSON."""

        result = self.send_message(
            message,
            expect_json=True,
            use_history=False,
            max_tokens=Config.WBS_REFINEMENT_MAX_TOKENS,
            temperature=0.0
        )

        if result["success"]:
            refined_wbs = self._merge_refined_wbs(current_wbs, result["data"])
            return {
                "success": True,
                "wbs": refined_wbs
            }
        return result

    def request_more_details(self, topic: str) -> Dict[str, Any]:
        """Request more details on a specific topic from the Analyst."""
        message = f"""Мне нужно больше информации для создания точного WBS.

Пожалуйста, уточни: {topic}

Опиши, какие именно детали нужны для планирования."""

        return self.send_message(message, expect_json=False, use_history=False, max_tokens=800)

    def validate_wbs(self, wbs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the WBS for completeness and consistency."""
        issues = []

        if "wbs" not in wbs:
            issues.append("Missing 'wbs' field")
        elif "phases" not in wbs["wbs"]:
            issues.append("Missing 'phases' in WBS")
        else:
            for phase in wbs["wbs"]["phases"]:
                if not phase.get("work_packages"):
                    issues.append(f"Phase {phase.get('id')} has no work packages")
                else:
                    for wp in phase["work_packages"]:
                        if not wp.get("tasks"):
                            issues.append(f"Work package {wp.get('id')} has no tasks")

        validation_result = {
            "valid": len(issues) == 0,
            "issues": issues
        }
        self._record_intermediate("planner_validation", validation_result)
        return validation_result
