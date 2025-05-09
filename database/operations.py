from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Project, Task, TaskDependency, Employee, DayOff, ProjectTemplate, TaskTemplate, \
    TaskTemplateDependency, AllowedUser
from config import DATABASE_URL
from logger import logger

def fuzzy_position_match(db_position, search_position):
    """Нечеткое сопоставление должностей"""
    if not db_position or not search_position:
        return False
        
    db_position_lower = db_position.lower().strip()
    search_position_lower = search_position.lower().strip()
    
    # Точное соответствие
    if db_position_lower == search_position_lower:
        return True
        
    # Стандартизация некоторых должностей
    variations = {
        "старший технический специалист": ["старший тех. специалист", "ст. тех. специалист", "старший тех специалист", "ст. технический специалист"],
        "технический специалист": ["тех. специалист", "тех специалист"],
        "руководитель настройки": ["руководитель сектора настройки"],
    }
    
    # Проверяем вариации
    for standard, variants in variations.items():
        if search_position_lower == standard:
            return db_position_lower in variants or any(v in db_position_lower for v in variants)
        elif db_position_lower == standard:
            return search_position_lower in variants or any(v in search_position_lower for v in variants)
    
    # Проверяем частичное соответствие
    return search_position_lower in db_position_lower or db_position_lower in search_position_lower

# Создаем соединение с БД
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def init_db():
    """Инициализирует базу данных."""
    logger.info(f"Инициализация базы данных с URL: {DATABASE_URL}")
    try:
        Base.metadata.create_all(engine)
        logger.info("База данных успешно инициализирована")
        
        # Проверяем, есть ли базовый проект
        session = Session()
        try:
            base_project = session.query(Project).filter(Project.name == "Базовый проект").first()

            if not base_project:
                # Создаем базовый проект
                base_project = Project(name="Базовый проект")
                session.add(base_project)
                session.flush()

                # Создаем базовых сотрудников
                default_employees = [
                    {
                        "name": "Иванов Иван Иванович",
                        "position": "Технический специалист",
                        "days_off": ["Среда", "Пятница"]
                    },
                    {
                        "name": "Петров Петр Петрович",
                        "position": "Старший технический специалист",
                        "days_off": ["Суббота", "Воскресенье"]
                    },
                    {
                        "name": "Сидоров Сидор Сидорович",
                        "position": "Руководитель настройки",
                        "days_off": ["Суббота", "Воскресенье"]
                    },
                    {
                        "name": "Смирнова Анна Ивановна",
                        "position": "Младший специалист",
                        "days_off": ["Суббота", "Воскресенье"]
                    },
                    {
                        "name": "Кузнецов Алексей Петрович",
                        "position": "Старший специалист",
                        "days_off": ["Суббота", "Воскресенье"]
                    },
                    {
                        "name": "Соколова Мария Александровна",
                        "position": "Руководитель контента",
                        "days_off": ["Суббота", "Воскресенье"]
                    }
                ]

                for emp_data in default_employees:
                    employee = Employee(
                        name=emp_data["name"],
                        position=emp_data["position"]
                    )
                    session.add(employee)
                    session.flush()

                    for day in emp_data["days_off"]:
                        day_off = DayOff(
                            employee_id=employee.id,
                            day=day
                        )
                        session.add(day_off)

                session.commit()
                logger.info("Базовые данные успешно инициализированы")
            else:
                logger.info("Базовые данные уже существуют")
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {str(e)}")
        raise


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


