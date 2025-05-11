"""
Модуль для создания задач в Jira на основе календарного плана
"""

import logging
from jira_integration.client import JiraClient
from config import JIRA_PROJECT_KEY

logger = logging.getLogger(__name__)

# Константы для категорий задач
CATEGORY_PMS = "ПМы"
CATEGORY_SETUP = "Настройка"
CATEGORY_CONTENT = "Контент"

# Маппинг должностей на категории
POSITION_CATEGORY_MAP = {
    # Должности категории "ПМы"
    "проектный менеджер": CATEGORY_PMS,
    "project manager": CATEGORY_PMS,
    "менеджер": CATEGORY_PMS,

    # Должности категории "Настройка"
    "технический специалист": CATEGORY_SETUP,
    "старший технический специалист": CATEGORY_SETUP,
    "руководитель настройки": CATEGORY_SETUP,
    "руководитель сектора настройки": CATEGORY_SETUP,

    # Должности категории "Контент"
    "младший специалист": CATEGORY_CONTENT,
    "старший специалист": CATEGORY_CONTENT,
    "руководитель контента": CATEGORY_CONTENT
}


def create_jira_issues(calendar_plan):
    """
    Creates Jira issues based on calendar plan.

    Args:
        calendar_plan: Calendar plan with tasks and task descriptions

    Returns:
        List of created issues
    """
    client = JiraClient()

    if not client.is_connected():
        logger.error("Cannot create Jira issues: Jira client is not connected")
        return []

    tasks = calendar_plan['tasks']
    jira_issues = {}
    created_issues = []

    # Get task descriptions from the calendar_plan if they exist
    task_descriptions = calendar_plan.get('task_descriptions', {})

    # Сначала группируем задачи по имени и определяем родительские задачи
    tasks_by_name = {}
    parent_tasks = set()

    for task in tasks:
        name = task.get('name', '')

        # Определяем, является ли это подзадачей
        if ' - ' in name:
            # Это подзадача - извлекаем имя родительской задачи
            parent_name = name.split(' - ')[0]

            # Добавляем в группу по имени родителя
            if parent_name not in tasks_by_name:
                tasks_by_name[parent_name] = []
            tasks_by_name[parent_name].append(task)

            # Запоминаем это как родительскую задачу
            parent_tasks.add(parent_name)
        else:
            # Обычная задача
            if name not in tasks_by_name:
                tasks_by_name[name] = []
            tasks_by_name[name].append(task)

    # Теперь обрабатываем задачи
    for task_name, task_group in tasks_by_name.items():
        if task_name in parent_tasks:
            # Это родительская задача с подзадачами

            # Найдем экземпляр родительской задачи, если он есть
            parent_task = next((t for t in task_group if t.get('name') == task_name), None)
            if parent_task is None:
                # Если нет прямого экземпляра родительской задачи, создаем виртуальный
                parent_task = {
                    'name': task_name,
                    'is_critical': any(t.get('is_critical', False) for t in task_group),
                    'duration': max(t.get('duration', 0) for t in task_group),
                    'start_date': min(t.get('start_date') for t in task_group),
                    'end_date': max(t.get('end_date') for t in task_group),
                    'is_parent': True
                }

            # Получаем только подзадачи из группы
            subtasks = [t for t in task_group if t.get('name') != task_name]

            # Создаём родительскую задачу без исполнителя
            parent_summary = f"{task_name}"
            parent_description = f"Родительская задача для {task_name}. Требуется {len(subtasks)} исполнителей."
            priority = "High" if parent_task.get('is_critical', False) else "Medium"
            parent_issue = client.create_issue(
                project_key=JIRA_PROJECT_KEY,
                summary=parent_summary,
                description=parent_description,
                priority=priority,
                issue_type="Task"
                # Не указываем assignee для родительской задачи
            )

            if parent_issue:
                parent_key = parent_issue.key
                created_issues.append({
                    'key': parent_key,
                    'summary': parent_summary,
                    'assignee': "Unassigned",
                    'priority': priority
                })

                # Создаем подзадачи с родительским ключом
                for subtask in subtasks:
                    subtask_summary = subtask['name']
                    task_id = str(subtask.get('id', ''))
                    task_description = task_descriptions.get(task_id, '')
                    if not task_description:
                        task_description = format_task_description(subtask)

                    subtask_priority = "High" if subtask.get('is_critical', False) else "Medium"
                    assignee = subtask.get('employee_email')
                    if not assignee:
                        assignee = subtask.get('employee')
                    if not assignee:
                        assignee = "Unassigned"

                    # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Используем parent_key и явно указываем issue_type="Sub-task"
                    subtask_issue = client.create_issue(
                        project_key=JIRA_PROJECT_KEY,
                        summary=subtask_summary,
                        description=task_description,
                        assignee=assignee,
                        due_date=subtask.get('end_date'),
                        priority=subtask_priority,
                        parent_key=parent_key,  # Указываем родительскую задачу
                        issue_type="Sub-task"  # Явно указываем тип "Sub-task"
                    )

                    if subtask_issue:
                        jira_issues[subtask.get('id', f"subtask_{task_name}_{assignee}")] = subtask_issue.key
                        created_issues.append({
                            'key': subtask_issue.key,
                            'summary': subtask_summary,
                            'assignee': assignee,
                            'priority': subtask_priority
                        })

                # Запоминаем ключ родительской задачи
                jira_issues[f"parent_{task_name}"] = parent_key

        else:
            # Обычная задача (не родительская)
            for task in task_group:
                summary = task['name']
                task_id = str(task.get('id', ''))
                task_description = task_descriptions.get(task_id, '')
                if not task_description:
                    task_description = format_task_description(task)

                priority = "High" if task.get('is_critical', False) else "Medium"
                assignee = task.get('employee_email')
                if not assignee:
                    assignee = task.get('employee')
                if not assignee:
                    assignee = "Unassigned"

                issue = client.create_issue(
                    project_key=JIRA_PROJECT_KEY,
                    summary=summary,
                    description=task_description,
                    assignee=assignee,
                    due_date=task.get('end_date'),
                    priority=priority,
                    issue_type="Task"
                )

                if issue:
                    jira_issues[task.get('id', f"task_{summary}")] = issue.key
                    created_issues.append({
                        'key': issue.key,
                        'summary': summary,
                        'assignee': assignee,
                        'priority': priority
                    })

    # Create dependencies between tasks
    create_task_dependencies(client, tasks, jira_issues)

    return created_issues

