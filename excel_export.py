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
            'level': 0
        })
        
        for wp in phase.get('work_packages', []):
            # Add work package
            items.append({
                'id': wp.get('id', ''),
                'name': wp.get('name', ''),
                'type': 'work_package',
                'hours': wp.get('estimated_hours', 0),
                'skills': wp.get('skills_required', []),
                'level': 1
            })
            
            # Add tasks
            for task in wp.get('tasks', []):
                items.append({
                    'id': task.get('id', ''),
                    'name': task.get('name', ''),
                    'type': 'task',
                    'hours': task.get('estimated_hours', 0),
                    'skills': task.get('skills_required', []) or wp.get('skills_required', []),
                    'level': 2
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
    headers = ["№ работы", "Название работы"] + all_roles + ["Стоимость (руб)"]
    
    for col, header in enumerate(headers, 1):
        cell = ws_wbs.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
    
    # Set column widths
    ws_wbs.column_dimensions['A'].width = 12  # ID
    ws_wbs.column_dimensions['B'].width = 40  # Name
    
    for i, role in enumerate(all_roles, 3):
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
        
        # Distribute hours among roles
        hours_by_role = distribute_hours_by_role(item['hours'], item['skills'])
        item_cost = 0
        
        # Role hours columns
        for col, role in enumerate(all_roles, 3):
            hours = hours_by_role.get(role, 0)
            cell = ws_wbs.cell(row=row, column=col, value=round(hours, 1) if hours > 0 else "")
            cell.font = font
            cell.border = border
            cell.alignment = Alignment(horizontal='center')
            if fill:
                cell.fill = fill
            
            # Update totals
            role_totals[role] += hours
            item_cost += hours * get_role_rate(role, rates)
        
        # Cost column
        cell = ws_wbs.cell(row=row, column=len(headers), value=round(item_cost, 0))
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal='right')
        cell.number_format = '#,##0'
        if fill:
            cell.fill = fill
        
        total_cost += item_cost
        row += 1
    
    # Add totals row
    row += 1
    
    # Label
    cell = ws_wbs.cell(row=row, column=1, value="ИТОГО")
    cell.font = total_font
    cell.fill = total_fill
    cell.border = border
    
    cell = ws_wbs.cell(row=row, column=2, value="")
    cell.fill = total_fill
    cell.border = border
    
    # Role totals
    for col, role in enumerate(all_roles, 3):
        cell = ws_wbs.cell(row=row, column=col, value=round(role_totals[role], 1))
        cell.font = total_font
        cell.fill = total_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
        cell.number_format = '#,##0.0'
    
    # Total cost
    cell = ws_wbs.cell(row=row, column=len(headers), value=round(total_cost, 0))
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
    row = 2
    all_roles_with_rates = set(all_roles) | set(DEFAULT_ROLE_RATES.keys())
    
    for role in sorted(all_roles_with_rates):
        cell = ws_rates.cell(row=row, column=1, value=role)
        cell.border = border
        
        rate = get_role_rate(role, rates)
        cell = ws_rates.cell(row=row, column=2, value=rate)
        cell.border = border
        cell.alignment = Alignment(horizontal='right')
        cell.number_format = '#,##0'
        
        row += 1
    
    # Add note about editing rates
    row += 2
    cell = ws_rates.cell(row=row, column=1, value="Примечание: Измените ставки на этом листе для пересчета стоимости.")
    cell.font = Font(italic=True, color="666666")
    ws_rates.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    
    # Freeze header row
    ws_rates.freeze_panes = 'A2'
    
    # === Sheet 3: Gantt Chart ===
    ws_gantt = wb.create_sheet(title="Диаграмма Гантта")
    
    # Create Gantt chart data
    gantt_data = _prepare_gantt_data(wbs_data)
    
    # Headers for Gantt
    gantt_headers = ["ID", "Название работы", "Тип", "Начало (день)", "Длительность (дней)", "Зависимости", "Параллельно"]
    for col, header in enumerate(gantt_headers, 1):
        cell = ws_gantt.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
    
    # Set column widths for Gantt
    ws_gantt.column_dimensions['A'].width = 12  # ID
    ws_gantt.column_dimensions['B'].width = 40  # Name
    ws_gantt.column_dimensions['C'].width = 15  # Type
    ws_gantt.column_dimensions['D'].width = 15  # Start day
    ws_gantt.column_dimensions['E'].width = 18  # Duration
    ws_gantt.column_dimensions['F'].width = 20  # Dependencies
    ws_gantt.column_dimensions['G'].width = 15  # Parallel
    
    # Add Gantt data
    row = 2
    for item in gantt_data:
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
        
        # ID
        cell = ws_gantt.cell(row=row, column=1, value=item['id'])
        cell.font = font
        cell.border = border
        if fill:
            cell.fill = fill
        
        # Name with indentation
        indent = "  " * item['level']
        cell = ws_gantt.cell(row=row, column=2, value=f"{indent}{item['name']}")
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        if fill:
            cell.fill = fill
        
        # Type
        type_names = {'phase': 'Фаза', 'work_package': 'Пакет работ', 'task': 'Задача'}
        cell = ws_gantt.cell(row=row, column=3, value=type_names.get(item['type'], item['type']))
        cell.font = font
        cell.border = border
        if fill:
            cell.fill = fill
        
        # Start day
        cell = ws_gantt.cell(row=row, column=4, value=item['start_day'])
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
        if fill:
            cell.fill = fill
        
        # Duration
        cell = ws_gantt.cell(row=row, column=5, value=item['duration_days'])
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
        if fill:
            cell.fill = fill
        
        # Dependencies
        deps_str = ", ".join(item['dependencies']) if item['dependencies'] else "-"
        cell = ws_gantt.cell(row=row, column=6, value=deps_str)
        cell.font = font
        cell.border = border
        if fill:
            cell.fill = fill
        
        # Parallel
        parallel_str = "Да" if item['can_parallel'] else "Нет"
        cell = ws_gantt.cell(row=row, column=7, value=parallel_str)
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
        if fill:
            cell.fill = fill
        
        row += 1
    
    # Add visual Gantt chart representation
    row += 2
    cell = ws_gantt.cell(row=row, column=1, value="Визуализация диаграммы Гантта:")
    cell.font = Font(bold=True, size=12)
    row += 1
    
    # Create visual timeline
    max_day = max((item['start_day'] + item['duration_days'] for item in gantt_data), default=0)
    
    # Add day headers
    header_row = row
    cell = ws_gantt.cell(row=header_row, column=1, value="Работа")
    cell.font = header_font
    cell.border = border
    
    for day in range(1, min(max_day + 1, 51)):  # Limit to 50 days for readability
        col = day + 1
        cell = ws_gantt.cell(row=header_row, column=col, value=day)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = border
        ws_gantt.column_dimensions[get_column_letter(col)].width = 4
    
    # Add bars for each work item
    for item in gantt_data:
        row += 1
        
        # Work item name (truncated)
        name = item['name'][:30] + "..." if len(item['name']) > 30 else item['name']
        cell = ws_gantt.cell(row=row, column=1, value=f"{item['id']} {name}")
        cell.font = task_font
        cell.border = border
        
        # Color based on type
        if item['type'] == 'phase':
            bar_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        elif item['type'] == 'work_package':
            bar_fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
        else:
            bar_fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
        
        # Draw the bar
        for day in range(1, min(max_day + 1, 51)):
            col = day + 1
            cell = ws_gantt.cell(row=row, column=col)
            cell.border = border
            
            if item['start_day'] < day <= item['start_day'] + item['duration_days']:
                cell.fill = bar_fill
    
    # Add legend
    row += 3
    cell = ws_gantt.cell(row=row, column=1, value="Легенда:")
    cell.font = Font(bold=True)
    
    row += 1
    cell = ws_gantt.cell(row=row, column=1, value="■ Фаза")
    cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    
    cell = ws_gantt.cell(row=row, column=2, value="■ Пакет работ")
    cell.fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
    
    cell = ws_gantt.cell(row=row, column=3, value="■ Задача")
    cell.fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
    
    # Freeze header row
    ws_gantt.freeze_panes = 'A2'
    
    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    logger.info(f"WBS Excel export created with {len(work_items)} work items, {len(all_roles)} roles, and Gantt chart")
    
    return output


def _prepare_gantt_data(wbs_data: dict) -> list:
    """Prepare data for Gantt chart visualization.
    
    Calculates start days based on dependencies and duration.
    
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
        
        # Process work packages
        wp_start_in_phase = 0
        for wp in phase.get('work_packages', []):
            wp_id = wp.get('id', '')
            wp_duration = wp.get('duration_days', 0)
            if not wp_duration:
                hours = wp.get('estimated_hours', 0)
                wp_duration = max(1, hours // 8)
            
            # Calculate start based on dependencies
            wp_dependencies = wp.get('dependencies', [])
            can_parallel = wp.get('can_start_parallel', False)
            
            dep_end_day = 0
            for dep_id in wp_dependencies:
                if dep_id in item_end_days:
                    dep_end_day = max(dep_end_day, item_end_days[dep_id])
            
            if can_parallel and dep_end_day == 0:
                wp_start = phase_start + wp_start_in_phase
            else:
                wp_start = max(phase_start + wp_start_in_phase, dep_end_day)
            
            # Process tasks within work package
            task_start_in_wp = 0
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
                
                if task_can_parallel and task_dep_end == 0:
                    task_start = wp_start + task_start_in_wp
                else:
                    task_start = max(wp_start + task_start_in_wp, task_dep_end)
                
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
                
                if not task_can_parallel:
                    task_start_in_wp = task_end - wp_start
                
                wp_start_in_phase = max(wp_start_in_phase, task_end - phase_start)
            
            # Add work package
            items.append({
                'id': wp_id,
                'name': wp.get('name', ''),
                'type': 'work_package',
                'level': 1,
                'start_day': wp_start,
                'duration_days': wp_duration,
                'dependencies': wp_dependencies,
                'can_parallel': can_parallel
            })
            
            wp_end = wp_start + wp_duration
            item_end_days[wp_id] = wp_end
            
            if not can_parallel:
                wp_start_in_phase = wp_end - phase_start
        
        # Add phase
        phase_end = phase_start + phase_duration
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
        
        item_end_days[phase_id] = phase_end
        current_day = phase_end
    
    # Sort items: phases first, then work packages, then tasks
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
