"""
Модуль для работы с импортом данных из CSV-файлов
"""
import csv
import io
import json
import logging
from database.operations import (
    create_new_project, add_project_task,
    add_task_dependencies, Session
)
from database.models import Project, Task, TaskDependency, TaskPart

logger = logging.getLogger(__name__)


def parse_csv_tasks(csv_data):
    """
    Парсит CSV-файл с задачами.

    Формат CSV:
    name,duration,position,predecessors,required_employees,roles_info

    Где roles_info - строка с описанием ролей и их продолжительностей в формате:
    "Технический специалист:1|Старший технический специалист:2"

    Args:
        csv_data: Содержимое CSV-файла

    Returns:
        Список задач
    """
    tasks = []

    try:
        # Если данные в виде строки, преобразуем в StringIO
        if isinstance(csv_data, str):
            csv_data = io.StringIO(csv_data)

        # Читаем CSV
        reader = csv.DictReader(csv_data)

        for row in reader:
            # Проверяем наличие обязательных полей
            if not all(field in row for field in ['name', 'duration']):
                logger.error("В CSV отсутствуют обязательные поля")
                return []

            try:
                # Пытаемся преобразовать длительность в число
                duration = int(row['duration'])

                # Пытаемся преобразовать количество сотрудников в число,
                # если поле есть, иначе устанавливаем 1 по умолчанию
                required_employees = 1
                if 'required_employees' in row and row['required_employees']:
                    required_employees = int(row['required_employees'])

                # Проверяем наличие поля roles_info и пытаемся его распарсить
                assignee_roles = []
                if 'roles_info' in row and row['roles_info']:
                    for role_part in row['roles_info'].split('|'):
                        if ':' in role_part:
                            position, role_duration = role_part.split(':')
                            assignee_roles.append({
                                "position": position.strip(),
                                "duration": int(role_duration.strip())
                            })

                # Определяем, имеет ли задача несколько исполнителей с разными ролями
                has_multiple_roles = len(assignee_roles) > 0

                task = {
                    'name': row['name'],
                    'duration': duration,
                    'position': row.get('position', '') if not has_multiple_roles else '',
                    'required_employees': required_employees if not has_multiple_roles else 1,
                    'predecessors': [],
                    'has_multiple_roles': has_multiple_roles,
                    'assignee_roles': assignee_roles
                }

                # Парсим предшественников, если они указаны
                if 'predecessors' in row and row['predecessors']:
                    task['predecessors'] = [pred.strip() for pred in row['predecessors'].split(',')]

                tasks.append(task)

            except ValueError as e:
                logger.error(f"Некорректные числовые значения для задачи: {row['name']}: {str(e)}")
                return []

        # Проверяем корректность зависимостей
        task_names = {task['name'] for task in tasks}
        for task in tasks:
            for predecessor in task['predecessors']:
                if predecessor not in task_names:
                    logger.warning(f"Зависимость от несуществующей задачи: {predecessor} для задачи {task['name']}")

        return tasks
    except Exception as e:
        logger.error(f"Ошибка при парсинге CSV: {str(e)}")
        return []


def validate_csv_format(csv_content):
    """
    Проверяет корректность формата CSV-файла.

    Args:
        csv_content: Содержимое CSV-файла

    Returns:
        (bool, str): Результат проверки и сообщение об ошибке
    """
    try:
        # Если данные в виде строки, преобразуем в StringIO
        if isinstance(csv_content, str):
            csv_data = io.StringIO(csv_content)
        else:
            csv_data = csv_content
            csv_data.seek(0)

        # Читаем заголовок CSV
        reader = csv.reader(csv_data)
        header = next(reader, None)

        if not header:
            return False, "CSV-файл пуст"

        # Проверяем наличие всех необходимых полей
        required_fields = ['name', 'duration']
        missing_fields = [field for field in required_fields if field not in header]

        if missing_fields:
            return False, f"В CSV отсутствуют обязательные поля: {', '.join(missing_fields)}"

        # Проверяем хотя бы одну строку данных
        first_row = next(reader, None)
        if not first_row:
            return False, "CSV-файл не содержит данных"

        # Проверяем, есть ли поле roles_info, если есть assignee_roles
        if 'assignee_roles' in header and 'roles_info' not in header:
            return False, "Обнаружено устаревшее поле 'assignee_roles'. Используйте 'roles_info' с форматом 'Должность:длительность|Должность:длительность'"

        return True, "CSV-файл корректен"

    except Exception as e:
        return False, f"Ошибка при проверке CSV: {str(e)}"


