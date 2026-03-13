"""
Specification Analyst Agent.
Analyzes technical specifications and extracts structured requirements.
"""
import json
import logging
from pathlib import Path
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
    
    def _build_project_type_reference(self) -> str:
        """Build project type and complexity reference for the prompt.
        
        Returns:
            Formatted reference string
        """
        rules = self._estimation_rules
        if not rules:
            return ""
        
        lines = ["\n\nСПРАВОЧНИК ДЛЯ ОПРЕДЕЛЕНИЯ ТИПА И СЛОЖНОСТИ ПРОЕКТА:"]
        
        # Project type baselines
        baselines = rules.get("project_type_baselines", {})
        if baselines:
            lines.append("\nТипы проектов и базовые трудозатраты:")
            for proj_type, info in baselines.items():
                rng = info.get("range_hours", [0, 0])
                duration = info.get("typical_duration_weeks", "N/A")
                lines.append(f"  - {proj_type}: {rng[0]}-{rng[1]} ч, длительность {duration} недель")
        
        # Complexity multipliers
        multipliers = rules.get("complexity_multipliers", {})
        if multipliers:
            lines.append("\nУровни сложности:")
            for level, info in multipliers.items():
                lines.append(f"  - {level}: множитель x{info.get('multiplier', 1.0)}, "
                           f"команда до {info.get('max_team_size', 'N/A')} чел, "
                           f"{info.get('description', '')}")
        
        lines.append("\nИспользуй project_type из списка выше (или ближайший аналог).")
        lines.append("Используй complexity_level строго из: Низкий, Средний, Высокий, Очень высокий.")
        
        return "\n".join(lines)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the Analyst Agent.
        
        Returns:
            System prompt string
        """
        project_ref = self._build_project_type_reference()
        
        return f"""Ты — опытный бизнес-аналитик и системный аналитик. Твоя задача — анализировать технические задания и извлекать структурированную информацию для планирования проекта.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON. НЕ ПИШИ НИЧЕГО КРОМЕ JSON.

Твой анализ должен включать:

1. **project_info** — информация о проекте:
   - project_name: название проекта
   - description: краткое описание (2-3 предложения)
   - project_type: тип проекта (используй справочник ниже)
   - estimated_duration: примерная длительность (используй справочник ниже)
   - complexity_level: уровень сложности (Низкий, Средний, Высокий, Очень высокий)

2. **functional_requirements** — функциональные требования:
   Массив объектов с полями:
   - id: идентификатор (FR-1, FR-2, ...)
   - name: название требования (краткое, уникальное)
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
{{
  "project_info": {{
    "project_name": "Система управления задачами",
    "description": "Веб-приложение для управления проектами и задачами",
    "project_type": "Веб-приложение (среднее)",
    "estimated_duration": "8-16 недель",
    "complexity_level": "Средний"
  }},
  "functional_requirements": [
    {{
      "id": "FR-1",
      "name": "Авторизация пользователей",
      "description": "Регистрация и вход в систему с поддержкой email и пароля",
      "priority": "Высокий",
      "category": "Безопасность"
    }}
  ],
  "non_functional_requirements": [],
  "technical_constraints": {{
    "platforms": ["Web"],
    "technologies": [],
    "integrations": [],
    "security_requirements": []
  }},
  "stakeholders": [],
  "assumptions": [],
  "risks": [],
  "clarifications_needed": []
}}

Правила:
1. Будь тщательным в анализе — от этого зависит качество плана работ
2. Выделяй ВСЕ функциональные требования, даже неочевидные — каждое должно стать задачей в WBS
3. Каждое требование должно быть атомарным и конкретным
4. Указывай предположения явно
5. Если информации недостаточно, добавляй вопросы в clarifications_needed
6. Оценивай риски реалистично
7. Используй справочник типов проектов для определения project_type и estimated_duration
{project_ref}"""

    # Maximum document size in characters to avoid exceeding LLM context window
    # GPT-4 supports 128K tokens (~400K chars); we allow up to 40K chars (~13K tokens)
    MAX_DOCUMENT_CHARS = 40000
    
    def analyze_specification(self, document_content: str) -> Dict[str, Any]:
        """Analyze a technical specification document.
        
        Args:
            document_content: Content of the technical specification
            
        Returns:
            Analysis result dictionary
        """
        logger.info(f"[{self.name}] Starting specification analysis...")
        
        # Truncate document if too long to avoid exceeding context window
        if len(document_content) > self.MAX_DOCUMENT_CHARS:
            logger.warning(
                f"[{self.name}] Document truncated from {len(document_content)} "
                f"to {self.MAX_DOCUMENT_CHARS} characters"
            )
            document_content = document_content[:self.MAX_DOCUMENT_CHARS] + \
                "\n\n... (документ обрезан из-за ограничений размера)"
        
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
        
        message = f"""На основе полученных уточнений, обнови анализ проекта.

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
