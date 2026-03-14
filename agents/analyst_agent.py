"""
Specification Analyst Agent.
Analyzes technical specifications and extracts structured requirements.
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import Config

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """Agent responsible for analyzing technical specifications."""

    MAX_REQUIREMENTS_FOR_SYNTHESIS = 40 if Config.SMALL_LLM_MODE else 60
    MAX_RISKS_FOR_SYNTHESIS = 12 if Config.SMALL_LLM_MODE else 20
    MAX_QUESTIONS_FOR_SYNTHESIS = 12 if Config.SMALL_LLM_MODE else 20
    MAX_FULL_DOCUMENT_CHARS = 40000
    PLACEHOLDER_TEXTS = {
        "название проекта",
        "краткое описание",
        "тип проекта",
        "название требования",
        "описание",
        "описание риска",
        "как снизить риск",
        "интересы и потребности",
        "текст рекомендации",
        "проект"
    }

    def __init__(self):
        """Initialize the Specification Analyst Agent."""
        super().__init__(
            name="Аналитик ТЗ",
            role="Анализирует техническое задание и извлекает структурированные требования"
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

    def _build_project_type_reference(self) -> str:
        """Build project type and complexity reference for the prompt."""
        rules = self._estimation_rules
        if not rules:
            return ""

        if Config.SMALL_LLM_MODE:
            baselines = ", ".join(rules.get("project_type_baselines", {}).keys())
            complexity = ", ".join(rules.get("complexity_multipliers", {}).keys())
            return (
                "Типы проектов: " + baselines + "\n"
                "Уровни сложности: " + complexity
            )

        lines = ["СПРАВОЧНИК ДЛЯ ОПРЕДЕЛЕНИЯ ТИПА И СЛОЖНОСТИ ПРОЕКТА:"]

        baselines = rules.get("project_type_baselines", {})
        if baselines:
            lines.append("Типы проектов и базовые трудозатраты:")
            for proj_type, info in baselines.items():
                rng = info.get("range_hours", [0, 0])
                duration = info.get("typical_duration_weeks", "N/A")
                lines.append(f"- {proj_type}: {rng[0]}-{rng[1]} ч, длительность {duration} недель")

        multipliers = rules.get("complexity_multipliers", {})
        if multipliers:
            lines.append("Уровни сложности:")
            for level, info in multipliers.items():
                lines.append(
                    f"- {level}: множитель x{info.get('multiplier', 1.0)}, "
                    f"команда до {info.get('max_team_size', 'N/A')} чел, "
                    f"{info.get('description', '')}"
                )

        lines.append("Используй project_type из списка выше или ближайший аналог.")
        lines.append("Используй complexity_level строго из: Низкий, Средний, Высокий, Очень высокий.")
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        """Build the full synthesis system prompt for the Analyst Agent."""
        project_ref = self._build_project_type_reference()
        if Config.SMALL_LLM_MODE:
            return f"""Ты аналитик ТЗ.

Верни только JSON.
Собери итоговую структуру:
- project_info
- functional_requirements
- non_functional_requirements
- technical_constraints
- stakeholders
- assumptions
- risks
- clarifications_needed

Правила:
- не выдумывай факты
- объединяй дубликаты
- требования делай короткими и атомарными
- если данных мало, добавляй вопросы в clarifications_needed
{project_ref}"""

        return f"""Ты — опытный бизнес-аналитик и системный аналитик.

Твоя задача — собрать ИТОГОВЫЙ структурированный анализ проекта.
ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON.
НЕ ВЫВОДИ <think> ИЛИ ЛЮБЫЕ ПРОМЕЖУТОЧНЫЕ РАССУЖДЕНИЯ.

Верни JSON со структурой:
{{
  "project_info": {{
    "project_name": "Название проекта",
    "description": "Краткое описание",
    "project_type": "Тип проекта",
    "estimated_duration": "8-16 недель",
    "complexity_level": "Средний"
  }},
  "functional_requirements": [
    {{
      "id": "FR-1",
      "name": "Название требования",
      "description": "Описание",
      "priority": "Высокий",
      "category": "Бизнес-логика"
    }}
  ],
  "non_functional_requirements": [
    {{
      "id": "NFR-1",
      "name": "Название требования",
      "description": "Описание",
      "category": "Безопасность"
    }}
  ],
  "technical_constraints": {{
    "platforms": [],
    "technologies": [],
    "integrations": [],
    "security_requirements": []
  }},
  "stakeholders": [
    {{
      "role": "Заказчик",
      "interests": "Интересы и потребности",
      "involvement": "Высокая"
    }}
  ],
  "assumptions": [],
  "risks": [
    {{
      "id": "R-1",
      "description": "Описание риска",
      "probability": "Средняя",
      "impact": "Высокое",
      "mitigation": "Как снизить риск"
    }}
  ],
  "clarifications_needed": []
}}

