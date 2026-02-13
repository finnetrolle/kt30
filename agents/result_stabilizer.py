"""
Result Stabilizer Module.
Implements ensemble approach for stabilizing WBS generation results.
"""
import logging
import json
import statistics
import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class EstimationRules:
    """Loads and provides access to estimation rules."""
    
    def __init__(self, rules_path: str = None):
        """Initialize estimation rules.
        
        Args:
            rules_path: Path to estimation rules JSON file
        """
        self.rules = self._load_rules(rules_path)
    
    def _load_rules(self, rules_path: str = None) -> Dict[str, Any]:
        """Load estimation rules from file."""
        if rules_path is None:
            rules_path = Path(__file__).parent.parent / "data" / "estimation_rules.json"
        
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            logger.info(f"Loaded estimation rules from {rules_path}")
            return rules
        except FileNotFoundError:
            logger.warning(f"Estimation rules file not found: {rules_path}")
            return self._get_default_rules()
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing estimation rules: {e}")
            return self._get_default_rules()
    
    def _get_default_rules(self) -> Dict[str, Any]:
        """Get default estimation rules."""
        return {
            "limits": {
                "min_hours_per_task": 2,
                "max_hours_per_task": 80,
                "min_hours_per_phase": 8,
                "max_hours_per_phase": 500
            },
            "complexity_multipliers": {
                "Низкий": {"multiplier": 0.8},
                "Средний": {"multiplier": 1.0},
                "Высокий": {"multiplier": 1.5}
            },
            "stabilization_settings": {
                "ensemble_iterations": 3,
                "consensus_method": "median",
                "outlier_threshold_std": 2.0
            }
        }
    
    def get_task_estimation(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Get estimation for a task by name pattern matching."""
        task_lower = task_name.lower()
        
        templates = self.rules.get("task_templates", {})
        for category, tasks in templates.items():
            for pattern, estimation in tasks.items():
                if pattern.lower() in task_lower:
                    return estimation
        
        return None
    
    def normalize_hours(self, hours: float, task_name: str = None) -> float:
        """Normalize hours to acceptable range."""
        limits = self.rules.get("limits", {})
        min_hours = limits.get("min_hours_per_task", 2)
        max_hours = limits.get("max_hours_per_task", 80)
        
        # Check against task template if available
        if task_name:
            estimation = self.get_task_estimation(task_name)
            if estimation:
                min_hours = max(min_hours, estimation.get("min_hours", min_hours))
                max_hours = min(max_hours, estimation.get("max_hours", max_hours))
        
        return max(min_hours, min(max_hours, hours))
    
    def get_complexity_multiplier(self, complexity: str) -> float:
        """Get multiplier for complexity level."""
        multipliers = self.rules.get("complexity_multipliers", {})
        return multipliers.get(complexity, {}).get("multiplier", 1.0)


class ResultStabilizer:
    """Stabilizes WBS results using ensemble approach.
    
    Features:
    - Multiple generation iterations
    - Outlier detection and removal
    - Consensus calculation (median/mean)
    - Validation against estimation rules
    - Confidence scoring
    """
    
    def __init__(self, estimation_rules: EstimationRules = None):
        """Initialize the result stabilizer.
        
        Args:
            estimation_rules: Estimation rules instance
        """
        self.rules = estimation_rules or EstimationRules()
        self.settings = self.rules.rules.get("stabilization_settings", {})
    
    def stabilize(self, wbs_results: List[Dict[str, Any]], 
                  method: str = None) -> Dict[str, Any]:
        """Stabilize multiple WBS results into one consensus result.
        
        Args:
            wbs_results: List of WBS results to stabilize
            method: Consensus method ('median', 'mean', 'trimmed_mean')
            
        Returns:
            Stabilized WBS result with metadata
        """
        if not wbs_results:
            return {"success": False, "error": "No results to stabilize"}
        
        if len(wbs_results) == 1:
            return {
                "success": True,
                "data": wbs_results[0],
                "metadata": {
                    "method": "single_result",
                    "confidence": 1.0,
                    "iterations": 1
                }
            }
        
        method = method or self.settings.get("consensus_method", "median")
        
        # Step 1: Remove outliers
        filtered_results = self._remove_outliers(wbs_results)
        
        if not filtered_results:
            filtered_results = wbs_results  # Fallback to all results
        
        # Step 2: Calculate consensus
        consensus_wbs = self._calculate_consensus(filtered_results, method)
        
        # Step 3: Normalize values
        normalized_wbs = self._normalize_wbs(consensus_wbs)
        
        # Step 4: Calculate confidence
        confidence = self._calculate_confidence(wbs_results, filtered_results, normalized_wbs)
        
        return {
            "success": True,
            "data": normalized_wbs,
            "metadata": {
                "method": method,
                "confidence": confidence,
                "total_iterations": len(wbs_results),
                "used_iterations": len(filtered_results),
                "outliers_removed": len(wbs_results) - len(filtered_results),
                "statistics": self._calculate_statistics(wbs_results)
            }
        }
    
    def _remove_outliers(self, wbs_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove outlier results based on total hours."""
        threshold = self.settings.get("outlier_threshold_std", 2.0)
        
        # Extract total hours
        totals = []
        for wbs in wbs_results:
            total = wbs.get('project_info', {}).get('total_estimated_hours', 0)
            if total > 0:
                totals.append(total)
        
        if len(totals) < 3:
            return wbs_results  # Not enough data to detect outliers
        
        mean = statistics.mean(totals)
        std = statistics.stdev(totals)
        
        if std == 0:
            return wbs_results  # All values are the same
        
        # Filter results within threshold
        filtered = []
        for i, wbs in enumerate(wbs_results):
            total = totals[i] if i < len(totals) else 0
            z_score = abs(total - mean) / std
            if z_score <= threshold:
                filtered.append(wbs)
            else:
                logger.info(f"Removed outlier: {total} hours (z-score: {z_score:.2f})")
        
        return filtered
    
    def _calculate_consensus(self, wbs_results: List[Dict[str, Any]], 
                            method: str) -> Dict[str, Any]:
        """Calculate consensus WBS from multiple results."""
        import copy
        
        if not wbs_results:
            return {}
        
        # Use first result as template
        consensus = copy.deepcopy(wbs_results[0])
        
        # Calculate consensus for project_info
        if 'project_info' in consensus:
            consensus['project_info'] = self._consensus_project_info(wbs_results, method)
        
        # Calculate consensus for phases
        if 'wbs' in consensus and 'phases' in consensus['wbs']:
            consensus['wbs']['phases'] = self._consensus_phases(wbs_results, method)
        
        return consensus
    
    def _consensus_project_info(self, wbs_results: List[Dict[str, Any]], 
                                method: str) -> Dict[str, Any]:
        """Calculate consensus for project_info."""
        # Collect all total hours
        totals = [
            wbs.get('project_info', {}).get('total_estimated_hours', 0)
            for wbs in wbs_results
        ]
        totals = [t for t in totals if t > 0]
        
        if not totals:
            return wbs_results[0].get('project_info', {})
        
        # Calculate consensus value
        if method == 'median':
            consensus_total = statistics.median(totals)
        elif method == 'trimmed_mean':
            sorted_totals = sorted(totals)
            trim = max(1, len(sorted_totals) // 4)
            trimmed = sorted_totals[trim:-trim] if len(sorted_totals) > trim * 2 else sorted_totals
            consensus_total = statistics.mean(trimmed) if trimmed else statistics.mean(totals)
        else:  # mean
            consensus_total = statistics.mean(totals)
        
        # Build consensus project_info
        import copy
        consensus_info = copy.deepcopy(wbs_results[0].get('project_info', {}))
        consensus_info['total_estimated_hours'] = round(consensus_total)
        
        # Calculate duration (40 hours per week)
        weeks = max(1, round(consensus_total / 40))
        consensus_info['estimated_duration'] = f"{weeks} недель"
        
        return consensus_info
    
    def _consensus_phases(self, wbs_results: List[Dict[str, Any]], 
                         method: str) -> List[Dict[str, Any]]:
        """Calculate consensus for phases."""
        import copy
        
        # Get phase structure from first result
        template_phases = wbs_results[0].get('wbs', {}).get('phases', [])
        consensus_phases = []
        
        for i, template_phase in enumerate(template_phases):
            consensus_phase = copy.deepcopy(template_phase)
            
            # Collect hours for this phase across all results
            phase_hours = []
            for wbs in wbs_results:
                phases = wbs.get('wbs', {}).get('phases', [])
                if i < len(phases):
                    hours = phases[i].get('estimated_hours', 0)
                    if hours > 0:
                        phase_hours.append(hours)
            
            if phase_hours:
                if method == 'median':
                    consensus_phase['estimated_hours'] = round(statistics.median(phase_hours))
                else:
                    consensus_phase['estimated_hours'] = round(statistics.mean(phase_hours))
            
            # Calculate duration from hours
            hours = consensus_phase.get('estimated_hours', 0)
            days = max(1, round(hours / 8))
            consensus_phase['duration'] = f"{days} дней"
            
            # Consensus for work packages
            if 'work_packages' in consensus_phase:
                consensus_phase['work_packages'] = self._consensus_work_packages(
                    wbs_results, i, method
                )
            
            consensus_phases.append(consensus_phase)
        
        return consensus_phases
    
    def _consensus_work_packages(self, wbs_results: List[Dict[str, Any]], 
                                 phase_idx: int, method: str) -> List[Dict[str, Any]]:
        """Calculate consensus for work packages in a phase."""
        import copy
        
        # Get template work packages
        template_wps = (
            wbs_results[0]
            .get('wbs', {}).get('phases', [])[phase_idx]
            .get('work_packages', [])
        )
        
        consensus_wps = []
        
        for j, template_wp in enumerate(template_wps):
            consensus_wp = copy.deepcopy(template_wp)
            
            # Collect hours for this work package
            wp_hours = []
            for wbs in wbs_results:
                phases = wbs.get('wbs', {}).get('phases', [])
                if phase_idx < len(phases):
                    wps = phases[phase_idx].get('work_packages', [])
                    if j < len(wps):
                        hours = wps[j].get('estimated_hours', 0)
                        if hours > 0:
                            wp_hours.append(hours)
            
            if wp_hours:
                if method == 'median':
                    consensus_wp['estimated_hours'] = round(statistics.median(wp_hours))
                else:
                    consensus_wp['estimated_hours'] = round(statistics.mean(wp_hours))
            
            # Consensus for tasks
            if 'tasks' in consensus_wp:
                consensus_wp['tasks'] = self._consensus_tasks(
                    wbs_results, phase_idx, j, method
                )
            
            consensus_wps.append(consensus_wp)
        
        return consensus_wps
    
    def _consensus_tasks(self, wbs_results: List[Dict[str, Any]], 
                        phase_idx: int, wp_idx: int, 
                        method: str) -> List[Dict[str, Any]]:
        """Calculate consensus for tasks in a work package."""
        import copy
        
        # Get template tasks
        template_tasks = (
            wbs_results[0]
            .get('wbs', {}).get('phases', [])[phase_idx]
            .get('work_packages', [])[wp_idx]
            .get('tasks', [])
        )
        
        consensus_tasks = []
        
        for k, template_task in enumerate(template_tasks):
            consensus_task = copy.deepcopy(template_task)
            
            # Collect hours for this task
            task_hours = []
            for wbs in wbs_results:
                try:
                    hours = (
                        wbs.get('wbs', {}).get('phases', [])[phase_idx]
                        .get('work_packages', [])[wp_idx]
                        .get('tasks', [])[k]
                        .get('estimated_hours', 0)
                    )
                    if hours > 0:
                        task_hours.append(hours)
                except (IndexError, KeyError):
                    pass
            
            if task_hours:
                if method == 'median':
                    consensus_task['estimated_hours'] = round(statistics.median(task_hours))
                else:
                    consensus_task['estimated_hours'] = round(statistics.mean(task_hours))
            
            # Normalize task hours
            task_name = consensus_task.get('name', '')
            consensus_task['estimated_hours'] = self.rules.normalize_hours(
                consensus_task.get('estimated_hours', 0), task_name
            )
            
            consensus_tasks.append(consensus_task)
        
        return consensus_tasks
    
    def _normalize_wbs(self, wbs: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize WBS values according to rules."""
        import copy
        normalized = copy.deepcopy(wbs)
        
        limits = self.rules.rules.get("limits", {})
        min_task = limits.get("min_hours_per_task", 2)
        max_task = limits.get("max_hours_per_task", 80)
        
        # Normalize phases
        if 'wbs' in normalized and 'phases' in normalized['wbs']:
            for phase in normalized['wbs']['phases']:
                # Normalize work packages
                for wp in phase.get('work_packages', []):
                    wp_hours = wp.get('estimated_hours', 0)
                    wp['estimated_hours'] = max(min_task, wp_hours)
                    
                    # Normalize tasks
                    for task in wp.get('tasks', []):
                        task_hours = task.get('estimated_hours', 0)
                        task_name = task.get('name', '')
                        task['estimated_hours'] = self.rules.normalize_hours(task_hours, task_name)
        
        # Recalculate total
        total_hours = 0
        for phase in normalized.get('wbs', {}).get('phases', []):
            total_hours += phase.get('estimated_hours', 0)
        
        if 'project_info' in normalized:
            normalized['project_info']['total_estimated_hours'] = total_hours
            weeks = max(1, round(total_hours / 40))
            normalized['project_info']['estimated_duration'] = f"{weeks} недель"
        
        return normalized
    
    def _calculate_confidence(self, all_results: List[Dict[str, Any]], 
                             filtered_results: List[Dict[str, Any]],
                             consensus: Dict[str, Any]) -> float:
        """Calculate confidence score for the consensus."""
        if len(all_results) < 2:
            return 1.0
        
        # Base confidence from number of results
        base_confidence = min(1.0, len(filtered_results) / 3.0)
        
        # Penalty for outliers
        outlier_ratio = (len(all_results) - len(filtered_results)) / len(all_results)
        outlier_penalty = outlier_ratio * 0.2
        
        # Variance penalty
        totals = [
            r.get('project_info', {}).get('total_estimated_hours', 0)
            for r in filtered_results
        ]
        totals = [t for t in totals if t > 0]
        
        variance_penalty = 0
        if len(totals) > 1:
            mean = statistics.mean(totals)
            std = statistics.stdev(totals)
            cv = std / mean if mean > 0 else 0
            variance_penalty = min(0.3, cv * 0.5)
        
        confidence = base_confidence - outlier_penalty - variance_penalty
        return max(0.0, min(1.0, confidence))
    
    def _calculate_statistics(self, wbs_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics for the results."""
        totals = [
            r.get('project_info', {}).get('total_estimated_hours', 0)
            for r in wbs_results
        ]
        totals = [t for t in totals if t > 0]
        
        if not totals:
            return {}
        
        stats = {
            "count": len(totals),
            "min": min(totals),
            "max": max(totals),
            "range": max(totals) - min(totals)
        }
        
        if len(totals) > 1:
            stats["mean"] = round(statistics.mean(totals), 1)
            stats["median"] = statistics.median(totals)
            stats["std"] = round(statistics.stdev(totals), 1)
            stats["cv"] = round(stats["std"] / stats["mean"], 3) if stats["mean"] > 0 else 0
        
        return stats


class EnsembleGenerator:
    """Generates multiple WBS results for ensemble stabilization."""
    
    def __init__(self, generator_func, stabilizer: ResultStabilizer = None):
        """Initialize ensemble generator.
        
        Args:
            generator_func: Function to generate single WBS
            stabilizer: ResultStabilizer instance
        """
        self.generator_func = generator_func
        self.stabilizer = stabilizer or ResultStabilizer()
    
    def generate_with_ensemble(self, document_content: str, 
                               iterations: int = None,
                               parallel: bool = False) -> Dict[str, Any]:
        """Generate WBS with ensemble stabilization.
        
        Args:
            document_content: Document to analyze
            iterations: Number of iterations (default from settings)
            parallel: Whether to run in parallel
            
        Returns:
            Stabilized WBS result
        """
        settings = self.stabilizer.rules.rules.get("stabilization_settings", {})
        iterations = iterations or settings.get("ensemble_iterations", 3)
        
        logger.info(f"Starting ensemble generation with {iterations} iterations")
        start_time = time.time()
        
        results = []
        
        if parallel and iterations > 1:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=min(iterations, 5)) as executor:
                futures = [
                    executor.submit(self.generator_func, document_content)
                    for _ in range(iterations)
                ]
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result.get('success'):
                            results.append(result.get('data'))
                    except Exception as e:
                        logger.error(f"Error in parallel generation: {e}")
        else:
            # Sequential execution
            for i in range(iterations):
                logger.info(f"Ensemble iteration {i + 1}/{iterations}")
                try:
                    result = self.generator_func(document_content)
                    if result.get('success'):
                        results.append(result.get('data'))
                except Exception as e:
                    logger.error(f"Error in iteration {i + 1}: {e}")
        
        if not results:
            return {
                "success": False,
                "error": "All iterations failed"
            }
        
        # Stabilize results
        stabilized = self.stabilizer.stabilize(results)
        
        elapsed_time = time.time() - start_time
        logger.info(f"Ensemble generation completed in {elapsed_time:.2f}s")
        
        if stabilized["success"]:
            return {
                "success": True,
                "data": stabilized["data"],
                "metadata": {
                    **stabilized["metadata"],
                    "elapsed_seconds": round(elapsed_time, 2),
                    "stabilization": "ensemble"
                }
            }
        
        return stabilized
