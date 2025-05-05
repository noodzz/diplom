# planning/network.py
"""
Модуль для расчета параметров сетевой модели и определения критического пути
"""


def calculate_network_parameters(project_data):
    """
    Рассчитывает параметры сетевой модели.

    Args:
        project_data: Данные проекта с задачами и зависимостями

    Returns:
        Dict с рассчитанными параметрами сетевой модели
    """
    tasks = project_data['tasks']

    # Создаем сетевую модель
    network = create_network_model(tasks)

    # Рассчитываем ранние сроки начала и окончания
    calculate_early_times(network)

    # Рассчитываем поздние сроки начала и окончания
    calculate_late_times(network)

    # Определяем критический путь
    critical_path = identify_critical_path(network)

    # Рассчитываем резервы времени для некритических работ
    calculate_reserves(network)

    return {
        'network': network,
        'critical_path': critical_path,
        'project_duration': network[-1]['early_finish'] if network else 0
    }


def create_network_model(tasks):
    """
    Создает сетевую модель на основе задач.

    Args:
        tasks: Список задач с предшественниками

    Returns:
        Сетевая модель в виде списка задач с дополнительными параметрами
    """
    # Создаем копию списка задач для сетевой модели
    network = []

    # Преобразуем каждую задачу в узел сетевой модели
    for task in tasks:
        network_task = {
            'id': task['id'],
            'name': task['name'],
            'duration': task['duration'],
            'position': task['position'],
            'predecessors': task.get('predecessors', []),
            'early_start': 0,
            'early_finish': 0,
            'late_start': 0,
            'late_finish': 0,
            'is_critical': False,
            'reserve': 0
        }
        network.append(network_task)

    # Сортируем задачи в топологическом порядке
    network = topological_sort(network)

    return network


def topological_sort(network):
    """
    Сортирует задачи в топологическом порядке (задачи-предшественники идут перед зависимыми задачами).

    Args:
        network: Несортированная сетевая модель

    Returns:
        Отсортированная сетевая модель
    """
    # Создаем словарь id -> задача для быстрого доступа
    tasks_by_id = {task['id']: task for task in network}

    # Для хранения отсортированного списка
    sorted_tasks = []

    # Множество уже обработанных задач
    processed = set()

    def visit(task_id):
        """Рекурсивно обрабатывает задачу и ее предшественников."""
        if task_id in processed:
            return

        task = tasks_by_id.get(task_id)
        if not task:
            return

        # Сначала посещаем все предшествующие задачи
        for predecessor_id in task.get('predecessors', []):
            visit(predecessor_id)

        # Добавляем текущую задачу в список
        if task_id not in processed:
            processed.add(task_id)
            sorted_tasks.append(task)

    # Обходим все задачи
    for task in network:
        visit(task['id'])

    return sorted_tasks


def calculate_early_times(network):
    """
    Рассчитывает ранние сроки начала и окончания для всех работ.

    Args:
        network: Сетевая модель

    Returns:
        Обновленная сетевая модель с ранними сроками
    """
    # Создаем словарь id -> задача для быстрого доступа
    tasks_by_id = {task['id']: task for task in network}

    # Для каждой задачи
    for task in network:
        # Если у задачи нет предшественников, то ранний срок начала = 0
        if not task['predecessors']:
            task['early_start'] = 0
        else:
            # Иначе ранний срок начала = максимум из ранних сроков окончания предшественников
            max_early_finish = 0
            for predecessor_id in task['predecessors']:
                predecessor = tasks_by_id.get(predecessor_id)
                if predecessor:
                    predecessor_finish = predecessor['early_start'] + predecessor['duration']
                    max_early_finish = max(max_early_finish, predecessor_finish)

            task['early_start'] = max_early_finish

        # Ранний срок окончания = ранний срок начала + длительность
        task['early_finish'] = task['early_start'] + task['duration']

    return network