Правила:
- Учитывай только факты из переданных агрегированных данных.
- Объединяй дубликаты и формулируй требования атомарно.
- Не выдумывай новые требования.
- Если данных мало, явно добавляй вопросы в clarifications_needed.
- project_type и estimated_duration определяй по справочнику.
{project_ref}"""

    def _build_full_document_system_prompt(self) -> str:
        """Build a legacy-style prompt for full-document recovery analysis."""
        project_ref = self._build_project_type_reference()
        return f"""Ты — опытный бизнес-аналитик и системный аналитик.

Твоя задача — анализировать технические задания и извлекать структурированную информацию для планирования проекта.
ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON.
НЕ ВЫВОДИ <think> ИЛИ ЛЮБЫЕ ПРОМЕЖУТОЧНЫЕ РАССУЖДЕНИЯ.

Верни JSON со структурой:
{{
  "project_info": {{
    "project_name": "Название проекта",
    "description": "Краткое описание",
    "project_type": "Тип проекта",
    "estimated_duration": "8-16 недель",
    "complexity_level": "Средний"
  }},
  "functional_requirements": [
    {{
      "id": "FR-1",
      "name": "Название требования",
      "description": "Описание",
      "priority": "Высокий",
      "category": "Бизнес-логика"
    }}
  ],
  "non_functional_requirements": [
    {{
      "id": "NFR-1",
      "name": "Название требования",
      "description": "Описание",
      "category": "Безопасность"
    }}
  ],
  "technical_constraints": {{
    "platforms": [],
    "technologies": [],
    "integrations": [],
    "security_requirements": []
  }},
  "stakeholders": [],
  "assumptions": [],
  "risks": [
    {{
      "id": "R-1",
      "description": "Описание риска",
      "probability": "Средняя",
      "impact": "Высокое",
      "mitigation": "Как снизить риск"
    }}
  ],
  "clarifications_needed": []
}}

Правила:
- Выделяй ВСЕ функциональные требования, даже если они сформулированы неявно.
- Каждое функциональное требование делай атомарным и конкретным.
- Не выдумывай факты вне текста ТЗ.
- Если данных недостаточно, добавляй вопросы в clarifications_needed.
- project_type и estimated_duration определяй по справочнику.
{project_ref}"""

    def _build_chunk_system_prompt(self) -> str:
        """Build a compact prompt for analyzing a single chunk."""
        return """Ты — аналитик, который разбирает только один фрагмент технического задания.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON.
НЕ ВЫВОДИ <think> ИЛИ ЛЮБЫЕ ПРОМЕЖУТОЧНЫЕ РАССУЖДЕНИЯ.
Извлекай только факты, которые явно относятся к текущему фрагменту.
Если во фрагменте чего-то нет, возвращай пустые массивы или пустые строки.

Верни JSON вида:
{
  "project_hints": {
    "project_names": [],
    "descriptions": [],
    "project_type_hints": [],
    "complexity_hints": []
  },
  "functional_requirements": [
    {
      "name": "Название требования",
      "description": "Краткое описание",
      "priority": "Высокий",
      "category": "Бизнес-логика"
    }
  ],
  "non_functional_requirements": [
    {
      "name": "Название требования",
      "description": "Краткое описание",
      "category": "Безопасность"
    }
  ],
  "technical_constraints": {
    "platforms": [],
    "technologies": [],
    "integrations": [],
    "security_requirements": []
  },
  "stakeholders": [
    {
      "role": "Заказчик",
      "interests": "Интересы и потребности",
      "involvement": "Высокая"
    }
  ],
  "assumptions": [],
  "risks": [
    {
      "description": "Описание риска",
      "probability": "Средняя",
      "impact": "Высокое",
      "mitigation": "Как снизить риск"
    }
  ],
  "clarifications_needed": []
}"""

    def _build_chunk_rescue_system_prompt(self) -> str:
        """Build a stricter rescue prompt for chunk extraction retries."""
        return """Ты извлекаешь факты только из одного фрагмента ТЗ.

Верни ТОЛЬКО валидный JSON.
НЕ ВЫВОДИ <think>, markdown, пояснения, шаблоны или сокращения.
ЗАПРЕЩЕНО использовать `...`, `etc`, `и т.д.` или пропуски внутри JSON.
Если данных нет, используй только пустые структуры: [], {}, "".
Не пересказывай схему. Не сокращай ответ. Не добавляй лишние ключи.

Строгий формат:
{
  "project_hints": {
    "project_names": [],
    "descriptions": [],
    "project_type_hints": [],
    "complexity_hints": []
  },
  "functional_requirements": [],
  "non_functional_requirements": [],
  "technical_constraints": {
    "platforms": [],
    "technologies": [],
    "integrations": [],
    "security_requirements": []
  },
  "stakeholders": [],
  "assumptions": [],
  "risks": [],
  "clarifications_needed": []
}"""

    def _build_chunk_rescue_message(self, chunk: Dict[str, str], index: int, total: int) -> str:
        """Build a stricter retry message for chunk extraction."""
        return f"""Повтори разбор фрагмента {index} из {total}.

Критично:
- не используй `...` и никакие placeholder-ы
- не возвращай схему или пример
- если факта нет, оставь пустой массив, пустой объект или пустую строку
- верни только валидный JSON по заданному формату

