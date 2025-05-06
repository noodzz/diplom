from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Project, Task, TaskDependency, Employee, DayOff, ProjectTemplate, TaskTemplate, \
    TaskTemplateDependency, AllowedUser
from config import DATABASE_URL
from logger import logger

# Создаем соединение с БД
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def init_db():
    """Инициализирует базу данных."""
    Base.metadata.create_all(engine)


def create_new_project(name):
    """
    Создает новый проект в БД.

    Args:
        name: Название проекта

    Returns:
        ID созданного проекта
    """
    session = Session()
    try:
        project = Project(name=name)
        session.add(project)
        session.commit()
        return project.id
    finally:
        session.close()


def add_project_task(project_id, name, duration, position):
    """
    Добавляет задачу в проект.

    Args:
        project_id: ID проекта
        name: Название задачи
        duration: Длительность задачи в днях
        position: Должность исполнителя

    Returns:
        ID созданной задачи
    """
    session = Session()
    try:
        task = Task(
            project_id=project_id,
            name=name,
            duration=duration,
            position=position
        )
        session.add(task)
        session.commit()
        return task.id
    finally:
        session.close()


def add_task_dependencies(task_id, predecessor_id):
    """
    Добавляет зависимость между задачами.

    Args:
        task_id: ID зависимой задачи
        predecessor_id: ID предшествующей задачи

    Returns:
        ID созданной зависимости
    """
    session = Session()
    try:
        dependency = TaskDependency(
            task_id=task_id,
            predecessor_id=predecessor_id
        )
        session.add(dependency)
        session.commit()
        return dependency.id
    finally:
        session.close()


def add_project_employee(project_id, name, position, days_off, email=None):
    """
    Adds an employee to a project.

    Args:
        project_id: ID of the project
        name: Full name of the employee
        position: Position of the employee
        days_off: List of days off
        email: Email of the employee (optional)

    Returns:
        ID of the created employee
    """
    session = Session()
    try:
        employee = Employee(
            project_id=project_id,
            name=name,
            position=position,
            email=email
        )
        session.add(employee)
        session.flush()

        for day in days_off:
            day_off = DayOff(
                employee_id=employee.id,
                day=day
            )
            session.add(day_off)

        session.commit()
        return employee.id
    finally:
        session.close()


def get_employees_by_position(project_id, position=None):
    """
    Получает список сотрудников проекта по должности.

    Args:
        project_id: ID проекта
        position: Должность сотрудников (необязательно)

    Returns:
        Список сотрудников
    """
    session = Session()
    try:
        query = session.query(Employee).filter(Employee.project_id == project_id)

        if position:
            query = query.filter(Employee.position == position)

        employees = query.all()

        result = []
        for employee in employees:
            days_off = session.query(DayOff).filter(DayOff.employee_id == employee.id).all()
            days_off_list = [day.day for day in days_off]

            result.append({
                'id': employee.id,
                'name': employee.name,
                'position': employee.position,
                'email': employee.email,  # Добавляем email в результат
                'days_off': days_off_list
            })

        return result
    finally:
        session.close()


def get_project_data(project_id):
    """
    Gets project data from the database.

    Args:
        project_id: Project ID

    Returns:
        Project data dictionary
    """
    session = Session()
    try:
        project = session.query(Project).filter(Project.id == project_id).first()

        if not project:
            return None

        # Get project tasks
        tasks = session.query(Task).filter(Task.project_id == project_id).all()
        print(f"Database tasks for project {project_id}: {len(tasks)}")

        tasks_data = []
        for task in tasks:
            # Get task dependencies
            dependencies = session.query(TaskDependency).filter(TaskDependency.task_id == task.id).all()
            predecessor_ids = [dep.predecessor_id for dep in dependencies]

            tasks_data.append({
                'id': task.id,
                'name': task.name,
                'duration': task.duration,
                'position': task.position,
                'predecessors': predecessor_ids
            })

        # Get project employees
        employees = session.query(Employee).filter(Employee.project_id == project_id).all()
        employees_data = []

        for employee in employees:
            days_off = session.query(DayOff).filter(DayOff.employee_id == employee.id).all()
            days_off_list = [day.day for day in days_off]

            employees_data.append({
                'id': employee.id,
                'name': employee.name,
                'position': employee.position,
                'email': employee.email,
                'days_off': days_off_list
            })

        return {
            'id': project.id,
            'name': project.name,
            'tasks': tasks_data,
            'employees': employees_data
        }
    finally:
        session.close()


