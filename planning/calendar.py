from datetime import datetime, timedelta
import logging

from sqlalchemy import text
from database.models import Task, TaskDependency
from database.operations import session_scope, Session

logger = logging.getLogger(__name__)


def calculate_parent_start_date(parent_task, subtasks, project_start_date):
    """Вычисляет дату начала родительской задачи на основе дат подзадач."""
    # Используем ранний старт из сетевой модели
    return project_start_date + timedelta(days=parent_task.get('early_start', 0))

def calculate_parent_end_date(parent_task, subtasks, project_start_date):
    """Вычисляет дату окончания родительской задачи на основе дат подзадач."""
    # Используем ранний финиш из сетевой модели
    return project_start_date + timedelta(days=parent_task.get('early_finish', 0))


def is_parent_task(task, all_tasks):
    """
    Determines if a task is a parent task based on several criteria:
    1. It has required_employees > 1
    2. There are subtasks with names like "[task name] - [position]"
    3. It has no position specified but has a duration

    Args:
        task: The task to check
        all_tasks: All tasks in the network for checking subtasks

    Returns:
        bool: True if it's a parent task, False otherwise
    """
    # Check if task has multiple required employees
    if task.get('required_employees', 1) > 1:
        return True

    # Check if task has no position but has duration (common for parent tasks)
    if not task.get('position') and task.get('duration'):
        return True

    # Check if there are subtasks with names starting with this task's name
    task_name = task.get('name', '')
    for other_task in all_tasks:
        other_name = other_task.get('name', '')
        # Check if other task is a subtask of this one
        if other_name.startswith(task_name + ' - '):
            return True

    return False


def assign_subtasks_within_parent_constraints(task, parent_start_date, parent_end_date, position_employee_map,
                                              employee_schedule, days_off_map, start_date, is_sequential=False,
                                              sequential_subtasks_dict=None, previous_subtask_end=None):
    """
    Назначает подзадачи так, чтобы они укладывались в сроки родительской задачи.
    Если is_sequential=True, подзадачи будут назначены последовательно, одна за другой.

    Args:
        task: Подзадача для назначения
        parent_start_date: Дата начала родительской задачи
        parent_end_date: Дата окончания родительской задачи
        position_employee_map: Словарь {должность: список сотрудников}
        employee_schedule: Расписание сотрудников
        days_off_map: Словарь выходных дней
        start_date: Дата начала проекта
        is_sequential: Флаг, указывающий, что подзадачи выполняются последовательно
        sequential_subtasks_dict: Словарь {parent_id: [упорядоченный список подзадач]}
        previous_subtask_end: Дата окончания предыдущей подзадачи для последовательного выполнения

    Returns:
        Tuple: (success, task_start_date, task_end_date, assigned_employee_id)
    """
    position = task.get('position', '')
    task_id = task.get('id')
    parent_id = task.get('parent_id')

    # Получаем сотрудников для данной должности
    available_employees = position_employee_map.get(position, [])
    if not available_employees:
        logger.warning(f"No employees found for position {position} for subtask {task['name']}")
        return False, None, None, None

    logger.info(f"Looking for employees with position {position} for task {task['name']}")

    # Проверяем, есть ли ограничения по предыдущим подзадачам при последовательном выполнении
    earliest_possible_start = parent_start_date

    # Если это последовательные подзадачи и есть предыдущая подзадача
    if is_sequential and previous_subtask_end:
        # Начало текущей подзадачи должно быть после окончания предыдущей
        earliest_possible_start = max(earliest_possible_start, previous_subtask_end + timedelta(days=1))
        logger.info(f"Sequential subtask, must start after {previous_subtask_end} (previous subtask)")

    # Перебираем всех сотрудников в поисках того, кто может выполнить задачу в рамках родительской
    for employee in available_employees:
        # Проверяем, когда сотрудник может начать задачу (не раньше earliest_possible_start)
        emp_earliest_start = find_earliest_available_date(
            employee['id'],
            earliest_possible_start,
            employee_schedule,
            days_off_map
        )

        # Проверяем, сможет ли сотрудник закончить до parent_end_date
        task_end_date = calculate_task_end_date_with_constraints(
            emp_earliest_start,
            task['duration'],
            days_off_map.get(employee['id'], []),
            parent_end_date
        )

        # Если task_end_date <= parent_end_date, значит сотрудник может выполнить задачу вовремя
        if task_end_date and task_end_date <= parent_end_date:
            logger.info(f"Found employee {employee['name']} for task {task['name']} to fit parent constraints")
            return True, emp_earliest_start, task_end_date, employee['id']

    # Если не нашли подходящего сотрудника, ищем самого раннего доступного
    logger.warning(f"Could not find employee to fit task {task['name']} within parent constraints")

    # Берем первого доступного сотрудника и назначаем как можно раньше
    if available_employees:
        employee = available_employees[0]
        earliest_start = find_earliest_available_date(
            employee['id'], earliest_possible_start, employee_schedule, days_off_map
        )
        task_end_date = calculate_task_end_date(
            earliest_start, task['duration'], days_off_map.get(employee['id'], [])
        )

        logger.info(
            f"Using employee {employee['name']} for task {task['name']} even though it exceeds parent constraints")
        return False, earliest_start, task_end_date, employee['id']

    return False, None, None, None