def calculate_late_times(network):
    """
    Рассчитывает поздние сроки начала и окончания для всех работ.

    Args:
        network: Сетевая модель с ранними сроками

    Returns:
        Обновленная сетевая модель с поздними сроками
    """
    # Находим максимальный ранний срок окончания (длина всего проекта)
    project_duration = max(task['early_finish'] for task in network) if network else 0

    # Создаем словарь id -> задача для быстрого доступа
    tasks_by_id = {task['id']: task for task in network}

    # Создаем обратный словарь: id задачи -> список задач, которые от нее зависят
    successors = {}
    for task in network:
        task_id = task['id']
        successors[task_id] = []

    for task in network:
        for predecessor_id in task['predecessors']:
            if predecessor_id in successors:
                successors[predecessor_id].append(task['id'])

    # Инициализируем поздние сроки окончания для всех задач = длине проекта
    for task in network:
        task['late_finish'] = project_duration

    # Обрабатываем задачи в обратном порядке
    for task in reversed(network):
        # Для задач без последователей поздний срок окончания = длине проекта
        successor_ids = successors.get(task['id'], [])
        if successor_ids:
            # Для остальных задач поздний срок окончания = минимум из поздних сроков начала последователей
            min_late_start = float('inf')
            for successor_id in successor_ids:
                successor = tasks_by_id.get(successor_id)
                if successor:
                    min_late_start = min(min_late_start, successor['late_start'])

            task['late_finish'] = min_late_start

        # Поздний срок начала = поздний срок окончания - длительность
        task['late_start'] = task['late_finish'] - task['duration']

    return network


def identify_critical_path(network):
    """
    Определяет критический путь в сетевой модели.

    Args:
        network: Сетевая модель с рассчитанными параметрами

    Returns:
        Список задач, входящих в критический путь
    """
    # Задача считается критической, если ранний срок начала = позднему сроку начала
    # или ранний срок окончания = позднему сроку окончания
    critical_tasks = []

    for task in network:
        if task['early_start'] == task['late_start'] or task['early_finish'] == task['late_finish']:
            task['is_critical'] = True
            critical_tasks.append(task)

    # Сортируем критические задачи по раннему сроку начала
    critical_tasks.sort(key=lambda x: x['early_start'])

    return critical_tasks


def calculate_reserves(network):
    """
    Рассчитывает резервы времени для некритических работ.

    Args:
        network: Сетевая модель с рассчитанными параметрами

    Returns:
        Обновленная сетевая модель с резервами времени
    """
    for task in network:
        # Полный резерв времени = поздний срок окончания - ранний срок окончания
        # или поздний срок начала - ранний срок начала (они равны)
        task['reserve'] = task['late_start'] - task['early_start']

    return network


def get_task_dependencies_graph(network):
    """
    Создает граф зависимостей между задачами для визуализации.

    Args:
        network: Сетевая модель

    Returns:
        Словарь с данными для построения графа
    """
    nodes = []
    edges = []

    # Создаем словарь id -> задача для быстрого доступа
    tasks_by_id = {task['id']: task for task in network}

    # Создаем узлы графа
    for task in network:
        nodes.append({
            'id': task['id'],
            'label': task['name'],
            'is_critical': task['is_critical']
        })

    # Создаем ребра графа
    for task in network:
        for predecessor_id in task.get('predecessors', []):
            if predecessor_id in tasks_by_id:
                edges.append({
                    'from': predecessor_id,
                    'to': task['id']
                })

    return {
        'nodes': nodes,
        'edges': edges
    }


def add_task_start_finish_dates(network, start_date):
    """
    Добавляет даты начала и окончания задач без учета выходных дней.

    Args:
        network: Сетевая модель с рассчитанными параметрами
        start_date: Дата начала проекта

    Returns:
        Обновленная сетевая модель с датами начала и окончания
    """
    from datetime import timedelta

    for task in network:
        task['start_date'] = start_date + timedelta(days=task['early_start'])
        task['finish_date'] = start_date + timedelta(days=task['early_finish'])

    return network