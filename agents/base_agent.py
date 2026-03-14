"""
Base agent class for the multi-agent system.
"""
import json
import logging
import time
from typing import Dict, Any, Optional, List
from openai import OpenAI
from config import Config
from json_utils import extract_json_from_response, repair_json_text
from progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)


class AgentEventLogger:
    """Logger for agent events with structured output.
    
    Optionally emits events to a ProgressTracker for frontend streaming.
    """
    
    def __init__(self):
        self._progress: Optional[ProgressTracker] = None
    
    def set_progress_tracker(self, tracker: Optional[ProgressTracker]):
        """Attach a progress tracker for frontend streaming."""
        self._progress = tracker
    
    def log_agent_started(self, agent_name: str, task: str):
        """Log when an agent starts working on a task."""
        logger.info(f"\n{'='*60}")
        logger.info(f"🤖 АГЕНТ НАЧАЛ РАБОТУ: {agent_name}")
        logger.info(f"📋 Задача: {task}")
        logger.info(f"{'='*60}")
        if self._progress:
            self._progress.agent(agent_name, f"🤖 {agent_name}: {task}")
    
    def log_llm_request(self, agent_name: str, message_preview: str, request_id: str = None):
        """Log when an agent sends a request to the LLM."""
        logger.info(f"\n{'─'*60}")
        logger.info(f"📤 [{agent_name}] ОТПРАВКА ЗАПРОСА В LLM")
        if request_id:
            logger.info(f"   Request ID: {request_id}")
        logger.info(f"   Сообщение (первые 200 символов):")
        logger.info(f"   {message_preview[:200]}...")
        logger.info(f"{'─'*60}")
        if self._progress:
            self._progress.agent(agent_name, f"📤 {agent_name}: отправка запроса в LLM...")
    
    def log_llm_response(self, agent_name: str, response_preview: str, elapsed_time: float = None):
        """Log when an agent receives a response from the LLM."""
        logger.info(f"\n{'─'*60}")
        logger.info(f"📥 [{agent_name}] ПОЛУЧЕН ОТВЕТ ОТ LLM")
        if elapsed_time:
            logger.info(f"   Время ожидания: {elapsed_time:.2f} сек")
        logger.info(f"   Ответ (первые 300 символов):")
        logger.info(f"   {response_preview[:300]}...")
        logger.info(f"{'─'*60}")
        if self._progress:
            time_str = f" ({elapsed_time:.1f} сек)" if elapsed_time else ""
            self._progress.agent(agent_name, f"📥 {agent_name}: ответ получен{time_str}")
    
    def log_agent_handoff(self, from_agent: str, to_agent: str, data_description: str):
        """Log when one agent hands off work to another agent."""
        logger.info(f"\n{'*'*60}")
        logger.info(f"🔄 ПЕРЕДАЧА ЗАДАЧИ МЕЖДУ АГЕНТАМИ")
        logger.info(f"   От: {from_agent}")
        logger.info(f"   Кому: {to_agent}")
        logger.info(f"   Передаваемые данные: {data_description}")
        logger.info(f"{'*'*60}")
        if self._progress:
            self._progress.agent(to_agent, f"🔄 Передача от {from_agent} → {to_agent}")
    
    def log_agent_completed(self, agent_name: str, result_summary: str):
        """Log when an agent completes its task."""
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ АГЕНТ ЗАВЕРШИЛ РАБОТУ: {agent_name}")
        logger.info(f"   Результат: {result_summary}")
        logger.info(f"{'='*60}\n")
        if self._progress:
            self._progress.agent(agent_name, f"✅ {agent_name}: {result_summary}")
    
    def log_agent_error(self, agent_name: str, error: str):
        """Log when an agent encounters an error."""
        logger.error(f"\n{'!'*60}")
        logger.error(f"❌ ОШИБКА АГЕНТА: {agent_name}")
        logger.error(f"   Ошибка: {error}")
        logger.error(f"{'!'*60}\n")
        if self._progress:
            self._progress.agent(agent_name, f"❌ {agent_name}: ошибка — {error}")


