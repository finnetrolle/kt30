"""
Agent Orchestrator.
Coordinates communication between multiple agents to generate WBS.
"""
import logging
import time
from typing import Dict, Any, Optional, List
from .analyst_agent import AnalystAgent
from .planner_agent import PlannerAgent
from .base_agent import AgentEventLogger

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrates the multi-agent WBS generation process.
    
    The workflow is:
    1. Analyst Agent analyzes the technical specification
    2. Planner Agent creates WBS based on the analysis
    3. (Optional) Agents can request clarifications from each other
    4. (Optional) Iterative refinement based on feedback
    
    Communication flow:
    ┌─────────────────┐
    │  Technical Spec │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  Analyst Agent  │──────┐
    └────────┬────────┘      │
             │               │ (clarifications)
             ▼               │
    ┌─────────────────┐      │
    │  Planner Agent  │◄─────┘
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │   WBS Result    │
    └─────────────────┘
    """
    
    def __init__(self):
        """Initialize the orchestrator with agents."""
        self.analyst = AnalystAgent()
        self.planner = PlannerAgent()
        self.conversation_log: List[Dict[str, Any]] = []
        self.event_logger = AgentEventLogger()
        
        logger.info("🎬 Оркестратор агентов инициализирован")
        logger.info(f"   Подключенные агенты: {self.analyst.name}, {self.planner.name}")
    
    def _log_conversation(self, agent_name: str, action: str, details: Dict[str, Any]):
        """Log a conversation step.
        
        Args:
            agent_name: Name of the agent
            action: Action performed
            details: Details of the action
        """
        entry = {
            "timestamp": time.time(),
            "agent": agent_name,
            "action": action,
            "details": details
        }
        self.conversation_log.append(entry)
        logger.info(f"[Orchestrator] {agent_name}: {action}")
    
    def generate_wbs(self, document_content: str, 
                     max_iterations: int = 2) -> Dict[str, Any]:
        """Generate WBS using the multi-agent system.
        
        Args:
            document_content: Content of the technical specification
            max_iterations: Maximum number of refinement iterations
            
        Returns:
            Final WBS result
        """
        logger.info("\n" + "="*70)
        logger.info("🚀 ЗАПУСК МУЛЬТИ-АГЕНТНОЙ СИСТЕМЫ ГЕНЕРАЦИИ WBS")
        logger.info("="*70)
        
        start_time = time.time()
        self.conversation_log = []
        
        # Reset agent conversations
        self.analyst.reset_conversation()
        self.planner.reset_conversation()
        
        # ============================================================
        # STEP 1: Analyst analyzes the specification
        # ============================================================
        self.event_logger.log_agent_started(
            self.analyst.name, 
            "Анализ технического задания и извлечение требований"
        )
        
        self._log_conversation("Orchestrator", "delegate_to_analyst", {
            "document_length": len(document_content),
            "target_agent": self.analyst.name
        })
        
        analysis_result = self.analyst.analyze_specification(document_content)
        
        if not analysis_result.get("success"):
            error = analysis_result.get("error", "Analysis failed")
            self.event_logger.log_agent_error(self.analyst.name, error)
            self._log_conversation("Orchestrator", "analyst_failed", {"error": error})
            return {
                "success": False,
                "error": f"Analyst Agent failed: {error}",
                "stage": "analysis"
            }
        
        analysis = analysis_result["analysis"]
        
        # Log analyst completion
        self.event_logger.log_agent_completed(
            self.analyst.name,
            f"Извлечено {len(analysis.get('functional_requirements', []))} функциональных требований, "
            f"{len(analysis.get('risks', []))} рисков"
        )
        
        self._log_conversation("Analyst", "analysis_complete", {
            "requirements_count": len(analysis.get("functional_requirements", [])),
            "risks_count": len(analysis.get("risks", [])),
            "clarifications_needed": len(analysis.get("clarifications_needed", []))
        })
        
        # ============================================================
        # STEP 2: Check if clarifications are needed
        # ============================================================
        clarifications = analysis.get("clarifications_needed", [])
        if clarifications and len(clarifications) > 0:
            logger.info(f"\n📝 Требуются уточнения ({len(clarifications)} вопросов):")
            for i, q in enumerate(clarifications, 1):
                logger.info(f"   {i}. {q}")
            logger.info("   Продолжаем с предположениями...")
            self._log_conversation("Orchestrator", "clarifications_needed", {
                "questions": clarifications
            })
        
        # ============================================================
        # STEP 3: Hand off to Planner Agent
        # ============================================================
        self.event_logger.log_agent_handoff(
            from_agent=self.analyst.name,
            to_agent=self.planner.name,
            data_description=f"Структурированный анализ: {len(analysis.get('functional_requirements', []))} требований, "
                           f"тип проекта: {analysis.get('project_info', {}).get('project_type', 'не указан')}"
        )
        
        self.event_logger.log_agent_started(
            self.planner.name,
            "Создание Work Breakdown Structure на основе анализа"
        )
        
        self._log_conversation("Orchestrator", "delegate_to_planner", {
            "source_agent": self.analyst.name,
            "target_agent": self.planner.name,
            "analysis_ready": True
        })
        
        wbs_result = self.planner.create_wbs(analysis)
        
        if not wbs_result.get("success"):
            error = wbs_result.get("error", "WBS creation failed")
            self.event_logger.log_agent_error(self.planner.name, error)
            self._log_conversation("Planner", "wbs_creation_failed", {"error": error})
            return {
                "success": False,
                "error": f"Planner Agent failed: {error}",
                "stage": "planning",
                "analysis": analysis
            }
        
        wbs = wbs_result["wbs"]
        
        # Log planner completion
        phases_count = len(wbs.get("wbs", {}).get("phases", []))
        total_hours = wbs.get("project_info", {}).get("total_estimated_hours", 0)
        
        self.event_logger.log_agent_completed(
            self.planner.name,
            f"Создано {phases_count} фаз, общая оценка: {total_hours} часов"
        )
        
        self._log_conversation("Planner", "wbs_complete", {
            "phases_count": phases_count,
            "total_hours": total_hours
        })
        
        # ============================================================
        # STEP 4: Validate and potentially refine
        # ============================================================
        validation = self.planner.validate_wbs(wbs)
        
        iteration = 0
        while not validation["valid"] and iteration < max_iterations:
            logger.info(f"\n🔄 Итерация уточнения {iteration + 1}/{max_iterations}")
            logger.info(f"   Проблемы: {validation['issues']}")
            
            self._log_conversation("Orchestrator", "validation_issues", {
                "issues": validation["issues"],
                "iteration": iteration + 1
            })
            
            # Request refinement
            feedback = f"Пожалуйста, исправь следующие проблемы: {', '.join(validation['issues'])}"
            
            self.event_logger.log_agent_started(
                self.planner.name,
                f"Уточнение WBS (итерация {iteration + 1})"
            )
            
            wbs_result = self.planner.refine_wbs(wbs, feedback)
            
            if wbs_result.get("success"):
                wbs = wbs_result["wbs"]
                validation = self.planner.validate_wbs(wbs)
                
                self.event_logger.log_agent_completed(
                    self.planner.name,
                    "WBS уточнен"
                )
            
            iteration += 1
        
        elapsed_time = time.time() - start_time
        
        # ============================================================
        # FINAL: Build result
        # ============================================================
        logger.info("\n" + "="*70)
        logger.info("🏁 МУЛЬТИ-АГЕНТНАЯ ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
        logger.info(f"   Общее время: {elapsed_time:.2f} сек")
        logger.info(f"   Итерации: {iteration + 1}")
        logger.info(f"   Фаз в WBS: {len(wbs.get('wbs', {}).get('phases', []))}")
        logger.info("="*70 + "\n")
        
        result = {
            "success": True,
            "data": wbs,
            "metadata": {
                "elapsed_seconds": round(elapsed_time, 2),
                "iterations": iteration + 1,
                "analysis_summary": {
                    "project_name": analysis.get("project_info", {}).get("project_name", ""),
                    "complexity": analysis.get("project_info", {}).get("complexity_level", ""),
                    "functional_requirements": len(analysis.get("functional_requirements", [])),
                    "non_functional_requirements": len(analysis.get("non_functional_requirements", [])),
                    "risks_identified": len(analysis.get("risks", []))
                },
                "wbs_summary": {
                    "phases": len(wbs.get("wbs", {}).get("phases", [])),
                    "total_hours": wbs.get("project_info", {}).get("total_estimated_hours", 0)
                }
            },
            "agent_conversation": self.conversation_log
        }
        
        self._log_conversation("Orchestrator", "generation_complete", {
            "elapsed_seconds": elapsed_time,
            "iterations": iteration + 1
        })
        
        return result
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the agent conversation.
        
        Returns:
            Human-readable conversation summary
        """
        if not self.conversation_log:
            return "No conversation recorded."
        
        summary_lines = ["=== Agent Conversation Summary ===\n"]
        
        for entry in self.conversation_log:
            timestamp = time.strftime("%H:%M:%S", time.localtime(entry["timestamp"]))
            agent = entry["agent"]
            action = entry["action"]
            
            summary_lines.append(f"[{timestamp}] {agent}: {action}")
            
            if entry["details"]:
                for key, value in entry["details"].items():
                    if isinstance(value, (list, dict)):
                        value = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                    summary_lines.append(f"    {key}: {value}")
        
        return "\n".join(summary_lines)
    
    def get_agent_analytics(self) -> Dict[str, Any]:
        """Get analytics about agent performance.
        
        Returns:
            Analytics dictionary
        """
        if not self.conversation_log:
            return {}
        
        analytics = {
            "total_steps": len(self.conversation_log),
            "agents_involved": list(set(e["agent"] for e in self.conversation_log)),
            "actions_performed": {},
            "timeline": []
        }
        
        for entry in self.conversation_log:
            action = entry["action"]
            analytics["actions_performed"][action] = \
                analytics["actions_performed"].get(action, 0) + 1
            analytics["timeline"].append({
                "agent": entry["agent"],
                "action": entry["action"],
                "timestamp": entry["timestamp"]
            })
        
        return analytics