def check_task_dependencies_complete(task_id, task_dependencies, task_completion_dates, current_date):
    """
    Checks if all dependencies for a task are complete by the current date.

    Args:
        task_id: ID of the task to check
        task_dependencies: Dictionary mapping task IDs to lists of predecessor IDs
        task_completion_dates: Dictionary mapping task IDs to their completion dates
        current_date: The current planning date

    Returns:
        Boolean: True if all dependencies are satisfied, False otherwise
    """
    # If task has no dependencies, it can start
    if task_id not in task_dependencies:
        return True

    # Check each predecessor
    for pred_id in task_dependencies.get(task_id, []):
        # If predecessor isn't complete yet, task can't start
        if pred_id not in task_completion_dates:
            return False

        # If predecessor completes after current_date, task can't start
        pred_end_date = task_completion_dates[pred_id]
        if pred_end_date >= current_date:
            return False

    # All dependencies are satisfied
    return True


def enforce_critical_path_order(calendar_plan, critical_path_names, start_date):
    """
    Enforces the correct order of tasks in the critical path.

    Args:
        calendar_plan: The calendar plan with tasks
        critical_path_names: List of task names in the critical path, in order
        start_date: Project start date

    Returns:
        Updated calendar plan
    """
    try:
        # Create a mapping of task names to task objects
        tasks_by_name = {}
        for task in calendar_plan['tasks']:
            if task['name'] not in tasks_by_name:
                tasks_by_name[task['name']] = task

        # Process critical path tasks in order
        current_date = start_date
        for name in critical_path_names:
            if name in tasks_by_name:
                task = tasks_by_name[name]

                # If task is a parent task with sequential subtasks,
                # just ensure it starts no earlier than current_date
                if task.get('is_parent', False):
                    if task['start_date'] < current_date:
                        # Calculate shift needed
                        shift = (current_date - task['start_date']).days

                        # Move parent task
                        task['start_date'] = current_date
                        task['end_date'] = task['end_date'] + timedelta(days=shift)

                        # Move all its subtasks by the same shift
                        for subtask in calendar_plan['tasks']:
                            if subtask.get('parent_task_id') == task['id']:
                                subtask['start_date'] += timedelta(days=shift)
                                subtask['end_date'] += timedelta(days=shift)

                    # Update current_date to after this parent task
                    current_date = task['end_date'] + timedelta(days=1)
                else:
                    # Regular task - ensure it starts on or after current_date
                    if task['start_date'] < current_date:
                        duration = (task['end_date'] - task['start_date']).days
                        task['start_date'] = current_date
                        task['end_date'] = current_date + timedelta(days=duration)

                    # Update current_date to after this task
                    current_date = task['end_date'] + timedelta(days=1)
        return calendar_plan
    except Exception as e:
        logger.error(f"Error in enforce_critical_path_order: {str(e)}")
        return calendar_plan  # Return unchanged


def fix_parent_task_dates(calendar_plan):
    """
    Fixes parent task dates to properly encapsulate their subtasks.

    Args:
        calendar_plan: The calendar plan with tasks

    Returns:
        Updated calendar plan
    """
    try:
        # Group tasks by parent_id
        tasks_by_parent = {}
        for task in calendar_plan['tasks']:
            parent_id = task.get('parent_task_id') or task.get('parent_id')
            if parent_id:
                if parent_id not in tasks_by_parent:
                    tasks_by_parent[parent_id] = []
                tasks_by_parent[parent_id].append(task)

        # Process each parent task
        for task in calendar_plan['tasks']:
            if task.get('is_parent', False) and task['id'] in tasks_by_parent:
                subtasks = tasks_by_parent[task['id']]
                if subtasks:
                    # Find earliest start and latest end date among subtasks
                    earliest_start = min(subtask['start_date'] for subtask in subtasks)
                    latest_end = max(subtask['end_date'] for subtask in subtasks)

                    # Update parent task dates
                    task['start_date'] = earliest_start
                    task['end_date'] = latest_end
                    task['duration'] = (latest_end - earliest_start).days + 1

        return calendar_plan
    except Exception as e:
        logger.error(f"Error in fix_parent_task_dates: {str(e)}")
        return calendar_plan  # Return unchanged


def get_sequential_parent_ids(project_id):
    """
    Get IDs of parent tasks with sequential_subtasks flag set to True.
    This function is separated to isolate database operations.
    """
    sequential_parent_ids = []
    try:
        # Use a new session specifically for this query
        session = Session()
        try:
            # Execute a simple query that doesn't require relationship loading
            result = session.execute(
                "SELECT id FROM tasks WHERE project_id = :pid AND sequential_subtasks = TRUE",
                {"pid": project_id}
            )
            sequential_parent_ids = [row[0] for row in result]
            logger.info(f"Found {len(sequential_parent_ids)} sequential parent task IDs")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting sequential parent IDs: {str(e)}")

    return sequential_parent_ids