def add_project_task(project_id, name, duration, position, required_employees=1):
    """
    Добавляет задачу в проект.

    Args:
        project_id: ID проекта
        name: Название задачи
        duration: Длительность задачи в днях
        position: Должность исполнителя
        required_employees: Количество сотрудников (по умолчанию 1)


    Returns:
        ID созданной задачи
    """
    session = Session()
    try:
        task = Task(
            project_id=project_id,
            name=name,
            duration=duration,
            position=position,
            required_employees=required_employees

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


def add_project_employee(name, position, days_off, email=None, project_id=None):
    """
    Adds an employee to a project, checking for duplicates.

    Args:
        name: Full name of the employee
        position: Position of the employee
        days_off: List of days off
        email: Email of the employee (optional)

    Returns:
        ID of the created employee or existing employee if duplicate
    """
    session = Session()
    try:
        if project_id:
            logger.info(f"Попытка добавления сотрудника в проект {project_id}: {name} ({position})")
        else:
            logger.info(f"Попытка добавления сотрудника: {name} ({position})")
            
        # Проверяем, существует ли уже такой сотрудник в проекте
        query = session.query(Employee).filter(
            Employee.name == name,
            Employee.position == position
        )
            
        existing_employee = query.first()
        
        if existing_employee:
            # Если сотрудник уже существует, возвращаем его ID
            logger.info(f"Сотрудник '{name}' уже существует в проекте с ID {existing_employee.id}")
            return existing_employee.id
            
        # Если нет, создаем нового сотрудника
        employee = Employee(
            name=name,
            position=position,
            email=email
        )
        session.add(employee)
        session.flush()
        logger.info(f"Создан новый сотрудник '{name}' с ID {employee.id}")

        for day in days_off:
            day_off = DayOff(
                employee_id=employee.id,
                day=day
            )
            session.add(day_off)
            logger.info(f"Добавлен выходной день {day} для сотрудника {employee.id}")

        session.commit()
        return employee.id
    except Exception as e:
        logger.error(f"Ошибка при добавлении сотрудника: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()


def get_employees_by_position(project_id=None, position=None):
    """
    Получает список сотрудников по должности с нечетким сопоставлением.
    """
    session = Session()
    try:
        # Базовый запрос
        query = session.query(Employee)

        # Отладочный вывод
        logger.info("Доступные должности в базе данных:")
        all_positions = session.query(Employee.position).distinct().all()
        for pos in all_positions:
            logger.info(f"  - '{pos[0]}'")
        logger.info(f"Ищем должность: '{position}'")

        # Получаем всех сотрудников
        all_employees = query.all()
        logger.info(f"Всего сотрудников в запросе: {len(all_employees)}")
        
        # Фильтруем вручную
        result = []
        for employee in all_employees:
            # Если должность не указана или есть нечеткое совпадение
            if not position or fuzzy_position_match(employee.position, position):
                days_off = session.query(DayOff).filter(DayOff.employee_id == employee.id).all()
                days_off_list = [day.day for day in days_off]
                
                result.append({
                    'id': employee.id,
                    'name': employee.name,
                    'position': employee.position,
                    'email': employee.email,
                    'days_off': days_off_list
                })
                logger.info(f"Подходящий сотрудник: {employee.name}, должность: '{employee.position}'")

        logger.info(f"Найдено подходящих сотрудников: {len(result)}")
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
    with session_scope() as session:
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
                'predecessors': predecessor_ids,
                'required_employees': task.required_employees
            })

        # Get project employees
        project = session.query(Project).filter(Project.id == project_id).first()
        employees = project.employees if project else []        
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


def create_project_template(name, description=None):
    """
    Создает новый шаблон проекта в БД.

    Args:
        name: Название шаблона
        description: Описание шаблона (необязательно)

    Returns:
        ID созданного шаблона
    """
    with session_scope() as session:
        template = ProjectTemplate(name=name, description=description)
        session.add(template)
        session.commit()
        return template.id


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
    with session_scope() as session:
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


def add_task_template_dependency(task_id, predecessor_id):
    """
    Добавляет зависимость между шаблонами задач.

    Args:
        task_id: ID зависимой задачи
        predecessor_id: ID предшествующей задачи

    Returns:
        ID созданной зависимости
    """
    with session_scope() as session:
        dependency = TaskTemplateDependency(
            task_id=task_id,
            predecessor_id=predecessor_id
        )
        session.add(dependency)
        session.commit()
        return dependency.id


def get_project_templates():
    """
    Получает список всех шаблонов проектов.

    Returns:
        Список шаблонов проектов
    """
    with session_scope() as session:
        templates = session.query(ProjectTemplate).all()
        result = []

        for template in templates:
            result.append({
                'id': template.id,
                'name': template.name,
                'description': template.description
            })

        return result


def get_template_tasks(template_id):
    """
    Получает список задач шаблона проекта.

    Args:
        template_id: ID шаблона проекта

    Returns:
        Список задач шаблона
    """
    with session_scope() as session:
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


def create_project_from_template(template_id, project_name):
    """
    Creates a project based on a template.

    Args:
        template_id: ID of the project template
        project_name: Name of the new project

    Returns:
        ID of the created project
    """
    with session_scope() as session:
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


def get_user_projects(user_id=None):
    """
    Получает список проектов пользователя.

    Args:
        user_id: ID пользователя в Telegram (необязательно)

    Returns:
        Список проектов в формате [{'id': id, 'name': name, 'created_at': date, 'tasks_count': count}]
    """
    with session_scope() as session:
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


def is_user_allowed(telegram_id):
    """
    Проверяет, имеет ли пользователь доступ к боту.

    Args:
        telegram_id: Telegram ID пользователя

    Returns:
        bool: True, если пользователь имеет доступ, иначе False
    """
    with session_scope() as session:
        user = session.query(AllowedUser).filter(AllowedUser.telegram_id == telegram_id).first()
        return user is not None


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
    with session_scope() as session:
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


def get_allowed_users():
    """
    Получает список всех разрешенных пользователей.

    Returns:
        List[dict]: Список словарей с данными пользователей
    """
    with session_scope() as session:
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


def get_all_positions():
    """
    Получает список всех уникальных должностей из базы данных.

    Returns:
        List[str]: Список уникальных должностей
    """
    with session_scope() as session:
        positions = session.query(Employee.position).distinct().all()
        return [position[0] for position in positions]


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

def add_employee_to_project(employee_id, project_id):
    session = Session()
    try:
        employee = session.query(Employee).get(employee_id)
        project = session.query(Project).get(project_id)
        if employee and project and employee not in project.employees:
            project.employees.append(employee)
            session.commit()
            return True
        return False
    finally:
        session.close()