def create_project_template(name, description=None):
    """
    Создает новый шаблон проекта в БД.

    Args:
        name: Название шаблона
        description: Описание шаблона (необязательно)

    Returns:
        ID созданного шаблона
    """
    session = Session()
    try:
        template = ProjectTemplate(name=name, description=description)
        session.add(template)
        session.commit()
        return template.id
    finally:
        session.close()


def add_task_template(template_id, name, duration, position, order=0,required_employees=1):
    """
    Добавляет шаблон задачи в шаблон проекта.

    Args:
        template_id: ID шаблона проекта
        name: Название задачи
        duration: Длительность задачи в днях
        position: Должность исполнителя
        order: Порядковый номер задачи
        required_employees: Number of employees required (default: 1)

    Returns:
        ID созданного шаблона задачи
    """
    session = Session()
    try:
        task = TaskTemplate(
            template_id=template_id,
            name=name,
            duration=duration,
            position=position,
            order=order,
            required_employees=required_employees
        )
        session.add(task)
        session.commit()
        return task.id
    finally:
        session.close()


def add_task_template_dependency(task_id, predecessor_id):
    """
    Добавляет зависимость между шаблонами задач.

    Args:
        task_id: ID зависимой задачи
        predecessor_id: ID предшествующей задачи

    Returns:
        ID созданной зависимости
    """
    session = Session()
    try:
        dependency = TaskTemplateDependency(
            task_id=task_id,
            predecessor_id=predecessor_id
        )
        session.add(dependency)
        session.commit()
        return dependency.id
    finally:
        session.close()


def get_project_templates():
    """
    Получает список всех шаблонов проектов.

    Returns:
        Список шаблонов проектов
    """
    session = Session()
    try:
        templates = session.query(ProjectTemplate).all()
        result = []

        for template in templates:
            result.append({
                'id': template.id,
                'name': template.name,
                'description': template.description
            })

        return result
    finally:
        session.close()


def get_template_tasks(template_id):
    """
    Получает список задач шаблона проекта.

    Args:
        template_id: ID шаблона проекта

    Returns:
        Список задач шаблона
    """
    session = Session()
    try:
        tasks = session.query(TaskTemplate).filter(TaskTemplate.template_id == template_id).order_by(
            TaskTemplate.order).all()
        result = []

        for task in tasks:
            # Получаем зависимости задачи
            dependencies = session.query(TaskTemplateDependency).filter(TaskTemplateDependency.task_id == task.id).all()
            predecessor_ids = [dep.predecessor_id for dep in dependencies]

            result.append({
                'id': task.id,
                'name': task.name,
                'duration': task.duration,
                'position': task.position,
                'order': task.order,
                'predecessors': predecessor_ids
            })

        return result
    finally:
        session.close()


def create_project_from_template(template_id, project_name):
    """
    Creates a project based on a template.

    Args:
        template_id: ID of the project template
        project_name: Name of the new project

    Returns:
        ID of the created project
    """
    session = Session()
    try:
        # Create a new project
        project = Project(name=project_name)
        session.add(project)
        session.flush()

        # Get template tasks
        template_tasks = session.query(TaskTemplate).filter(TaskTemplate.template_id == template_id).order_by(
            TaskTemplate.order).all()

        # Dictionary to map template task ID to created task ID
        task_id_map = {}

        # Create tasks for the project
        for template_task in template_tasks:
            # Check if the template_task has required_employees attribute
            req_employees = getattr(template_task, 'required_employees', 1)

            task = Task(
                project_id=project.id,
                name=template_task.name,
                duration=template_task.duration,
                position=template_task.position,
                required_employees=req_employees
            )
            session.add(task)
            session.flush()

            # Save ID mapping
            task_id_map[template_task.id] = task.id

        # Add dependencies between tasks
        for template_task in template_tasks:
            dependencies = session.query(TaskTemplateDependency).filter(
                TaskTemplateDependency.task_id == template_task.id).all()

            for dependency in dependencies:
                if dependency.predecessor_id in task_id_map and template_task.id in task_id_map:
                    task_dependency = TaskDependency(
                        task_id=task_id_map[template_task.id],
                        predecessor_id=task_id_map[dependency.predecessor_id]
                    )
                    session.add(task_dependency)

        session.commit()
        return project.id
    finally:
        session.close()