def process_sequential_subtasks(calendar_plan, start_date):
    """
    Ensures sequential subtasks are properly scheduled one after another.
    """
    # COMPLETELY REBUILD THE FUNCTION TO AVOID SESSION ISSUES

    # Instead of looking up sequential tasks from the database,
    # let's identify them directly from the calendar_plan data
    sequential_parent_ids = []

    # Try to get the sequential parent ids from the database in a safe way
    session = None
    try:
        session = Session()
        # Use simple query avoiding ORM
        query = "SELECT id FROM tasks WHERE project_id = :pid AND sequential_subtasks = true"
        result = session.execute(query, {"pid": calendar_plan.get('project_id')})
        sequential_parent_ids = [row[0] for row in result]
        logger.info(f"Retrieved {len(sequential_parent_ids)} sequential parent IDs: {sequential_parent_ids}")
    except Exception as e:
        logger.error(f"Error getting sequential parent IDs: {str(e)}")
        # Fall back to empty list if query fails
        sequential_parent_ids = []
    finally:
        # Make absolutely sure the session is closed
        if session:
            session.close()

    # Group tasks by parent
    tasks_by_parent = {}
    for task in calendar_plan['tasks']:
        parent_id = task.get('parent_task_id') or task.get('parent_id')
        if parent_id is not None:  # Use explicit None check
            if parent_id not in tasks_by_parent:
                tasks_by_parent[parent_id] = []
            tasks_by_parent[parent_id].append(task)

    # Process each parent ID that we found to be sequential
    for parent_id in sequential_parent_ids:
        if parent_id in tasks_by_parent:
            subtasks = tasks_by_parent[parent_id]

            # Find parent task in calendar_plan
            parent_task = None
            for task in calendar_plan['tasks']:
                if task.get('id') == parent_id:
                    parent_task = task
                    break

            if parent_task and subtasks:
                logger.info(
                    f"Processing sequential subtasks for parent {parent_id}: {parent_task.get('name', 'Unknown')}")

                # Sort subtasks by name for consistent ordering
                subtasks.sort(key=lambda t: t.get('name', ''))

                # Process subtasks in order
                current_date = parent_task.get('start_date')

                # The rest of your sequential subtask processing code...
                for i, subtask in enumerate(subtasks):
                    # Get employee days off
                    employee_name = subtask.get('employee')
                    employee_days_off = []

                    # Find employee days off
                    if employee_name:
                        for emp in calendar_plan.get('employees', []):
                            if emp.get('name') == employee_name:
                                employee_days_off = [get_weekday_number(day) for day in emp.get('days_off', [])]
                                break

                    # Calculate appropriate start date
                    subtask_start = current_date
                    if employee_days_off:
                        # Skip days off
                        while subtask_start.weekday() in employee_days_off:
                            subtask_start += timedelta(days=1)

                    # Calculate end date based on duration
                    duration = subtask.get('duration', 0)
                    working_days = 0
                    subtask_end = subtask_start

                    while working_days < duration:
                        if subtask_end.weekday() not in employee_days_off:
                            working_days += 1

                        if working_days < duration:
                            subtask_end += timedelta(days=1)

                    # Update subtask dates
                    subtask['start_date'] = subtask_start
                    subtask['end_date'] = subtask_end

                    # Update current_date for next subtask
                    current_date = subtask_end + timedelta(days=1)

                # Update parent task to match subtasks
                if subtasks:
                    earliest_start = min(s.get('start_date', start_date) for s in subtasks)
                    latest_end = max(s.get('end_date', start_date) for s in subtasks)

                    parent_task['start_date'] = earliest_start
                    parent_task['end_date'] = latest_end

                    if earliest_start and latest_end:
                        parent_task['duration'] = (latest_end - earliest_start).days + 1

    return calendar_plan


