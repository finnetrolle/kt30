"""
WBS Planner Agent.
Creates Work Breakdown Structure based on analysis from the Analyst Agent.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """Agent responsible for creating Work Breakdown Structure.
    
    This agent:
    - Receives structured analysis from the Analyst Agent
    - Creates detailed WBS with phases, work packages, and tasks
    - Estimates effort for each work item using estimation rules
    - Assigns required skills/roles to tasks
    - Identifies dependencies between tasks
    """
    
    def __init__(self):
        """Initialize the WBS Planner Agent."""
        super().__init__(
            name="Планировщик WBS",
            role="Создает детальную структуру работ (WBS) на основе анализа требований"
        )
        self._estimation_rules = self._load_estimation_rules()
    
    def _load_estimation_rules(self) -> Dict[str, Any]:
        """Load estimation rules from JSON file.
        
        Returns:
            Estimation rules dictionary
        """
        rules_path = Path(__file__).parent.parent / "data" / "estimation_rules.json"
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load estimation rules: {e}")
            return {}
    
    def _build_estimation_reference(self) -> str:
        """Build a compact estimation reference from rules for the prompt.
        
        Returns:
            Formatted estimation reference string
        """
        rules = self._estimation_rules
        if not rules:
            return ""
        
        lines = ["\n\nСПРАВОЧНИК ТИПОВЫХ ТРУДОЗАТРАТ (используй для оценки):"]
        
        # Task templates
        templates = rules.get("task_templates", {})
        for category, tasks in templates.items():
            lines.append(f"\n{category}:")
            for task_name, est in tasks.items():
                lines.append(f"  - {task_name}: {est['min_hours']}-{est['max_hours']} ч (типично {est['typical_hours']} ч)")
        
        # Phase ratios
        phase_ratios = rules.get("phase_ratios", {})
        if phase_ratios:
            lines.append("\nРАСПРЕДЕЛЕНИЕ ТРУДОЗАТРАТ ПО ФАЗАМ:")
            for phase_name, info in phase_ratios.items():
                ratio = info.get("ratio", 0)
                lines.append(f"  - {phase_name}: {int(ratio*100)}% от общего объёма")
        
        # Project type baselines
        baselines = rules.get("project_type_baselines", {})
        if baselines:
            lines.append("\nБАЗОВЫЕ ОЦЕНКИ ПО ТИПАМ ПРОЕКТОВ:")
            for proj_type, info in baselines.items():
                rng = info.get("range_hours", [0, 0])
                lines.append(f"  - {proj_type}: {rng[0]}-{rng[1]} ч (базово {info.get('baseline_hours', 0)} ч)")
        
        # Limits
        limits = rules.get("limits", {})
        if limits:
            lines.append(f"\nЛИМИТЫ: задача {limits.get('min_hours_per_task', 2)}-{limits.get('max_hours_per_task', 80)} ч, "
                        f"фаза {limits.get('min_hours_per_phase', 8)}-{limits.get('max_hours_per_phase', 500)} ч, "
                        f"проект {limits.get('min_total_hours', 40)}-{limits.get('max_total_hours', 5000)} ч")
        
        return "\n".join(lines)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the Planner Agent.
        
        Returns:
            System prompt string
        """
        estimation_ref = self._build_estimation_reference()
        
        return f"""Ты — опытный проектный менеджер и планировщик проектов разработки ПО. Твоя задача — создавать детальные Work Breakdown Structure (WBS) на основе анализа требований.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON. НЕ ПИШИ НИЧЕГО КРОМЕ JSON. ВАЖНО: все строки должны быть валидными, без переносов внутри строк.

Твой WBS должен включать:

1. project_info — информация о проекте:
   - project_name: название проекта
   - description: описание (краткое)
   - estimated_duration: общая длительность
   - complexity_level: уровень сложности
   - total_estimated_hours: общая оценка трудозатрат (ЧИСЛО, сумма часов всех фаз)

2. wbs — структура работ:
   - phases: массив фаз проекта
   
   Каждая фаза (phase) содержит:
   - id: идентификатор фазы ("1", "2", "3")
   - name: название фазы
   - description: описание фазы
   - duration: длительность фазы в днях (число)
   - estimated_hours: оценка трудозатрат в часах (ЧИСЛО)
   - work_packages: массив пакетов работ
   
   Каждый пакет работ (work_package) содержит:
   - id: идентификатор ("1.1", "1.2")
   - name: название пакета
   - description: описание
   - estimated_hours: оценка трудозатрат (ЧИСЛО)
   - duration_days: длительность в рабочих днях (ЧИСЛО)
   - dependencies: массив идентификаторов (пустой массив если нет)
   - can_start_parallel: true или false
   - deliverables: массив результатов
   - skills_required: массив требуемых навыков
   - tasks: массив задач
   
   Каждая задача (task) содержит:
   - id: идентификатор ("1.1.1", "1.1.2")
   - name: название задачи
   - description: описание
   - estimated_hours: оценка трудозатрат (ЧИСЛО)
   - duration_days: длительность в рабочих днях (ЧИСЛО)
   - status: "pending"
   - skills_required: массив требуемых навыков
   - dependencies: массив идентификаторов (пустой массив если нет)
   - can_start_parallel: true или false

3. risks — риски проекта (максимум 5 рисков):
   - id: идентификатор
   - description: описание риска
   - probability: вероятность
   - impact: влияние
   - mitigation: митигация

4. assumptions — предположения при планировании (массив строк)

5. recommendations — рекомендации по проекту (максимум 5):
   - category: категория
   - priority: приоритет
   - recommendation: текст рекомендации

Стандартные фазы:
1. Планирование и анализ
2. Проектирование
3. Разработка
4. Тестирование
5. Развертывание

ВАЖНО:
- ВСЕ estimated_hours и duration_days должны быть ЧИСЛАМИ (не строками)
- total_estimated_hours = сумма estimated_hours всех фаз
- estimated_hours фазы = сумма estimated_hours всех work_packages в фазе
- estimated_hours work_package = сумма estimated_hours всех tasks в work_package
- duration_days = estimated_hours / 8 (округлить вверх)
- can_start_parallel = true если задача может выполняться одновременно с другими
- dependencies = [] если нет зависимостей
- Все description должны быть краткими (одно предложение)
- Соблюдай валидный JSON синтаксис
- Не используй переносы строк внутри строковых значений
- Используй справочник трудозатрат ниже для реалистичных оценок
{estimation_ref}"""

    def create_wbs(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create WBS based on the analysis from Analyst Agent.
        
        Args:
            analysis: Structured analysis from the Analyst Agent
            
        Returns:
            WBS result dictionary
        """
        logger.info(f"[{self.name}] Starting WBS creation...")
        
        # Format the analysis for the prompt
        import json
        analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
        
        message = f"""На основе следующего анализа технического задания, создай детальную структуру работ (WBS).

ВЕРНИ ТОЛЬКО JSON БЕЗ КАКИХ-ЛИБО ДОПОЛНИТЕЛЬНЫХ КОММЕНТАРИЕВ.

Анализ ТЗ:
{analysis_json}

Создай WBS с реалистичными оценками трудозатрат и распределением по ролям.
JSON:"""
        
        result = self.send_message(message, expect_json=True)
        
        if result["success"]:
            logger.info(f"[{self.name}] WBS creation completed successfully")
            return {
                "success": True,
                "wbs": result["data"]
            }
        else:
            logger.error(f"[{self.name}] WBS creation failed: {result.get('error')}")
            return result
    
    def refine_wbs(self, current_wbs: Dict[str, Any], 
                   feedback: str) -> Dict[str, Any]:
        """Refine the WBS based on feedback.
        
        Args:
            current_wbs: Current WBS
            feedback: Feedback for refinement
            
        Returns:
            Refined WBS
        """
        import json
        wbs_json = json.dumps(current_wbs, ensure_ascii=False, indent=2)
        
        message = f"""Улучши текущий WBS на основе следующей обратной связи.

Текущий WBS:
{wbs_json}

Обратная связь:
{feedback}

Предоставь улучшенный WBS в том же JSON формате."""
        
        result = self.send_message(message, expect_json=True)
        
        if result["success"]:
            return {
                "success": True,
                "wbs": result["data"]
            }
        return result
    
    def request_more_details(self, topic: str) -> Dict[str, Any]:
        """Request more details on a specific topic from the Analyst.
        
        Args:
            topic: Topic to request details about
            
        Returns:
            Response with request for details
        """
        message = f"""Мне нужно больше информации для создания точного WBS.

Пожалуйста, уточни: {topic}

Опиши, какие именно детали нужны для планирования."""
        
        return self.send_message(message, expect_json=False)
    
    def validate_wbs(self, wbs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the WBS for completeness and consistency.
        
        Args:
            wbs: WBS to validate
            
        Returns:
            Validation result
        """
        issues = []
        
        # Check for required fields
        if 'wbs' not in wbs:
            issues.append("Missing 'wbs' field")
        elif 'phases' not in wbs['wbs']:
            issues.append("Missing 'phases' in WBS")
        else:
            # Check phases
            for phase in wbs['wbs']['phases']:
                if not phase.get('work_packages'):
                    issues.append(f"Phase {phase.get('id')} has no work packages")
                else:
                    for wp in phase['work_packages']:
                        if not wp.get('tasks'):
                            issues.append(f"Work package {wp.get('id')} has no tasks")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues
        }
