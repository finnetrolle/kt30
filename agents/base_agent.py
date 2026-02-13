"""
Base agent class for the multi-agent system.
"""
import logging
import json
import re
import time
from typing import Dict, Any, Optional, List
from openai import OpenAI
from config import Config

logger = logging.getLogger(__name__)


class AgentEventLogger:
    """Logger for agent events with structured output."""
    
    @staticmethod
    def log_agent_started(agent_name: str, task: str):
        """Log when an agent starts working on a task."""
        logger.info(f"\n{'='*60}")
        logger.info(f"🤖 АГЕНТ НАЧАЛ РАБОТУ: {agent_name}")
        logger.info(f"📋 Задача: {task}")
        logger.info(f"{'='*60}")
    
    @staticmethod
    def log_llm_request(agent_name: str, message_preview: str, request_id: str = None):
        """Log when an agent sends a request to the LLM."""
        logger.info(f"\n{'─'*60}")
        logger.info(f"📤 [{agent_name}] ОТПРАВКА ЗАПРОСА В LLM")
        if request_id:
            logger.info(f"   Request ID: {request_id}")
        logger.info(f"   Сообщение (первые 200 символов):")
        logger.info(f"   {message_preview[:200]}...")
        logger.info(f"{'─'*60}")
    
    @staticmethod
    def log_llm_response(agent_name: str, response_preview: str, elapsed_time: float = None):
        """Log when an agent receives a response from the LLM."""
        logger.info(f"\n{'─'*60}")
        logger.info(f"📥 [{agent_name}] ПОЛУЧЕН ОТВЕТ ОТ LLM")
        if elapsed_time:
            logger.info(f"   Время ожидания: {elapsed_time:.2f} сек")
        logger.info(f"   Ответ (первые 300 символов):")
        logger.info(f"   {response_preview[:300]}...")
        logger.info(f"{'─'*60}")
    
    @staticmethod
    def log_agent_handoff(from_agent: str, to_agent: str, data_description: str):
        """Log when one agent hands off work to another agent."""
        logger.info(f"\n{'*'*60}")
        logger.info(f"🔄 ПЕРЕДАЧА ЗАДАЧИ МЕЖДУ АГЕНТАМИ")
        logger.info(f"   От: {from_agent}")
        logger.info(f"   Кому: {to_agent}")
        logger.info(f"   Передаваемые данные: {data_description}")
        logger.info(f"{'*'*60}")
    
    @staticmethod
    def log_agent_completed(agent_name: str, result_summary: str):
        """Log when an agent completes its task."""
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ АГЕНТ ЗАВЕРШИЛ РАБОТУ: {agent_name}")
        logger.info(f"   Результат: {result_summary}")
        logger.info(f"{'='*60}\n")
    
    @staticmethod
    def log_agent_error(agent_name: str, error: str):
        """Log when an agent encounters an error."""
        logger.error(f"\n{'!'*60}")
        logger.error(f"❌ ОШИБКА АГЕНТА: {agent_name}")
        logger.error(f"   Ошибка: {error}")
        logger.error(f"{'!'*60}\n")


class BaseAgent:
    """Base class for all agents in the multi-agent system."""
    
    def __init__(self, name: str, role: str):
        """Initialize the base agent.
        
        Args:
            name: Agent name for logging
            role: Agent role description
        """
        self.name = name
        self.role = role
        self.client = OpenAI(
            api_key=Config.OPENAI_API_KEY,
            base_url=Config.OPENAI_API_BASE
        )
        self.model = Config.OPENAI_MODEL
        self.json_mode = Config.OPENAI_JSON_MODE
        self.conversation_history: List[Dict[str, str]] = []
        self.event_logger = AgentEventLogger()
        
        logger.info(f"🤖 Агент '{name}' инициализирован")
        logger.info(f"   Роль: {role}")
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for this agent.
        
        Returns:
            System prompt string
        """
        raise NotImplementedError("Subclasses must implement _build_system_prompt")
    
    def _extract_json_from_response(self, text: str) -> Optional[str]:
        """Extract JSON from response that might contain markdown or other text.
        
        Args:
            text: Raw response text
            
        Returns:
            Extracted JSON string or None if not found
        """
        # Try to parse the whole text as JSON
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        
        # Find JSON in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json_match.group(1).strip()
        
        # Find all JSON objects and try each
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
        
        # Try each candidate, starting from the largest
        candidates.sort(key=len, reverse=True)
        
        for candidate in candidates:
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
        
        # Last resort - find first { and last }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return text[first_brace:last_brace + 1]
        
        return None
    
    def send_message(self, message: str, expect_json: bool = True, 
                     request_id: str = None) -> Dict[str, Any]:
        """Send a message to the agent and get a response.
        
        Args:
            message: Message to send
            expect_json: Whether to parse response as JSON
            request_id: Optional request ID for tracking
            
        Returns:
            Response dictionary
        """
        # Log LLM request
        self.event_logger.log_llm_request(self.name, message, request_id)
        
        # Add message to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        # Build messages for API call
        messages = [
            {"role": "system", "content": self._build_system_prompt()}
        ] + self.conversation_history
        
        # Prepare API call parameters
        api_params = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 8000
        }
        
        if self.json_mode and expect_json:
            api_params["response_format"] = {"type": "json_object"}
            logger.info(f"   [Using JSON response format]")
        
        try:
            start_time = time.time()
            logger.info(f"   [Вызов API...]")
            
            response = self.client.chat.completions.create(**api_params)
            
            elapsed_time = time.time() - start_time
            response_text = response.choices[0].message.content
            
            # Log LLM response
            self.event_logger.log_llm_response(self.name, response_text, elapsed_time)
            
            # Log token usage if available
            if response.usage:
                logger.info(f"   Токены: prompt={response.usage.prompt_tokens}, "
                           f"completion={response.usage.completion_tokens}, "
                           f"total={response.usage.total_tokens}")
            
            # Add response to conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": response_text
            })
            
            if expect_json:
                json_text = self._extract_json_from_response(response_text)
                if json_text:
                    parsed_data = json.loads(json_text)
                    logger.info(f"   ✅ JSON успешно извлечен и распарсен")
                    return {
                        "success": True,
                        "data": parsed_data,
                        "raw_response": response_text,
                        "elapsed_time": elapsed_time
                    }
                else:
                    logger.warning(f"   ⚠️ Не удалось извлечь JSON из ответа")
                    return {
                        "success": False,
                        "error": "Could not extract JSON from response",
                        "raw_response": response_text
                    }
            else:
                return {
                    "success": True,
                    "data": response_text,
                    "elapsed_time": elapsed_time
                }
                
        except Exception as e:
            self.event_logger.log_agent_error(self.name, str(e))
            return {
                "success": False,
                "error": str(e)
            }
    
    def reset_conversation(self):
        """Reset the conversation history."""
        self.conversation_history = []
        logger.info(f"[{self.name}] История对话 сброшена")
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation.
        
        Returns:
            Summary string
        """
        return f"Agent: {self.name}\nMessages exchanged: {len(self.conversation_history)}"
