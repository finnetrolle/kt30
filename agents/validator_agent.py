"""
Validator Agent.
Validates and normalizes WBS results for consistency and realism.
"""
import logging
import json
import statistics
from typing import Dict, Any, List, Optional, Tuple
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


# Standard estimation rules for common tasks (in hours)
ESTIMATION_RULES = {
    "task_templates": {
        "Авторизация": {"min_hours": 8, "max_hours": 24, "typical_hours": 16},
        "Регистрация": {"min_hours": 6, "max_hours": 16, "typical_hours": 10},
        "Логин": {"min_hours": 4, "max_hours": 8, "typical_hours": 6},
        "CRUD операции": {"min_hours": 4, "max_hours": 16, "typical_hours": 8},
        "API endpoint": {"min_hours": 2, "max_hours": 8, "typical_hours": 4},
        "Форма": {"min_hours": 4, "max_hours": 16, "typical_hours": 8},
        "Страница": {"min_hours": 4, "max_hours": 16, "typical_hours": 8},
        "Отчет": {"min_hours": 8, "max_hours": 24, "typical_hours": 16},
        "Дашборд": {"min_hours": 16, "max_hours": 40, "typical_hours": 24},
        "Интеграция": {"min_hours": 16, "max_hours": 80, "typical_hours": 32},
        "Тестирование": {"min_hours": 4, "max_hours": 16, "typical_hours": 8},
        "Документация": {"min_hours": 2, "max_hours": 8, "typical_hours": 4},
        "Миграция данных": {"min_hours": 8, "max_hours": 40, "typical_hours": 16},
        "Админ-панель": {"min_hours": 24, "max_hours": 80, "typical_hours": 40},
        "Уведомления": {"min_hours": 8, "max_hours": 24, "typical_hours": 12},
        "Поиск": {"min_hours": 8, "max_hours": 24, "typical_hours": 12},
        "Фильтрация": {"min_hours": 4, "max_hours": 12, "typical_hours": 6},
        "Экспорт": {"min_hours": 4, "max_hours": 16, "typical_hours": 8},
        "Импорт": {"min_hours": 8, "max_hours": 24, "typical_hours": 12},
        "Валидация": {"min_hours": 2, "max_hours": 8, "typical_hours": 4},
    },
    "phase_ratios": {
        "Планирование": 0.10,
        "Анализ": 0.10,
        "Проектирование": 0.15,
        "Разработка": 0.40,
        "Тестирование": 0.15,
        "Развертывание": 0.10,
    },
    "complexity_multipliers": {
        "Низкий": 0.8,
        "Средний": 1.0,
        "Высокий": 1.5,
    },
    "min_hours_per_task": 2,
    "max_hours_per_task": 80,
    "min_hours_per_phase": 8,
    "max_hours_per_phase": 500,
}


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
        
        # Check tasks
        tasks = wp.get('tasks', [])
        if not tasks:
            result.add_warning("structure", "Work package has no tasks", location)
            return
        
        # Validate each task
        for task in tasks:
            self._validate_task(task, location, result)
        
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
                       parent_location: str, result: ValidationResult):
        """Validate a single task."""
        task_id = task.get('id', 'unknown')
        task_name = task.get('name', '')
        location = f"{parent_location}.task[{task_id}]"
        
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
        
        complexity = project_info.get('complexity_level', 'Средний')
        if complexity not in self.estimation_rules['complexity_multipliers']:
            result.add_warning("estimation", 
                             f"Unknown complexity level: {complexity}", location)
    
    def _validate_total_hours(self, wbs: Dict[str, Any], result: ValidationResult):
        """Validate total hours consistency."""
        declared_total = wbs.get('project_info', {}).get('total_estimated_hours', 0)
        
        # Calculate actual sum
        actual_total = 0
        phases = wbs.get('wbs', {}).get('phases', [])
        for phase in phases:
            actual_total += phase.get('estimated_hours', 0)
        
        if declared_total > 0 and actual_total > 0:
            diff_ratio = abs(declared_total - actual_total) / max(declared_total, 1)
            if diff_ratio > 0.2:  # More than 20% difference
                result.add_warning("estimation",
                    f"Declared total ({declared_total}) differs from sum of phases ({actual_total})",
                    "project_info")
    
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
        
        return max(0.0, min(1.0, base_score))
    
    def normalize_wbs(self, wbs: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize WBS values to acceptable ranges.
        
        Args:
            wbs: WBS to normalize
            
        Returns:
            Normalized WBS
        """
        import copy
        normalized = copy.deepcopy(wbs)
        
        # Normalize phases
        if 'wbs' in normalized and 'phases' in normalized['wbs']:
            for phase in normalized['wbs']['phases']:
                # Normalize phase hours
                hours = phase.get('estimated_hours', 0)
                hours = max(self.estimation_rules['min_hours_per_phase'], hours)
                hours = min(self.estimation_rules['max_hours_per_phase'], hours)
                phase['estimated_hours'] = hours
                
                # Normalize work packages
                for wp in phase.get('work_packages', []):
                    wp_hours = wp.get('estimated_hours', 0)
                    wp['estimated_hours'] = max(self.estimation_rules['min_hours_per_task'], wp_hours)
                    
                    # Normalize tasks
                    for task in wp.get('tasks', []):
                        task_hours = task.get('estimated_hours', 0)
                        task['estimated_hours'] = max(
                            self.estimation_rules['min_hours_per_task'],
                            min(self.estimation_rules['max_hours_per_task'], task_hours)
                        )
        
        # Recalculate total
        total_hours = 0
        for phase in normalized.get('wbs', {}).get('phases', []):
            total_hours += phase.get('estimated_hours', 0)
        
        if 'project_info' in normalized:
            normalized['project_info']['total_estimated_hours'] = total_hours
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
        import json
        wbs_json = json.dumps(wbs, ensure_ascii=False, indent=2)
        
        message = f"""Проверь следующий WBS на корректность и реалистичность.

ВЕРНИ ТОЛЬКО JSON БЕЗ КАКИХ-ЛИБО ДОПОЛНИТЕЛЬНЫХ КОММЕНТАРИЕВ.

WBS:
{wbs_json}

JSON:"""
        
        result = self.send_message(message, expect_json=True)
        
        if result["success"]:
            return {
                "success": True,
                "validation": result["data"]
            }
        return result
