# planning/calendar.py
"""
Модуль для создания календарного плана с учетом выходных дней сотрудников
"""

from datetime import datetime, timedelta


def create_calendar_plan(network_parameters, project_data):
    """
    Creates a calendar plan considering employee days off.

    Args:
        network_parameters: Network model parameters
        project_data: Project data with employees and their days off

    Returns:
        Calendar plan with task start/end dates
    """
    network = network_parameters['network']
    employees = project_data['employees']
    critical_path = network_parameters['critical_path']

    # Debug log: Print task count from the network
    print(f"Tasks in network: {len(network)}")

    # Convert day names to numerical values
    days_off_map = {
        employee['id']: [get_weekday_number(day) for day in employee['days_off']]
        for employee in employees
    }

    # Map positions to employees
    position_employee_map = {}
    for employee in employees:
        position = employee['position']
        if position not in position_employee_map:
            position_employee_map[position] = []
        position_employee_map[position].append(employee)

    # Create calendar plan
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    calendar_plan = {
        'tasks': [],
        'critical_path': [task['name'] for task in critical_path],
        'project_duration': calculate_project_duration_with_days_off(network, employees, start_date)
    }

    # Track employee schedules
    employee_schedule = {employee['id']: [] for employee in employees}

    # Optimize employee assignment
    optimized_network = optimize_employee_assignment(network, position_employee_map, employee_schedule, days_off_map,
                                                     start_date)

    # Debug log: Print task count after optimization
    print(f"Tasks after optimization: {len(optimized_network)}")

    # Create calendar tasks
    for task in optimized_network:
        employee_id = task.get('assigned_employee_id')
        employee = next((e for e in employees if e['id'] == employee_id), None)

        if not employee:
            # Find any employee with the right position
            possible_employees = position_employee_map.get(task['position'], [])
            if possible_employees:
                employee = possible_employees[0]
                task['assigned_employee_id'] = employee['id']
            else:
                # Instead of skipping, assign to "Unassigned"
                print(f"No employee found for position: {task['position']}, task: {task['name']}")
                calendar_task = {
                    'id': task['id'],
                    'name': task['name'],
                    'start_date': start_date + timedelta(days=task['early_start']),
                    'end_date': start_date + timedelta(days=task['early_start'] + task['duration']),
                    'duration': task['duration'],
                    'is_critical': task['is_critical'],
                    'reserve': task['reserve'],
                    'employee': "Unassigned",
                    'predecessors': task.get('predecessors', [])
                }
                calendar_plan['tasks'].append(calendar_task)
                continue

        # Calculate task dates considering days off
        task_start_date, task_end_date = calculate_task_dates(
            task,
            employee['id'],
            days_off_map[employee['id']],
            start_date,
            employee_schedule
        )

        # Add task to employee schedule
        employee_schedule[employee['id']].append({
            'task_id': task['id'],
            'start_date': task_start_date,
            'end_date': task_end_date
        })

        # Add task to calendar plan
        calendar_plan['tasks'].append({
            'id': task['id'],
            'name': task['name'],
            'start_date': task_start_date,
            'end_date': task_end_date,
            'duration': task['duration'],
            'is_critical': task['is_critical'],
            'reserve': task['reserve'],
            'employee': employee['name'],
            'employee_email': employee.get('email'),
            'predecessors': task.get('predecessors', [])
        })

    # Debug log: Print final task count
    print(f"Final calendar plan tasks: {len(calendar_plan['tasks'])}")

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
    for task in [t for t in optimized_network if t.get('is_critical', False)]:
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
    for task in [t for t in optimized_network if not t.get('is_critical', False)]:
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