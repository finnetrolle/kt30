"""
Validator Agent.
Validates and normalizes WBS results for consistency and realism.
"""
import logging
import json
import statistics
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from config import Config
from wbs_utils import canonicalize_wbs_result
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


def _load_estimation_rules_from_file() -> Dict[str, Any]:
    """Load estimation rules from the canonical JSON file.
    
    Returns:
        Estimation rules dictionary
    """
    rules_path = Path(__file__).parent.parent / "data" / "estimation_rules.json"
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            full_rules = json.load(f)
        
        # Build flat task_templates for backward compatibility
        flat_templates = {}
        for category, tasks in full_rules.get("task_templates", {}).items():
            for task_name, estimation in tasks.items():
                flat_templates[task_name] = estimation
        
        limits = full_rules.get("limits", {})
        
        # Build complexity_multipliers as flat dict for backward compatibility
        complexity = {}
        for level, info in full_rules.get("complexity_multipliers", {}).items():
            complexity[level] = info.get("multiplier", 1.0)
        
        # Build phase_ratios as flat dict
        phase_ratios = {}
        for phase_name, info in full_rules.get("phase_ratios", {}).items():
            phase_ratios[phase_name] = info.get("ratio", 0.1)
        
        return {
            "task_templates": flat_templates,
            "phase_ratios": phase_ratios,
            "complexity_multipliers": complexity,
            "project_type_baselines": full_rules.get("project_type_baselines", {}),
            "min_hours_per_task": limits.get("min_hours_per_task", 2),
            "max_hours_per_task": limits.get("max_hours_per_task", 80),
            "min_hours_per_phase": limits.get("min_hours_per_phase", 8),
            "max_hours_per_phase": limits.get("max_hours_per_phase", 500),
            "min_total_hours": limits.get("min_total_hours", 40),
            "max_total_hours": limits.get("max_total_hours", 5000),
        }
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load estimation rules from file: {e}, using defaults")
        return {
            "task_templates": {},
            "phase_ratios": {},
            "complexity_multipliers": {"Низкий": 0.7, "Средний": 1.0, "Высокий": 1.4},
            "project_type_baselines": {},
            "min_hours_per_task": 2,
            "max_hours_per_task": 80,
            "min_hours_per_phase": 8,
            "max_hours_per_phase": 500,
            "min_total_hours": 40,
            "max_total_hours": 5000,
        }


# Load rules from the single source of truth: data/estimation_rules.json
ESTIMATION_RULES = _load_estimation_rules_from_file()