class BaseAgent:
    """Base class for all agents in the multi-agent system."""

    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_TOKENS = Config.DEFAULT_LLM_MAX_TOKENS
    
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
            base_url=Config.OPENAI_API_BASE,
            timeout=600.0  # 10 min timeout per request for local LLM
        )
        self.model = Config.OPENAI_MODEL
        self.json_mode = Config.OPENAI_JSON_MODE
        self.conversation_history: List[Dict[str, str]] = []
        self.event_logger = AgentEventLogger()
        self._progress_tracker: Optional[ProgressTracker] = None
        
        logger.info(f"🤖 Агент '{name}' инициализирован")
        logger.info(f"   Роль: {role}")
    
    def set_progress_tracker(self, tracker: Optional[ProgressTracker], stream_events: bool = True):
        """Attach a progress tracker for frontend streaming.
        
        Args:
            tracker: ProgressTracker instance or None
            stream_events: Whether agent status messages should be streamed
        """
        self._progress_tracker = tracker
        self.event_logger.set_progress_tracker(tracker if stream_events else None)

    def _record_intermediate(self, stage: str, payload: Any):
        """Persist an intermediate payload for the current run if enabled."""
        if self._progress_tracker:
            self._progress_tracker.record_intermediate(f"{self.name}:{stage}", payload)

    def _record_llm_call(self, payload: Dict[str, Any]):
        """Persist an LLM interaction for the current run if enabled."""
        if self._progress_tracker:
            self._progress_tracker.record_llm_call(payload)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for this agent.
        
        Returns:
            System prompt string
        """
        raise NotImplementedError("Subclasses must implement _build_system_prompt")
    
    def _extract_json_from_response(self, text: str) -> Optional[str]:
        """Extract JSON from response that might contain markdown or other text.
        
        Delegates to shared json_utils module.
        
        Args:
            text: Raw response text
            
        Returns:
            Extracted JSON string or None if not found
        """
        return extract_json_from_response(text, log_prefix=f"   [{self.name}] ")
    
    def send_message(self, message: str, expect_json: bool = True,
                     request_id: str = None, use_history: bool = True,
                     max_tokens: Optional[int] = None,
                     temperature: Optional[float] = None,
                     system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Send a message to the agent and get a response.
        
        Args:
            message: Message to send
            expect_json: Whether to parse response as JSON
            request_id: Optional request ID for tracking
            use_history: Whether to append and send conversation history
            max_tokens: Optional per-call completion token cap
            temperature: Optional per-call temperature override
            system_prompt: Optional per-call system prompt override
            
        Returns:
            Response dictionary
        """
        # Log LLM request
        self.event_logger.log_llm_request(self.name, message, request_id)
        
        message_entry = {
            "role": "user",
            "content": message
        }

        if use_history:
            self.conversation_history.append(message_entry)
            messages = [
                {"role": "system", "content": system_prompt or self._build_system_prompt()}
            ] + self.conversation_history
        else:
            messages = [
                {"role": "system", "content": system_prompt or self._build_system_prompt()},
                message_entry
            ]
        
        # Prepare API call parameters
        api_params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.DEFAULT_TEMPERATURE,
            "max_tokens": max_tokens if max_tokens is not None else self.DEFAULT_MAX_TOKENS
        }
        
        if self.json_mode and expect_json:
            api_params["response_format"] = {"type": "json_object"}
            logger.info(f"   [Using JSON response format]")

        llm_request_payload = {
            "agent": self.name,
            "request_id": request_id,
            "model": self.model,
            "expect_json": expect_json,
            "use_history": use_history,
            "temperature": api_params["temperature"],
            "max_tokens": api_params["max_tokens"],
            "messages": messages,
            "response_format": api_params.get("response_format")
        }
        
        # Retry with exponential backoff
        max_retries = 3
        base_delay = 2.0  # seconds
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.info(f"   [Retry {attempt}/{max_retries - 1}, waiting {delay:.1f}s...]")
                    time.sleep(delay)
                
                start_time = time.time()
                logger.info(f"   [API call attempt {attempt + 1}/{max_retries}...]")
                
                response = self.client.chat.completions.create(**api_params)
                
                elapsed_time = time.time() - start_time
                response_text = response.choices[0].message.content
                
                # Log LLM response
                self.event_logger.log_llm_response(self.name, response_text, elapsed_time)
                
                # Log token usage if available
                if response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens or 0,
                        "completion_tokens": response.usage.completion_tokens or 0,
                        "total_tokens": response.usage.total_tokens or 0
                    }
                    logger.info(f"   Tokens: prompt={response.usage.prompt_tokens}, "
                               f"completion={response.usage.completion_tokens}, "
                               f"total={response.usage.total_tokens}")
                    if self._progress_tracker:
                        self._progress_tracker.usage(
                            self.name,
                            usage,
                            {
                                "elapsed_seconds": round(elapsed_time, 2),
                                "model": self.model
                            }
                        )
                else:
                    usage = {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                
                if use_history:
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": response_text
                    })
                
                if expect_json:
                    json_text = self._extract_json_from_response(response_text)
                    if json_text:
                        try:
                            parsed_data = json.loads(json_text)
                        except json.JSONDecodeError as error:
                            repaired_json = repair_json_text(
                                json_text,
                                log_prefix=f"   [{self.name}] "
                            )
                            if repaired_json is None:
                                snippet_start = max(0, error.pos - 120)
                                snippet_end = min(len(json_text), error.pos + 120)
                                logger.warning(
                                    "   ⚠️ Broken JSON excerpt around parse error: %s",
                                    json_text[snippet_start:snippet_end]
                                )
                                logger.warning(
                                    f"   ⚠️ JSON extraction succeeded but parsing still failed: {error}"
                                )
                                self._record_llm_call({
                                    **llm_request_payload,
                                    "attempt": attempt + 1,
                                    "status": "error",
                                    "elapsed_seconds": round(elapsed_time, 2),
                                    "usage": usage,
                                    "response": response_text,
                                    "extracted_json": json_text[:4000],
                                    "error": str(error),
                                    "error_type": "json_parse"
                                })
                                return {
                                    "success": False,
                                    "error": str(error),
                                    "raw_response": response_text,
                                    "extracted_json": json_text[:2000],
                                    "usage": {
                                        **usage,
                                        "elapsed_seconds": round(elapsed_time, 2)
                                    }
                                }
                            json_text = repaired_json
                            parsed_data = json.loads(json_text)
                            logger.info("   ✅ JSON repaired after initial parse failure")
                        logger.info(f"   ✅ JSON extracted and parsed successfully")
                        self._record_llm_call({
                            **llm_request_payload,
                            "attempt": attempt + 1,
                            "status": "success",
                            "elapsed_seconds": round(elapsed_time, 2),
                            "usage": usage,
                            "response": response_text,
                            "parsed_data": parsed_data
                        })
                        return {
                            "success": True,
                            "data": parsed_data,
                            "raw_response": response_text,
                            "elapsed_time": elapsed_time,
                            "usage": {
                                **usage,
                                "elapsed_seconds": round(elapsed_time, 2)
                            }
                        }
                    else:
                        logger.warning(f"   ⚠️ Could not extract JSON from response")
                        self._record_llm_call({
                            **llm_request_payload,
                            "attempt": attempt + 1,
                            "status": "error",
                            "elapsed_seconds": round(elapsed_time, 2),
                            "usage": usage,
                            "response": response_text,
                            "error": "Could not extract JSON from response",
                            "error_type": "json_extract"
                        })
                        return {
                            "success": False,
                            "error": "Could not extract JSON from response",
                            "raw_response": response_text,
                            "usage": {
                                **usage,
                                "elapsed_seconds": round(elapsed_time, 2)
                            }
                        }
                else:
                    self._record_llm_call({
                        **llm_request_payload,
                        "attempt": attempt + 1,
                        "status": "success",
                        "elapsed_seconds": round(elapsed_time, 2),
                        "usage": usage,
                        "response": response_text
                    })
                    return {
                        "success": True,
                        "data": response_text,
                        "elapsed_time": elapsed_time,
                        "usage": {
                            **usage,
                            "elapsed_seconds": round(elapsed_time, 2)
                        }
                    }
                    
            except Exception as e:
                last_error = e
                error_str = str(e)
                self._record_llm_call({
                    **llm_request_payload,
                    "attempt": attempt + 1,
                    "status": "error",
                    "error": error_str,
                    "error_type": "request_exception"
                })
                # Retry on rate limit (429), server errors (5xx), timeouts
                is_retryable = any(keyword in error_str.lower() for keyword in [
                    "rate limit", "429", "500", "502", "503", "504",
                    "timeout", "connection", "overloaded"
                ])
                
                if is_retryable and attempt < max_retries - 1:
                    logger.warning(f"   ⚠️ Retryable error (attempt {attempt + 1}): {error_str}")
                    continue
                else:
                    self.event_logger.log_agent_error(self.name, error_str)
                    return {
                        "success": False,
                        "error": error_str,
                        "usage": {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0
                        }
                    }
        
        # Should not reach here, but just in case
        self.event_logger.log_agent_error(self.name, str(last_error))
        return {
            "success": False,
            "error": str(last_error),
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
    
    def reset_conversation(self):
        """Reset the conversation history."""
        self.conversation_history = []
        logger.info(f"[{self.name}] Conversation history reset")
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation.
        
        Returns:
            Summary string
        """
        return f"Agent: {self.name}\nMessages exchanged: {len(self.conversation_history)}"
