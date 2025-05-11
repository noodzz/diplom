"""
Function to automatically assign employees from the database to a project
based on required positions in the project tasks.
"""

from database.operations import get_employees_by_position, add_employee_to_project, Session
from database.models import Project, Task
from logger import logger


def auto_assign_employees_to_project(project_id):
    """
    Automatically assigns employees from the database to a project
    based on the positions required by the project's tasks.

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

        # Get project tasks
        tasks = session.query(Task).filter(Task.project_id == project_id).all()
        if not tasks:
            logger.info(f"No tasks found for project: {project_id}")
            return []

        # Get unique positions from tasks
        required_positions = set()
        for task in tasks:
            if task.position:
                required_positions.add(task.position)

            # Also check task parts if they exist (for multi-role tasks)
            for part in task.parts:
                if part.position:
                    required_positions.add(part.position)

        logger.info(f"Required positions for project {project_id}: {required_positions}")

        # Find employees for each required position
        for position in required_positions:
            # Get employees for this position
            employees = get_employees_by_position(position=position)

            if not employees:
                logger.warning(f"No employees found for position: {position}")
                continue

            # Add all employees with this position to the project
            for employee in employees:
                # Check if employee is already assigned to avoid duplicates
                if employee['id'] not in assigned_employee_ids:
                    add_employee_to_project(employee['id'], project_id)
                    assigned_employee_ids.append(employee['id'])
                    logger.info(f"Assigned employee {employee['name']} (ID: {employee['id']}) to project {project_id}")

    except Exception as e:
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