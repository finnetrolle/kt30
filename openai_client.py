"""
OpenAI API client module for analyzing technical specifications and generating WBS.
"""
import json
import os
import logging
import time
import re
from typing import Optional, Dict, Any
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError
from config import Config


logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client for interacting with OpenAI API."""
    
    def __init__(self):
        """Initialize the OpenAI client."""
        logger.info("Initializing OpenAI client...")
        logger.info(f"  - API Base URL: {Config.OPENAI_API_BASE}")
        logger.info(f"  - Model: {Config.OPENAI_MODEL}")
        logger.info(f"  - JSON Mode: {Config.OPENAI_JSON_MODE}")
        
        # Mask API key for logging
        api_key = Config.OPENAI_API_KEY
        if api_key:
            masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
            logger.info(f"  - API Key: {masked_key}")
        else:
            logger.warning("  - API Key: NOT SET!")
        
        self.client = OpenAI(
            api_key=Config.OPENAI_API_KEY,
            base_url=Config.OPENAI_API_BASE
        )
        self.model = Config.OPENAI_MODEL
        self.json_mode = Config.OPENAI_JSON_MODE
        self.wbs_template = self._load_wbs_template()
        logger.info("OpenAI client initialized successfully")
    
    def _load_wbs_template(self) -> str:
        """Load the WBS template from file.
        
        Returns:
            Content of the WBS template file
        """
        template_path = Config.WBS_TEMPLATE_PATH
        logger.info(f"Loading WBS template from: {template_path}")
        
        if not os.path.exists(template_path):
            logger.error(f"WBS template file not found: {template_path}")
            raise FileNotFoundError(f"WBS template file not found: {template_path}")
        
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"WBS template loaded: {len(content)} characters")
        return content
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM.
        
        Returns:
            System prompt string
        """
        # Use a more direct prompt that works with various LLM models
        return """Ты генерируешь Work Breakdown Structure (WBS) для проектов разработки ПО.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON. НЕ ПИШИ НИЧЕГО КРОМЕ JSON.

Пример формата ответа:
{"project_info":{"project_name":"Пример","description":"Описание","estimated_duration":"4 недели","complexity_level":"Средний"},"wbs":{"phases":[{"id":"1","name":"Планирование","description":"Фаза планирования","duration":"1 неделя","work_packages":[{"id":"1.1","name":"Анализ требований","description":"Сбор требований","estimated_hours":16,"dependencies":[],"deliverables":["Документ требований"],"skills_required":["Аналитик"],"tasks":[{"id":"1.1.1","name":"Интервью","description":"Интервью с заказчиком","estimated_hours":8,"status":"pending"}]}]}]},"risks":[],"assumptions":[],"recommendations":[]}

Структура:
- project_info: информация о проекте
- wbs.phases: фазы проекта (Планирование, Проектирование, Разработка, Тестирование, Развертывание, Поддержка)
- work_packages: пакеты работ в каждой фазе
- tasks: задачи в каждом пакете
- risks: риски проекта
- assumptions: предположения
- recommendations: рекомендации

Правила:
1. Оценивай трудозатраты в часах
2. Указывай зависимости между задачами
3. Выделяй необходимые навыки
4. Формируй список результатов (deliverables)"""

    def _build_user_prompt(self, document_content: str) -> str:
        """Build the user prompt with document content.
        
        Args:
            document_content: Content of the technical specification document
            
        Returns:
            User prompt string
        """
        # Truncate document if too long
        max_chars = 8000
        if len(document_content) > max_chars:
            document_content = document_content[:max_chars] + "\n... (документ обрезан)"
            logger.warning(f"Document truncated to {max_chars} characters")
        
        return f"""Создай WBS для следующего технического задания.

ВЕРНИ ТОЛЬКО JSON БЕЗ КАКИХ-ЛИБО ДОПОЛНИТЕЛЬНЫХ КОММЕНТАРИЕВ.

Техническое задание:
{document_content}

JSON:"""

    def _extract_json_from_response(self, text: str, log_prefix: str = "") -> str:
        """Extract JSON from response that might contain markdown or other text.
        
        Args:
            text: Raw response text
            log_prefix: Prefix for logging
            
        Returns:
            Extracted JSON string or None if not found
        """
        logger.info(f"{log_prefix}Attempting to extract JSON from response...")
        logger.debug(f"{log_prefix}Response starts with: {text[:300]}...")
        
        # Method 1: Try to parse the whole text as JSON
        try:
            json.loads(text)
            logger.info(f"{log_prefix}Entire response is valid JSON")
            return text
        except json.JSONDecodeError:
            pass
        
        # Method 2: Find JSON in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            extracted = json_match.group(1).strip()
            logger.info(f"{log_prefix}Found JSON in markdown code block")
            return extracted
        
        # Method 3: Find all JSON objects and try each
        # Look for complete JSON objects
        brace_count = 0
        json_start = -1
        candidates = []
        
        for i, char in enumerate(text):
            if char == '{':
                if brace_count == 0:
                    json_start = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and json_start != -1:
                    candidates.append(text[json_start:i+1])
                    json_start = -1
        
        # Try each candidate, starting from the largest (usually the main response)
        candidates.sort(key=len, reverse=True)
        
        for candidate in candidates:
            try:
                json.loads(candidate)
                logger.info(f"{log_prefix}Found valid JSON object ({len(candidate)} chars)")
                return candidate
            except json.JSONDecodeError:
                continue
        
        # Method 4: Last resort - find first { and last }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            extracted = text[first_brace:last_brace + 1]
            logger.info(f"{log_prefix}Extracted text between first and last brace")
            return extracted
        
        logger.error(f"{log_prefix}Could not extract JSON from response")
        return None

    def analyze_document(self, document_content: str, request_id: str = None) -> Dict[str, Any]:
        """Analyze a technical specification document and generate WBS.
        
        Args:
            document_content: Content of the technical specification document
            request_id: Optional request ID for logging
            
        Returns:
            Dictionary containing the WBS analysis result
        """
        log_prefix = f"[{request_id}] " if request_id else ""
        
        logger.info(f"{log_prefix}Starting document analysis...")
        logger.info(f"{log_prefix}  - Document content length: {len(document_content)} characters")
        logger.info(f"{log_prefix}  - JSON mode: {self.json_mode}")
        
        try:
            # Build prompts
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(document_content)
            
            logger.info(f"{log_prefix}  - System prompt length: {len(system_prompt)} characters")
            logger.info(f"{log_prefix}  - User prompt length: {len(user_prompt)} characters")
            
            # Prepare API call parameters
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1,  # Very low temperature for consistent JSON
                "max_tokens": 8000   # Increased token limit
            }
            
            # Only add response_format for OpenAI API
            if self.json_mode:
                api_params["response_format"] = {"type": "json_object"}
                logger.info(f"{log_prefix}Using JSON response format mode")
            
            # Make API call
            logger.info(f"{log_prefix}Sending request to API...")
            start_time = time.time()
            
            response = self.client.chat.completions.create(**api_params)
            
            elapsed_time = time.time() - start_time
            logger.info(f"{log_prefix}API response received in {elapsed_time:.2f} seconds")
            
            # Extract the response content
            result_text = response.choices[0].message.content
            logger.info(f"{log_prefix}  - Response length: {len(result_text)} characters")
            
            # Log usage statistics
            if response.usage:
                logger.info(f"{log_prefix}  - Prompt tokens: {response.usage.prompt_tokens}")
                logger.info(f"{log_prefix}  - Completion tokens: {response.usage.completion_tokens}")
                logger.info(f"{log_prefix}  - Total tokens: {response.usage.total_tokens}")
            
            # Check if response was truncated
            if response.usage and response.usage.completion_tokens >= 7900:
                logger.warning(f"{log_prefix}Response may have been truncated (hit token limit)")
            
            # Extract JSON from response
            json_text = self._extract_json_from_response(result_text, log_prefix)
            
            if json_text is None:
                logger.error(f"{log_prefix}No JSON found in response")
                return {
                    "success": False,
                    "error": "Модель не вернула JSON. Возможно, модель не подходит для этой задачи или требует больше токенов.",
                    "raw_response": result_text[:2000]
                }
            
            # Parse JSON response
            logger.info(f"{log_prefix}Parsing JSON response...")
            try:
                result = json.loads(json_text)
            except json.JSONDecodeError as e:
                logger.error(f"{log_prefix}JSON parse error: {str(e)}")
                logger.error(f"{log_prefix}JSON text (first 500 chars): {json_text[:500]}")
                
                return {
                    "success": False,
                    "error": f"Ошибка парсинга JSON: {str(e)}. Модель вернула невалидный JSON.",
                    "raw_response": result_text[:2000],
                    "extracted_json": json_text[:1000]
                }
            
            logger.info(f"{log_prefix}Document analysis completed successfully")
            
            return {
                "success": True,
                "data": result,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                    "elapsed_seconds": round(elapsed_time, 2)
                }
            }
            
        except APIConnectionError as e:
            logger.error(f"{log_prefix}Failed to connect to API: {str(e)}")
            return {
                "success": False,
                "error": f"Не удалось подключиться к API: {str(e)}"
            }
        except APITimeoutError as e:
            logger.error(f"{log_prefix}API request timed out: {str(e)}")
            return {
                "success": False,
                "error": f"Превышено время ожидания ответа от API: {str(e)}"
            }
        except APIError as e:
            logger.error(f"{log_prefix}API error: {str(e)}")
            return {
                "success": False,
                "error": f"Ошибка API: {str(e)}"
            }
        except Exception as e:
            logger.exception(f"{log_prefix}Unexpected error: {str(e)}")
            return {
                "success": False,
                "error": f"Непредвиденная ошибка: {str(e)}"
            }
    
    def test_connection(self) -> bool:
        """Test the connection to OpenAI API.
        
        Returns:
            True if connection is successful, False otherwise
        """
        logger.info("Testing API connection...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "Hello, this is a test."}
                ],
                max_tokens=10
            )
            logger.info("API connection test successful")
            return True
        except Exception as e:
            logger.error(f"API connection test failed: {str(e)}")
            return False


