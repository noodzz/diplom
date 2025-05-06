"""
Модуль для создания задач в Jira на основе календарного плана
"""

import logging
from jira_integration.client import JiraClient
from config import JIRA_PROJECT_KEY

logger = logging.getLogger(__name__)


def create_jira_issues(calendar_plan):
    """
    Creates Jira issues based on calendar plan.

    Args:
        calendar_plan: Calendar plan with tasks

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

    # First create parent tasks for multi-assignee tasks
    parent_tasks = {}
    for task in tasks:
        # Check if this is a task that requires multiple employees
        if 'required_employees' in task and task['required_employees'] > 1:
            # Create parent task if not already created
            if task['name'] not in parent_tasks:
                summary = f"{task['name']} (Group Task)"
                description = f"Parent task for {task['name']} requiring {task['required_employees']} employees."

                # Create parent issue with Medium priority
                issue = client.create_issue(
                    project_key=JIRA_PROJECT_KEY,
                    summary=summary,
                    description=description,
                    priority="Medium"
                )

                if issue:
                    parent_tasks[task['name']] = issue.key

    # Now create individual tasks
    for task in tasks:
        summary = task['name']
        description = format_task_description(task)

        # Set priority based on whether task is critical
        priority = "High" if task['is_critical'] else "Medium"

        # Use email if available, otherwise use name
        assignee = (task.get('employee_email') or '').strip()
        if not assignee:
            logger.warning(f"No email for employee: {task.get('employee')}, using name instead")
            assignee = task.get('employee')

        # Create the issue
        parent_key = parent_tasks.get(task['name'])
        issue = client.create_issue(
            project_key=JIRA_PROJECT_KEY,
            summary=summary,
            description=description,
            assignee=assignee,
            due_date=task.get('end_date'),
            priority=priority,
            parent_key=parent_key
        )

        if issue:
            jira_issues[task['id']] = issue.key
            created_issues.append({
                'key': issue.key,
                'summary': summary,
                'assignee': assignee,
                'priority': priority
            })

    # Create dependencies (but in the correct direction)
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

    # Build a dictionary of task IDs to predecessor IDs for easier lookup
    task_predecessors = {}
    for task in tasks:
        task_id = task['id']
        predecessors = task.get('predecessors', [])
        task_predecessors[task_id] = predecessors

    # Create dependencies
    for task in tasks:
        task_id = task['id']
        predecessors = task_predecessors.get(task_id, [])

        for predecessor_id in predecessors:
            if predecessor_id in jira_issues and task_id in jira_issues:
                # IMPORTANT: This is the fix - make sure dependencies are created in the right direction
                # A depends on B means B blocks A
                # So if task depends on predecessor, then predecessor blocks task
                client.create_dependency(
                    issue_key=jira_issues[task_id],  # Dependent issue (blocked by)
                    depends_on_key=jira_issues[predecessor_id],  # Blocking issue (blocks)
                    link_type=dependency_link_type
                )
                logger.info(f"Created dependency: {jira_issues[task_id]} depends on {jira_issues[predecessor_id]}")