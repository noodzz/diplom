"""
Модуль для работы с импортом данных из CSV-файлов
"""
import csv
import io
import logging
from database.operations import (
    create_new_project, add_project_task,
    add_task_dependencies, Session
)
from database.models import Project, Task, TaskDependency

logger = logging.getLogger(__name__)


def parse_csv_tasks(csv_data):
    """
    Парсит CSV-файл с задачами.

    Формат CSV:
    name,duration,position,predecessors

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
            if not all(field in row for field in ['name', 'duration', 'position']):
                logger.error("В CSV отсутствуют обязательные поля")
                return []

            try:
                # Пытаемся преобразовать длительность в число
                duration = int(row['duration'])
            except ValueError:
                logger.error(f"Некорректная длительность для задачи: {row['name']}")
                return []

            task = {
                'name': row['name'],
                'duration': duration,
                'position': row['position'],
                'predecessors': []
            }

            # Парсим предшественников, если они указаны
            if 'predecessors' in row and row['predecessors']:
                task['predecessors'] = [pred.strip() for pred in row['predecessors'].split(',')]

            tasks.append(task)

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
        required_fields = ['name', 'duration', 'position']
        missing_fields = [field for field in required_fields if field not in header]

        if missing_fields:
            return False, f"В CSV отсутствуют обязательные поля: {', '.join(missing_fields)}"

        # Проверяем хотя бы одну строку данных
        first_row = next(reader, None)
        if not first_row:
            return False, "CSV-файл не содержит данных"

        return True, "CSV-файл корректен"

    except Exception as e:
        return False, f"Ошибка при проверке CSV: {str(e)}"


def create_project_from_csv(project_name, csv_data):
    """
    Создает проект на основе CSV-файла с задачами.

    Args:
        project_name: Название нового проекта
        csv_data: Содержимое CSV-файла

    Returns:
        ID созданного проекта или None в случае ошибки
    """
    # Парсим задачи из CSV
    tasks = parse_csv_tasks(csv_data)

    if not tasks:
        logger.error("Не удалось распарсить задачи из CSV")
        return None

    session = Session()
    try:
        # Создаем новый проект
        project = Project(name=project_name)
        session.add(project)
        session.flush()

        # Словарь для соответствия названия задачи -> ID созданной задачи
        task_name_map = {}

        # Создаем задачи для проекта
        for task_data in tasks:
            task = Task(
                project_id=project.id,
                name=task_data['name'],
                duration=task_data['duration'],
                position=task_data['position']
            )
            session.add(task)
            session.flush()

            # Сохраняем соответствие название -> ID
            task_name_map[task_data['name']] = task.id

        # Добавляем зависимости между задачами
        for task_data in tasks:
            if 'predecessors' in task_data and task_data['predecessors']:
                for predecessor_name in task_data['predecessors']:
                    if predecessor_name in task_name_map:
                        task_dependency = TaskDependency(
                            task_id=task_name_map[task_data['name']],
                            predecessor_id=task_name_map[predecessor_name]
                        )
                        session.add(task_dependency)

        session.commit()
        logger.info(f"Создан проект из CSV: {project_name} (ID: {project.id})")
        return project.id

    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при создании проекта из CSV: {str(e)}")
        return None

    finally:
        session.close()


def generate_sample_csv():
    """
    Генерирует пример CSV-файла с задачами.

    Returns:
        Строка с примером CSV
    """
    sample_data = """name,duration,position,predecessors
Расчёт стоимостей,3,Проектный менеджер,
Создание тарифов обучения,1,Технический специалист,Расчёт стоимостей
Создание продуктовых типов и продуктов,2,Старший тех. специалист,Создание тарифов обучения
Создание потоков обучения,2,Старший тех. специалист,Создание продуктовых типов и продуктов
Создание тарифов для внешнего сайта,1,Старший тех. специалист,Создание тарифов обучения
Создание модулей обучения,2,Руководитель контента,
Настройка связей между потоками и модулями,1,Старший специалист,"Создание потоков обучения,Создание модулей обучения"
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
        writer.writerow(['name', 'duration', 'position', 'predecessors'])

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
                ','.join(predecessors)
            ])

        return output.getvalue()

    except Exception as e:
        logger.error(f"Ошибка при экспорте проекта в CSV: {str(e)}")
        return None

    finally:
        session.close()