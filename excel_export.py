"""
Excel export module for WBS (Work Breakdown Structure).
Generates Excel files with work packages, roles, hours, costs, and Gantt chart.
"""
import logging
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.chart.label import DataLabelList

logger = logging.getLogger(__name__)

# Default role rates (rubles per hour)
# These can be customized on the second sheet of the Excel file
DEFAULT_ROLE_RATES = {
    "Проектный менеджер": 1500,
    "Бизнес-аналитик": 1200,
    "Системный аналитик": 1300,
    "Архитектор": 2000,
    "Разработчик (Frontend)": 1000,
    "Разработчик (Backend)": 1100,
    "Разработчик (Full-stack)": 1200,
    "UI/UX дизайнер": 1000,
    "Тестировщик (QA)": 800,
    "DevOps инженер": 1500,
    "Администратор БД": 1400,
    "Технический писатель": 700,
    "Руководитель проекта": 1800,
    "Scrum мастер": 1200,
    "Аналитик": 1200,
    "Дизайнер": 1000,
    "Разработчик": 1100,
    "Тестировщик": 800,
    "Инженер": 1200,
}

# Role aliases for normalization
ROLE_ALIASES = {
    "Frontend разработчик": "Разработчик (Frontend)",
    "Backend разработчик": "Разработчик (Backend)",
    "Full-stack разработчик": "Разработчик (Full-stack)",
    "QA инженер": "Тестировщик (QA)",
    "QA": "Тестировщик (QA)",
    "PM": "Проектный менеджер",
    "БА": "Бизнес-аналитик",
    "СА": "Системный аналитик",
    "БД": "Администратор БД",
    "DBA": "Администратор БД",
}