def get_user_projects(user_id=None):
    """
    Получает список проектов пользователя.

    Args:
        user_id: ID пользователя в Telegram (необязательно)

    Returns:
        Список проектов в формате [{'id': id, 'name': name, 'created_at': date, 'tasks_count': count}]
    """
    session = Session()
    try:
        query = session.query(Project)

        # Если будет добавлена привязка к пользователю, можно раскомментировать
        # if user_id:
        #     query = query.filter(Project.user_id == user_id)

        projects = query.order_by(Project.created_at.desc()).all()

        result = []
        for project in projects:
            # Получаем количество задач в проекте
            tasks_count = session.query(Task).filter(Task.project_id == project.id).count()

            # Форматируем дату создания
            created_at = project.created_at.strftime("%d.%m.%Y %H:%M") if project.created_at else "Н/Д"

            result.append({
                'id': project.id,
                'name': project.name,
                'created_at': created_at,
                'tasks_count': tasks_count
            })

        return result
    except Exception as e:
        logger.error(f"Error retrieving projects: {str(e)}")
        return []
    finally:
        session.close()


def is_user_allowed(telegram_id):
    """
    Проверяет, имеет ли пользователь доступ к боту.

    Args:
        telegram_id: Telegram ID пользователя

    Returns:
        bool: True, если пользователь имеет доступ, иначе False
    """
    session = Session()
    try:
        user = session.query(AllowedUser).filter(AllowedUser.telegram_id == telegram_id).first()
        return user is not None
    finally:
        session.close()


def add_allowed_user(telegram_id, name=None, added_by=None, is_admin=False):
    """
    Добавляет пользователя в список разрешенных.

    Args:
        telegram_id: Telegram ID пользователя
        name: Имя пользователя (опционально)
        added_by: ID администратора, добавившего пользователя (опционально)
        is_admin: Флаг администратора (по умолчанию False)

    Returns:
        bool: True, если пользователь успешно добавлен, иначе False
    """
    session = Session()
    try:
        # Проверяем, не добавлен ли пользователь уже
        existing = session.query(AllowedUser).filter(AllowedUser.telegram_id == telegram_id).first()
        if existing:
            return False

        user = AllowedUser(
            telegram_id=telegram_id,
            name=name,
            added_by=added_by,
            is_admin=is_admin
        )
        session.add(user)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при добавлении пользователя: {str(e)}")
        return False
    finally:
        session.close()


def get_allowed_users():
    """
    Получает список всех разрешенных пользователей.

    Returns:
        List[dict]: Список словарей с данными пользователей
    """
    session = Session()
    try:
        users = session.query(AllowedUser).all()
        result = []

        for user in users:
            result.append({
                'id': user.id,
                'telegram_id': user.telegram_id,
                'name': user.name,
                'is_admin': user.is_admin,
                'added_at': user.added_at.strftime("%d.%m.%Y %H:%M")
            })

        return result
    finally:
        session.close()


def remove_allowed_user(telegram_id):
    """
    Удаляет пользователя из списка разрешенных.

    Args:
        telegram_id: Telegram ID пользователя

    Returns:
        bool: True, если пользователь успешно удален, иначе False
    """
    with session_scope() as session:
        user = session.query(AllowedUser).filter(
            AllowedUser.telegram_id == telegram_id
        ).first()

        if not user:
            return False

        session.delete(user)
        return True

@contextmanager
def session_scope():
    """
    Контекстный менеджер для работы с сессиями SQLAlchemy.
    Автоматически выполняет commit при успешном завершении
    и rollback при возникновении исключения.
    """
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при работе с БД: {str(e)}")
        raise
    finally:
        session.close()