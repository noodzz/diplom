"""
Модуль для создания задач в Jira на основе календарного плана
"""

import logging
from jira_integration.client import JiraClient
from config import JIRA_PROJECT_KEY

logger = logging.getLogger(__name__)


def create_jira_issues(calendar_plan):
    """
    Создает задачи в Jira на основе календарного плана.

    Args:
        calendar_plan: Календарный план с задачами

    Returns:
        Список созданных задач или пустой список в случае ошибки
    """
    client = JiraClient()

    # Проверяем подключение к Jira
    if not client.is_connected():
        logger.error("Cannot create Jira issues: Jira client is not connected")
        return []

    tasks = calendar_plan['tasks']

    # Словарь для хранения созданных задач (id задачи -> jira_integration key)
    jira_issues = {}
    created_issues = []

    # Создаем все задачи
    for task in tasks:
        # Формируем заголовок и описание задачи
        summary = task['name']
        description = format_task_description(task)

        # Определяем приоритет задачи (критические задачи имеют высокий приоритет)
        priority = "High" if task['is_critical'] else "Medium"

        # Создаем задачу в Jira
        issue = client.create_issue(
            project_key=JIRA_PROJECT_KEY,
            summary=summary,
            description=description,
            assignee=task['employee'],
            due_date=task['end_date'],
            priority=priority
        )

        if issue:
            jira_issues[task['id']] = issue.key

            created_issues.append({
                'key': issue.key,
                'summary': summary,
                'assignee': task['employee']
            })

    # Устанавливаем зависимости между задачами
    create_task_dependencies(client, tasks, jira_issues)

    return created_issues


def format_task_description(task):
    """
    Форматирует описание задачи для Jira.

    Args:
        task: Задача из календарного плана

    Returns:
        Отформатированное описание задачи
    """
    # Определяем статус критической задачи
    critical_status = "Да" if task['is_critical'] else "Нет"

    # Форматируем описание в Markdown
    description = f"""
h2. Информация о задаче

* *Длительность*: {task['duration']} дней
* *Начало*: {task['start_date'].strftime('%d.%m.%Y')}
* *Окончание*: {task['end_date'].strftime('%d.%m.%Y')}
* *Исполнитель*: {task['employee']}
* *Критическая задача*: {critical_status}
* *Резерв времени*: {task['reserve']} дней

h2. Внимание

Эта задача является частью автоматически сгенерированного календарного плана.
Изменение сроков выполнения критических задач может привести к задержке всего проекта.
"""
    return description


def create_task_dependencies(client, tasks, jira_issues):
    """
    Создает зависимости между задачами в Jira.

    Args:
        client: Клиент Jira
        tasks: Список задач из календарного плана
        jira_issues: Словарь соответствия id задачи -> jira_integration key
    """
    # Получаем доступные типы связей
    link_types = client.get_available_link_types()

    # Определяем тип связи для зависимостей
    # В разных инсталляциях Jira могут быть разные типы связей
    # Пытаемся найти подходящий тип связи
    dependency_link_type = None
    for link_type in link_types:
        if "depend" in link_type.lower() or "block" in link_type.lower():
            dependency_link_type = link_type
            break

    # Если подходящий тип связи не найден, используем первый доступный
    if not dependency_link_type and link_types:
        dependency_link_type = link_types[0]

    # Если нет доступных типов связей, выходим
    if not dependency_link_type:
        logger.warning("No link types available in Jira, dependencies will not be created")
        return

    # Создаем зависимости между задачами
    for task in tasks:
        if 'predecessors' in task and task['predecessors']:
            for predecessor_id in task['predecessors']:
                if predecessor_id in jira_issues and task['id'] in jira_issues:
                    client.create_dependency(
                        jira_issues[task['id']],
                        jira_issues[predecessor_id],
                        dependency_link_type
                    )