def calculate_project_duration_with_parallel(wbs_data: dict) -> dict:
    """Calculate actual project duration considering parallel execution.
    
    Args:
        wbs_data: WBS data dictionary
        
    Returns:
        Dictionary with duration information:
        - total_days: total working days considering parallel execution
        - total_weeks: total weeks
        - phase_durations: dict of phase_id -> actual days
    """
    if not wbs_data or 'phases' not in wbs_data:
        return {'total_days': 0, 'total_weeks': 0, 'phase_durations': {}}
    
    item_end_days = {}
    phase_durations = {}
    current_day = 0
    
    for phase in wbs_data.get('phases', []):
        phase_id = phase.get('id', '')
        phase_start = current_day
        
        # Track parallel work packages
        parallel_wp_end = phase_start
        sequential_wp_start = phase_start
        
        for wp in phase.get('work_packages', []):
            wp_id = wp.get('id', '')
            wp_duration = wp.get('duration_days', 0)
            if not wp_duration:
                hours = wp.get('estimated_hours', 0)
                wp_duration = max(1, hours // 8)
            
            wp_dependencies = wp.get('dependencies', [])
            can_parallel = wp.get('can_start_parallel', False)
            
            dep_end_day = 0
            for dep_id in wp_dependencies:
                if dep_id in item_end_days:
                    dep_end_day = max(dep_end_day, item_end_days[dep_id])
            
            if can_parallel:
                wp_start = dep_end_day if dep_end_day > 0 else phase_start
            else:
                wp_start = max(sequential_wp_start, dep_end_day)
            
            # Process tasks
            parallel_task_end = wp_start
            sequential_task_start = wp_start
            
            for task in wp.get('tasks', []):
                task_id = task.get('id', '')
                task_duration = task.get('duration_days', 0)
                if not task_duration:
                    hours = task.get('estimated_hours', 0)
                    task_duration = max(1, hours // 8)
                
                task_dependencies = task.get('dependencies', [])
                task_can_parallel = task.get('can_start_parallel', False)
                
                task_dep_end = 0
                for dep_id in task_dependencies:
                    if dep_id in item_end_days:
                        task_dep_end = max(task_dep_end, item_end_days[dep_id])
                
                if task_can_parallel:
                    task_start = task_dep_end if task_dep_end > 0 else wp_start
                else:
                    task_start = max(sequential_task_start, task_dep_end)
                
                task_end = task_start + task_duration
                item_end_days[task_id] = task_end
                
                if not task_can_parallel:
                    sequential_task_start = task_end
                
                parallel_task_end = max(parallel_task_end, task_end)
            
            wp_end = wp_start + wp_duration
            item_end_days[wp_id] = wp_end
            
            if not can_parallel:
                sequential_wp_start = wp_end
            
            parallel_wp_end = max(parallel_wp_end, wp_end)
        
        actual_phase_end = parallel_wp_end
        phase_durations[phase_id] = actual_phase_end - phase_start
        current_day = actual_phase_end
    
    total_days = current_day
    total_weeks = max(1, (total_days + 4) // 5)  # Ceiling division for weeks
    
    return {
        'total_days': total_days,
        'total_weeks': total_weeks,
        'phase_durations': phase_durations
    }


def build_dependencies_matrix(wbs_data: dict) -> list:
    """Build a dependencies matrix showing what each task depends on and what can run in parallel.
    
    Args:
        wbs_data: WBS data dictionary
        
    Returns:
        List of dependency entries with task_id, depends_on, and parallel_with
    """
    matrix = []
    
    if not wbs_data or 'phases' not in wbs_data:
        return matrix
    
    # Collect all tasks and work packages with their parallel info
    all_items = {}
    parallel_groups = {}  # Group items that can run in parallel
    
    for phase in wbs_data.get('phases', []):
        phase_id = phase.get('id', '')
        
        for wp in phase.get('work_packages', []):
            wp_id = wp.get('id', '')
            wp_can_parallel = wp.get('can_start_parallel', False)
            wp_dependencies = wp.get('dependencies', [])
            
            all_items[wp_id] = {
                'id': wp_id,
                'name': wp.get('name', ''),
                'type': 'work_package',
                'can_parallel': wp_can_parallel,
                'dependencies': wp_dependencies,
                'phase_id': phase_id
            }
            
            # Group parallel work packages by phase
            if wp_can_parallel:
                if phase_id not in parallel_groups:
                    parallel_groups[phase_id] = []
                parallel_groups[phase_id].append(wp_id)
            
            for task in wp.get('tasks', []):
                task_id = task.get('id', '')
                task_can_parallel = task.get('can_start_parallel', False)
                task_dependencies = task.get('dependencies', [])
                
                all_items[task_id] = {
                    'id': task_id,
                    'name': task.get('name', ''),
                    'type': 'task',
                    'can_parallel': task_can_parallel,
                    'dependencies': task_dependencies,
                    'wp_id': wp_id,
                    'phase_id': phase_id
                }
                
                # Group parallel tasks by work package
                if task_can_parallel:
                    if wp_id not in parallel_groups:
                        parallel_groups[wp_id] = []
                    parallel_groups[wp_id].append(task_id)
    
    # Build the matrix
    for item_id, item in all_items.items():
        # Find what can run in parallel with this item
        parallel_with = []
        
        if item['can_parallel']:
            # Find the group key (phase for work packages, wp for tasks)
            group_key = item.get('phase_id') if item['type'] == 'work_package' else item.get('wp_id')
            
            if group_key in parallel_groups:
                parallel_with = [pid for pid in parallel_groups[group_key] if pid != item_id]
        
        matrix.append({
            'task_id': item_id,
            'task_name': item['name'],
            'type': item['type'],
            'depends_on': item['dependencies'],
            'parallel_with': parallel_with
        })
    
    return matrix


def normalize_role(role_name: str) -> str:
    """Normalize role name using aliases.
    
    Args:
        role_name: Original role name
        
    Returns:
        Normalized role name
    """
    # Check aliases first
    if role_name in ROLE_ALIASES:
        return ROLE_ALIASES[role_name]
    
    # Check if role exists in default rates
    if role_name in DEFAULT_ROLE_RATES:
        return role_name
    
    # Return original if no normalization found
    return role_name


def get_role_rate(role_name: str, custom_rates: dict = None) -> int:
    """Get hourly rate for a role.
    
    Args:
        role_name: Name of the role
        custom_rates: Optional dictionary of custom rates
        
    Returns:
        Hourly rate for the role
    """
    if custom_rates and role_name in custom_rates:
        return custom_rates[role_name]
    
    normalized = normalize_role(role_name)
    if normalized in DEFAULT_ROLE_RATES:
        return DEFAULT_ROLE_RATES[normalized]
    
    # Default rate for unknown roles
    return 1000


def extract_all_roles(wbs_data: dict) -> list:
    """Extract all unique roles from WBS data.
    
    Args:
        wbs_data: WBS data dictionary
        
    Returns:
        Sorted list of unique role names
    """
    roles = set()
    
    if not wbs_data or 'phases' not in wbs_data:
        return sorted(list(roles))
    
    for phase in wbs_data.get('phases', []):
        for wp in phase.get('work_packages', []):
            # Get roles from skills_required
            for skill in wp.get('skills_required', []):
                roles.add(normalize_role(skill))
            
            # Get roles from tasks
            for task in wp.get('tasks', []):
                for skill in task.get('skills_required', []):
                    roles.add(normalize_role(skill))
    
    return sorted(list(roles))


def extract_all_work_items(wbs_data: dict) -> list:
    """Extract all work items (phases, work packages, tasks) from WBS.
    
    Args:
        wbs_data: WBS data dictionary
        
    Returns:
        List of work items with their properties
    """
    items = []
    
    if not wbs_data or 'phases' not in wbs_data:
        return items
    
    for phase in wbs_data.get('phases', []):
        # Add phase as a work item
        items.append({
            'id': phase.get('id', ''),
            'name': phase.get('name', ''),
            'type': 'phase',
            'hours': phase.get('estimated_hours', 0),
            'skills': phase.get('skills_required', []),
            'level': 0,
            'can_start_parallel': False,
            'dependencies': []
        })
        
        for wp in phase.get('work_packages', []):
            # Add work package
            items.append({
                'id': wp.get('id', ''),
                'name': wp.get('name', ''),
                'type': 'work_package',
                'hours': wp.get('estimated_hours', 0),
                'skills': wp.get('skills_required', []),
                'level': 1,
                'can_start_parallel': wp.get('can_start_parallel', False),
                'dependencies': wp.get('dependencies', [])
            })
            
            # Add tasks
            for task in wp.get('tasks', []):
                items.append({
                    'id': task.get('id', ''),
                    'name': task.get('name', ''),
                    'type': 'task',
                    'hours': task.get('estimated_hours', 0),
                    'skills': task.get('skills_required', []) or wp.get('skills_required', []),
                    'level': 2,
                    'can_start_parallel': task.get('can_start_parallel', False),
                    'dependencies': task.get('dependencies', [])
                })
    
    return items


def distribute_hours_by_role(hours: int, skills: list) -> dict:
    """Distribute hours among roles.
    
    Simple distribution: equal split among all required skills/roles.
    
    Args:
        hours: Total hours for the work item
        skills: List of required skills/roles
        
    Returns:
        Dictionary mapping roles to hours
    """
    if not skills or hours <= 0:
        return {}
    
    normalized_skills = [normalize_role(s) for s in skills]
    unique_skills = list(set(normalized_skills))
    
    if not unique_skills:
        return {}
    
    # Equal distribution
    hours_per_role = hours / len(unique_skills)
    
    return {role: hours_per_role for role in unique_skills}


def create_wbs_excel(result_data: dict, custom_rates: dict = None) -> BytesIO:
    """Create Excel file with WBS data.
    
    Args:
        result_data: Analysis result data
        custom_rates: Optional dictionary of custom role rates
        
    Returns:
        BytesIO object containing the Excel file
    """
    logger.info("Creating WBS Excel export...")
    
    wb = Workbook()
    
    # Get WBS data
    wbs_data = result_data.get('wbs', {}) if result_data else {}
    
    # Extract roles and work items
    all_roles = extract_all_roles(wbs_data)
    work_items = extract_all_work_items(wbs_data)
    
    # Use default rates if no custom rates provided
    rates = custom_rates or DEFAULT_ROLE_RATES.copy()
    
    # === Sheet 1: WBS with hours and costs ===
    ws_wbs = wb.active
    ws_wbs.title = "WBS"
    
    # Define styles
    header_font = Font(bold=True, size=12)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, size=12, color="FFFFFF")
    phase_font = Font(bold=True, size=11)
    phase_fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
    wp_font = Font(bold=True, size=10)
    wp_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    task_font = Font(size=10)
    total_font = Font(bold=True, size=11)
    total_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Create headers
    headers = ["№ работы", "Название работы", "Паралл."] + all_roles + ["Стоимость (руб)"]
    
    for col, header in enumerate(headers, 1):
        cell = ws_wbs.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
    
    # Set column widths
    ws_wbs.column_dimensions['A'].width = 12  # ID
    ws_wbs.column_dimensions['B'].width = 40  # Name
    ws_wbs.column_dimensions['C'].width = 8   # Parallel indicator
    
    for i, role in enumerate(all_roles, 4):
        col_letter = get_column_letter(i)
        ws_wbs.column_dimensions[col_letter].width = 15
    
    ws_wbs.column_dimensions[get_column_letter(len(headers))].width = 18  # Cost
    
    # Track totals
    role_totals = {role: 0 for role in all_roles}
    total_cost = 0
    
    # Add work items
    row = 2
    for item in work_items:
        # Determine style based on item type
        if item['type'] == 'phase':
            font = phase_font
            fill = phase_fill
        elif item['type'] == 'work_package':
            font = wp_font
            fill = wp_fill
        else:
            font = task_font
            fill = None
        
        # ID column
        cell = ws_wbs.cell(row=row, column=1, value=item['id'])
        cell.font = font
        cell.border = border
        if fill:
            cell.fill = fill
        
        # Name column with indentation based on level
        indent = "  " * item['level']
        cell = ws_wbs.cell(row=row, column=2, value=f"{indent}{item['name']}")
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        if fill:
            cell.fill = fill
        
        # Parallel indicator column
        can_parallel = item.get('can_start_parallel', False)
        parallel_text = "🔄" if can_parallel else ""
        cell = ws_wbs.cell(row=row, column=3, value=parallel_text)
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
        if fill:
            cell.fill = fill
        
        # Distribute hours among roles
        hours_by_role = distribute_hours_by_role(item['hours'], item['skills'])
        
        # Build the cost formula that references rates from Sheet 2
        cost_formula_parts = []
        
        # Role hours columns (start from column 4 now)
        for col, role in enumerate(all_roles, 4):
            hours = hours_by_role.get(role, 0)
            cell = ws_wbs.cell(row=row, column=col, value=round(hours, 1) if hours > 0 else 0)
            cell.font = font
            cell.border = border
            cell.alignment = Alignment(horizontal='center')
            if fill:
                cell.fill = fill
            # Hide zero values
            if hours == 0:
                cell.number_format = '0.0;0.0;'  # Format to hide zero values
            
            # Update totals
            role_totals[role] += hours
            
            # Build formula part: hours * VLOOKUP for rate
            # Only add to formula if there are hours
            if hours > 0:
                col_letter = get_column_letter(col)
                # VLOOKUP formula to find rate for this role in 'Ставки профессий' sheet
                formula_part = f"IF({col_letter}{row}=0,0,{col_letter}{row}*VLOOKUP(\"{role}\",'Ставки профессий'!$A:$B,2,FALSE))"
                cost_formula_parts.append(formula_part)
        
        # Cost column with formula
        cost_col = len(headers)
        if cost_formula_parts:
            cost_formula = "=" + "+".join(cost_formula_parts)
            cell = ws_wbs.cell(row=row, column=cost_col, value=cost_formula)
        else:
            cell = ws_wbs.cell(row=row, column=cost_col, value=0)
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal='right')
        cell.number_format = '#,##0'
        if fill:
            cell.fill = fill
        
        row += 1
    
    data_end_row = row - 1
    
    # Add totals row
    row += 1
    totals_row = row
    
    # Label
    cell = ws_wbs.cell(row=row, column=1, value="ИТОГО")
    cell.font = total_font
    cell.fill = total_fill
    cell.border = border
    
    cell = ws_wbs.cell(row=row, column=2, value="")
    cell.fill = total_fill
    cell.border = border
    
    # Parallel column in totals
    cell = ws_wbs.cell(row=row, column=3, value="")
    cell.fill = total_fill
    cell.border = border
    
    # Role totals with SUM formulas (start from column 4)
    for col, role in enumerate(all_roles, 4):
        col_letter = get_column_letter(col)
        formula = f"=SUM({col_letter}2:{col_letter}{data_end_row})"
        cell = ws_wbs.cell(row=row, column=col, value=formula)
        cell.font = total_font
        cell.fill = total_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
        cell.number_format = '#,##0.0'
    
    # Total cost with SUM formula
    cost_col_letter = get_column_letter(len(headers))
    cost_formula = f"=SUM({cost_col_letter}2:{cost_col_letter}{data_end_row})"
    cell = ws_wbs.cell(row=row, column=len(headers), value=cost_formula)
    cell.font = total_font
    cell.fill = total_fill
    cell.border = border
    cell.alignment = Alignment(horizontal='right')
    cell.number_format = '#,##0'
    
    # Freeze header row
    ws_wbs.freeze_panes = 'A2'
    
    # === Sheet 2: Role Rates ===
    ws_rates = wb.create_sheet(title="Ставки профессий")
    
    # Headers
    headers_rates = ["Профессия (роль)", "Ставка в час (руб)"]
    for col, header in enumerate(headers_rates, 1):
        cell = ws_rates.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border
    
    ws_rates.column_dimensions['A'].width = 30
    ws_rates.column_dimensions['B'].width = 20
    
    # Add all roles with their rates
    rate_row = 2
    all_roles_with_rates = set(all_roles) | set(DEFAULT_ROLE_RATES.keys())
    
    # Sort roles, but put roles that are actually used first
    sorted_roles = sorted(all_roles_with_rates, key=lambda r: (r not in all_roles, r))
    
    for role in sorted_roles:
        cell = ws_rates.cell(row=rate_row, column=1, value=role)
        cell.border = border
        
        rate = get_role_rate(role, rates)
        cell = ws_rates.cell(row=rate_row, column=2, value=rate)
        cell.border = border
        cell.alignment = Alignment(horizontal='right')
        cell.number_format = '#,##0'
        
        rate_row += 1
    
    # Add note about editing rates
    rate_row += 2
    cell = ws_rates.cell(row=rate_row, column=1, value="Примечание: Измените ставки на этом листе для автоматического пересчета стоимости на листе WBS.")
    cell.font = Font(italic=True, color="666666")
    ws_rates.merge_cells(start_row=rate_row, start_column=1, end_row=rate_row, end_column=2)
    
    # Freeze header row
    ws_rates.freeze_panes = 'A2'
    
    # === Sheet 3: Gantt Chart ===
    ws_gantt = wb.create_sheet(title="Диаграмма Гантта")
    
    # Create Gantt chart data
    gantt_data = _prepare_gantt_data(wbs_data)
    
    # Calculate max day for the timeline
    max_day = max((int(item['start_day']) + int(item['duration_days']) for item in gantt_data), default=0)
    
    # Use weeks for timeline (each column = 1 week = 5 working days)
    # This allows up to 1 year (52 weeks) to fit comfortably in Excel
    DAYS_PER_WEEK = 5
    max_week = int((max_day + DAYS_PER_WEEK - 1) // DAYS_PER_WEEK)  # Ceiling division
    max_week = min(max_week, 52)  # Limit to 52 weeks (1 year)
    
    # Fixed columns: A=ID, B=Name, C=Start, D=Duration, then week columns starting from E
    first_week_col = 5  # Column E is the first week column
    
    # Header row 1: Main headers
    # ID column
    cell = ws_gantt.cell(row=1, column=1, value="ID")
    cell.font = header_font_white
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    cell.border = border
    
    # Name column
    cell = ws_gantt.cell(row=1, column=2, value="Название работы")
    cell.font = header_font_white
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    cell.border = border
    
    # Start week column
    cell = ws_gantt.cell(row=1, column=3, value="Неделя")
    cell.font = header_font_white
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    cell.border = border
    
    # Duration column
    cell = ws_gantt.cell(row=1, column=4, value="Дней")
    cell.font = header_font_white
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    cell.border = border
    
    # Week columns - each week gets its own column
    for week in range(1, max_week + 1):
        col = first_week_col + week - 1
        cell = ws_gantt.cell(row=1, column=col, value=f"W{week}")
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border
    
    # Set column widths
    ws_gantt.column_dimensions['A'].width = 10  # ID
    ws_gantt.column_dimensions['B'].width = 45  # Name - wider to fit task names
    ws_gantt.column_dimensions['C'].width = 8   # Start week
    ws_gantt.column_dimensions['D'].width = 6   # Duration
    
    # Week columns - narrow width
    for week in range(1, max_week + 1):
        col = first_week_col + week - 1
        ws_gantt.column_dimensions[get_column_letter(col)].width = 4
    
    # Define parallel indicator fill (light blue for parallel tasks)
    parallel_fill = PatternFill(start_color="9DC3E6", end_color="9DC3E6", fill_type="solid")
    
    # Add data rows with Gantt bars
    row = 2
    for item in gantt_data:
        # Determine style based on item type
        can_parallel = item.get('can_parallel', False)
        
        if item['type'] == 'phase':
            font = phase_font
            fill = phase_fill
            bar_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        elif item['type'] == 'work_package':
            font = wp_font
            fill = wp_fill
            # Use different color for parallel work packages
            if can_parallel:
                bar_fill = PatternFill(start_color="00B050", end_color="00B050", fill_type="solid")
            else:
                bar_fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
        else:
            font = task_font
            fill = None
            # Use different color for parallel tasks
            if can_parallel:
                bar_fill = PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid")
            else:
                bar_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
        
        # ID column
        cell = ws_gantt.cell(row=row, column=1, value=item['id'])
        cell.font = font
        cell.border = border
        if fill:
            cell.fill = fill
        
        # Name column with indentation based on level
        indent = "  " * item['level']
        parallel_marker = " 🔄" if can_parallel else ""
        cell = ws_gantt.cell(row=row, column=2, value=f"{indent}{item['name']}{parallel_marker}")
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        if fill:
            cell.fill = fill
        
        # Start week column (1-based week number)
        start_week = item['start_day'] // DAYS_PER_WEEK + 1
        cell = ws_gantt.cell(row=row, column=3, value=start_week)
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
        if fill:
            cell.fill = fill
        
        # Duration column
        cell = ws_gantt.cell(row=row, column=4, value=item['duration_days'])
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
        if fill:
            cell.fill = fill
        
        # Gantt bar - fill cells for the weeks that overlap with the task
        # Task occupies weeks from (start_day //5 + 1) to ((start_day + duration - 1) //5 + 1)
        task_start_week = item['start_day'] // DAYS_PER_WEEK + 1
        task_end_week = (item['start_day'] + item['duration_days'] - 1) // DAYS_PER_WEEK + 1
        
        for week in range(1, max_week + 1):
            col = first_week_col + week - 1
            cell = ws_gantt.cell(row=row, column=col)
            cell.border = border
            
            # Fill the cell if this week overlaps with the task
            if task_start_week <= week <= task_end_week:
                cell.fill = bar_fill
        
        row += 1
    
    # Add legend at the bottom
    row += 2
    cell = ws_gantt.cell(row=row, column=1, value="Легенда:")
    cell.font = Font(bold=True)
    
    row += 1
    cell = ws_gantt.cell(row=row, column=1, value="■")
    cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    cell.border = border
    cell = ws_gantt.cell(row=row, column=2, value="Фаза")
    
    row += 1
    cell = ws_gantt.cell(row=row, column=1, value="■")
    cell.fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
    cell.border = border
    cell = ws_gantt.cell(row=row, column=2, value="Пакет работ (последовательно)")
    
    row += 1
    cell = ws_gantt.cell(row=row, column=1, value="■")
    cell.fill = PatternFill(start_color="00B050", end_color="00B050", fill_type="solid")
    cell.border = border
    cell = ws_gantt.cell(row=row, column=2, value="Пакет работ (параллельно) 🔄")
    
    row += 1
    cell = ws_gantt.cell(row=row, column=1, value="■")
    cell.fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
    cell.border = border
    cell = ws_gantt.cell(row=row, column=2, value="Задача (последовательно)")
    
    row += 1
    cell = ws_gantt.cell(row=row, column=1, value="■")
    cell.fill = PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid")
    cell.border = border
    cell = ws_gantt.cell(row=row, column=2, value="Задача (параллельно) 🔄")
    
    # Add note about weeks and parallel execution
    row += 2
    cell = ws_gantt.cell(row=row, column=1, value="Примечание: W = рабочая неделя (5 дней). 🔄 = может выполняться параллельно с другими задачами. Параллельные задачи начинаются одновременно.")
    cell.font = Font(italic=True, color="666666")
    ws_gantt.merge_cells(start_row=row, start_column=1, end_row=row, end_column=15)
    
    # Freeze panes: freeze first row and first 4 columns (ID, Name, Start, Duration)
    ws_gantt.freeze_panes = 'E2'
    
    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    logger.info(f"WBS Excel export created with {len(work_items)} work items, {len(all_roles)} roles, and Gantt chart")
    
    return output


def _prepare_gantt_data(wbs_data: dict) -> list:
    """Prepare data for Gantt chart visualization.
    
    Calculates start days based on dependencies and parallel execution capability.
    Tasks marked as can_start_parallel will start at the same time as other parallel tasks.
    
    Args:
        wbs_data: WBS data dictionary
        
    Returns:
        List of items with start_day, duration_days, and dependencies
    """
    items = []
    
    if not wbs_data or 'phases' not in wbs_data:
        return items
    
    # Track end days for each item by ID
    item_end_days = {}
    current_day = 0
    
    for phase in wbs_data.get('phases', []):
        phase_id = phase.get('id', '')
        phase_duration = phase.get('duration', 0)
        
        # Try to get duration from different fields
        if not phase_duration:
            phase_duration = phase.get('duration_days', 0)
        if not phase_duration:
            hours = phase.get('estimated_hours', 0)
            phase_duration = max(1, hours // 8)  # Convert hours to days
        
        # Phase starts at current day
        phase_start = current_day
        
        # Track parallel work packages and their max end day
        parallel_wp_end = phase_start
        sequential_wp_start = phase_start
        
        # First pass: identify parallel groups and calculate start days for work packages
        work_packages_data = []
        for wp in phase.get('work_packages', []):
            wp_id = wp.get('id', '')
            wp_duration = wp.get('duration_days', 0)
            if not wp_duration:
                hours = wp.get('estimated_hours', 0)
                wp_duration = max(1, hours // 8)
            
            wp_dependencies = wp.get('dependencies', [])
            can_parallel = wp.get('can_start_parallel', False)
            
            # Calculate dependency end day
            dep_end_day = 0
            for dep_id in wp_dependencies:
                if dep_id in item_end_days:
                    dep_end_day = max(dep_end_day, item_end_days[dep_id])
            
            # Determine start day based on parallel flag and dependencies
            if can_parallel:
                # Parallel tasks start at the earliest possible time
                # If no dependencies, start at phase start
                # If has dependencies, start after dependencies
                if dep_end_day > 0:
                    wp_start = dep_end_day
                else:
                    wp_start = phase_start
            else:
                # Sequential tasks start after previous sequential task
                # or after dependencies (whichever is later)
                wp_start = max(sequential_wp_start, dep_end_day)
            
            work_packages_data.append({
                'wp': wp,
                'wp_id': wp_id,
                'wp_duration': wp_duration,
                'wp_start': wp_start,
                'can_parallel': can_parallel,
                'dependencies': wp_dependencies
            })
            
            wp_end = wp_start + wp_duration
            
            # Update tracking for next sequential task
            if not can_parallel:
                sequential_wp_start = wp_end
            
            # Track max parallel end for phase duration calculation
            parallel_wp_end = max(parallel_wp_end, wp_end)
            
            item_end_days[wp_id] = wp_end
        
        # Second pass: process tasks within each work package
        for wp_data in work_packages_data:
            wp = wp_data['wp']
            wp_id = wp_data['wp_id']
            wp_start = wp_data['wp_start']
            wp_duration = wp_data['wp_duration']
            can_parallel_wp = wp_data['can_parallel']
            
            # Track parallel tasks and their max end day within this work package
            parallel_task_end = wp_start
            sequential_task_start = wp_start
            
            for task in wp.get('tasks', []):
                task_id = task.get('id', '')
                task_duration = task.get('duration_days', 0)
                if not task_duration:
                    hours = task.get('estimated_hours', 0)
                    task_duration = max(1, hours // 8)
                
                task_dependencies = task.get('dependencies', [])
                task_can_parallel = task.get('can_start_parallel', False)
                
                # Calculate dependency end day
                task_dep_end = 0
                for dep_id in task_dependencies:
                    if dep_id in item_end_days:
                        task_dep_end = max(task_dep_end, item_end_days[dep_id])
                
                # Determine start day based on parallel flag and dependencies
                if task_can_parallel:
                    # Parallel tasks start at the earliest possible time
                    if task_dep_end > 0:
                        task_start = task_dep_end
                    else:
                        task_start = wp_start
                else:
                    # Sequential tasks start after previous sequential task
                    task_start = max(sequential_task_start, task_dep_end)
                
                items.append({
                    'id': task_id,
                    'name': task.get('name', ''),
                    'type': 'task',
                    'level': 2,
                    'start_day': task_start,
                    'duration_days': task_duration,
                    'dependencies': task_dependencies,
                    'can_parallel': task_can_parallel
                })
                
                task_end = task_start + task_duration
                item_end_days[task_id] = task_end
                
                # Update tracking for next sequential task
                if not task_can_parallel:
                    sequential_task_start = task_end
                
                parallel_task_end = max(parallel_task_end, task_end)
            
            # Add work package with calculated start and duration
            items.append({
                'id': wp_id,
                'name': wp.get('name', ''),
                'type': 'work_package',
                'level': 1,
                'start_day': wp_start,
                'duration_days': wp_duration,
                'dependencies': wp_data['dependencies'],
                'can_parallel': can_parallel_wp
            })
        
        # Calculate actual phase duration based on work packages
        actual_phase_end = parallel_wp_end
        phase_duration = actual_phase_end - phase_start
        
        # Add phase
        items.append({
            'id': phase_id,
            'name': phase.get('name', ''),
            'type': 'phase',
            'level': 0,
            'start_day': phase_start,
            'duration_days': phase_duration,
            'dependencies': [],
            'can_parallel': False
        })
        
        item_end_days[phase_id] = actual_phase_end
        current_day = actual_phase_end
    
    # Sort items: by start day, then by type (phases first, then work packages, then tasks)
    type_order = {'phase': 0, 'work_package': 1, 'task': 2}
    items.sort(key=lambda x: (x['start_day'], type_order.get(x['type'], 3), x['id']))
    
    return items


def export_wbs_to_excel(result_data: dict, custom_rates: dict = None) -> tuple:
    """Export WBS to Excel file.
    
    Args:
        result_data: Analysis result data
        custom_rates: Optional dictionary of custom role rates
        
    Returns:
        Tuple of (BytesIO object, filename)
    """
    excel_file = create_wbs_excel(result_data, custom_rates)
    filename = "wbs_export.xlsx"
    
    return excel_file, filename