def create_calendar_plan(network_parameters, project_data, start_date=None):
    """
    Создает календарный план, используя структуру сетевой модели напрямую.
    """
    if start_date is None:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    network = network_parameters['network']
    employees = project_data['employees']
    critical_path = network_parameters['critical_path']
    project_id = project_data['id']

    # Simplified calendar plan structure
    calendar_plan = {
        'tasks': [],
        'critical_path': [task['name'] for task in critical_path],
        'project_duration': 0,
        'employees': employees,
        'project_id': project_id
    }

    logger.info("=== Начало создания календарного плана ===")
    logger.info(f"Количество задач в сети: {len(network)}")
    logger.info(f"Количество сотрудников: {len(employees)}")
    logger.info(f"Дата начала проекта: {start_date.strftime('%d.%m.%Y')}")
    logger.info(f"Критический путь: {calendar_plan['critical_path']}")

    # Setup employee mappings
    employee_by_id = {emp['id']: emp for emp in employees}
    position_to_employees = {}
    for emp in employees:
        position = emp['position']
        if position not in position_to_employees:
            position_to_employees[position] = []
        position_to_employees[position].append(emp)

    # Map days off for each employee
    days_off_map = {}
    for emp in employees:
        days_off_map[emp['id']] = [get_weekday_number(day) for day in emp.get('days_off', [])]

    try:
        # Create a mapping of task ID to task for quick lookups
        task_by_id = {task['id']: task for task in network}

        # Create a mapping of task IDs to their dependent tasks
        # This is what the network model already has - each task lists its predecessors
        task_predecessors = {}
        for task in network:
            task_id = task['id']
            predecessors = task.get('predecessors', [])
            task_predecessors[task_id] = predecessors

        # Track completion dates for dependency calculations
        task_completion_dates = {}

        # Employee tracking
        employee_assignments = {}
        employee_schedule = {}

        # Create a topological sort ordering based on dependencies
        # This ensures we process tasks in dependency order
        processed_tasks = set()
        task_order = []

        def process_dependencies(task_id):
            """Process a task after its dependencies"""
            if task_id in processed_tasks:
                return

            # Process all predecessors first
            for pred_id in task_predecessors.get(task_id, []):
                process_dependencies(pred_id)

            processed_tasks.add(task_id)
            task_order.append(task_id)

        # Create topological ordering for all tasks
        for task in network:
            process_dependencies(task['id'])

        # Process tasks in dependency order
        for task_id in task_order:
            task = task_by_id.get(task_id)
            if not task:
                continue

            # Skip parent tasks
            if task.get('is_parent', False) or task.get('required_employees', 1) > 1:
                logger.info(f"Skipping parent task: {task['name']}")
                continue

            # Get task attributes
            position = task.get('position', '')
            duration = task.get('duration', 0)

            # Calculate earliest start date based on dependencies
            earliest_start = start_date
            for pred_id in task_predecessors.get(task_id, []):
                if pred_id in task_completion_dates:
                    pred_end = task_completion_dates[pred_id]
                    new_start = pred_end + timedelta(days=1)
                    if new_start > earliest_start:
                        earliest_start = new_start
                        logger.info(
                            f"Task {task['name']} depends on task {task_by_id.get(pred_id, {}).get('name', '')}, starting at {earliest_start.strftime('%d.%m.%Y')}")

            # Find an employee for this task
            available_employees = position_to_employees.get(position, [])
            if not available_employees:
                logger.warning(f"No employees found for position: {position}, task: {task['name']}")
                employee = None
            else:
                # Sort by workload
                sorted_employees = sorted(
                    available_employees,
                    key=lambda e: len(employee_assignments.get(e['id'], []))
                )
                employee = sorted_employees[0]

            # Calculate dates
            if employee:
                # Account for employee's days off
                emp_days_off = days_off_map.get(employee['id'], [])

                # Skip days off for start date
                current_date = earliest_start
                while current_date.weekday() in emp_days_off:
                    current_date += timedelta(days=1)

                # Calculate end date accounting for days off
                working_days = 0
                end_date = current_date

                while working_days < duration:
                    if end_date.weekday() not in emp_days_off:
                        working_days += 1

                    if working_days < duration:
                        end_date += timedelta(days=1)

                # Add to employee schedule
                if employee['id'] not in employee_assignments:
                    employee_assignments[employee['id']] = []
                    employee_schedule[employee['id']] = []

                employee_assignments[employee['id']].append(task_id)
                employee_schedule[employee['id']].append({
                    'task_id': task_id,
                    'start_date': current_date,
                    'end_date': end_date
                })

                # Add task to calendar plan
                task_entry = {
                    'id': task_id,
                    'name': task['name'],
                    'start_date': current_date,
                    'end_date': end_date,
                    'duration': duration,
                    'is_critical': task.get('is_critical', False),
                    'reserve': task.get('reserve', 0),
                    'employee': employee['name'],
                    'employee_email': employee.get('email', ''),
                    'position': position
                }

                calendar_plan['tasks'].append(task_entry)

                # Record completion date for dependency management
                task_completion_dates[task_id] = end_date

                logger.info(
                    f"Scheduled task {task['name']} for {employee['name']} from {current_date.strftime('%d.%m.%Y')} to {end_date.strftime('%d.%m.%Y')}")
            else:
                # No employee available, schedule without assignment
                current_date = earliest_start
                end_date = current_date + timedelta(days=duration - 1)

                task_entry = {
                    'id': task_id,
                    'name': task['name'],
                    'start_date': current_date,
                    'end_date': end_date,
                    'duration': duration,
                    'is_critical': task.get('is_critical', False),
                    'reserve': task.get('reserve', 0),
                    'employee': 'Не назначен',
                    'position': position
                }

                calendar_plan['tasks'].append(task_entry)

                # Record completion date for dependency management
                task_completion_dates[task_id] = end_date

                logger.info(
                    f"Scheduled task {task['name']} with no employee from {current_date.strftime('%d.%m.%Y')} to {end_date.strftime('%d.%m.%Y')}")

        # Calculate project duration
        if calendar_plan['tasks']:
            latest_end_date = max(task['end_date'] for task in calendar_plan['tasks'])
            calendar_plan['project_duration'] = (latest_end_date - start_date).days + 1
        else:
            calendar_plan['project_duration'] = 0

        # Log summary
        logger.info("\n=== Итоги создания календарного плана ===")
        logger.info(f"Создано задач: {len(calendar_plan['tasks'])}")
        logger.info(f"Критический путь: {', '.join(calendar_plan['critical_path'])}")
        logger.info(f"Длительность проекта: {calendar_plan['project_duration']} дней")

        # Log employee workload
        logger.info("\n=== Распределение нагрузки между сотрудниками ===")
        for emp_id, tasks in employee_assignments.items():
            if emp_id in employee_by_id:
                emp = employee_by_id[emp_id]
                total_days = sum(task_by_id.get(task_id, {}).get('duration', 0) for task_id in tasks)
                logger.info(f"{emp['name']} ({emp['position']}): {total_days} дней ({len(tasks)} задач)")

        return calendar_plan

    except Exception as e:
        logger.error(f"Error creating calendar plan: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())  # Print full traceback
        # Return minimal valid plan
        return calendar_plan

def optimize_employee_assignment(network, position_employee_map, employee_schedule, days_off_map, start_date):
    """
    Optimizes employee assignment to tasks to minimize project time and balance workload.

    Args:
        network: Network model
        position_employee_map: Dictionary mapping positions to lists of employees
        employee_schedule: Current employee schedules
        days_off_map: Dictionary mapping employee IDs to their days off
        start_date: Project start date

    Returns:
        Optimized network model with assigned employees
    """
    # Copy network for working with it
    optimized_network = network.copy()

    # Print available positions and employee counts for debugging
    print("Available positions and employees:")
    for position, employees in position_employee_map.items():
        print(f"  {position}: {len(employees)} employees")

    # Create a flexible position mapping to handle similar position names
    flexible_position_map = {}
    for position in position_employee_map.keys():
        # Create variations of position name in lowercase for fuzzy matching
        position_lower = position.lower()
        flexible_position_map[position_lower] = position

        # Add variations without spaces, with underscores, etc.
        position_normalized = position_lower.replace(" ", "")
        flexible_position_map[position_normalized] = position

        # Add key components of position names for matching
        if "технический" in position_lower:
            if "старший" in position_lower:
                flexible_position_map["старший технический специалист"] = position
                flexible_position_map["старший тех. специалист"] = position
            else:
                flexible_position_map["технический специалист"] = position
                flexible_position_map["тех. специалист"] = position

        if "специалист" in position_lower:
            if "старший" in position_lower:
                flexible_position_map["старший специалист"] = position
            elif "младший" in position_lower:
                flexible_position_map["младший специалист"] = position
            else:
                flexible_position_map["специалист"] = position

        if "руководитель" in position_lower:
            if "контент" in position_lower:
                flexible_position_map["руководитель контента"] = position
            elif "настройк" in position_lower:
                flexible_position_map["руководитель настройки"] = position
                flexible_position_map["руководитель сектора настройки"] = position
            else:
                flexible_position_map["руководитель"] = position

        if "менеджер" in position_lower:
            flexible_position_map["менеджер"] = position
            flexible_position_map["проектный менеджер"] = position

    # Track workload for each employee (total assigned task duration)
    employee_workload = {}
    for position, emps in position_employee_map.items():
        for emp in emps:
            employee_workload[emp['id']] = 0

    # Find employees for each position in tasks, with flexible matching
    task_position_map = {}
    for task in optimized_network:
        position = task['position'].lower()
        if position in flexible_position_map:
            matched_position = flexible_position_map[position]
            task_position_map[task['id']] = matched_position
        else:
            # Try to find a partial match
            best_match = None
            for pos_key, pos_value in flexible_position_map.items():
                if pos_key in position or position in pos_key:
                    best_match = pos_value
                    break

            if best_match:
                task_position_map[task['id']] = best_match
                print(f"Flexible position match: {task['position']} -> {best_match}")
            else:
                print(f"No position match found for: {task['position']}")
                # Use the original position and hope for the best
                task_position_map[task['id']] = task['position']

    # Sort tasks by priority (critical tasks first, then by early start)
    optimized_network.sort(key=lambda x: (not x['is_critical'], x['early_start']))

    # First pass: assign critical tasks
    for task in [t for t in optimized_network if t.get('is_critical', False) and not t.get('is_parent', False)]:
        # Get the matched position
        matched_position = task_position_map.get(task['id'], task['position'])

        # Get employees for this position
        available_employees = position_employee_map.get(matched_position, [])

        if not available_employees:
            print(f"No employees found for position: {matched_position}, task: {task['name']}")
            continue

        # Filter employees by availability at this time
        available_employees = [e for e in available_employees if is_employee_available(
            e['id'],
            task.get('early_start', 0),
            task.get('early_start', 0) + task.get('duration', 0),
            employee_schedule,
            start_date
        )]

        if available_employees:
            # Sort by workload
            available_employees.sort(key=lambda e: employee_workload[e['id']])

            # Assign task
            best_employee = available_employees[0]
            task['assigned_employee_id'] = best_employee['id']
            task['employee'] = best_employee['name']
            task['employee_email'] = best_employee.get('email', '')

            # Update workload
            employee_workload[best_employee['id']] += task['duration']

            # Update schedule
            add_to_employee_schedule(
                employee_schedule,
                best_employee['id'],
                task['id'],
                task.get('early_start', 0),
                task.get('duration', 0),
                days_off_map.get(best_employee['id'], []),
                start_date
            )

            print(f"Assigned critical task '{task['name']}' to {best_employee['name']}")
        else:
            print(f"No available employees for critical task: {task['name']}")

    # Second pass: assign non-critical tasks
    for task in [t for t in optimized_network if not t.get('is_critical', False) and not t.get('is_parent', False)]:
        if 'assigned_employee_id' in task:
            continue  # Skip if already assigned

        # Get the matched position
        matched_position = task_position_map.get(task['id'], task['position'])

        # Get employees for this position
        available_employees = position_employee_map.get(matched_position, [])

        if not available_employees:
            print(f"No employees found for position: {matched_position}, task: {task['name']}")
            continue

        # Find best employee based on availability and workload
        best_employee = None
        earliest_finish = None

        for employee in available_employees:
            # Calculate earliest start for this employee
            earliest_start = find_earliest_start(
                employee['id'],
                task.get('early_start', 0),
                employee_schedule,
                days_off_map.get(employee['id'], []),
                start_date
            )

            # Calculate finish date
            finish_date = calculate_finish_date(
                earliest_start,
                task['duration'],
                days_off_map.get(employee['id'], [])
            )

            # Choose earliest finish or lowest workload if tied
            if earliest_finish is None or finish_date < earliest_finish:
                earliest_finish = finish_date
                best_employee = employee
            elif finish_date == earliest_finish and employee_workload[employee['id']] < employee_workload[
                best_employee['id']]:
                best_employee = employee

        if best_employee:
            # Assign task
            task['assigned_employee_id'] = best_employee['id']
            task['employee'] = best_employee['name']
            task['employee_email'] = best_employee.get('email', '')

            # Update workload
            employee_workload[best_employee['id']] += task['duration']

            # Update schedule
            earliest_start = find_earliest_start(
                best_employee['id'],
                task.get('early_start', 0),
                employee_schedule,
                days_off_map.get(best_employee['id'], []),
                start_date
            )

            add_to_employee_schedule(
                employee_schedule,
                best_employee['id'],
                task['id'],
                earliest_start,
                task['duration'],
                days_off_map.get(best_employee['id'], []),
                start_date
            )

            print(f"Assigned task '{task['name']}' to {best_employee['name']}")
        else:
            print(f"Could not assign any employee to task: {task['name']}")

    # Print assignment statistics
    assigned_count = sum(1 for task in optimized_network if 'assigned_employee_id' in task)
    print(f"Assigned {assigned_count}/{len(optimized_network)} tasks")

    # Print employee workload distribution
    print("Employee workload distribution:")
    for emp_id, workload in sorted(employee_workload.items(), key=lambda x: x[1], reverse=True):
        employee = next((e for pos in position_employee_map.values() for e in pos if e['id'] == emp_id), None)
        if employee:
            print(f"  {employee['name']} ({employee['position']}): {workload} days")

    return optimized_network


def is_employee_available(employee_id, start_time, end_time, employee_schedule, start_date):
    """
    Checks if an employee is available during the specified time period.

    Args:
        employee_id: Employee ID
        start_time: Task start time (days from project start)
        end_time: Task end time (days from project start)
        employee_schedule: Dictionary of employee schedules
        start_date: Project start date

    Returns:
        True if employee is available, False otherwise
    """
    task_start = start_date + timedelta(days=start_time)
    task_end = start_date + timedelta(days=end_time)

    for scheduled_task in employee_schedule.get(employee_id, []):
        # Check for overlap
        if not (scheduled_task['end_date'] < task_start or scheduled_task['start_date'] > task_end):
            return False

    return True


def find_earliest_start(employee_id, earliest_possible_start, employee_schedule, days_off, start_date):
    """
    Finds the earliest possible start date for an employee.

    Args:
        employee_id: Employee ID
        earliest_possible_start: Earliest possible start time (days from project start)
        employee_schedule: Dictionary of employee schedules
        days_off: Employee's days off
        start_date: Project start date

    Returns:
        Earliest possible start date
    """
    current_date = start_date + timedelta(days=earliest_possible_start)

    # Adjust for days off
    while current_date.weekday() in days_off:
        current_date += timedelta(days=1)

    # Check existing schedule
    for scheduled_task in sorted(employee_schedule.get(employee_id, []), key=lambda x: x['end_date']):
        if scheduled_task['end_date'] >= current_date:
            # Need to start after this task
            current_date = scheduled_task['end_date'] + timedelta(days=1)

            # Adjust for days off again
            while current_date.weekday() in days_off:
                current_date += timedelta(days=1)

    # Return days from project start
    return (current_date - start_date).days


def calculate_finish_date(start_day, duration, days_off):
    """
    Calculates the finish date accounting for days off.

    Args:
        start_day: Start day (days from project start)
        duration: Task duration in working days
        days_off: Employee's days off

    Returns:
        Finish date (days from project start)
    """
    working_days = 0
    current_day = start_day

    while working_days < duration:
        current_weekday = (start_day + (current_day - start_day)) % 7
        if current_weekday not in days_off:
            working_days += 1

        current_day += 1

    return current_day - 1


def add_to_employee_schedule(employee_schedule, employee_id, task_id, start_day, duration, days_off, start_date):
    """
    Adds a task to an employee's schedule.

    Args:
        employee_schedule: Dictionary of employee schedules
        employee_id: Employee ID
        task_id: Task ID
        start_day: Start day (days from project start)
        duration: Task duration in working days
        days_off: Employee's days off
        start_date: Project start date
    """
    task_start = start_date + timedelta(days=start_day)

    # Calculate end date
    working_days = 0
    current_date = task_start

    while working_days < duration:
        if current_date.weekday() not in days_off:
            working_days += 1

        if working_days < duration:
            current_date += timedelta(days=1)

    # Add to schedule
    if employee_id not in employee_schedule:
        employee_schedule[employee_id] = []

    employee_schedule[employee_id].append({
        'task_id': task_id,
        'start_date': task_start,
        'end_date': current_date
    })


def adjust_dates_for_days_off(start_date, duration, days_off):
    """
    Adjusts task start and end dates to account for employee days off.

    Args:
        start_date: Initial start date
        duration: Task duration in working days
        days_off: List of employee's days off (as weekday numbers)

    Returns:
        Tuple of (adjusted_start_date, adjusted_end_date)
    """
    # Adjust start date if it falls on a day off
    current_date = start_date
    while current_date.weekday() in days_off:
        current_date += timedelta(days=1)

    # Calculate end date by adding working days
    working_days = 0
    end_date = current_date

    while working_days < duration:
        end_date += timedelta(days=1)
        if end_date.weekday() not in days_off:
            working_days += 1

    # End date should be the last working day
    if end_date.weekday() in days_off:
        while end_date.weekday() in days_off:
            end_date -= timedelta(days=1)

    return current_date, end_date


def calculate_earliest_start(task, employee_id, days_off, employee_schedule, start_date):
    """
    Calculates the earliest possible start date for a task based on employee availability.

    Args:
        task: Task to schedule
        employee_id: ID of the employee
        days_off: Employee's days off
        employee_schedule: Dictionary of employee schedules
        start_date: Project start date

    Returns:
        Earliest possible start date for the task
    """
    # Earliest possible start date based on task's early start
    earliest_date = start_date + timedelta(days=task.get('early_start', 0))

    # Check employee's current schedule for conflicts
    for scheduled_task in employee_schedule.get(employee_id, []):
        # If this scheduled task ends after our earliest start,
        # we need to start after it ends
        if scheduled_task['end_date'] > earliest_date:
            earliest_date = scheduled_task['end_date'] + timedelta(days=1)

    # Adjust for employee's days off
    while earliest_date.weekday() in days_off:
        earliest_date += timedelta(days=1)

    return earliest_date


def calculate_task_dates(task, employee_id, days_off, start_date, employee_schedule):
    """
    Вычисляет даты начала и окончания задачи с учетом выходных дней и других задач сотрудника.

    Args:
        task: Задача
        employee_id: ID сотрудника
        days_off: Выходные дни сотрудника
        start_date: Дата начала проекта
        employee_schedule: Текущие задачи сотрудника

    Returns:
        Кортеж (дата начала, дата окончания)
    """
    # Вычисляем самую раннюю дату начала задачи
    task_start_date = calculate_earliest_start(task, employee_id, days_off, employee_schedule, start_date)

    # Вычисляем дату окончания задачи
    task_end_date = calculate_task_end_date(task_start_date, task['duration'], days_off)

    return task_start_date, task_end_date


def calculate_task_end_date(start_date, duration, days_off):
    """
    Calculates end date for a task considering days off.

    Args:
        start_date: Task start date
        duration: Task duration in working days
        days_off: Employee's days off

    Returns:
        Task end date
    """
    working_days = 0
    current_date = start_date

    while working_days < duration:
        if current_date.weekday() not in days_off:
            working_days += 1

        if working_days < duration:
            current_date += timedelta(days=1)

    return current_date


def calculate_project_duration_with_days_off(network, employees, start_date):
    """
    Вычисляет общую продолжительность проекта с учетом выходных дней.

    Args:
        network: Сетевая модель
        employees: Список сотрудников
        start_date: Дата начала проекта

    Returns:
        Общая продолжительность проекта в календарных днях
    """
    if not network:
        return 0

    # Находим последнюю задачу проекта по раннему сроку окончания
    last_task = max(network, key=lambda x: x['early_finish'])
    project_duration_working_days = last_task['early_finish']

    # Преобразуем в календарные дни с учетом выходных
    # Предполагаем, что у всех сотрудников одинаковые выходные (упрощение)
    # В реальности нужно учитывать распределение задач между сотрудниками
    if employees:
        # Берем первого сотрудника для примера
        days_off = [get_weekday_number(day) for day in employees[0]['days_off']]

        # Считаем календарные дни
        working_days = 0
        current_date = start_date
        calendar_days = 0

        while working_days < project_duration_working_days:
            if current_date.weekday() not in days_off:
                working_days += 1

            current_date += timedelta(days=1)
            calendar_days += 1

        return calendar_days

    # Если нет сотрудников, возвращаем длительность в рабочих днях
    return project_duration_working_days


def get_weekday_number(day_name):
    """
    Преобразует название дня недели в числовой формат.

    Args:
        day_name: Название дня недели

    Returns:
        Числовой формат дня недели (0-6, где 0 - понедельник)
    """
    days = {
        'понедельник': 0,
        'вторник': 1,
        'среда': 2,
        'четверг': 3,
        'пятница': 4,
        'суббота': 5,
        'воскресенье': 6
    }

    return days.get(day_name.lower(), -1)


def adjust_date_for_days_off(date, days_off):
    """
    Корректирует дату с учетом выходных дней.

    Args:
        date: Дата начала задачи
        days_off: Список выходных дней

    Returns:
        Скорректированная дата начала задачи
    """
    while date.weekday() in days_off:
        date += timedelta(days=1)

    return date


def ensure_tasks_included(network_parameters, calendar_plan, start_date):
    """
    Проверяет, что все задачи из сетевой модели включены в календарный план.
    """
    network = network_parameters['network']
    critical_path = network_parameters['critical_path']

    # Создаем словарь имен задач, которые уже есть в плане
    existing_names = {task.get('name', '') for task in calendar_plan['tasks']}
    logger.info(f"Существующие задачи в плане: {existing_names}")

    tasks_added = 0

    # Определяем список критических задач
    critical_tasks = set()
    if isinstance(calendar_plan['critical_path'], list):
        critical_tasks = set(calendar_plan['critical_path'])

    # Добавляем отсутствующие задачи, в первую очередь критические
    for task in network:
        # Если задача с таким именем уже есть, пропускаем её
        if task['name'] in existing_names:
            continue

        # Проверяем, является ли задача критической
        is_critical = task['name'] in critical_tasks or task.get('is_critical', False)

        # Вычисляем даты начала и окончания
        task_start = start_date + timedelta(days=task.get('early_start', 0))
        task_end = start_date + timedelta(days=task.get('early_finish', 0))

        # Добавляем задачу в календарный план
        calendar_plan['tasks'].append({
            'id': task.get('id'),
            'name': task.get('name'),
            'start_date': task_start,
            'end_date': task_end,
            'duration': task.get('duration', 0),
            'is_critical': is_critical,
            'reserve': task.get('reserve', 0),
            'position': task.get('position', ''),
            'employee': 'Не назначен'
        })

        tasks_added += 1
        logger.info(f"Добавлена {'критическая ' if is_critical else ''}задача {task.get('name')} в календарный план")

    logger.info(f"Всего добавлено задач: {tasks_added}")
    return calendar_plan

def find_earliest_available_date(employee_id, after_date, employee_schedule, days_off_map):
    """
    Находит самую раннюю дату, когда сотрудник доступен после указанной даты.

    Args:
        employee_id: ID сотрудника
        after_date: Дата, после которой искать доступность
        employee_schedule: Расписание сотрудников
        days_off_map: Словарь выходных дней

    Returns:
        datetime: Самая ранняя доступная дата
    """
    current_date = after_date
    days_off = days_off_map.get(employee_id, [])

    # Пропускаем выходные дни
    while current_date.weekday() in days_off:
        current_date += timedelta(days=1)

    # Проверяем существующие задачи сотрудника
    for task in sorted(employee_schedule.get(employee_id, []), key=lambda x: x['end_date']):
        # Если текущая дата попадает в интервал задачи, передвигаем на день после окончания
        if task['start_date'] <= current_date <= task['end_date']:
            current_date = task['end_date'] + timedelta(days=1)
            # И снова пропускаем выходные
            while current_date.weekday() in days_off:
                current_date += timedelta(days=1)

    return current_date


def calculate_task_end_date_with_constraints(start_date, duration, days_off, max_end_date):
    """
    Вычисляет дату окончания задачи с учетом ограничения по максимальной дате окончания.

    Args:
        start_date: Дата начала задачи
        duration: Длительность задачи в рабочих днях
        days_off: Список выходных дней сотрудника
        max_end_date: Максимальная дата окончания

    Returns:
        datetime: Дата окончания задачи или None, если невозможно уложиться в ограничение
    """
    working_days = 0
    current_date = start_date

    while working_days < duration:
        if current_date.weekday() not in days_off:
            working_days += 1

        if working_days < duration:
            current_date += timedelta(days=1)

        # Проверяем, не превысили ли максимальную дату
        if current_date > max_end_date:
            return None

    return current_date

