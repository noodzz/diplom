# planning/calendar.py
"""
Модуль для создания календарного плана с учетом выходных дней сотрудников
"""

from datetime import datetime, timedelta


def create_calendar_plan(network_parameters, project_data):
    """
    Создает календарный план с учетом выходных дней сотрудников.

    Args:
        network_parameters: Параметры сетевой модели
        project_data: Данные проекта с сотрудниками и их выходными

    Returns:
        Календарный план с датами начала и окончания задач
    """
    network = network_parameters['network']
    employees = project_data['employees']
    critical_path = network_parameters['critical_path']

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

    # Создаем календарный план
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    calendar_plan = {
        'tasks': [],
        'critical_path': [task['name'] for task in critical_path],
        'project_duration': calculate_project_duration_with_days_off(network, employees, start_date)
    }

    # Словарь для отслеживания загруженности сотрудников
    employee_schedule = {employee['id']: [] for employee in employees}

    # Оптимизируем назначение сотрудников на задачи
    optimized_network = optimize_employee_assignment(network, position_employee_map, employee_schedule, days_off_map,
                                                     start_date)

    # Создаем задачи календарного плана
    for task in optimized_network:
        employee_id = task.get('assigned_employee_id')
        employee = next((e for e in employees if e['id'] == employee_id), None)

        if not employee:
            # Если сотрудник не назначен, найдем любого сотрудника с подходящей должностью
            possible_employees = position_employee_map.get(task['position'], [])
            if possible_employees:
                employee = possible_employees[0]
                task['assigned_employee_id'] = employee['id']
            else:
                continue  # Пропускаем задачу, если нет подходящего сотрудника

        # Учитываем выходные дни сотрудника при определении дат начала и окончания
        task_start_date, task_end_date = calculate_task_dates(
            task,
            employee['id'],
            days_off_map[employee['id']],
            start_date,
            employee_schedule
        )

        # Добавляем задачу в расписание сотрудника
        employee_schedule[employee['id']].append({
            'task_id': task['id'],
            'start_date': task_start_date,
            'end_date': task_end_date
        })

        # Добавляем задачу в календарный план
        calendar_plan['tasks'].append({
            'id': task['id'],
            'name': task['name'],
            'start_date': task_start_date,
            'end_date': task_end_date,
            'duration': task['duration'],
            'is_critical': task['is_critical'],
            'reserve': task['reserve'],
            'employee': employee['name'],
            'employee_email': employee.get('email'),  # Добавляем email сотрудника
            'predecessors': task.get('predecessors', [])
        })

    return calendar_plan


def optimize_employee_assignment(network, position_employee_map, employee_schedule, days_off_map, start_date):
    """
    Оптимизирует назначение сотрудников на задачи для минимизации времени проекта.

    Args:
        network: Сетевая модель
        position_employee_map: Словарь должность -> список сотрудников
        employee_schedule: Текущие задачи сотрудников
        days_off_map: Выходные дни сотрудников
        start_date: Дата начала проекта

    Returns:
        Оптимизированная сетевая модель с назначенными сотрудниками
    """
    # Копируем сеть для работы с ней
    optimized_network = network.copy()

    # Сортируем задачи по приоритету (сначала критические, затем по раннему сроку начала)
    optimized_network.sort(key=lambda x: (not x['is_critical'], x['early_start']))

    for task in optimized_network:
        position = task['position']
        available_employees = position_employee_map.get(position, [])

        if not available_employees:
            continue

        # Проверяем, какой сотрудник может выполнить задачу быстрее всего
        best_employee = None
        earliest_end_date = None

        for employee in available_employees:
            # Вычисляем, когда сотрудник может начать выполнение задачи
            employee_earliest_start = calculate_earliest_start(
                task,
                employee['id'],
                days_off_map[employee['id']],
                employee_schedule,
                start_date
            )

            # Вычисляем, когда сотрудник закончит выполнение задачи
            task_end_date = calculate_task_end_date(
                employee_earliest_start,
                task['duration'],
                days_off_map[employee['id']]
            )

            # Если это первый сотрудник или он может закончить задачу раньше предыдущего лучшего
            if earliest_end_date is None or task_end_date < earliest_end_date:
                best_employee = employee
                earliest_end_date = task_end_date

        # Назначаем лучшего сотрудника на задачу
        if best_employee:
            task['assigned_employee_id'] = best_employee['id']

    return optimized_network


def calculate_earliest_start(task, employee_id, days_off, employee_schedule, start_date):
    """
    Вычисляет самую раннюю дату начала задачи для конкретного сотрудника.

    Args:
        task: Задача
        employee_id: ID сотрудника
        days_off: Выходные дни сотрудника
        employee_schedule: Текущие задачи сотрудника
        start_date: Дата начала проекта

    Returns:
        Самая ранняя возможная дата начала задачи
    """
    # Минимальная дата начала исходя из сетевой модели
    earliest_date = start_date + timedelta(days=task['early_start'])

    # Проверяем, не занят ли сотрудник другими задачами
    employee_tasks = employee_schedule.get(employee_id, [])
    if employee_tasks:
        # Находим последнюю задачу сотрудника
        latest_task = max(employee_tasks, key=lambda x: x['end_date'])
        # Дата начала должна быть после окончания последней задачи
        task_start_after_previous = latest_task['end_date'] + timedelta(days=1)
        earliest_date = max(earliest_date, task_start_after_previous)

    # Корректируем дату с учетом выходных дней
    return adjust_date_for_days_off(earliest_date, days_off)


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
    Вычисляет дату окончания задачи с учетом выходных дней.

    Args:
        start_date: Дата начала задачи
        duration: Длительность задачи в рабочих днях
        days_off: Выходные дни

    Returns:
        Дата окончания задачи
    """
    working_days = 0
    current_date = start_date

    while working_days < duration:
        # Если день не выходной, считаем его рабочим
        if current_date.weekday() not in days_off:
            working_days += 1

        current_date += timedelta(days=1)

    # Конечная дата - это предыдущий день
    return current_date - timedelta(days=1)


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