def format_parent_task_description(task_group):
    """
    Форматирует описание родительской задачи.

    Args:
        task_group: Группа задач с одинаковым названием, но разными исполнителями

    Returns:
        Форматированное описание для родительской задачи
    """
    # Составляем информацию о задаче
    total_duration = sum(task['duration'] for task in task_group)
    earliest_start = min(task['start_date'] for task in task_group)
    latest_finish = max(task['end_date'] for task in task_group)

    # Собираем информацию о должностях
    positions = [task['position'] for task in task_group]
    positions_str = ", ".join(positions)

    # Определяем статус критичности
    is_critical = any(task['is_critical'] for task in task_group)
    critical_status = "Да" if is_critical else "Нет"

    # Форматируем описание в Markdown для Jira
    description = f"""
h2. Информация о составной задаче

* *Общая длительность*: {total_duration} дней
* *Начало*: {earliest_start.strftime('%d.%m.%Y')}
* *Окончание*: {latest_finish.strftime('%d.%m.%Y')}
* *Требуемые должности*: {positions_str}
* *Критическая задача*: {critical_status}

h2. Описание задачи

Эта задача разделена на подзадачи для специалистов разных должностей. 
Общее число исполнителей: {len(task_group)}.

h2. Внимание

Эта задача является частью автоматически сгенерированного календарного плана.
Изменение сроков выполнения критических задач может привести к задержке всего проекта.
"""
    return description


def get_task_category(position):
    """
    Определяет категорию задачи на основе должности исполнителя.

    Args:
        position: Должность исполнителя задачи

    Returns:
        Категория задачи (ПМы, Настройка, Контент)
    """
    if not position:
        return None

    position_lower = position.lower()

    # Прямое совпадение
    if position_lower in POSITION_CATEGORY_MAP:
        return POSITION_CATEGORY_MAP[position_lower]

    # Частичное совпадение
    for pos, category in POSITION_CATEGORY_MAP.items():
        if pos in position_lower:
            return category

    # Определение по ключевым словам
    if any(keyword in position_lower for keyword in ["менеджер", "manager", "пм"]):
        return CATEGORY_PMS
    elif any(keyword in position_lower for keyword in ["настройк", "технич", "setup"]):
        return CATEGORY_SETUP
    elif any(keyword in position_lower for keyword in ["контент", "content", "специалист"]):
        return CATEGORY_CONTENT

    # По умолчанию возвращаем None, если категория не определена
    return None


def find_project_manager(calendar_plan):
    """
    Finds a project manager in the calendar plan.

    Args:
        calendar_plan: Calendar plan with tasks and employees

    Returns:
        Dictionary with project manager info or empty dict if not found
    """
    # Try to find project manager in tasks
    for task in calendar_plan.get('tasks', []):
        position = task.get('position', '').lower()
        if 'менеджер' in position or 'manager' in position:
            return {
                'name': task.get('employee', 'Проектный менеджер'),
                'email': task.get('employee_email', '')
            }

    # If not found in tasks, return default
    return {
        'name': 'Проектный менеджер',
        'email': ''
    }


