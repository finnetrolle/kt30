"""
Specification Analyst Agent.
Analyzes technical specifications and extracts structured requirements.
"""
import logging
from typing import Dict, Any
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """Agent responsible for analyzing technical specifications.
    
    This agent:
    - Analyzes the technical specification document
    - Extracts key requirements and constraints
    - Identifies project scope and boundaries
    - Structures the information for the WBS Planner
    """
    
    def __init__(self):
        """Initialize the Specification Analyst Agent."""
        super().__init__(
            name="Аналитик ТЗ",
            role="Анализирует техническое задание и извлекает структурированные требования"
        )
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the Analyst Agent.
        
        Returns:
            System prompt string
        """
        return """Ты — опытный бизнес-аналитик и системный аналитик. Твоя задача — анализировать технические задания и извлекать структурированную информацию для планирования проекта.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON. НЕ ПИШИ НИЧЕГО КРОМЕ JSON.

Твой анализ должен включать:

1. **project_info** — информация о проекте:
   - project_name: название проекта
   - description: краткое описание (2-3 предложения)
   - project_type: тип проекта (веб-приложение, мобильное приложение, API, интеграция, и т.д.)
   - estimated_duration: примерная длительность
   - complexity_level: уровень сложности (Низкий, Средний, Высокий)

2. **functional_requirements** — функциональные требования:
   Массив объектов с полями:
   - id: идентификатор (FR-1, FR-2, ...)
   - name: название требования
   - description: подробное описание
   - priority: приоритет (Высокий, Средний, Низкий)
   - category: категория (Пользовательский интерфейс, Бизнес-логика, Интеграция, и т.д.)

3. **non_functional_requirements** — нефункциональные требования:
   Массив объектов с полями:
   - id: идентификатор (NFR-1, NFR-2, ...)
   - name: название требования
   - description: описание
   - category: категория (Производительность, Безопасность, Масштабируемость, и т.д.)

4. **technical_constraints** — технические ограничения:
   - platforms: целевые платформы
   - technologies: предпочтительные технологии
   - integrations: необходимые интеграции
   - security_requirements: требования безопасности

5. **stakeholders** — заинтересованные стороны:
   Массив объектов с полями:
   - role: роль (Заказчик, Пользователь, Администратор, и т.д.)
   - interests: интересы и потребности
   - involvement: уровень вовлеченности

6. **assumptions** — предположения:
   Массив строк с предположениями, сделанными при анализе

7. **risks** — выявленные риски:
   Массив объектов с полями:
   - id: идентификатор (R-1, R-2, ...)
   - description: описание риска
   - probability: вероятность (Низкая, Средняя, Высокая)
   - impact: влияние (Низкое, Среднее, Высокое)
   - mitigation: предложения по митигации

8. **clarifications_needed** — вопросы для уточнения:
   Массив вопросов, если в ТЗ недостаточно информации

Пример формата ответа:
{
  "project_info": {
    "project_name": "Система управления задачами",
    "description": "Веб-приложение для управления проектами и задачами",
    "project_type": "Веб-приложение",
    "estimated_duration": "3-4 месяца",
    "complexity_level": "Средний"
  },
  "functional_requirements": [
    {
      "id": "FR-1",
      "name": "Авторизация пользователей",
      "description": "Регистрация и вход в систему",
      "priority": "Высокий",
      "category": "Безопасность"
    }
  ],
  "non_functional_requirements": [],
  "technical_constraints": {
    "platforms": ["Web"],
    "technologies": [],
    "integrations": [],
    "security_requirements": []
  },
  "stakeholders": [],
  "assumptions": [],
  "risks": [],
  "clarifications_needed": []
}

Правила:
1. Будь тщательным в анализе — от этого зависит качество плана работ
2. Выделяй неочевидные требования
3. Указывай предположения явно
4. Если информации недостаточно, добавляй вопросы в clarifications_needed
5. Оценивай риски реалистично"""

    def analyze_specification(self, document_content: str) -> Dict[str, Any]:
        """Analyze a technical specification document.
        
        Args:
            document_content: Content of the technical specification
            
        Returns:
            Analysis result dictionary
        """
        logger.info(f"[{self.name}] Starting specification analysis...")
        
        message = f"""Проанализируй следующее техническое задание и предоставь структурированный анализ.

ВЕРНИ ТОЛЬКО JSON БЕЗ КАКИХ-ЛИБО ДОПОЛНИТЕЛЬНЫХ КОММЕНТАРИЕВ.

Техническое задание:
{document_content}

JSON:"""
        
        result = self.send_message(message, expect_json=True)
        
        if result["success"]:
            logger.info(f"[{self.name}] Specification analysis completed successfully")
            return {
                "success": True,
                "analysis": result["data"]
            }
        else:
            logger.error(f"[{self.name}] Specification analysis failed: {result.get('error')}")
            return result
    
    def request_clarification(self, question: str) -> Dict[str, Any]:
        """Request clarification on a specific topic.
        
        Args:
            question: Question to ask
            
        Returns:
            Clarification response
        """
        message = f"Уточни, пожалуйста: {question}"
        return self.send_message(message, expect_json=False)
    
    def refine_analysis(self, original_analysis: Dict[str, Any], 
                       clarifications: Dict[str, str]) -> Dict[str, Any]:
        """Refine the analysis based on clarifications.
        
        Args:
            original_analysis: Original analysis result
            clarifications: Dictionary of clarifications (question -> answer)
            
        Returns:
            Refined analysis
        """
        clarification_text = "\n".join([
            f"Вопрос: {q}\nОтвет: {a}"
            for q, a in clarifications.items()
        ])
        
        message = f"""На основе получленных уточнений, обнови анализ проекта.

Исходный анализ:
{original_analysis}

Уточнения:
{clarification_text}

Предоставь обновленный анализ в том же JSON формате."""
        
        result = self.send_message(message, expect_json=True)
        
        if result["success"]:
            return {
                "success": True,
                "analysis": result["data"]
            }
        return result
