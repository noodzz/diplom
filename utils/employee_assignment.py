"""
Function to automatically assign employees from the database to a project
based on required positions in the project tasks.
"""

from database.operations import add_employee_to_project, Session
from database.models import Project, Task, Employee
from logger import logger


def auto_assign_employees_to_project(project_id):
    """
    Automatically assigns ALL employees from the database to a project
    regardless of position requirements.

    Args:
        project_id: ID of the project to assign employees to

    Returns:
        list: List of assigned employee IDs
    """
    session = Session()
    assigned_employee_ids = []

    try:
        # Get the project
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            logger.error(f"Project not found: {project_id}")
            return []

        # Get ALL employees directly from the database
        employees = session.query(Employee).all()

        if not employees:
            logger.warning("No employees found in the database")
            return []

        logger.info(f"Found {len(employees)} employees in the database")

        # Add ALL employees to the project
        for employee in employees:
            if employee not in project.employees:
                project.employees.append(employee)
                assigned_employee_ids.append(employee.id)
                logger.info(f"Assigned employee {employee.name} (ID: {employee.id}) to project {project_id}")

        session.commit()
        logger.info(f"Total {len(assigned_employee_ids)} employees assigned to project {project_id}")

    except Exception as e:
        session.rollback()
        logger.error(f"Error auto-assigning employees to project {project_id}: {str(e)}")
        return []

    finally:
        session.close()

    return assigned_employee_ids


def get_required_positions_from_csv_tasks(csv_tasks):
    """
    Extracts required positions from a list of parsed CSV tasks.

    Args:
        csv_tasks: List of task dictionaries parsed from CSV

    Returns:
        set: Set of required positions
    """
    required_positions = set()

    for task in csv_tasks:
        # Add position from main task
        if task.get('position'):
            required_positions.add(task['position'])

        # Add positions from roles_info or assignee_roles if present
        if task.get('has_multiple_roles') and task.get('assignee_roles'):
            for role in task['assignee_roles']:
                if role.get('position'):
                    required_positions.add(role['position'])

    return required_positions

def assign_all_employees_to_project(project_id):
    """
    Назначает всех сотрудников из базы данных на указанный проект.

    Args:
        project_id: ID проекта

    Returns:
        int: Количество назначенных сотрудников
    """
    session = Session()
    count = 0

    try:
        # Получаем проект
        project = session.query(Project).get(project_id)
        if not project:
            logger.error(f"Проект с ID {project_id} не найден")
            return 0

        # Получаем всех сотрудников
        all_employees = session.query(Employee).all()
        if not all_employees:
            logger.warning("В базе данных не найдено сотрудников")
            return 0

        logger.info(f"Найдено {len(all_employees)} сотрудников для назначения на проект {project_id}")

        # Назначаем каждого сотрудника на проект
        for employee in all_employees:
            if employee not in project.employees:
                project.employees.append(employee)
                count += 1
                logger.info(f"Сотрудник {employee.name} ({employee.position}) назначен на проект {project_id}")

        session.commit()
        logger.info(f"Всего назначено {count} сотрудников на проект {project_id}")
        return count

    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при назначении сотрудников на проект: {str(e)}")
        return 0

    finally:
        session.close()