def format_task_description(task, subtitle=None):
    """
    Форматирует описание задачи для Jira.

    Args:
        task: Задача из календарного плана
        subtitle: Подзаголовок (необязательно)

    Returns:
        Отформатированное описание задачи
    """
    # Определяем статус критической задачи
    critical_status = "Да" if task['is_critical'] else "Нет"

    # Определяем категорию задачи
    category = get_task_category(task.get('position', ''))
    category_text = f"* *Категория*: {category}\n" if category else ""

    # Форматируем описание в Markdown
    description = f"""
h2. Информация о задаче
"""

    if subtitle:
        description += f"\nh3. {subtitle}\n"

    description += f"""
* *Длительность*: {task['duration']} дней
* *Начало*: {task['start_date'].strftime('%d.%m.%Y')}
* *Окончание*: {task['end_date'].strftime('%d.%m.%Y')}
* *Исполнитель*: {task.get('employee', 'Не назначено')}
* *Должность*: {task.get('position', 'Не указано')}
{category_text}* *Критическая задача*: {critical_status}
* *Резерв времени*: {task.get('reserve', 0)} дней

h2. Внимание

Эта задача является частью автоматически сгенерированного календарного плана.
Изменение сроков выполнения критических задач может привести к задержке всего проекта.
"""
    return description


def create_task_dependencies(client, tasks, jira_issues):
    """
    Creates dependencies between Jira issues.

    Args:
        client: Jira client
        tasks: Tasks from calendar plan
        jira_issues: Dictionary mapping task IDs to Jira issue keys
    """
    # Get available link types
    link_types = client.get_available_link_types()

    # Find appropriate link type for dependencies
    dependency_link_type = None
    for link_type in link_types:
        if "depend" in link_type.lower() or "block" in link_type.lower():
            dependency_link_type = link_type
            break

    if not dependency_link_type and link_types:
        dependency_link_type = link_types[0]

    if not dependency_link_type:
        logger.warning("No link types available in Jira, dependencies will not be created")
        return

    # Группируем задачи по имени для обработки групповых задач
    tasks_by_name = {}
    for task in tasks:
        name = task['name']
        if name not in tasks_by_name:
            tasks_by_name[name] = []
        tasks_by_name[name].append(task)

    # Создаем зависимости
    for task_name, task_group in tasks_by_name.items():
        required_employees = task_group[0].get('required_employees', 1)
        
        # Получаем ID родительской задачи для групповых задач
        if required_employees > 1:
            # Находим родительскую задачу по имени
            parent_key = None
            for issue_key, issue in jira_issues.items():
                if isinstance(issue, dict) and issue.get('summary') == f"{task_name} (Групповая задача)":
                    parent_key = issue_key
                    break
            
            if parent_key:
                # Для каждой подзадачи создаем зависимости
                for task in task_group:
                    task_id = task['id']
                    predecessors = task.get('predecessors', [])
                    
                    for predecessor_id in predecessors:
                        # Находим родительскую задачу предшественника
                        predecessor_parent_key = None
                        for pred_task in tasks:
                            if pred_task['id'] == predecessor_id:
                                pred_name = pred_task['name']
                                for issue_key, issue in jira_issues.items():
                                    if isinstance(issue, dict) and issue.get('summary') == f"{pred_name} (Групповая задача)":
                                        predecessor_parent_key = issue_key
                                        break
                                break
                        
                        if predecessor_parent_key:
                            # Создаем зависимость между родительскими задачами
                            client.create_dependency(
                                issue_key=predecessor_parent_key,                # blocks
                                depends_on_key=parent_key,    # is blocked by
                                link_type=dependency_link_type
                            )
                            logger.info(f"Created dependency between group tasks: {predecessor_parent_key} blocks {parent_key}")
        else:
            # Стандартная обработка для обычных задач
            task = task_group[0]
            task_id = task['id']
            predecessors = task.get('predecessors', [])
            
            for predecessor_id in predecessors:
                # Находим задачу предшественника
                predecessor_key = None
                for pred_task in tasks:
                    if pred_task['id'] == predecessor_id:
                        pred_name = pred_task['name']
                        pred_required_employees = pred_task.get('required_employees', 1)
                        
                        if pred_required_employees > 1:
                            # Если предшественник - групповая задача, используем родительскую задачу
                            for issue_key, issue in jira_issues.items():
                                if isinstance(issue, dict) and issue.get('summary') == f"{pred_name} (Групповая задача)":
                                    predecessor_key = issue_key
                                    break
                        else:
                            # Если предшественник - обычная задача
                            predecessor_key = jira_issues.get(predecessor_id)
                        
                        break
                
                if predecessor_key and task_id in jira_issues:
                    # Создаем зависимость: predecessor_key blocks jira_issues[task_id]
                    client.create_dependency(
                        issue_key=predecessor_key,                # blocks
                        depends_on_key=jira_issues[task_id],    # is blocked by
                        link_type=dependency_link_type
                    )
                    logger.info(f"Created dependency: {predecessor_key} blocks {jira_issues[task_id]}")
                else:
                    logger.warning(f"Could not create dependency: Missing Jira issue for task {task_id} or predecessor {predecessor_id}")