def analyze_specification(document_content: str, request_id: str = None) -> Dict[str, Any]:
    """Analyze a technical specification and generate WBS.
    
    This function now uses the multi-agent system for better results.
    
    Args:
        document_content: Content of the technical specification document
        request_id: Optional request ID for logging
        
    Returns:
        Dictionary containing the analysis result
    """
    log_prefix = f"[{request_id}] " if request_id else ""
    logger.info(f"{log_prefix}Using multi-agent system for WBS generation")
    
    try:
        from agents import AgentOrchestrator
        from config import Config, StabilizationConfig
        
        # Initialize orchestrator with stabilization settings
        orchestrator = AgentOrchestrator(
            stabilization_mode=StabilizationConfig.MODE,
            estimation_rules_path=StabilizationConfig.ESTIMATION_RULES_PATH
        )
        result = orchestrator.generate_wbs(
            document_content,
            stabilization_mode=StabilizationConfig.MODE
        )
        
        if result["success"]:
            logger.info(f"{log_prefix}Multi-agent WBS generation successful")
            
            # Log conversation summary
            conversation_summary = orchestrator.get_conversation_summary()
            logger.debug(f"{log_prefix}Agent conversation:\n{conversation_summary}")
            
            return {
                "success": True,
                "data": result["data"],
                "usage": {
                    "elapsed_seconds": result["metadata"]["elapsed_seconds"],
                    "iterations": result["metadata"]["iterations"],
                    "agent_system": "multi-agent-v1"
                },
                "metadata": result["metadata"],
                "agent_conversation": result.get("agent_conversation", [])
            }
        else:
            logger.error(f"{log_prefix}Multi-agent WBS generation failed: {result.get('error')}")
            return result
            
    except Exception as e:
        logger.exception(f"{log_prefix}Multi-agent system error: {str(e)}")
        logger.info(f"{log_prefix}Falling back to single-agent system")
        
        # Fallback to original single-agent approach
        client = OpenAIClient()
        return client.analyze_document(document_content, request_id=request_id)


def analyze_specification_single_agent(document_content: str, request_id: str = None) -> Dict[str, Any]:
    """Analyze using the original single-agent approach (for comparison).
    
    Args:
        document_content: Content of the technical specification document
        request_id: Optional request ID for logging
        
    Returns:
        Dictionary containing the analysis result
    """
    client = OpenAIClient()
    return client.analyze_document(document_content, request_id=request_id)