def create_project_from_tasks(project_name, tasks):
    """
    Creates a project based on a list of parsed tasks.

    Args:
        project_name: Name of the new project
        tasks: List of parsed task data

    Returns:
        ID of the created project or None on error
    """
    session = Session()
    try:
        # Create new project
        project = Project(name=project_name)
        session.add(project)
        session.flush()

        # Dictionary to map task name to created task ID
        task_name_map = {}

        # Create tasks for the project
        for task_data in tasks:
            # Check if task has multiple roles with different positions
            if task_data.get('has_multiple_roles') and task_data.get('assignee_roles'):
                # Create parent task
                parent_task = Task(
                    project_id=project.id,
                    name=task_data['name'],
                    duration=task_data['duration'],
                    position='',  # Parent task has no specific position
                    required_employees=len(task_data['assignee_roles'])
                )
                session.add(parent_task)
                session.flush()

                task_name_map[task_data['name']] = parent_task.id

                # Create subtasks for each role
                for i, role in enumerate(task_data['assignee_roles']):
                    subtask_name = f"{task_data['name']} - {role['position']}"
                    subtask = Task(
                        project_id=project.id,
                        name=subtask_name,
                        duration=role['duration'],
                        position=role['position'],
                        required_employees=1,
                        parent_id=parent_task.id
                    )
                    session.add(subtask)
                    session.flush()

                    # Also create TaskPart record
                    task_part = TaskPart(
                        task_id=parent_task.id,
                        name=subtask_name,
                        position=role['position'],
                        duration=role['duration'],
                        order=i + 1,
                        required_employees=1
                    )
                    session.add(task_part)

                    # Add dependency on previous subtask if it exists
                    if i > 0:
                        prev_subtask_id = subtask.id - 1
                        task_dependency = TaskDependency(
                            task_id=subtask.id,
                            predecessor_id=prev_subtask_id
                        )
                        session.add(task_dependency)
            else:
                # Regular task
                task = Task(
                    project_id=project.id,
                    name=task_data['name'],
                    duration=task_data['duration'],
                    position=task_data['position'],
                    required_employees=task_data.get('required_employees', 1)
                )
                session.add(task)
                session.flush()

                task_name_map[task_data['name']] = task.id

        # Add dependencies between tasks
        for task_data in tasks:
            if 'predecessors' in task_data and task_data['predecessors']:
                task_id = task_name_map.get(task_data['name'])
                if task_id:
                    for predecessor_name in task_data['predecessors']:
                        predecessor_id = task_name_map.get(predecessor_name)
                        if predecessor_id:
                            task_dependency = TaskDependency(
                                task_id=task_id,
                                predecessor_id=predecessor_id
                            )
                            session.add(task_dependency)

        session.commit()
        logger.info(f"Created project from tasks: {project_name} (ID: {project.id})")
        return project.id

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating project from tasks: {str(e)}")
        return None

    finally:
        session.close()


def create_project_from_csv(project_name, csv_data):
    """
    Creates a project based on CSV file data.

    Args:
        project_name: Name of the new project
        csv_data: CSV file content

    Returns:
        ID of the created project or None on error
    """
    # Parse tasks from CSV
    tasks = parse_csv_tasks(csv_data)

    if not tasks:
        logger.error("Failed to parse tasks from CSV")
        return None

    return create_project_from_tasks(project_name, tasks)


def generate_sample_csv():
    """
    Генерирует пример CSV-файла с задачами.

    Returns:
        Строка с примером CSV
    """
    sample_data = """name,duration,position,predecessors,required_employees,roles_info
Расчёт стоимостей,3,Проектный менеджер,,1,
Создание тарифов обучения,1,Технический специалист,Расчёт стоимостей,1,
Создание продуктовых типов и продуктов,2,Старший тех. специалист,Создание тарифов обучения,2,
Создание потоков обучения,2,Старший тех. специалист,Создание продуктовых типов и продуктов,2,
Создание тарифов для внешнего сайта,1,Старший тех. специалист,Создание тарифов обучения,1,
Создание модулей обучения,2,Руководитель контента,,2,
Настройка связей между потоками и модулями,1,Старший специалист,"Создание потоков обучения,Создание модулей обучения",1,
Создание и настройка интерфейса,3,,"Создание тарифов обучения",1,Технический специалист:1|Старший технический специалист:2
"""
    return sample_data


def export_project_to_csv(project_id):
    """
    Экспортирует проект в CSV-файл.

    Args:
        project_id: ID проекта

    Returns:
        Строка с CSV-представлением проекта или None в случае ошибки
    """
    session = Session()
    try:
        # Получаем задачи проекта
        tasks = session.query(Task).filter(Task.project_id == project_id).all()

        if not tasks:
            logger.error(f"Проект не содержит задач (ID: {project_id})")
            return None

        # Словарь для соответствия ID задачи -> название задачи
        task_id_map = {task.id: task.name for task in tasks}

        # Словарь для хранения зависимостей задач
        task_dependencies = {}

        # Получаем зависимости задач
        for task in tasks:
            dependencies = session.query(TaskDependency).filter(TaskDependency.task_id == task.id).all()
            task_dependencies[task.id] = [dep.predecessor_id for dep in dependencies]

        # Формируем CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Записываем заголовок
        writer.writerow(['name', 'duration', 'position', 'predecessors', 'required_employees'])

        # Записываем данные задач
        for task in tasks:
            predecessors = []
            for predecessor_id in task_dependencies.get(task.id, []):
                if predecessor_id in task_id_map:
                    predecessors.append(task_id_map[predecessor_id])

            writer.writerow([
                task.name,
                task.duration,
                task.position,
                ','.join(predecessors),
                task.required_employees
            ])

        return output.getvalue()

    except Exception as e:
        logger.error(f"Ошибка при экспорте проекта в CSV: {str(e)}")
        return None

    finally:
        session.close()