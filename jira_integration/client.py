"""
Модуль для работы с Jira API
"""

import logging
from jira import JIRA
from config import JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

logger = logging.getLogger(__name__)


class JiraClient:
    """Клиент для работы с Jira API."""

    def __init__(self):
        """Инициализирует клиент Jira."""
        try:
            self.client = JIRA(
                server=JIRA_URL,
                basic_auth=(JIRA_USERNAME, JIRA_API_TOKEN)
            )
            logger.info("Jira API client successfully initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Jira API client: {str(e)}")
            self.client = None

    def is_connected(self):
        """
        Проверяет подключение к Jira.

        Returns:
            bool: True, если подключение успешно, иначе False
        """
        if not self.client:
            return False

        try:
            # Пытаемся получить профиль текущего пользователя
            self.client.myself()
            return True
        except Exception as e:
            logger.error(f"Jira connection test failed: {str(e)}")
            return False

    def create_issue(self, project_key, summary, description, assignee=None, due_date=None,
                     priority=None, issue_type='Task', parent_key=None):
        """
        Creates a Jira issue.

        Args:
            project_key: Jira project key
            summary: Issue summary
            description: Issue description
            assignee: Assignee email or username
            due_date: Due date
            priority: Priority (High, Medium, Low)
            issue_type: Issue type (default: Task)
            parent_key: Parent issue key for sub-tasks

        Returns:
            Created issue or None on error
        """
        if not self.client:
            logger.error("Jira client is not initialized")
            return None

        try:
            issue_dict = {
                'project': {'key': project_key},
                'summary': summary,
                'description': description,
                'issuetype': {'name': issue_type}
            }

            if assignee:
                # First, try to find user by email
                user = None
                try:
                    # Try exact email match first
                    users_by_email = self.client.search_users(query=assignee, property="email")
                    if users_by_email:
                        user = users_by_email[0]
                        logger.info(f"Found user by email: {user.displayName}")
                except Exception as e:
                    logger.warning(f"Error searching by email: {str(e)}")

                # If not found by email, try by display name
                if not user:
                    try:
                        users_by_name = self.client.search_users(query=assignee)
                        if users_by_name:
                            user = users_by_name[0]
                            logger.info(f"Found user by name: {user.displayName}")
                    except Exception as e:
                        logger.warning(f"Error searching by name: {str(e)}")

                # If user found, assign the issue
                if user:
                    issue_dict['assignee'] = {'accountId': user.accountId}
                else:
                    logger.warning(f"User {assignee} not found in Jira")

            if due_date:
                issue_dict['duedate'] = due_date.strftime('%Y-%m-%d')

            if priority:
                issue_dict['priority'] = {'name': priority}

            # If parent key is provided, create a sub-task
            if parent_key:
                issue_dict['parent'] = {'key': parent_key}
                issue_dict['issuetype'] = {'name': 'Sub-task'}

            issue = self.client.create_issue(fields=issue_dict)
            logger.info(f"Created Jira issue {issue.key}: {summary}")
            return issue

        except Exception as e:
            logger.error(f"Failed to create Jira issue: {str(e)}")
            return None

    def create_dependency(self, issue_key, depends_on_key, link_type="Depends"):
        """
        Создает зависимость между задачами.

        Args:
            issue_key: Ключ зависимой задачи
            depends_on_key: Ключ задачи, от которой зависит
            link_type: Тип связи (по умолчанию "Depends")

        Returns:
            True, если зависимость успешно создана, иначе False
        """
        if not self.client:
            logger.error("Jira client is not initialized")
            return False

        try:
            # Проверяем доступные типы связей
            link_types = self.get_available_link_types()

            # Если указанный тип связи недоступен, используем первый доступный тип
            if link_type not in link_types and link_types:
                logger.warning(f"Link type '{link_type}' not found, using '{link_types[0]}' instead")
                link_type = link_types[0]

            # Создаем зависимость
            self.client.create_issue_link(
                type=link_type,
                inwardIssue=issue_key,
                outwardIssue=depends_on_key
            )
            logger.info(f"Created dependency: {issue_key} depends on {depends_on_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to create dependency between {issue_key} and {depends_on_key}: {str(e)}")
            return False

    def get_available_link_types(self):
        """
        Получает список доступных типов связей между задачами.

        Returns:
            Список доступных типов связей или пустой список в случае ошибки
        """
        if not self.client:
            return []

        try:
            link_types = self.client.issue_link_types()
            return [link_type.name for link_type in link_types]
        except Exception as e:
            logger.error(f"Failed to get link types: {str(e)}")
            return []

    def find_user(self, name):
        """
        Ищет пользователя Jira по имени.

        Args:
            name: Имя пользователя

        Returns:
            Пользователь Jira или None, если пользователь не найден
        """
        if not self.client:
            return None

        try:
            users = self.client.search_users(user=name)
            return users[0] if users else None
        except Exception as e:
            logger.error(f"Failed to find user {name}: {str(e)}")
            return None

    def get_project_issues(self, project_key, max_results=50):
        """
        Получает список задач проекта.

        Args:
            project_key: Ключ проекта в Jira
            max_results: Максимальное количество результатов

        Returns:
            Список задач проекта или пустой список в случае ошибки
        """
        if not self.client:
            return []

        try:
            issues = self.client.search_issues(
                f'project = {project_key}',
                maxResults=max_results
            )
            return issues
        except Exception as e:
            logger.error(f"Failed to get issues for project {project_key}: {str(e)}")
            return []

    def update_issue_status(self, issue_key, transition_name):
        """
        Изменяет статус задачи.

        Args:
            issue_key: Ключ задачи
            transition_name: Название перехода

        Returns:
            True, если статус успешно изменен, иначе False
        """
        if not self.client:
            return False

        try:
            issue = self.client.issue(issue_key)
            transitions = self.client.transitions(issue)

            # Ищем подходящий переход
            transition_id = None
            for t in transitions:
                if t['name'].lower() == transition_name.lower():
                    transition_id = t['id']
                    break

            if transition_id:
                self.client.transition_issue(issue, transition_id)
                logger.info(f"Changed status of issue {issue_key} to '{transition_name}'")
                return True
            else:
                logger.warning(f"Transition '{transition_name}' not found for issue {issue_key}")
                return False

        except Exception as e:
            logger.error(f"Failed to update status of issue {issue_key}: {str(e)}")
            return False