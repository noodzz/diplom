# planning/network.py
"""
Модуль для расчета параметров сетевой модели и определения критического пути
"""
from logger import logger


def calculate_network_parameters(project_data):
    """
    Рассчитывает параметры сетевой модели.

    Args:
        project_data: Данные проекта с задачами и зависимостями

    Returns:
        Dict с рассчитанными параметрами сетевой модели
    """
    # Получаем задачи проекта
    tasks = project_data.get('tasks', [])

    if not tasks:
        logger.warning("Нет задач для расчета сетевой модели")
        return {
            'network': [],
            'critical_path': [],
            'project_duration': 0
        }

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

    # Логируем результаты для отладки
    logger.info(f"Рассчитана сетевая модель: {len(network)} задач, проект: {network[-1]['early_finish']} дней")
    logger.info(f"Критический путь: {[task['name'] for task in critical_path]}")

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

    # Ищем родительские задачи и подзадачи
    parent_tasks = {task['id']: task for task in tasks if task.get('is_parent', False)}

    # Преобразуем каждую задачу в узел сетевой модели
    for task in tasks:
        # Пропускаем подзадачи - они обрабатываются в контексте родительских задач
        if task.get('is_subtask', False):
            continue

        # Проверяем, является ли это родительской задачей с подзадачами
        is_parent = task.get('is_parent', False) or task.get('id') in parent_tasks

        # Если это родительская задача, обрабатываем ее иначе
        if is_parent:
            # Для родительской задачи длительность определяется её подзадачами
            network_task = {
                'id': task['id'],
                'name': task['name'],
                'duration': task['duration'],
                'position': task.get('position', ''),
                'predecessors': task.get('predecessors', []),
                'required_employees': task.get('required_employees', 1),
                'sequential_subtasks': task.get('sequential_subtasks', False),
                'is_parent': True,
                'early_start': 0,
                'early_finish': 0,
                'late_start': 0,
                'late_finish': 0,
                'is_critical': False,
                'reserve': 0
            }
        else:
            # Обычная задача
            network_task = {
                'id': task['id'],
                'name': task['name'],
                'duration': task['duration'],
                'position': task.get('position', ''),
                'predecessors': task.get('predecessors', []),
                'required_employees': task.get('required_employees', 1),
                'early_start': 0,
                'early_finish': 0,
                'late_start': 0,
                'late_finish': 0,
                'is_critical': False,
                'reserve': 0
            }

        network.append(network_task)

    # Сортируем задачи в топологическом порядке с учетом зависимостей
    network = topological_sort(network)

    # Для диагностики логируем результат
    logger.debug(f"Создана сетевая модель: {len(network)} задач")
    for task in network:
        logger.debug(f"Задача: {task['name']}, предшественники: {task['predecessors']}")

    return network


def topological_sort(network):
    """
    Сортирует задачи в топологическом порядке (с учетом зависимостей).

    Args:
        network: Несортированная сетевая модель

    Returns:
        Отсортированная сетевая модель
    """
    # Создаем словарь id -> задача для быстрого доступа
    tasks_by_id = {task['id']: task for task in network}

    # Создаем словарь id -> имя для отчетов
    task_names = {task['id']: task['name'] for task in network}

    # Создаем граф зависимостей
    graph = {}
    for task in network:
        task_id = task['id']
        graph[task_id] = []

    # Заполняем граф
    for task in network:
        task_id = task['id']
        for pred_id in task.get('predecessors', []):
            if pred_id in graph:
                graph[pred_id].append(task_id)

    # Нахождение порядка выполнения задач
    visited = set()
    temp = set()
    order = []

    def visit(task_id):
        """Обход графа в глубину с проверкой циклов"""
        if task_id in temp:
            # Цикл!
            cycle_path = []
            for t_id in list(temp) + [task_id]:
                cycle_path.append(task_names.get(t_id, str(t_id)))
            logger.error(f"Обнаружена циклическая зависимость: {' -> '.join(cycle_path)}")
            raise ValueError(f"Циклическая зависимость: {' -> '.join(cycle_path)}")

        if task_id not in visited:
            temp.add(task_id)
            for successor in graph.get(task_id, []):
                visit(successor)
            temp.remove(task_id)
            visited.add(task_id)
            order.insert(0, task_id)

    # Обходим все задачи
    for task_id in graph:
        if task_id not in visited:
            try:
                visit(task_id)
            except ValueError as e:
                logger.error(f"Ошибка при топологической сортировке: {str(e)}")
                # В случае ошибки возвращаем исходный порядок
                return network

    # Восстанавливаем порядок задач
    sorted_tasks = []
    for task_id in order:
        if task_id in tasks_by_id:
            sorted_tasks.append(tasks_by_id[task_id])

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
    if not network:
        return network

    # Находим максимальный ранний срок окончания (длина всего проекта)
    project_duration = max(task['early_finish'] for task in network)

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

    # Для диагностики выводим критический путь
    logger.info(f"Критический путь: {[task['name'] for task in critical_tasks]}")

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