class ValidationResult:
    """Result of validation with details."""
    
    def __init__(self):
        self.is_valid = True
        self.issues: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.corrections: List[Dict[str, Any]] = []
        self.normalized_wbs: Optional[Dict[str, Any]] = None
        self.confidence_score: float = 1.0
    
    def add_issue(self, category: str, message: str, location: str, 
                  current_value: Any = None, suggested_value: Any = None):
        """Add a validation issue."""
        self.is_valid = False
        self.issues.append({
            "category": category,
            "message": message,
            "location": location,
            "current_value": current_value,
            "suggested_value": suggested_value
        })
    
    def add_warning(self, category: str, message: str, location: str):
        """Add a validation warning."""
        self.warnings.append({
            "category": category,
            "message": message,
            "location": location
        })
    
    def add_correction(self, location: str, field: str, 
                       old_value: Any, new_value: Any, reason: str):
        """Add a correction that was applied."""
        self.corrections.append({
            "location": location,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "issues_count": len(self.issues),
            "warnings_count": len(self.warnings),
            "corrections_count": len(self.corrections),
            "confidence_score": self.confidence_score,
            "issues": self.issues,
            "warnings": self.warnings,
            "corrections": self.corrections
        }


class ValidatorAgent(BaseAgent):
    """Agent responsible for validating and normalizing WBS results.
    
    This agent:
    - Validates WBS structure and completeness
    - Checks estimation realism against standard rules
    - Normalizes values to acceptable ranges
    - Calculates confidence scores
    - Provides detailed validation reports
    """
    
    def __init__(self, estimation_rules: Dict[str, Any] = None):
        """Initialize the Validator Agent.
        
        Args:
            estimation_rules: Custom estimation rules (optional)
        """
        super().__init__(
            name="Валидатор WBS",
            role="Проверяет и нормализует результаты WBS для стабильности"
        )
        self.estimation_rules = estimation_rules or ESTIMATION_RULES
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the Validator Agent."""
        return """Ты — опытный QA инженер и проектный аналитик. Твоя задача — проверять Work Breakdown Structure (WBS) на корректность, реалистичность и полноту.

ОТВЕТ ДОЛЖЕН БЫТЬ ТОЛЬКО В ФОРМАТЕ JSON. НЕ ПИШИ НИЧЕГО КРОМЕ JSON.

Твоя проверка должна включать:

1. **structure_validation** — проверка структуры:
   - all_phases_present: все ли фазы присутствуют
   - all_work_packages_have_tasks: есть ли задачи в пакетах работ
   - dependencies_valid: корректны ли зависимости

2. **estimation_validation** — проверка оценок:
   - hours_realistic: реалистичны ли оценки трудозатрат
   - phase_ratios_correct: правильное ли распределение по фазам
   - total_hours_reasonable: общая оценка в разумных пределах

3. **completeness_validation** — проверка полноты:
   - all_fields_filled: все ли поля заполнены
   - deliverables_defined: определены ли результаты
   - skills_specified: указаны ли требуемые навыки

4. **issues** — найденные проблемы:
   Массив объектов с полями:
   - severity: "error" или "warning"
   - location: где найдена проблема
   - description: описание проблемы
   - suggestion: предложение по исправлению

5. **normalized_values** — нормализованные значения:
   - suggested_total_hours: рекомендуемое общее количество часов
   - suggested_duration_weeks: рекомендуемая длительность в неделях
   - adjustments: массив корректировок

Пример ответа:
{
  "structure_validation": {
    "all_phases_present": true,
    "all_work_packages_have_tasks": true,
    "dependencies_valid": true
  },
  "estimation_validation": {
    "hours_realistic": false,
    "phase_ratios_correct": true,
    "total_hours_reasonable": true,
    "issues_found": ["Оценки для задач авторизации завышены"]
  },
  "completeness_validation": {
    "all_fields_filled": true,
    "deliverables_defined": true,
    "skills_specified": true
  },
  "issues": [],
  "normalized_values": {
    "suggested_total_hours": 320,
    "suggested_duration_weeks": 8,
    "adjustments": []
  },
  "confidence_score": 0.85
}"""

    def validate_wbs(self, wbs: Dict[str, Any]) -> ValidationResult:
        """Validate WBS structure and content.
        
        Args:
            wbs: WBS to validate
            
        Returns:
            ValidationResult with details
        """
        result = ValidationResult()
        wbs = canonicalize_wbs_result(wbs)
        
        # Check basic structure
        if 'wbs' not in wbs:
            result.add_issue("structure", "Missing 'wbs' field", "root")
            return result
        
        if 'phases' not in wbs.get('wbs', {}):
            result.add_issue("structure", "Missing 'phases' field", "wbs")
            return result
        
        phases = wbs['wbs'].get('phases', [])
        
        # Validate each phase
        for phase in phases:
            self._validate_phase(phase, result)
        
        # Validate project info
        self._validate_project_info(wbs.get('project_info', {}), result)
        
        # Validate total hours consistency
        self._validate_total_hours(wbs, result)
        
        # Calculate confidence score
        result.confidence_score = self._calculate_confidence(result, wbs)
        self._record_intermediate("validation_completed", result.to_dict())
        
        return result
    
    def _validate_phase(self, phase: Dict[str, Any], result: ValidationResult):
        """Validate a single phase."""
        phase_id = phase.get('id', 'unknown')
        phase_name = phase.get('name', 'unnamed')
        location = f"phase[{phase_id}]"
        
        # Check required fields
        required_fields = ['name', 'duration', 'estimated_hours', 'work_packages']
        for field in required_fields:
            if field not in phase:
                result.add_issue("structure", f"Missing field: {field}", location)
        
        # Validate hours
        hours = phase.get('estimated_hours', 0)
        if hours < self.estimation_rules['min_hours_per_phase']:
            result.add_warning("estimation", 
                             f"Phase hours ({hours}) below minimum", location)
        elif hours > self.estimation_rules['max_hours_per_phase']:
            result.add_issue("estimation", 
                           f"Phase hours ({hours}) exceed maximum", location,
                           current_value=hours,
                           suggested_value=self.estimation_rules['max_hours_per_phase'])
        
        # Validate work packages
        work_packages = phase.get('work_packages', [])
        if not work_packages:
            result.add_issue("structure", "Phase has no work packages", location)
            return
        
        for wp in work_packages:
            self._validate_work_package(wp, location, result)
    
    def _validate_work_package(self, wp: Dict[str, Any], 
                               parent_location: str, result: ValidationResult):
        """Validate a work package."""
        wp_id = wp.get('id', 'unknown')
        location = f"{parent_location}.wp[{wp_id}]"
        wp_requirement_ids = [req_id for req_id in wp.get('requirement_ids', []) if req_id]

        if not wp_requirement_ids:
            result.add_issue("traceability", "Work package has no requirement_ids", location)
        
        # Check tasks
        tasks = wp.get('tasks', [])
        if not tasks:
            result.add_warning("structure", "Work package has no tasks", location)
            return
        
        # Validate each task
        for task in tasks:
            self._validate_task(task, location, wp_requirement_ids, result)
        
        # Check work package hours vs sum of task hours
        wp_hours = wp.get('estimated_hours', 0)
        task_hours_sum = sum(t.get('estimated_hours', 0) for t in tasks)
        
        if wp_hours > 0 and task_hours_sum > 0:
            diff_ratio = abs(wp_hours - task_hours_sum) / max(wp_hours, 1)
            if diff_ratio > 0.3:  # More than 30% difference
                result.add_warning("estimation", 
                    f"WP hours ({wp_hours}) differ from sum of tasks ({task_hours_sum})",
                    location)
    
    def _validate_task(self, task: Dict[str, Any], 
                       parent_location: str, wp_requirement_ids: List[str], result: ValidationResult):
        """Validate a single task."""
        task_id = task.get('id', 'unknown')
        task_name = task.get('name', '')
        location = f"{parent_location}.task[{task_id}]"
        task_requirement_ids = [req_id for req_id in task.get('requirement_ids', []) if req_id]

        if not task_requirement_ids:
            result.add_issue("traceability", "Task has no requirement_ids", location)
        elif wp_requirement_ids and not set(task_requirement_ids).issubset(set(wp_requirement_ids)):
            result.add_issue(
                "traceability",
                "Task requirement_ids must be a subset of the parent work package requirement_ids",
                location
            )
        
        hours = task.get('estimated_hours', 0)
        
        # Check minimum hours
        if hours < self.estimation_rules['min_hours_per_task']:
            result.add_correction(
                location, "estimated_hours", hours,
                self.estimation_rules['min_hours_per_task'],
                f"Hours below minimum ({hours} < {self.estimation_rules['min_hours_per_task']})"
            )
        
        # Check maximum hours
        if hours > self.estimation_rules['max_hours_per_task']:
            result.add_correction(
                location, "estimated_hours", hours,
                self.estimation_rules['max_hours_per_task'],
                f"Hours exceed maximum ({hours} > {self.estimation_rules['max_hours_per_task']})"
            )
        
        # Check against estimation rules for task type
        if task_name:
            for pattern, rules in self.estimation_rules['task_templates'].items():
                if pattern.lower() in task_name.lower():
                    if hours < rules['min_hours'] or hours > rules['max_hours']:
                        result.add_warning("estimation",
                            f"Task '{task_name}' hours ({hours}) outside typical range "
                            f"({rules['min_hours']}-{rules['max_hours']})",
                            location)
                    break
    
    def _validate_project_info(self, project_info: Dict[str, Any], 
                               result: ValidationResult):
        """Validate project info."""
        location = "project_info"
        
        if not project_info.get('project_name'):
            result.add_warning("completeness", "Missing project name", location)
        
        if not project_info.get('total_estimated_hours'):
            result.add_warning("completeness", "Missing total estimated hours", location)
        
        project_type = project_info.get('project_type', '')
        if not project_type:
            result.add_warning("completeness", "Missing project type", location)
        elif self.estimation_rules.get('project_type_baselines') and project_type not in self.estimation_rules['project_type_baselines']:
            result.add_warning("estimation", 
                             f"Unknown project type: {project_type}", location)

        complexity = project_info.get('complexity_level', 'Средний')
        if complexity not in self.estimation_rules['complexity_multipliers']:
            result.add_warning("estimation", 
                             f"Unknown complexity level: {complexity}", location)
    
    def _calculate_actual_total_hours(self, wbs: Dict[str, Any]) -> float:
        """Calculate the total hours from phases."""
        total = 0.0
        for phase in wbs.get('wbs', {}).get('phases', []):
            total += self._coerce_to_number(phase.get('estimated_hours', 0))
        return total

    def _expected_total_hours_range(
        self,
        project_info: Dict[str, Any]
    ) -> Optional[Tuple[int, int, int]]:
        """Return the expected total-hour range for the project type and complexity."""
        baselines = self.estimation_rules.get('project_type_baselines', {})
        project_type = project_info.get('project_type')
        if not project_type or project_type not in baselines:
            return None

        baseline_info = baselines.get(project_type, {})
        baseline_hours = self._coerce_to_number(baseline_info.get('baseline_hours', 0))
        range_hours = baseline_info.get('range_hours', []) or []
        if len(range_hours) >= 2:
            min_hours = self._coerce_to_number(range_hours[0], baseline_hours or 0)
            max_hours = self._coerce_to_number(range_hours[1], baseline_hours or 0)
        elif baseline_hours > 0:
            min_hours = baseline_hours * 0.7
            max_hours = baseline_hours * 1.3
        else:
            return None

        complexity = project_info.get('complexity_level', 'Средний')
        complexity_multiplier = self.estimation_rules['complexity_multipliers'].get(complexity, 1.0)
        adjusted_min = round(max(self.estimation_rules.get('min_total_hours', 40), min_hours * complexity_multiplier))
        adjusted_max = round(min(self.estimation_rules.get('max_total_hours', 5000), max_hours * complexity_multiplier))
        adjusted_baseline = round(baseline_hours * complexity_multiplier) if baseline_hours > 0 else round((adjusted_min + adjusted_max) / 2)

        if adjusted_min > adjusted_max:
            adjusted_min, adjusted_max = adjusted_max, adjusted_min

        return adjusted_min, adjusted_max, adjusted_baseline

    def _validate_total_hours(self, wbs: Dict[str, Any], result: ValidationResult):
        """Validate total hours consistency."""
        project_info = wbs.get('project_info', {})
        declared_total = self._coerce_to_number(project_info.get('total_estimated_hours', 0))
        
        # Calculate actual sum
        actual_total = self._calculate_actual_total_hours(wbs)
        
        if declared_total > 0 and actual_total > 0:
            diff_ratio = abs(declared_total - actual_total) / max(declared_total, 1)
            if diff_ratio > 0.2:  # More than 20% difference
                result.add_warning("estimation",
                    f"Declared total ({declared_total}) differs from sum of phases ({actual_total})",
                    "project_info")

        min_total = self.estimation_rules.get('min_total_hours', 40)
        max_total = self.estimation_rules.get('max_total_hours', 5000)
        total_for_rules = actual_total or declared_total
        if total_for_rules > 0:
            if total_for_rules < min_total:
                result.add_warning(
                    "estimation",
                    f"Total hours ({round(total_for_rules)}) below minimum project threshold ({min_total})",
                    "project_info"
                )
            elif total_for_rules > max_total:
                result.add_issue(
                    "estimation",
                    f"Total hours ({round(total_for_rules)}) exceed maximum project threshold ({max_total})",
                    "project_info",
                    current_value=round(total_for_rules),
                    suggested_value=max_total
                )

        expected_range = self._expected_total_hours_range(project_info)
        if expected_range and total_for_rules > 0:
            expected_min, expected_max, expected_baseline = expected_range
            if total_for_rules < expected_min or total_for_rules > expected_max:
                project_type = project_info.get('project_type', 'unknown')
                complexity = project_info.get('complexity_level', 'Средний')
                message = (
                    f"Total hours ({round(total_for_rules)}) outside expected range for "
                    f"'{project_type}' with complexity '{complexity}' ({expected_min}-{expected_max})"
                )
                if total_for_rules < expected_min:
                    gap_ratio = (expected_min - total_for_rules) / max(expected_min, 1)
                else:
                    gap_ratio = (total_for_rules - expected_max) / max(expected_max, 1)

                if gap_ratio >= 0.35:
                    result.add_issue(
                        "estimation",
                        message,
                        "project_info",
                        current_value=round(total_for_rules),
                        suggested_value=expected_baseline
                    )
                else:
                    result.add_warning("estimation", message, "project_info")
    
    def _calculate_confidence(self, result: ValidationResult, 
                              wbs: Dict[str, Any]) -> float:
        """Calculate confidence score for the WBS."""
        base_score = 1.0
        
        # Deduct for issues
        base_score -= len(result.issues) * 0.1
        base_score -= len(result.warnings) * 0.02
        
        # Check completeness
        phases = wbs.get('wbs', {}).get('phases', [])
        if len(phases) < 3:
            base_score -= 0.1
        
        # Check for tasks
        total_tasks = 0
        for phase in phases:
            for wp in phase.get('work_packages', []):
                total_tasks += len(wp.get('tasks', []))
        
        if total_tasks < 5:
            base_score -= 0.1

        project_info = wbs.get('project_info', {})
        total_hours = self._calculate_actual_total_hours(wbs) or self._coerce_to_number(
            project_info.get('total_estimated_hours', 0)
        )
        expected_range = self._expected_total_hours_range(project_info)
        if expected_range and total_hours > 0:
            expected_min, expected_max, _ = expected_range
            if total_hours < expected_min:
                base_score -= min(0.25, ((expected_min - total_hours) / max(expected_min, 1)) * 0.35)
            elif total_hours > expected_max:
                base_score -= min(0.25, ((total_hours - expected_max) / max(expected_max, 1)) * 0.35)
        
        return max(0.0, min(1.0, base_score))
    
    @staticmethod
    def _coerce_to_number(value: Any, default: float = 0) -> float:
        """Coerce a value to a number, handling string inputs from LLM.
        
        Args:
            value: Value to coerce (may be int, float, str like "16 часов", etc.)
            default: Default value if coercion fails
            
        Returns:
            Numeric value
        """
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Extract first number from string like "16 часов", "2-3 дня", etc.
            import re
            match = re.search(r'[\d.]+', value)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    pass
        return default
    
    def normalize_wbs(self, wbs: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize WBS values to acceptable ranges with bottom-up recalculation.
        
        Performs:
        1. Type coercion (string → number) for all estimated_hours and duration_days
        2. Clamp task hours to [min_hours_per_task, max_hours_per_task]
        3. Recalculate duration_days = ceil(estimated_hours / 8)
        4. Bottom-up recalculation: tasks → work_packages → phases → total
        
        Args:
            wbs: WBS to normalize
            
        Returns:
            Normalized WBS
        """
        import copy
        import math
        normalized = canonicalize_wbs_result(wbs)
        
        min_task = self.estimation_rules['min_hours_per_task']
        max_task = self.estimation_rules['max_hours_per_task']
        min_phase = self.estimation_rules['min_hours_per_phase']
        max_phase = self.estimation_rules['max_hours_per_phase']
        
        # Normalize phases with bottom-up recalculation
        total_hours = 0
        if 'wbs' in normalized and 'phases' in normalized['wbs']:
            for phase in normalized['wbs']['phases']:
                phase_hours_sum = 0
                
                # Normalize work packages
                for wp in phase.get('work_packages', []):
                    wp_hours_sum = 0
                    
                    # Normalize tasks (bottom level)
                    for task in wp.get('tasks', []):
                        # Type coercion
                        task_hours = self._coerce_to_number(task.get('estimated_hours', 0))
                        # Clamp to range
                        task_hours = max(min_task, min(max_task, task_hours))
                        task['estimated_hours'] = round(task_hours)
                        # Recalculate duration_days
                        task['duration_days'] = math.ceil(task_hours / 8)
                        
                        wp_hours_sum += task_hours
                    
                    # Bottom-up: WP hours = sum of task hours
                    if wp.get('tasks'):
                        wp_hours = wp_hours_sum
                    else:
                        wp_hours = self._coerce_to_number(wp.get('estimated_hours', 0))
                    wp['estimated_hours'] = round(max(min_task, wp_hours))

                    if not wp.get('requirement_ids'):
                        inherited_requirement_ids = []
                        for task in wp.get('tasks', []):
                            for requirement_id in task.get('requirement_ids', []):
                                if requirement_id and requirement_id not in inherited_requirement_ids:
                                    inherited_requirement_ids.append(requirement_id)
                        wp['requirement_ids'] = inherited_requirement_ids

                    parent_requirement_ids = []
                    for requirement_id in wp.get('requirement_ids', []):
                        if requirement_id and requirement_id not in parent_requirement_ids:
                            parent_requirement_ids.append(requirement_id)
                    wp['requirement_ids'] = parent_requirement_ids

                    for task in wp.get('tasks', []):
                        task_requirement_ids = []
                        for requirement_id in task.get('requirement_ids', []):
                            if not requirement_id:
                                continue
                            if parent_requirement_ids and requirement_id not in parent_requirement_ids:
                                continue
                            if requirement_id not in task_requirement_ids:
                                task_requirement_ids.append(requirement_id)
                        if not task_requirement_ids:
                            task_requirement_ids = list(parent_requirement_ids)
                        task['requirement_ids'] = task_requirement_ids
                    
                    # Recalculate WP duration_days
                    wp['duration_days'] = math.ceil(wp['estimated_hours'] / 8)
                    
                    phase_hours_sum += wp['estimated_hours']
                
                # Bottom-up: phase hours = sum of WP hours
                if phase.get('work_packages'):
                    phase_hours = phase_hours_sum
                else:
                    phase_hours = self._coerce_to_number(phase.get('estimated_hours', 0))
                
                # Clamp phase hours
                phase_hours = max(min_phase, min(max_phase, phase_hours))
                phase['estimated_hours'] = round(phase_hours)
                
                # Recalculate phase duration
                phase_days = math.ceil(phase_hours / 8)
                phase['duration'] = f"{phase_days} дней"
                
                total_hours += phase['estimated_hours']
        
        # Update project_info with bottom-up total
        if 'project_info' in normalized:
            normalized['project_info']['total_estimated_hours'] = round(total_hours)
            # Estimate duration (assuming 8 hours per day, 5 days per week)
            weeks = max(1, round(total_hours / 40))
            normalized['project_info']['estimated_duration'] = f"{weeks} недель"
        
        return normalized
    
    def check_consistency(self, wbs_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check consistency across multiple WBS results.
        
        Args:
            wbs_list: List of WBS results to compare
            
        Returns:
            Consistency report
        """
        if len(wbs_list) < 2:
            return {"consistent": True, "message": "Only one WBS provided"}
        
        # Extract totals
        totals = []
        for wbs in wbs_list:
            total = wbs.get('project_info', {}).get('total_estimated_hours', 0)
            totals.append(total)
        
        # Calculate statistics
        mean_total = statistics.mean(totals)
        std_total = statistics.stdev(totals) if len(totals) > 1 else 0
        cv = std_total / mean_total if mean_total > 0 else 0  # Coefficient of variation
        
        # Check consistency (CV < 0.2 is considered consistent)
        is_consistent = cv < 0.2
        
        return {
            "consistent": is_consistent,
            "coefficient_of_variation": round(cv, 3),
            "mean_hours": round(mean_total, 1),
            "std_hours": round(std_total, 1),
            "min_hours": min(totals),
            "max_hours": max(totals),
            "range_hours": max(totals) - min(totals),
            "values": totals,
            "message": "Results are consistent" if is_consistent else 
                      f"High variance in results (CV={cv:.2f})"
        }
    
    def get_consensus(self, wbs_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get consensus WBS from multiple results.
        
        Uses median values for numerical fields and most common
        values for categorical fields.
        
        Args:
            wbs_list: List of WBS results
            
        Returns:
            Consensus WBS
        """
        if not wbs_list:
            return {}
        
        if len(wbs_list) == 1:
            return wbs_list[0]
        
        # Start with the first WBS as template
        import copy
        consensus = copy.deepcopy(wbs_list[0])
        
        # Collect all totals for median calculation
        totals = [wbs.get('project_info', {}).get('total_estimated_hours', 0) 
                  for wbs in wbs_list]
        median_total = statistics.median(totals)
        
        # Apply median total
        if 'project_info' in consensus:
            consensus['project_info']['total_estimated_hours'] = median_total
            weeks = max(1, round(median_total / 40))
            consensus['project_info']['estimated_duration'] = f"{weeks} недель"
        
        # Normalize phases using median values
        if 'wbs' in consensus and 'phases' in consensus['wbs']:
            for i, phase in enumerate(consensus['wbs']['phases']):
                phase_hours = []
                for wbs in wbs_list:
                    phases = wbs.get('wbs', {}).get('phases', [])
                    if i < len(phases):
                        phase_hours.append(phases[i].get('estimated_hours', 0))
                
                if phase_hours:
                    phase['estimated_hours'] = statistics.median(phase_hours)
        
        return consensus
    
    def validate_with_llm(self, wbs: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to validate WBS for semantic correctness.
        
        Args:
            wbs: WBS to validate
            
        Returns:
            Validation result from LLM
        """
        compact_wbs = {
            "project_info": wbs.get("project_info", {}),
            "phases": [
                {
                    "id": phase.get("id", ""),
                    "name": phase.get("name", ""),
                    "estimated_hours": phase.get("estimated_hours", 0),
                    "work_packages": [
                        {
                            "id": wp.get("id", ""),
                            "name": wp.get("name", ""),
                            "estimated_hours": wp.get("estimated_hours", 0),
                            "tasks_count": len(wp.get("tasks", [])),
                            "task_names": [task.get("name", "") for task in wp.get("tasks", [])[:6]]
                        }
                        for wp in phase.get("work_packages", [])[:10]
                    ]
                }
                for phase in wbs.get("wbs", {}).get("phases", [])
            ],
            "risks": wbs.get("risks", [])[:5],
            "assumptions": wbs.get("assumptions", [])[:10]
        }

        message = f"""Проверь следующий компактный срез WBS на корректность и реалистичность.

ВЕРНИ ТОЛЬКО JSON БЕЗ КАКИХ-ЛИБО ДОПОЛНИТЕЛЬНЫХ КОММЕНТАРИЕВ.

WBS:
{json.dumps(compact_wbs, ensure_ascii=False, indent=2)}

JSON:"""
        
        result = self.send_message(
            message,
            expect_json=True,
            use_history=False,
            max_tokens=Config.VALIDATION_MAX_TOKENS,
            temperature=0.0
        )
        
        if result["success"]:
            return {
                "success": True,
                "validation": result["data"]
            }
        return result
