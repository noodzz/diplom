from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Project, Task, TaskDependency, Employee, DayOff, ProjectTemplate, TaskTemplate, TaskTemplateDependency
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


def add_project_employee(project_id, name, position, days_off):
    """
    Добавляет сотрудника в проект.

    Args:
        project_id: ID проекта
        name: ФИО сотрудника
        position: Должность сотрудника
        days_off: Список выходных дней

    Returns:
        ID созданного сотрудника
    """
    session = Session()
    try:
        employee = Employee(
            project_id=project_id,
            name=name,
            position=position
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
    Получает данные проекта из БД.

    Args:
        project_id: ID проекта

    Returns:
        Словарь с данными проекта
    """
    session = Session()
    try:
        project = session.query(Project).filter(Project.id == project_id).first()

        if not project:
            return None

        # Получаем задачи проекта
        tasks = session.query(Task).filter(Task.project_id == project_id).all()
        tasks_data = []

        for task in tasks:
            # Получаем зависимости задачи
            dependencies = session.query(TaskDependency).filter(TaskDependency.task_id == task.id).all()
            predecessor_ids = [dep.predecessor_id for dep in dependencies]

            tasks_data.append({
                'id': task.id,
                'name': task.name,
                'duration': task.duration,
                'position': task.position,
                'predecessors': predecessor_ids
            })

        # Получаем сотрудников проекта
        employees = session.query(Employee).filter(Employee.project_id == project_id).all()
        employees_data = []

        for employee in employees:
            # Получаем выходные дни сотрудника
            days_off = session.query(DayOff).filter(DayOff.employee_id == employee.id).all()
            days_off_list = [day.day for day in days_off]

            employees_data.append({
                'id': employee.id,
                'name': employee.name,
                'position': employee.position,
                'email': employee.email,  # Добавляем email в результат
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


def add_task_template(template_id, name, duration, position, order=0):
    """
    Добавляет шаблон задачи в шаблон проекта.

    Args:
        template_id: ID шаблона проекта
        name: Название задачи
        duration: Длительность задачи в днях
        position: Должность исполнителя
        order: Порядковый номер задачи

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
            order=order
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
    Создает проект на основе шаблона.

    Args:
        template_id: ID шаблона проекта
        project_name: Название нового проекта

    Returns:
        ID созданного проекта
    """
    session = Session()
    try:
        # Создаем новый проект
        project = Project(name=project_name)
        session.add(project)
        session.flush()

        # Получаем задачи шаблона
        template_tasks = session.query(TaskTemplate).filter(TaskTemplate.template_id == template_id).order_by(
            TaskTemplate.order).all()

        # Словарь для соответствия ID шаблона задачи -> ID созданной задачи
        task_id_map = {}

        # Создаем задачи для проекта
        for template_task in template_tasks:
            task = Task(
                project_id=project.id,
                name=template_task.name,
                duration=template_task.duration,
                position=template_task.position
            )
            session.add(task)
            session.flush()

            # Сохраняем соответствие ID
            task_id_map[template_task.id] = task.id

        # Добавляем зависимости между задачами
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
