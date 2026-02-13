"""
WBS Planner Agent.
Creates Work Breakdown Structure based on analysis from the Analyst Agent.
"""
import logging
from typing import Dict, Any, List
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """Agent responsible for creating Work Breakdown Structure.
    
    This agent:
    - Receives structured analysis from the Analyst Agent
    - Creates detailed WBS with phases, work packages, and tasks
    - Estimates effort for each work item
    - Assigns required skills/roles to tasks
    - Identifies dependencies between tasks
    """
    
    def __init__(self):
        """Initialize the WBS Planner Agent."""
        super().__init__(
            name="Планировщик WBS",
            role="Создает детальную структуру работ (WBS) на основе анализа требований"
        )
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the Planner Agent.
        
        Returns:
            System prompt string
        """
        return """Ты — опытный проектный менеджер и планировщик проектов разработки ПО. Твоя задача — создавать детальные Work Breakdown Structure (WBS) на основе анализа требований.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON. НЕ ПИШИ НИЧЕГО КРОМЕ JSON. ВАЖНО: все строки должны быть валидными, без переносов внутри строк.

Твой WBS должен включать:

1. project_info — информация о проекте:
   - project_name: название проекта
   - description: описание (краткое)
   - estimated_duration: общая длительность
   - complexity_level: уровень сложности
   - total_estimated_hours: общая оценка трудозатрат

2. wbs — структура работ:
   - phases: массив фаз проекта
   
   Каждая фаза (phase) содержит:
   - id: идентификатор фазы ("1", "2", "3")
   - name: название фазы
   - description: описание фазы
   - duration: длительность фазы в днях (число)
   - estimated_hours: оценка трудозатрат в часах
   - work_packages: массив пакетов работ
   
   Каждый пакет работ (work_package) содержит:
   - id: идентификатор ("1.1", "1.2")
   - name: название пакета
   - description: описание
   - estimated_hours: оценка трудозатрат
   - duration_days: длительность в рабочих днях
   - dependencies: массив идентификаторов (пустой массив если нет)
   - can_start_parallel: true или false
   - deliverables: массив результатов
   - skills_required: массив требуемых навыков
   - tasks: массив задач
   
   Каждая задача (task) содержит:
   - id: идентификатор ("1.1.1", "1.1.2")
   - name: название задачи
   - description: описание
   - estimated_hours: оценка трудозатрат
   - duration_days: длительность в рабочих днях
   - status: "pending"
   - skills_required: массив требуемых навыков
   - dependencies: массив идентификаторов (пустой массив если нет)
   - can_start_parallel: true или false

3. risks — риски проекта (максимум5 рисков):
   - id: идентификатор
   - description: описание риска
   - probability: вероятность
   - impact: влияние
   - mitigation: митигация

4. assumptions — предположения при планировании (массив строк)

5. recommendations — рекомендации по проекту (максимум5):
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
- Все description должны быть краткими (одно предложение)
- duration_days = estimated_hours /8 (округлить вверх)
- can_start_parallel = true если задача может выполняться одновременно с другими
- dependencies = [] если нет зависимостей
- Соблюдай валидный JSON синтаксис
- Не используй переносы строк внутри строковых значений"""

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
