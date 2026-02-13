"""
Agent Orchestrator.
Coordinates communication between multiple agents to generate WBS.
Includes stabilization features for consistent results.
"""
import logging
import time
from typing import Dict, Any, Optional, List
from .analyst_agent import AnalystAgent
from .planner_agent import PlannerAgent
from .validator_agent import ValidatorAgent, ValidationResult
from .result_stabilizer import ResultStabilizer, EstimationRules, EnsembleGenerator
from .base_agent import AgentEventLogger

logger = logging.getLogger(__name__)


class StabilizationMode:
    """Stabilization mode constants."""
    SINGLE = "single"  # Single pass, no stabilization
    VALIDATE = "validate"  # Single pass with validation
    ENSEMBLE = "ensemble"  # Multiple passes with consensus
    ENSEMBLE_VALIDATE = "ensemble_validate"  # Ensemble + validation


class AgentOrchestrator:
    """Orchestrates the multi-agent WBS generation process.
    
    The workflow is:
    1. Analyst Agent analyzes the technical specification
    2. Planner Agent creates WBS based on the analysis
    3. (Optional) Validator Agent validates the result
    4. (Optional) Multiple iterations for ensemble stabilization
    5. (Optional) Result normalization
    
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
    │ Validator Agent │ (optional)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │   Stabilizer    │ (optional)
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │   WBS Result    │
    └─────────────────┘
    """
    
    def __init__(self, stabilization_mode: str = None, 
                 estimation_rules_path: str = None):
        """Initialize the orchestrator with agents.
        
        Args:
            stabilization_mode: Mode for result stabilization
            estimation_rules_path: Path to estimation rules file
        """
        self.analyst = AnalystAgent()
        self.planner = PlannerAgent()
        self.validator = ValidatorAgent()
        self.conversation_log: List[Dict[str, Any]] = []
        self.event_logger = AgentEventLogger()
        
        # Load estimation rules
        self.estimation_rules = EstimationRules(estimation_rules_path)
        
        # Set stabilization mode
        settings = self.estimation_rules.rules.get("stabilization_settings", {})
        self.stabilization_mode = stabilization_mode or settings.get("default_mode", "validate")
        
        # Ensemble settings
        self.ensemble_iterations = settings.get("ensemble_iterations", 3)
        
        logger.info("🎬 Оркестратор агентов инициализирован")
        logger.info(f"   Подключенные агенты: {self.analyst.name}, {self.planner.name}, {self.validator.name}")
        logger.info(f"   Режим стабилизации: {self.stabilization_mode}")
    
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
                     max_iterations: int = 2,
                     stabilization_mode: str = None) -> Dict[str, Any]:
        """Generate WBS using the multi-agent system.
        
        Args:
            document_content: Content of the technical specification
            max_iterations: Maximum number of refinement iterations
            stabilization_mode: Override default stabilization mode
            
        Returns:
            Final WBS result
        """
        mode = stabilization_mode or self.stabilization_mode
        
        logger.info("\n" + "="*70)
        logger.info("🚀 ЗАПУСК МУЛЬТИ-АГЕНТНОЙ СИСТЕМЫ ГЕНЕРАЦИИ WBS")
        logger.info(f"   Режим стабилизации: {mode}")
        logger.info("="*70)
        
        start_time = time.time()
        self.conversation_log = []
        
        # Reset agent conversations
        self.analyst.reset_conversation()
        self.planner.reset_conversation()
        
        if mode == StabilizationMode.ENSEMBLE or mode == StabilizationMode.ENSEMBLE_VALIDATE:
            # Use ensemble approach
            return self._generate_with_ensemble(document_content, max_iterations, mode, start_time)
        else:
            # Single pass
            return self._generate_single(document_content, max_iterations, mode, start_time)
    
    def _generate_single(self, document_content: str, max_iterations: int,
                         mode: str, start_time: float) -> Dict[str, Any]:
        """Generate WBS in single pass mode."""
        
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
        
        # ============================================================
        # STEP 5: Validation with Validator Agent (if enabled)
        # ============================================================
        validation_result = None
        if mode in [StabilizationMode.VALIDATE, StabilizationMode.ENSEMBLE_VALIDATE]:
            self.event_logger.log_agent_started(
                self.validator.name,
                "Валидация и нормализация WBS"
            )
            
            validation_result = self.validator.validate_wbs(wbs)
            
            self._log_conversation("Validator", "validation_complete", {
                "is_valid": validation_result.is_valid,
                "issues_count": len(validation_result.issues),
                "warnings_count": len(validation_result.warnings),
                "confidence_score": validation_result.confidence_score
            })
            
            # Normalize if auto_normalize is enabled
            settings = self.estimation_rules.rules.get("stabilization_settings", {})
            if settings.get("auto_normalize", True):
                wbs = self.validator.normalize_wbs(wbs)
                self._log_conversation("Validator", "wbs_normalized", {
                    "corrections": len(validation_result.corrections)
                })
            
            self.event_logger.log_agent_completed(
                self.validator.name,
                f"Валидация завершена. Confidence: {validation_result.confidence_score:.2f}"
            )
        
        elapsed_time = time.time() - start_time
        
        # ============================================================
        # FINAL: Build result
        # ============================================================
        logger.info("\n" + "="*70)
        logger.info("🏁 МУЛЬТИ-АГЕНТНАЯ ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
        logger.info(f"   Общее время: {elapsed_time:.2f} сек")
        logger.info(f"   Итерации: {iteration + 1}")
        logger.info(f"   Фаз в WBS: {len(wbs.get('wbs', {}).get('phases', []))}")
        if validation_result:
            logger.info(f"   Confidence: {validation_result.confidence_score:.2f}")
        logger.info("="*70 + "\n")
        
        result = {
            "success": True,
            "data": wbs,
            "metadata": {
                "elapsed_seconds": round(elapsed_time, 2),
                "iterations": iteration + 1,
                "stabilization_mode": mode,
                "analysis_summary": {
                    "project_name": analysis.get("project_info", {}).get("project_name", ""),
                    "complexity": analysis.get("project_info", {}).get("complexity_level", ""),
                    "functional_requirements": len(analysis.get("functional_requirements", [])),
                    "non_functional_requirements": len(analysis.get("non_functional_requirements", [])),
                    "risks_identified": len(analysis.get("risks", []))
                },
                "wbs_summary": {
                    "phases": len(wbs.get('wbs', {}).get('phases', [])),
                    "total_hours": wbs.get('project_info', {}).get('total_estimated_hours', 0)
                }
            },
            "agent_conversation": self.conversation_log
        }
        
        if validation_result:
            result["validation"] = validation_result.to_dict()
        
        self._log_conversation("Orchestrator", "generation_complete", {
            "elapsed_seconds": elapsed_time,
            "iterations": iteration + 1,
            "mode": mode
        })
        
        return result
    
    def _generate_with_ensemble(self, document_content: str, max_iterations: int,
                                mode: str, start_time: float) -> Dict[str, Any]:
        """Generate WBS with ensemble stabilization."""
        
        logger.info(f"\n🎭 Режим ENSEMBLE: запуск {self.ensemble_iterations} итераций")
        
        results = []
        
        for i in range(self.ensemble_iterations):
            logger.info(f"\n{'='*50}")
            logger.info(f"📊 ENSEMBLE ИТЕРАЦИЯ {i + 1}/{self.ensemble_iterations}")
            logger.info(f"{'='*50}")
            
            # Reset agents for fresh generation
            self.analyst.reset_conversation()
            self.planner.reset_conversation()
            
            # Generate single WBS
            result = self._generate_single_iteration(document_content, max_iterations)
            
            if result.get("success"):
                results.append(result["data"])
                logger.info(f"   ✅ Итерация {i + 1} завершена успешно")
            else:
                logger.warning(f"   ⚠️ Итерация {i + 1} завершилась с ошибкой: {result.get('error')}")
        
        if not results:
            return {
                "success": False,
                "error": "Все итерации завершились с ошибкой"
            }
        
        # ============================================================
        # Stabilize results
        # ============================================================
        logger.info(f"\n{'='*50}")
        logger.info("🔧 СТАБИЛИЗАЦИЯ РЕЗУЛЬТАТОВ")
        logger.info(f"{'='*50}")
        
        stabilizer = ResultStabilizer(self.estimation_rules)
        stabilized = stabilizer.stabilize(results)
        
        if not stabilized["success"]:
            # Fallback to first result
            logger.warning("Стабилизация не удалась, используем первый результат")
            final_wbs = results[0]
            stabilization_metadata = {"method": "fallback"}
        else:
            final_wbs = stabilized["data"]
            stabilization_metadata = stabilized["metadata"]
            logger.info(f"   Метод консенсуса: {stabilization_metadata.get('method')}")
            logger.info(f"   Использовано итераций: {stabilization_metadata.get('used_iterations')}")
            logger.info(f"   Выбросов удалено: {stabilization_metadata.get('outliers_removed')}")
            logger.info(f"   Confidence: {stabilization_metadata.get('confidence', 0):.2f}")
        
        # ============================================================
        # Final validation (if enabled)
        # ============================================================
        validation_result = None
        if mode == StabilizationMode.ENSEMBLE_VALIDATE:
            validation_result = self.validator.validate_wbs(final_wbs)
            
            settings = self.estimation_rules.rules.get("stabilization_settings", {})
            if settings.get("auto_normalize", True):
                final_wbs = self.validator.normalize_wbs(final_wbs)
        
        elapsed_time = time.time() - start_time
        
        # ============================================================
        # Build final result
        # ============================================================
        logger.info("\n" + "="*70)
        logger.info("🏁 ENSEMBLE ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
        logger.info(f"   Общее время: {elapsed_time:.2f} сек")
        logger.info(f"   Всего итераций: {self.ensemble_iterations}")
        logger.info(f"   Успешных итераций: {len(results)}")
        logger.info(f"   Фаз в WBS: {len(final_wbs.get('wbs', {}).get('phases', []))}")
        logger.info(f"   Общая оценка: {final_wbs.get('project_info', {}).get('total_estimated_hours', 0)} часов")
        logger.info("="*70 + "\n")
        
        result = {
            "success": True,
            "data": final_wbs,
            "metadata": {
                "elapsed_seconds": round(elapsed_time, 2),
                "stabilization_mode": mode,
                "ensemble": {
                    "total_iterations": self.ensemble_iterations,
                    "successful_iterations": len(results),
                    **stabilization_metadata
                },
                "wbs_summary": {
                    "phases": len(final_wbs.get('wbs', {}).get('phases', [])),
                    "total_hours": final_wbs.get('project_info', {}).get('total_estimated_hours', 0)
                }
            },
            "agent_conversation": self.conversation_log
        }
        
        if validation_result:
            result["validation"] = validation_result.to_dict()
        
        return result
    
    def _generate_single_iteration(self, document_content: str, 
                                   max_iterations: int) -> Dict[str, Any]:
        """Generate a single WBS iteration (for ensemble mode)."""
        
        # Step 1: Analyst
        analysis_result = self.analyst.analyze_specification(document_content)
        
        if not analysis_result.get("success"):
            return analysis_result
        
        analysis = analysis_result["analysis"]
        
        # Step 2: Planner
        wbs_result = self.planner.create_wbs(analysis)
        
        if not wbs_result.get("success"):
            return wbs_result
        
        wbs = wbs_result["wbs"]
        
        # Step 3: Validate and refine
        validation = self.planner.validate_wbs(wbs)
        
        iteration = 0
        while not validation["valid"] and iteration < max_iterations:
            feedback = f"Исправь: {', '.join(validation['issues'])}"
            wbs_result = self.planner.refine_wbs(wbs, feedback)
            
            if wbs_result.get("success"):
                wbs = wbs_result["wbs"]
                validation = self.planner.validate_wbs(wbs)
            
            iteration += 1
        
        return {
            "success": True,
            "data": wbs
        }
    
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
