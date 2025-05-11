# planning/calendar.py
"""
Модуль для создания календарного плана с учетом выходных дней сотрудников
"""

from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)


def calculate_parent_start_date(parent_task, subtasks, project_start_date):
    """Вычисляет дату начала родительской задачи на основе дат подзадач."""
    # Используем ранний старт из сетевой модели
    return project_start_date + timedelta(days=parent_task.get('early_start', 0))

def calculate_parent_end_date(parent_task, subtasks, project_start_date):
    """Вычисляет дату окончания родительской задачи на основе дат подзадач."""
    # Используем ранний финиш из сетевой модели
    return project_start_date + timedelta(days=parent_task.get('early_finish', 0))


# planning/calendar.py

from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def create_calendar_plan(network_parameters, project_data, start_date=None):
    """
    Создает календарный план с учетом выходных дней сотрудников.
    """
    if start_date is None:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    network = network_parameters['network']
    employees = project_data['employees']
    critical_path = network_parameters['critical_path']

    # Логируем основную информацию
    logger.info("=== Начало создания календарного плана ===")
    logger.info(f"Количество задач в сети: {len(network)}")
    logger.info(f"Количество сотрудников: {len(employees)}")
    logger.info(f"Дата начала проекта: {start_date.strftime('%d.%m.%Y')}")

    # Преобразуем названия дней недели в числовые значения
    days_off_map = {
        employee['id']: [get_weekday_number(day) for day in employee['days_off']]
        for employee in employees
    }

    # Находим связи сотрудник-должность
    position_employee_map = {}
    for employee in employees:
        position = employee['position']
        if position not in position_employee_map:
            position_employee_map[position] = []
        position_employee_map[position].append(employee)

    # Логи маппинга должностей
    logger.info("\n=== Маппинг должностей ===")
    for position, emps in position_employee_map.items():
        logger.info(f"Должность '{position}': {len(emps)} сотрудников")
        for emp in emps:
            logger.info(f"  - {emp['name']}")

    # Создаем календарный план
    calendar_plan = {
        'tasks': [],
        'critical_path': [task['name'] for task in critical_path],
        'project_duration': calculate_project_duration_with_days_off(network, employees, start_date)
    }

    # Словарь для отслеживания загруженности сотрудников
    employee_schedule = {employee['id']: [] for employee in employees}

    # Создаем счетчик нагрузки для каждого сотрудника
    employee_workload = {employee['id']: 0 for employee in employees}

    # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: используем функцию оптимизации
    optimized_network = optimize_employee_assignment(network, position_employee_map, employee_schedule, days_off_map,
                                                     start_date)

    # Создаем словарь для быстрого доступа к задачам
    network_by_id = {task['id']: task for task in optimized_network}

    # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: сначала обрабатываем критический путь, потом остальные задачи
    critical_task_ids = [task['id'] for task in critical_path]

    # Сортируем все задачи: сначала критические, затем остальные
    all_tasks = sorted(optimized_network, key=lambda t: t['early_start'])
    critical_tasks = [t for t in all_tasks if t['id'] in critical_task_ids]
    non_critical_tasks = [t for t in all_tasks if t['id'] not in critical_task_ids]

    # 1. Сначала обрабатываем критические задачи
    current_date = start_date
    for task in critical_tasks:
        position = task.get('position', '')

        # Если у задачи есть назначенный сотрудник из оптимизации
        if 'assigned_employee_id' in task:
            employee_id = task['assigned_employee_id']
            employee = next((e for e in employees if e['id'] == employee_id), None)

            if employee:
                # Вычисляем даты с учетом доступности сотрудника
                task_start_date, task_end_date = calculate_task_dates(
                    task, employee_id, days_off_map.get(employee_id, []),
                    current_date, employee_schedule
                )

                # Обновляем текущую дату для следующей критической задачи
                current_date = task_end_date + timedelta(days=1)

                # Добавляем в расписание сотрудника
                employee_schedule[employee_id].append({
                    'task_id': task['id'],
                    'start_date': task_start_date,
                    'end_date': task_end_date
                })

                # Обновляем нагрузку
                employee_workload[employee_id] += task['duration']

                # Добавляем задачу в план
                calendar_plan['tasks'].append({
                    'id': task['id'],
                    'name': task['name'],
                    'start_date': task_start_date,
                    'end_date': task_end_date,
                    'duration': task['duration'],
                    'is_critical': True,
                    'reserve': 0,
                    'employee': employee['name'],
                    'employee_email': employee.get('email', ''),
                    'position': position
                })
        else:
            # Если нет назначенного сотрудника, добавляем задачу без исполнителя
            task_start_date = current_date
            task_end_date = task_start_date + timedelta(days=task['duration'] - 1)
            current_date = task_end_date + timedelta(days=1)

            calendar_plan['tasks'].append({
                'id': task['id'],
                'name': task['name'],
                'start_date': task_start_date,
                'end_date': task_end_date,
                'duration': task['duration'],
                'is_critical': True,
                'reserve': 0,
                'employee': 'Не назначен',
                'position': position
            })

    # 2. Затем обрабатываем остальные задачи
    for task in non_critical_tasks:
        position = task.get('position', '')
        required_employees = task.get('required_employees', 1)

        # Обрабатываем задачи с одним исполнителем
        if required_employees == 1:
            # Если есть назначенный сотрудник из оптимизации
            if 'assigned_employee_id' in task:
                employee_id = task['assigned_employee_id']
                employee = next((e for e in employees if e['id'] == employee_id), None)

                if employee:
                    # Вычисляем даты с учетом доступности сотрудника и предшественников
                    earliest_start = start_date

                    # Учитываем предшественников
                    for pred_id in task.get('predecessors', []):
                        pred_task = network_by_id.get(pred_id)
                        if pred_task and 'assigned_employee_id' in pred_task:
                            for scheduled in employee_schedule.get(employee_id, []):
                                if scheduled['task_id'] == pred_id:
                                    if scheduled['end_date'] > earliest_start:
                                        earliest_start = scheduled['end_date'] + timedelta(days=1)

                    task_start_date, task_end_date = calculate_task_dates(
                        task, employee_id, days_off_map.get(employee_id, []),
                        earliest_start, employee_schedule
                    )

                    # Добавляем в расписание сотрудника
                    employee_schedule[employee_id].append({
                        'task_id': task['id'],
                        'start_date': task_start_date,
                        'end_date': task_end_date
                    })

                    # Обновляем нагрузку
                    employee_workload[employee_id] += task['duration']

                    # Добавляем задачу в план
                    calendar_plan['tasks'].append({
                        'id': task['id'],
                        'name': task['name'],
                        'start_date': task_start_date,
                        'end_date': task_end_date,
                        'duration': task['duration'],
                        'is_critical': False,
                        'reserve': task.get('reserve', 0),
                        'employee': employee['name'],
                        'employee_email': employee.get('email', ''),
                        'position': position
                    })
            else:
                # Если нет назначенного сотрудника, выбираем наименее загруженного
                available_employees = position_employee_map.get(position, [])
                if available_employees:
                    available_employees = sorted(available_employees, key=lambda e: employee_workload[e['id']])
                    employee = available_employees[0]

                    # Вычисляем даты с учетом доступности
                    task_start_date, task_end_date = calculate_task_dates(
                        task, employee['id'], days_off_map.get(employee['id'], []),
                        start_date, employee_schedule
                    )

                    # Добавляем в расписание
                    employee_schedule[employee['id']].append({
                        'task_id': task['id'],
                        'start_date': task_start_date,
                        'end_date': task_end_date
                    })

                    # Обновляем нагрузку
                    employee_workload[employee['id']] += task['duration']

                    # Добавляем задачу в план
                    calendar_plan['tasks'].append({
                        'id': task['id'],
                        'name': task['name'],
                        'start_date': task_start_date,
                        'end_date': task_end_date,
                        'duration': task['duration'],
                        'is_critical': False,
                        'reserve': task.get('reserve', 0),
                        'employee': employee['name'],
                        'employee_email': employee.get('email', ''),
                        'position': position
                    })

        # Обрабатываем групповые задачи (требуется несколько исполнителей)
        elif required_employees > 1:
            available_employees = position_employee_map.get(position, [])
            if available_employees:
                # Сортируем по нагрузке
                available_employees = sorted(available_employees, key=lambda e: employee_workload[e['id']])

                # Выбираем требуемое количество сотрудников
                selected_employees = available_employees[:required_employees]

                if len(selected_employees) == required_employees:
                    # Создаем задачи для каждого сотрудника
                    for i, employee in enumerate(selected_employees):
                        task_start_date, task_end_date = calculate_task_dates(
                            task, employee['id'], days_off_map.get(employee['id'], []),
                            start_date, employee_schedule
                        )

                        # Добавляем в расписание
                        employee_schedule[employee['id']].append({
                            'task_id': f"{task['id']}_{i}",
                            'start_date': task_start_date,
                            'end_date': task_end_date
                        })

                        # Обновляем нагрузку
                        employee_workload[employee['id']] += task['duration']

                        # Добавляем задачу в план
                        calendar_plan['tasks'].append({
                            'id': f"{task['id']}_{i}",
                            'name': task['name'],
                            'start_date': task_start_date,
                            'end_date': task_end_date,
                            'duration': task['duration'],
                            'is_critical': False,
                            'reserve': task.get('reserve', 0),
                            'employee': employee['name'],
                            'employee_email': employee.get('email', ''),
                            'position': position
                        })

    # Проверяем, все ли задачи включены в план
    critical_task_names = set(calendar_plan['critical_path'])
    existing_tasks = {task.get('name', '') for task in calendar_plan['tasks']}

    # Добавляем недостающие задачи критического пути
    for task in network:
        if task['name'] in critical_task_names and task['name'] not in existing_tasks:
            task_start = start_date + timedelta(days=task.get('early_start', 0))
            task_end = start_date + timedelta(days=task.get('early_finish', 0))

            calendar_plan['tasks'].append({
                'id': task.get('id'),
                'name': task.get('name'),
                'start_date': task_start,
                'end_date': task_end,
                'duration': task.get('duration', 0),
                'is_critical': True,
                'reserve': 0,
                'position': task.get('position', ''),
                'employee': 'Не назначен'
            })

    # Итоги
    logger.info("\n=== Итоги создания календарного плана ===")
    logger.info(f"Создано задач: {len(calendar_plan['tasks'])}")
    logger.info(f"Критический путь: {', '.join(calendar_plan['critical_path'])}")
    logger.info(f"Длительность проекта: {calendar_plan['project_duration']} дней")

    # Выводим нагрузку сотрудников
    logger.info("\n=== Распределение нагрузки между сотрудниками ===")
    for emp_id, workload in sorted(employee_workload.items(), key=lambda x: x[1], reverse=True):
        employee = next((e for e in employees if e['id'] == emp_id), None)
        if employee:
            logger.info(f"{employee['name']} ({employee['position']}): {workload} дней")

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