Фрагмент:
{chunk["content"]}

JSON:"""

    def _empty_partial_analysis(self) -> Dict[str, Any]:
        """Return an empty partial analysis structure for hard fallbacks."""
        return {
            "project_hints": {
                "project_names": [],
                "descriptions": [],
                "project_type_hints": [],
                "complexity_hints": []
            },
            "functional_requirements": [],
            "non_functional_requirements": [],
            "technical_constraints": {
                "platforms": [],
                "technologies": [],
                "integrations": [],
                "security_requirements": []
            },
            "stakeholders": [],
            "assumptions": [],
            "risks": [],
            "clarifications_needed": []
        }

    def _is_placeholder_text(self, value: Any) -> bool:
        """Detect obvious schema placeholder text echoed by the model."""
        normalized = self._normalize_space(value).lower()
        return bool(normalized) and normalized in self.PLACEHOLDER_TEXTS

    def _sanitize_requirement_items(self, items: Any, nfr: bool = False) -> List[Dict[str, Any]]:
        """Drop placeholder and malformed requirement items."""
        if not isinstance(items, list):
            return []

        cleaned: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            name = self._normalize_space(item.get("name"))
            description = self._normalize_space(item.get("description"))
            category = self._normalize_space(item.get("category"))

            if self._is_placeholder_text(name):
                name = ""
            if self._is_placeholder_text(description):
                description = ""
            if self._is_placeholder_text(category):
                category = ""

            if not name and description:
                name = description[:120]
            if not name:
                continue

            cleaned_item = {
                "name": name,
                "description": description or name,
                "category": category or ("Общее" if nfr else "Бизнес-логика")
            }

            if not nfr:
                priority = self._normalize_space(item.get("priority"))
                cleaned_item["priority"] = priority or "Средний"

            if item.get("id"):
                cleaned_item["id"] = self._normalize_space(item.get("id"))

            cleaned.append(cleaned_item)

        return cleaned

    def _sanitize_risks(self, items: Any) -> List[Dict[str, Any]]:
        """Drop placeholder or malformed risks."""
        if not isinstance(items, list):
            return []

        cleaned: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            description = self._normalize_space(item.get("description"))
            mitigation = self._normalize_space(item.get("mitigation"))
            if self._is_placeholder_text(description):
                description = ""
            if self._is_placeholder_text(mitigation):
                mitigation = ""
            if not description:
                continue

            risk = {
                "description": description,
                "probability": self._normalize_space(item.get("probability")) or "Средняя",
                "impact": self._normalize_space(item.get("impact")) or "Среднее",
                "mitigation": mitigation
            }
            if item.get("id"):
                risk["id"] = self._normalize_space(item.get("id"))
            cleaned.append(risk)

        return cleaned

    def _sanitize_stakeholders(self, items: Any) -> List[Dict[str, Any]]:
        """Normalize stakeholder structures."""
        if not isinstance(items, list):
            return []

        cleaned: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            role = self._normalize_space(item.get("role"))
            interests = self._normalize_space(item.get("interests"))
            involvement = self._normalize_space(item.get("involvement"))

            if self._is_placeholder_text(role):
                role = ""
            if self._is_placeholder_text(interests):
                interests = ""

            if not role:
                continue

            cleaned.append({
                "role": role,
                "interests": interests,
                "involvement": involvement or "Средняя"
            })

        return cleaned

    def _sanitize_string_list(self, values: Any, limit: Optional[int] = None) -> List[str]:
        """Normalize, deduplicate and drop obvious placeholders from string lists."""
        if not isinstance(values, list):
            return []
        filtered = [
            value for value in values
            if not self._is_placeholder_text(value)
        ]
        return self._merge_unique_strings(filtered, limit=limit)

    def _sanitize_partial_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a chunk-level analysis and remove placeholder echoes."""
        hints = data.get("project_hints", {}) if isinstance(data, dict) else {}
        constraints = data.get("technical_constraints", {}) if isinstance(data, dict) else {}
        return {
            "project_hints": {
                "project_names": self._sanitize_string_list(hints.get("project_names", []), limit=10),
                "descriptions": self._sanitize_string_list(hints.get("descriptions", []), limit=10),
                "project_type_hints": self._sanitize_string_list(hints.get("project_type_hints", []), limit=10),
                "complexity_hints": self._sanitize_string_list(hints.get("complexity_hints", []), limit=10)
            },
            "functional_requirements": self._sanitize_requirement_items(
                data.get("functional_requirements", []),
                nfr=False
            ),
            "non_functional_requirements": self._sanitize_requirement_items(
                data.get("non_functional_requirements", []),
                nfr=True
            ),
            "technical_constraints": {
                "platforms": self._sanitize_string_list(constraints.get("platforms", []), limit=20),
                "technologies": self._sanitize_string_list(constraints.get("technologies", []), limit=20),
                "integrations": self._sanitize_string_list(constraints.get("integrations", []), limit=20),
                "security_requirements": self._sanitize_string_list(
                    constraints.get("security_requirements", []),
                    limit=20
                )
            },
            "stakeholders": self._sanitize_stakeholders(data.get("stakeholders", [])),
            "assumptions": self._sanitize_string_list(data.get("assumptions", []), limit=20),
            "risks": self._sanitize_risks(data.get("risks", [])),
            "clarifications_needed": self._sanitize_string_list(
                data.get("clarifications_needed", []),
                limit=self.MAX_QUESTIONS_FOR_SYNTHESIS
            )
        }

    def _sanitize_final_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a final analysis payload before it reaches downstream agents."""
        project_info = data.get("project_info", {}) if isinstance(data, dict) else {}
        constraints = data.get("technical_constraints", {}) if isinstance(data, dict) else {}
        return {
            "project_info": {
                "project_name": "" if self._is_placeholder_text(project_info.get("project_name")) else self._normalize_space(project_info.get("project_name")),
                "description": "" if self._is_placeholder_text(project_info.get("description")) else self._normalize_space(project_info.get("description")),
                "project_type": "" if self._is_placeholder_text(project_info.get("project_type")) else self._normalize_space(project_info.get("project_type")),
                "estimated_duration": self._normalize_space(project_info.get("estimated_duration")),
                "complexity_level": self._normalize_space(project_info.get("complexity_level"))
            },
            "functional_requirements": self._sanitize_requirement_items(
                data.get("functional_requirements", []),
                nfr=False
            ),
            "non_functional_requirements": self._sanitize_requirement_items(
                data.get("non_functional_requirements", []),
                nfr=True
            ),
            "technical_constraints": {
                "platforms": self._sanitize_string_list(constraints.get("platforms", []), limit=20),
                "technologies": self._sanitize_string_list(constraints.get("technologies", []), limit=20),
                "integrations": self._sanitize_string_list(constraints.get("integrations", []), limit=20),
                "security_requirements": self._sanitize_string_list(
                    constraints.get("security_requirements", []),
                    limit=20
                )
            },
            "stakeholders": self._sanitize_stakeholders(data.get("stakeholders", [])),
            "assumptions": self._sanitize_string_list(data.get("assumptions", []), limit=20),
            "risks": self._sanitize_risks(data.get("risks", [])),
            "clarifications_needed": self._sanitize_string_list(
                data.get("clarifications_needed", []),
                limit=self.MAX_QUESTIONS_FOR_SYNTHESIS
            )
        }

    def _count_meaningful_requirements(self, items: Any) -> int:
        """Count non-placeholder requirements."""
        return len(self._sanitize_requirement_items(items, nfr=False))

    def _analyze_full_document_fallback(
        self,
        document_content: str,
        chunk_errors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Retry analysis with the legacy full-document prompt when chunked mode fails."""
        content = document_content
        if len(content) > self.MAX_FULL_DOCUMENT_CHARS:
            logger.warning(
                f"[{self.name}] Full-document fallback truncated from {len(content)} "
                f"to {self.MAX_FULL_DOCUMENT_CHARS} characters"
            )
            content = content[:self.MAX_FULL_DOCUMENT_CHARS] + "\n\n... (документ обрезан из-за ограничений размера)"

        message = f"""Проанализируй следующее техническое задание и предоставь структурированный анализ.

ВЕРНИ ТОЛЬКО JSON БЕЗ КАКИХ-ЛИБО ДОПОЛНИТЕЛЬНЫХ КОММЕНТАРИЕВ.

Техническое задание:
{content}

JSON:"""

        result = self.send_message(
            message,
            expect_json=True,
            use_history=False,
            max_tokens=max(Config.DEFAULT_LLM_MAX_TOKENS, 8000),
            temperature=0.0,
            system_prompt=self._build_full_document_system_prompt()
        )

        if not result.get("success"):
            return result

        analysis = self._sanitize_final_analysis(result["data"])
        if self._count_meaningful_requirements(analysis.get("functional_requirements", [])) == 0:
            return {
                "success": False,
                "error": "Full-document fallback returned no meaningful functional requirements",
                "raw_response": result.get("raw_response", "")[:2000]
            }

        return {
            "success": True,
            "analysis": analysis,
            "metadata": {
                "used_full_document_fallback": True,
                "analysis_chunk_errors": chunk_errors or []
            }
        }

    def _normalize_space(self, value: Any) -> str:
        """Normalize spaces in text values."""
        return " ".join(str(value or "").strip().split())

    def _split_large_paragraph(self, paragraph: str, max_chars: int) -> List[str]:
        """Split a large paragraph into smaller sentence-based pieces."""
        text = self._normalize_space(paragraph)
        if len(text) <= max_chars:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        segments: List[str] = []
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) > max_chars:
                for start in range(0, len(sentence), max_chars):
                    part = sentence[start:start + max_chars].strip()
                    if part:
                        segments.append(part)
                continue

            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                segments.append(current)
                current = sentence
            else:
                current = candidate

        if current:
            segments.append(current)
        return segments or [text[:max_chars]]

    def _looks_like_heading(self, paragraph: str) -> bool:
        """Heuristic for detecting heading-like paragraphs."""
        text = self._normalize_space(paragraph)
        if not text or len(text) > 120:
            return False
        if text.endswith((".", ",", ";", ":")):
            return False
        if "|" in text:
            return False
        if re.match(r"^\d+(\.\d+)*[\.)]?\s+\S+", text):
            return True
        if text.isupper():
            return True
        words = text.split()
        return len(words) <= 8 and text[:1].isupper()

    def _split_document_into_chunks(self, document_content: str) -> List[Dict[str, str]]:
        """Split the document into small semantically meaningful chunks."""
        target_size = max(2000, Config.ANALYSIS_CHUNK_CHARS)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", document_content) if p.strip()]
        if len(paragraphs) <= 1:
            paragraphs = [line.strip() for line in document_content.splitlines() if line.strip()]
        chunks: List[Dict[str, str]] = []
        current_parts: List[str] = []
        current_heading = "Общий контекст"
        current_size = 0

        def flush_chunk() -> None:
            nonlocal current_parts, current_size
            if not current_parts:
                return
            chunks.append({
                "title": current_heading,
                "content": "\n\n".join(current_parts)
            })
            current_parts = []
            current_size = 0

        for paragraph in paragraphs:
            pieces = self._split_large_paragraph(paragraph, target_size)
            for piece in pieces:
                if self._looks_like_heading(piece):
                    if current_parts:
                        flush_chunk()
                    current_heading = piece[:120]

                piece_len = len(piece)
                if current_parts and current_size + piece_len > target_size:
                    flush_chunk()

                current_parts.append(piece)
                current_size += piece_len

        flush_chunk()

        if not chunks:
            chunks.append({
                "title": "Полный документ",
                "content": document_content[:target_size]
            })

        for idx, chunk in enumerate(chunks, start=1):
            chunk["id"] = f"chunk-{idx}"
        return chunks

    def _merge_unique_strings(self, values: List[Any], limit: Optional[int] = None) -> List[str]:
        """Merge strings while preserving order."""
        seen = set()
        result: List[str] = []
        for value in values:
            normalized = self._normalize_space(value)
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(normalized)
            if limit and len(result) >= limit:
                break
        return result

    def _merge_requirements(self, items: List[Dict[str, Any]], nfr: bool = False) -> List[Dict[str, Any]]:
        """Merge requirement objects by normalized name."""
        merged: Dict[str, Dict[str, Any]] = {}
        priority_rank = {"Высокий": 3, "Средний": 2, "Низкий": 1}

        for item in items:
            name = self._normalize_space(item.get("name"))
            if not name:
                continue
            key = name.lower()
            description = self._normalize_space(item.get("description"))
            category = self._normalize_space(item.get("category"))
            if key not in merged:
                merged[key] = {
                    "name": name,
                    "description": description or name,
                    "category": category or ("Общее" if nfr else "Бизнес-логика")
                }
                if not nfr:
                    merged[key]["priority"] = self._normalize_space(item.get("priority")) or "Средний"
                continue

            current = merged[key]
            if len(description) > len(current.get("description", "")):
                current["description"] = description
            if category and len(category) > len(current.get("category", "")):
                current["category"] = category
            if not nfr:
                current_priority = current.get("priority", "Средний")
                new_priority = self._normalize_space(item.get("priority")) or current_priority
                if priority_rank.get(new_priority, 0) > priority_rank.get(current_priority, 0):
                    current["priority"] = new_priority

        return list(merged.values())

    def _merge_stakeholders(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge stakeholder objects by role."""
        merged: Dict[str, Dict[str, Any]] = {}
        for item in items:
            role = self._normalize_space(item.get("role"))
            if not role:
                continue
            key = role.lower()
            interests = self._normalize_space(item.get("interests"))
            involvement = self._normalize_space(item.get("involvement"))
            current = merged.setdefault(key, {
                "role": role,
                "interests": interests,
                "involvement": involvement or "Средняя"
            })
            if len(interests) > len(current.get("interests", "")):
                current["interests"] = interests
            if involvement and len(involvement) > len(current.get("involvement", "")):
                current["involvement"] = involvement
        return list(merged.values())

    def _merge_risks(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge risk objects by description."""
        merged: Dict[str, Dict[str, Any]] = {}
        for item in items:
            description = self._normalize_space(item.get("description"))
            if not description:
                continue
            key = description.lower()
            current = merged.setdefault(key, {
                "description": description,
                "probability": self._normalize_space(item.get("probability")) or "Средняя",
                "impact": self._normalize_space(item.get("impact")) or "Среднее",
                "mitigation": self._normalize_space(item.get("mitigation"))
            })
            mitigation = self._normalize_space(item.get("mitigation"))
            if len(mitigation) > len(current.get("mitigation", "")):
                current["mitigation"] = mitigation
        return list(merged.values())

    def _merge_partial_analyses(self, partials: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge chunk-level extraction results into compact structured data."""
        project_hints = {
            "project_names": [],
            "descriptions": [],
            "project_type_hints": [],
            "complexity_hints": []
        }
        technical_constraints = {
            "platforms": [],
            "technologies": [],
            "integrations": [],
            "security_requirements": []
        }
        functional_requirements: List[Dict[str, Any]] = []
        non_functional_requirements: List[Dict[str, Any]] = []
        stakeholders: List[Dict[str, Any]] = []
        assumptions: List[str] = []
        risks: List[Dict[str, Any]] = []
        clarifications: List[str] = []

        for partial in partials:
            hints = partial.get("project_hints", {})
            for key in project_hints:
                project_hints[key].extend(hints.get(key, []))

            constraints = partial.get("technical_constraints", {})
            for key in technical_constraints:
                technical_constraints[key].extend(constraints.get(key, []))

            functional_requirements.extend(partial.get("functional_requirements", []))
            non_functional_requirements.extend(partial.get("non_functional_requirements", []))
            stakeholders.extend(partial.get("stakeholders", []))
            assumptions.extend(partial.get("assumptions", []))
            risks.extend(partial.get("risks", []))
            clarifications.extend(partial.get("clarifications_needed", []))

        return {
            "project_hints": {
                key: self._merge_unique_strings(values, limit=10)
                for key, values in project_hints.items()
            },
            "functional_requirements": self._merge_requirements(
                functional_requirements
            )[:self.MAX_REQUIREMENTS_FOR_SYNTHESIS],
            "non_functional_requirements": self._merge_requirements(
                non_functional_requirements, nfr=True
            )[:self.MAX_REQUIREMENTS_FOR_SYNTHESIS],
            "technical_constraints": {
                key: self._merge_unique_strings(values, limit=20)
                for key, values in technical_constraints.items()
            },
            "stakeholders": self._merge_stakeholders(stakeholders)[:20],
            "assumptions": self._merge_unique_strings(assumptions, limit=20),
            "risks": self._merge_risks(risks)[:self.MAX_RISKS_FOR_SYNTHESIS],
            "clarifications_needed": self._merge_unique_strings(
                clarifications, limit=self.MAX_QUESTIONS_FOR_SYNTHESIS
            )
        }

    def _build_chunk_message(self, chunk: Dict[str, str], index: int, total: int) -> str:
        """Build a user message for chunk-level extraction."""
        return f"""Разбери фрагмент {index} из {total} технического задания.

Название/контекст фрагмента: {chunk.get("title", f"Фрагмент {index}")}.

Извлеки требования, ограничения, риски и вопросы только из этого фрагмента.
Не дублируй одно и то же разными формулировками.

Фрагмент:
{chunk["content"]}

JSON:"""

    def _analyze_chunk(self, chunk: Dict[str, str], index: int, total: int) -> Dict[str, Any]:
        """Analyze a single chunk using a stateless low-context call."""
        message = self._build_chunk_message(chunk, index, total)
        worker = AnalystAgent()
        if self._progress_tracker:
            worker.set_progress_tracker(self._progress_tracker, stream_events=False)
        result = worker.send_message(
            message,
            expect_json=True,
            use_history=False,
            max_tokens=Config.ANALYSIS_CHUNK_MAX_TOKENS,
            temperature=0.0,
            system_prompt=worker._build_chunk_system_prompt()
        )

        if result.get("success"):
            result["data"] = self._sanitize_partial_analysis(result.get("data", {}))
            return result

        logger.warning(
            f"[{self.name}] Chunk {index} primary extraction failed, retrying with rescue prompt: "
            f"{result.get('error')}"
        )

        rescue_result = worker.send_message(
            self._build_chunk_rescue_message(chunk, index, total),
            expect_json=True,
            use_history=False,
            max_tokens=max(Config.ANALYSIS_CHUNK_MAX_TOKENS, 4000),
            temperature=0.0,
            system_prompt=worker._build_chunk_rescue_system_prompt()
        )

        if rescue_result.get("success"):
            rescue_result["data"] = self._sanitize_partial_analysis(rescue_result.get("data", {}))
            rescue_result["warning"] = f"chunk {index} required rescue retry"
            return rescue_result

        fallback_error = rescue_result.get("error") or result.get("error", "unknown error")
        logger.warning(
            f"[{self.name}] Chunk {index} rescue failed, using empty partial fallback: {fallback_error}"
        )
        return {
            "success": True,
            "data": self._empty_partial_analysis(),
            "warning": f"chunk {index} used empty fallback after JSON errors: {fallback_error}"
        }

    def _build_fallback_analysis(self, merged: Dict[str, Any]) -> Dict[str, Any]:
        """Build analysis deterministically if synthesis call fails."""
        hints = merged.get("project_hints", {})
        project_type = (hints.get("project_type_hints") or ["Веб-приложение (среднее)"])[0]
        complexity = (hints.get("complexity_hints") or ["Средний"])[0]
        baselines = self._estimation_rules.get("project_type_baselines", {})
        estimated_duration = baselines.get(project_type, {}).get("typical_duration_weeks", "8-16")

        analysis = {
            "project_info": {
                "project_name": (hints.get("project_names") or ["Проект"])[0],
                "description": (hints.get("descriptions") or ["Описание проекта собрано из фрагментов ТЗ."])[0],
                "project_type": project_type,
                "estimated_duration": f"{estimated_duration} недель" if estimated_duration.isdigit() else estimated_duration,
                "complexity_level": complexity
            },
            "functional_requirements": [],
            "non_functional_requirements": [],
            "technical_constraints": merged.get("technical_constraints", {}),
            "stakeholders": merged.get("stakeholders", []),
            "assumptions": merged.get("assumptions", []),
            "risks": [],
            "clarifications_needed": merged.get("clarifications_needed", [])
        }

        for idx, item in enumerate(merged.get("functional_requirements", []), start=1):
            analysis["functional_requirements"].append({
                "id": f"FR-{idx}",
                "name": item.get("name", f"Требование {idx}"),
                "description": item.get("description", item.get("name", "")),
                "priority": item.get("priority", "Средний"),
                "category": item.get("category", "Бизнес-логика")
            })

        for idx, item in enumerate(merged.get("non_functional_requirements", []), start=1):
            analysis["non_functional_requirements"].append({
                "id": f"NFR-{idx}",
                "name": item.get("name", f"Нефункциональное требование {idx}"),
                "description": item.get("description", item.get("name", "")),
                "category": item.get("category", "Общее")
            })

        for idx, risk in enumerate(merged.get("risks", []), start=1):
            analysis["risks"].append({
                "id": f"R-{idx}",
                "description": risk.get("description", ""),
                "probability": risk.get("probability", "Средняя"),
                "impact": risk.get("impact", "Среднее"),
                "mitigation": risk.get("mitigation", "")
            })

        return analysis

    def analyze_specification(self, document_content: str) -> Dict[str, Any]:
        """Analyze a technical specification document with small parallel calls."""
        logger.info(f"[{self.name}] Starting specification analysis...")

        chunks = self._split_document_into_chunks(document_content)
        total_chunks = len(chunks)
        logger.info(f"[{self.name}] Split specification into {total_chunks} chunks")
        self._record_intermediate(
            "chunks_created",
            {
                "total_chunks": total_chunks,
                "chunks": [
                    {
                        "id": chunk.get("id"),
                        "title": chunk.get("title"),
                        "chars": len(chunk.get("content", ""))
                    }
                    for chunk in chunks
                ]
            }
        )

        if self._progress_tracker:
            self._progress_tracker.info(
                f"🧩 Аналитик разбил ТЗ на {total_chunks} небольших фрагментов"
            )

        partials: List[Dict[str, Any]] = []
        errors: List[str] = []
        max_workers = max(1, min(Config.LLM_MAX_PARALLEL_REQUESTS, total_chunks))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._analyze_chunk, chunk, idx, total_chunks): idx
                for idx, chunk in enumerate(chunks, start=1)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result()
                    if result.get("success"):
                        partials.append(result["data"])
                        if result.get("warning"):
                            errors.append(result["warning"])
                        if self._progress_tracker:
                            self._progress_tracker.info(
                                f"📌 Обработан фрагмент ТЗ {idx}/{total_chunks}"
                            )
                    else:
                        errors.append(f"chunk {idx}: {result.get('error', 'unknown error')}")
                except Exception as exc:
                    logger.exception(f"[{self.name}] Chunk {idx} analysis failed: {exc}")
                    errors.append(f"chunk {idx}: {exc}")

        self._record_intermediate(
            "chunk_results_collected",
            {
                "successful_chunks": len(partials),
                "errors": errors,
                "partials": partials
            }
        )

        if not partials:
            error_message = "; ".join(errors) or "No chunk analysis results"
            logger.error(f"[{self.name}] Specification analysis failed: {error_message}")
            self._record_intermediate(
                "analysis_failed",
                {
                    "error": error_message,
                    "analysis_chunks": total_chunks,
                    "analysis_chunk_errors": errors
                }
            )
            return {
                "success": False,
                "error": error_message
            }

        merged = self._merge_partial_analyses(partials)
        self._record_intermediate("merged_chunk_analysis", merged)

        if self._count_meaningful_requirements(merged.get("functional_requirements", [])) == 0:
            logger.warning(
                f"[{self.name}] Chunked analysis produced no meaningful functional requirements, "
                "retrying with full-document fallback"
            )
            fallback_result = self._analyze_full_document_fallback(document_content, errors)
            if fallback_result.get("success"):
                return fallback_result

            error_message = fallback_result.get(
                "error",
                "Chunked analysis and full-document fallback produced no meaningful functional requirements"
            )
            logger.error(f"[{self.name}] Specification analysis failed: {error_message}")
            self._record_intermediate(
                "analysis_failed_after_fallback",
                {
                    "error": error_message,
                    "analysis_chunks": total_chunks,
                    "analysis_chunk_errors": errors
                }
            )
            return {
                "success": False,
                "error": error_message,
                "metadata": {
                    "analysis_chunks": total_chunks,
                    "analysis_chunk_errors": errors,
                    "used_full_document_fallback": True
                }
            }

        if self._progress_tracker:
            self._progress_tracker.info(
                "🧠 Аналитик собирает единый структурированный анализ из частичных результатов"
            )

        if not Config.ENABLE_ANALYSIS_SYNTHESIS_LLM:
            logger.info(f"[{self.name}] LLM synthesis disabled, using deterministic merge")
            fallback_analysis = self._build_fallback_analysis(merged)
            self._record_intermediate(
                "analysis_completed",
                {
                    "mode": "deterministic_merge",
                    "analysis": fallback_analysis,
                    "metadata": {
                        "analysis_chunks": total_chunks,
                        "analysis_chunk_errors": errors,
                        "used_fallback_merge": True,
                        "skipped_llm_synthesis": True
                    }
                }
            )
            return {
                "success": True,
                "analysis": fallback_analysis,
                "metadata": {
                    "analysis_chunks": total_chunks,
                    "analysis_chunk_errors": errors,
                    "used_fallback_merge": True,
                    "skipped_llm_synthesis": True
                }
            }

        synthesis_payload = json.dumps(merged, ensure_ascii=False, indent=2)
        synthesis_message = f"""Собери итоговый анализ проекта по агрегированным данным из нескольких фрагментов ТЗ.

Агрегированные данные:
{synthesis_payload}

Сформируй единый JSON:"""

        result = self.send_message(
            synthesis_message,
            expect_json=True,
            use_history=False,
            max_tokens=Config.ANALYSIS_SYNTHESIS_MAX_TOKENS,
            temperature=0.0
        )

        if result["success"]:
            analysis = self._sanitize_final_analysis(result["data"])
            if self._count_meaningful_requirements(analysis.get("functional_requirements", [])) == 0:
                logger.warning(
                    f"[{self.name}] Synthesis returned no meaningful functional requirements, "
                    "falling back to deterministic merge"
                )
                fallback_analysis = self._build_fallback_analysis(merged)
                self._record_intermediate(
                    "analysis_completed",
                    {
                        "mode": "fallback_after_empty_synthesis",
                        "analysis": fallback_analysis,
                        "metadata": {
                            "analysis_chunks": total_chunks,
                            "analysis_chunk_errors": errors,
                            "used_fallback_merge": True,
                            "discarded_empty_synthesis": True,
                            "synthesis_usage": result.get("usage", {})
                        }
                    }
                )
                return {
                    "success": True,
                    "analysis": fallback_analysis,
                    "metadata": {
                        "analysis_chunks": total_chunks,
                        "analysis_chunk_errors": errors,
                        "used_fallback_merge": True,
                        "discarded_empty_synthesis": True,
                        "synthesis_usage": result.get("usage", {})
                    }
                }
            logger.info(f"[{self.name}] Specification analysis completed successfully")
            self._record_intermediate(
                "analysis_completed",
                {
                    "mode": "llm_synthesis",
                    "analysis": analysis,
                    "metadata": {
                        "analysis_chunks": total_chunks,
                        "analysis_chunk_errors": errors,
                        "synthesis_usage": result.get("usage", {})
                    }
                }
            )
            return {
                "success": True,
                "analysis": analysis,
                "metadata": {
                    "analysis_chunks": total_chunks,
                    "analysis_chunk_errors": errors,
                    "synthesis_usage": result.get("usage", {})
                }
            }

        logger.warning(
            f"[{self.name}] Synthesis failed, falling back to deterministic merge: "
            f"{result.get('error')}"
        )
        fallback_analysis = self._build_fallback_analysis(merged)
        self._record_intermediate(
            "analysis_completed",
            {
                "mode": "fallback_after_synthesis_error",
                "analysis": fallback_analysis,
                "metadata": {
                    "analysis_chunks": total_chunks,
                    "analysis_chunk_errors": errors,
                    "used_fallback_merge": True,
                    "synthesis_usage": result.get("usage", {})
                }
            }
        )
        return {
            "success": True,
            "analysis": fallback_analysis,
            "metadata": {
                "analysis_chunks": total_chunks,
                "analysis_chunk_errors": errors,
                "used_fallback_merge": True,
                "synthesis_usage": result.get("usage", {})
            }
        }

    def request_clarification(self, question: str) -> Dict[str, Any]:
        """Request clarification on a specific topic."""
        message = f"Уточни, пожалуйста: {question}"
        return self.send_message(message, expect_json=False, use_history=False, max_tokens=800)

    def refine_analysis(self, original_analysis: Dict[str, Any],
                        clarifications: Dict[str, str]) -> Dict[str, Any]:
        """Refine the analysis based on clarifications."""
        clarification_text = "\n".join(
            f"Вопрос: {q}\nОтвет: {a}"
            for q, a in clarifications.items()
        )

        message = f"""На основе полученных уточнений, обнови анализ проекта.

Исходный анализ:
{json.dumps(original_analysis, ensure_ascii=False, indent=2)}

Уточнения:
{clarification_text}

Предоставь обновленный анализ в том же JSON формате."""

        result = self.send_message(
            message,
            expect_json=True,
            use_history=False,
            max_tokens=Config.ANALYSIS_SYNTHESIS_MAX_TOKENS,
            temperature=0.0
        )

        if result["success"]:
            return {
                "success": True,
                "analysis": result["data"]
            }
        return result
