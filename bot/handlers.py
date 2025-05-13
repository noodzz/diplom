from datetime import datetime, timedelta

from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from logger import logger
from bot.states import BotStates
from bot.keyboards import (
    main_menu_keyboard, project_type_keyboard, templates_keyboard,
    task_actions_keyboard, dependencies_actions_keyboard,
    employees_actions_keyboard, plan_actions_keyboard, projects_keyboard,
    position_selection_keyboard, back_to_main_keyboard
)
from bot.messages import (
    WELCOME_MESSAGE, HELP_MESSAGE, SELECT_PROJECT_TYPE_MESSAGE,
    SELECT_TEMPLATE_PROMPT, UPLOAD_CSV_PROMPT, CREATE_PROJECT_PROMPT,
    ADD_TASK_PROMPT, ADD_DEPENDENCIES_PROMPT, ADD_EMPLOYEES_PROMPT,
    PLAN_CALCULATION_START, EXPORT_TO_JIRA_SUCCESS, CSV_FORMAT_ERROR, MY_ID_MESSAGE
)
from config import ALLOWED_USERS
from database.models import AllowedUser, Employee, DayOff, Project, Task, TaskDependency, DayOff, ProjectTemplate, \
    TaskTemplate, \
    TaskTemplateDependency, TaskPart
from database.operations import (
    create_new_project, add_project_task, add_task_dependencies,
    add_project_employee, add_employee_to_project, get_project_data, get_employees_by_position,
    get_project_templates, create_project_from_template, get_user_projects, get_allowed_users, add_allowed_user,
    is_user_allowed, session_scope, get_all_positions, Session, check_circular_dependencies, get_task_dependencies
)
from utils.csv_import import create_project_from_csv, parse_csv_tasks, create_project_from_tasks
from planning.network import calculate_network_parameters
from planning.calendar import create_calendar_plan
from planning.visualization import generate_gantt_chart
from jira_integration.issue_creator import create_jira_issues
from bot.telegram_helpers import safe_edit_message_text
import telegram
import io
import csv
from datetime import datetime, timedelta


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начальный обработчик, отправляет приветственное сообщение и меню."""
    message = update.message or update.callback_query.message

    if update.callback_query:
        await update.callback_query.answer()

    await message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=main_menu_keyboard()
    )
    return BotStates.MAIN_MENU


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет справочное сообщение."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            HELP_MESSAGE,
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            HELP_MESSAGE,
            reply_markup=main_menu_keyboard()
        )
    return BotStates.MAIN_MENU


async def select_project_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора типа проекта."""
    query = update.callback_query

    if query:
        await query.answer()
        await query.edit_message_text(
            SELECT_PROJECT_TYPE_MESSAGE,
            reply_markup=project_type_keyboard()
        )
    else:
        await update.message.reply_text(
            SELECT_PROJECT_TYPE_MESSAGE,
            reply_markup=project_type_keyboard()
        )

    return BotStates.SELECT_PROJECT_TYPE


async def use_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора шаблона проекта."""
    query = update.callback_query
    await query.answer()

    # Получаем список шаблонов проектов
    templates = get_project_templates()

    if not templates:
        await safe_edit_message_text(
            query,
            "Шаблоны проектов не найдены. Пожалуйста, создайте новый проект или добавьте шаблоны.",
            reply_markup=project_type_keyboard()
        )
        return BotStates.SELECT_PROJECT_TYPE

    # Формируем сообщение со списком шаблонов
    message = SELECT_TEMPLATE_PROMPT + "\n"
    for i, template in enumerate(templates):
        message += f"{i + 1}. {template['name']}"
        if template['description']:
            message += f" - {template['description']}"
        message += "\n"

    await safe_edit_message_text(
        query,
        message,
        reply_markup=templates_keyboard(templates)
    )

    return BotStates.SELECT_TEMPLATE


async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора конкретного шаблона проекта."""
    query = update.callback_query
    await query.answer()

    # Получаем ID выбранного шаблона
    template_id = int(query.data.split('_')[1])

    # Сохраняем ID шаблона в контексте
    context.user_data['template_id'] = template_id

    # Запрашиваем название проекта
    await safe_edit_message_text(query, CREATE_PROJECT_PROMPT)

    return BotStates.CREATE_PROJECT


async def set_project_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for setting project start date."""
    query = update.callback_query
    logger.info("set_project_start_date handler called with callback_data: %s", query.data)
    await query.answer()

    # Update the message to ask for a start date
    keyboard = [
        [
            InlineKeyboardButton("Сегодня", callback_data="date_today"),
            InlineKeyboardButton("Завтра", callback_data="date_tomorrow")
        ],
        [
            InlineKeyboardButton("Через неделю", callback_data="date_plus7"),
            InlineKeyboardButton("Через 2 недели", callback_data="date_plus14")
        ],
        [
            InlineKeyboardButton("Первый день месяца", callback_data="date_month_start"),
            InlineKeyboardButton("Произвольная дата", callback_data="date_custom")
        ],
        [
            InlineKeyboardButton("Отмена", callback_data="back_to_project")
        ]
    ]

    # Update message with date selection options
    try:
        await query.edit_message_text(
            "Укажите дату начала проекта:\n\n"
            "Выберите из предложенных вариантов или нажмите 'Произвольная дата' для ввода своей даты в формате ДД.ММ.ГГГГ.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info("Date selection message sent successfully")
        return BotStates.SET_START_DATE
    except Exception as e:
        logger.error(f"Error in set_project_start_date: {str(e)}")
        # Fallback message if there's an error
        await query.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте еще раз выбрать дату начала проекта.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Отмена", callback_data="back_to_project")]
            ])
        )
        return BotStates.ADD_TASK

async def process_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the start date input from user."""

    if update.callback_query:
        query = update.callback_query
        await query.answer()

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        if query.data == "date_today":
            start_date = today
        elif query.data == "date_tomorrow":
            start_date = today + timedelta(days=1)
        elif query.data == "date_plus7":
            start_date = today + timedelta(days=7)
        elif query.data == "date_plus14":
            start_date = today + timedelta(days=14)
        elif query.data == "date_month_start":
            # First day of current month
            start_date = today.replace(day=1)
        elif query.data == "date_custom":
            return await request_custom_date(update, context)
        elif query.data == "back_to_project":
            return await select_project(update, context)
        else:
            # Unknown callback data
            logger.warning(f"Unknown callback data in process_start_date: {query.data}")
            return await select_project(update, context)

        # Store the date in context
        context.user_data['project_start_date'] = start_date

        # Save the date to database
        project_id = context.user_data.get('current_project_id')
        if project_id:
            # Import function from database.operations
            from database.operations import set_project_start_date_in_db
            success = set_project_start_date_in_db(project_id, start_date.date())

            if success:
                # Вместо BotStates.ADD_TASK возвращаем SELECT_PROJECT для правильной обработки кнопок
                return await show_project_with_message(
                    query,
                    context,
                    project_id,
                    f"Дата начала проекта установлена: {start_date.strftime('%d.%m.%Y')}"
                )
            else:
                await query.edit_message_text(
                    f"Дата начала проекта установлена: {start_date.strftime('%d.%m.%Y')}\n"
                    "⚠️ Возникла ошибка при сохранении даты в базе данных.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Назад к проекту", callback_data="back_to_project")]
                    ])
                )
                # Возвращаем состояние SELECT_PROJECT
                return BotStates.SELECT_PROJECT
        else:
            await query.edit_message_text(
                f"Дата начала проекта установлена: {start_date.strftime('%d.%m.%Y')}",
                reply_markup=main_menu_keyboard()
            )
            return BotStates.MAIN_MENU

    # Handle text input for custom date
    text = update.message.text.strip()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        if text.lower() == 'сегодня':
            start_date = today
        elif text.lower() == 'завтра':
            start_date = today + timedelta(days=1)
        elif text.startswith('+'):
            # Handle relative dates like "+5"
            days = int(text[1:])
            start_date = today + timedelta(days=days)
        else:
            # Parse date in DD.MM.YYYY format
            start_date = datetime.strptime(text, '%d.%m.%Y')

        # Store the date in context
        context.user_data['project_start_date'] = start_date

        # Save the date to database
        project_id = context.user_data.get('current_project_id')
        if project_id:
            # Import function from database.operations
            from database.operations import set_project_start_date_in_db
            set_project_start_date_in_db(project_id, start_date.date())

        # Confirm the date setting
        await update.message.reply_text(
            f"Дата начала проекта установлена: {start_date.strftime('%d.%m.%Y')}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Назад к проекту", callback_data="back_to_project")]
            ])
        )
        # Возвращаем состояние SELECT_PROJECT вместо ADD_TASK
        return BotStates.SELECT_PROJECT

    except (ValueError, IndexError):
        # Handle invalid date format
        await update.message.reply_text(
            "Неверный формат даты. Пожалуйста, укажите дату в формате ДД.ММ.ГГГГ (например, 15.05.2025) "
            "или используйте 'сегодня', 'завтра' или '+N' дней.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Отмена", callback_data="back_to_project")]
            ])
        )
        return BotStates.SET_START_DATE


async def show_project_with_message(query, context, project_id, message):
    """Show project details with a message."""
    # Get project data
    project_data = get_project_data(project_id)

    if not project_data:
        await query.edit_message_text(
            "Проект не найден или был удален.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Format project information with the message
    project_info = format_project_info(project_data, context)

    # Создаем клавиатуру для проекта
    keyboard = get_project_keyboard(project_data)

    try:
        await query.edit_message_text(
            f"{message}\n\n{project_info}",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        logger.info(f"Сообщение с информацией о проекте после установки даты отправлено успешно")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения о проекте: {str(e)}")
        # В случае ошибки отправляем новое сообщение
        await query.message.reply_text(
            f"{message}\n\n{project_info}",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    return BotStates.SELECT_PROJECT


def format_project_info(project_data, context):
    """Format project information including start date if set."""
    # Basic project info
    message = f"📊 *Проект: {project_data['name']}*\n\n"

    # Сначала пробуем взять дату из БД
    start_date = project_data.get('start_date')

    # Если даты нет в БД, пробуем взять из контекста
    if not start_date and 'project_start_date' in context.user_data:
        start_date = context.user_data['project_start_date']

    # Отображаем дату, если она есть
    if start_date:
        # Конвертируем datetime.date в строку, если это объект date
        if hasattr(start_date, 'strftime'):
            date_str = start_date.strftime('%d.%m.%Y')
        else:
            date_str = str(start_date)
        message += f"*Дата начала:* {date_str}\n\n"

    # Information about tasks
    message += f"*Задачи:* {len(project_data['tasks'])}\n\n"

    if project_data['tasks']:
        message += "*Список задач:*\n"
        for i, task in enumerate(project_data['tasks'][:5]):  # Show only first 5 tasks
            message += f"{i + 1}. {task['name']} ({task['duration']} дн.) - {task['position']}\n"

        if len(project_data['tasks']) > 5:
            message += f"... и еще {len(project_data['tasks']) - 5} задач\n"
    else:
        message += "Задачи еще не добавлены.\n"

    message += "\n*Сотрудники:* "
    if project_data['employees']:
        message += f"{len(project_data['employees'])}\n"
    else:
        message += "пока не добавлены.\n"

    return message

def get_project_keyboard(project_data):
    """Get keyboard for project actions."""
    keyboard = [
        [InlineKeyboardButton("Добавить задачи", callback_data="add_tasks")],
        [InlineKeyboardButton("Добавить сотрудников", callback_data="add_employees")],
        [InlineKeyboardButton("Назначить всех сотрудников", callback_data="assign_all_employees")],  # Новая кнопка
        [InlineKeyboardButton("Установить дату начала", callback_data="set_start_date")],
        [InlineKeyboardButton("Рассчитать календарный план", callback_data="calculate")],
        [InlineKeyboardButton("Назад к списку проектов", callback_data="list_projects")],
        [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def upload_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик загрузки CSV-файла."""
    query = update.callback_query

    if query:
        await query.answer()
        await safe_edit_message_text(query,UPLOAD_CSV_PROMPT)

    return BotStates.UPLOAD_CSV


async def process_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик обработки CSV-файла."""
    message = update.message

    # Проверяем, был ли отправлен файл
    if message.document:
        # Получаем файл
        file = await message.document.get_file()
        file_bytes = io.BytesIO()
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)

        # Декодируем CSV
        try:
            csv_content = file_bytes.read().decode('utf-8')
            tasks = parse_csv_tasks(csv_content)

            if not tasks:
                await message.reply_text(CSV_FORMAT_ERROR)
                return BotStates.UPLOAD_CSV

            # Сохраняем задачи в контексте
            context.user_data['csv_tasks'] = tasks

            # Запрашиваем название проекта
            await message.reply_text(CREATE_PROJECT_PROMPT)
            return BotStates.CREATE_PROJECT

        except Exception as e:
            await message.reply_text(f"Ошибка при обработке CSV-файла: {str(e)}\n\n{CSV_FORMAT_ERROR}")
            return BotStates.UPLOAD_CSV

    # Проверяем, был ли отправлен текст
    elif message.text:
        try:
            # Пробуем распарсить текст как CSV
            tasks = parse_csv_tasks(message.text)

            if not tasks:
                await message.reply_text(CSV_FORMAT_ERROR)
                return BotStates.UPLOAD_CSV

            # Сохраняем задачи в контексте
            context.user_data['csv_tasks'] = tasks

            # Запрашиваем название проекта
            await message.reply_text(CREATE_PROJECT_PROMPT)
            return BotStates.CREATE_PROJECT

        except Exception as e:
            await message.reply_text(f"Ошибка при обработке текста как CSV: {str(e)}\n\n{CSV_FORMAT_ERROR}")
            return BotStates.UPLOAD_CSV

    else:
        await message.reply_text("Пожалуйста, отправьте CSV-файл или текст в формате CSV.")
        return BotStates.UPLOAD_CSV


async def create_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for creating a new project."""
    query = update.callback_query

    if query and query.data == 'create_project':
        await query.answer()
        # Go to project type selection
        return await select_project_type(update, context)

    # Get project name from text
    project_name = update.message.text

    # Create project based on the selected method
    if 'template_id' in context.user_data:
        # Create from template
        template_id = context.user_data['template_id']
        project_id = create_project_from_template(template_id, project_name)
        context.user_data['current_project_id'] = project_id
        project_data = get_project_data(project_id)
        context.user_data['tasks'] = project_data['tasks']

        # Auto-assign employees
        from utils.employee_assignment import auto_assign_employees_to_project
        auto_assign_employees_to_project(project_id)
        project_data = get_project_data(project_id)
        context.user_data['employees'] = project_data['employees']

        # Ask for start date
        keyboard = [
            [InlineKeyboardButton("Указать дату начала", callback_data="set_start_date")],
            [InlineKeyboardButton("Рассчитать с сегодняшней даты", callback_data="calculate")]
        ]
        await update.message.reply_text(
            f"Проект '{project_name}' создан на основе шаблона. Сотрудники автоматически назначены.\n\n"
            f"Укажите дату начала проекта или рассчитайте план с сегодняшней даты:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif 'csv_tasks' in context.user_data:
        # Create from CSV
        csv_tasks = context.user_data['csv_tasks']
        project_id = create_project_from_tasks(project_name, csv_tasks)

        if not project_id:
            await update.message.reply_text("Ошибка при создании проекта из CSV. Попробуйте еще раз.")
            return BotStates.CREATE_PROJECT

        context.user_data['current_project_id'] = project_id
        project_data = get_project_data(project_id)
        context.user_data['tasks'] = project_data['tasks']
        context.user_data['employees'] = project_data['employees']

        # Ask for start date
        keyboard = [
            [InlineKeyboardButton("Указать дату начала", callback_data="set_start_date")],
            [InlineKeyboardButton("Рассчитать с сегодняшней даты", callback_data="calculate")]
        ]
        await update.message.reply_text(
            f"Проект '{project_name}' успешно создан из CSV!\n\n"
            f"Укажите дату начала проекта или рассчитайте план с сегодняшней даты:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:
        # Normal project creation
        project_id = create_new_project(project_name)
        context.user_data['current_project_id'] = project_id
        context.user_data['tasks'] = []

        await update.message.reply_text(
            f"Проект '{project_name}' создан. Теперь добавьте задачи.\n\n{ADD_TASK_PROMPT}"
        )

    return BotStates.ADD_TASK


def create_parent_child_tasks(project_id, task_data):
    """
    Создает родительские и дочерние задачи более надежным способом.

    Args:
        project_id: ID проекта
        task_data: Словарь с данными задачи

    Returns:
        tuple: (parent_task_id, [subtask_ids])
    """
    session = Session()
    try:
        # Определяем, является ли задача групповой
        has_multiple_roles = task_data.get('has_multiple_roles', False)
        required_employees = task_data.get('required_employees', 1)
        is_group_task = has_multiple_roles or required_employees > 1

        # Если это не групповая задача, создаем обычную задачу
        if not is_group_task:
            task = Task(
                project_id=project_id,
                name=task_data['name'],
                duration=task_data['duration'],
                position=task_data.get('position', ''),
                required_employees=1
            )
            session.add(task)
            session.commit()
            logger.info(f"Создана обычная задача: {task.name} (ID: {task.id})")
            return task.id, []

        # Создаем родительскую задачу
        parent_task = Task(
            project_id=project_id,
            name=task_data['name'],
            duration=task_data['duration'],
            position='',  # У родительской задачи нет позиции
            required_employees=required_employees,
            sequential_subtasks=task_data.get('sequential_subtasks', False)
        )
        session.add(parent_task)
        session.flush()  # Получаем ID без коммита

        subtask_ids = []

        # Создаем подзадачи в зависимости от типа групповой задачи
        if has_multiple_roles and task_data.get('assignee_roles'):
            # Создаем подзадачи для разных ролей
            for i, role in enumerate(task_data['assignee_roles']):
                position = role['position']
                duration = role['duration']

                subtask_name = f"{task_data['name']} - {position}"
                subtask = Task(
                    project_id=project_id,
                    name=subtask_name,
                    duration=duration,
                    position=position,
                    required_employees=1,
                    parent_id=parent_task.id
                )
                session.add(subtask)
                session.flush()
                subtask_ids.append(subtask.id)

                # Создаем запись в TaskPart для отслеживания частей задачи
                task_part = TaskPart(
                    task_id=parent_task.id,
                    name=subtask_name,
                    position=position,
                    duration=duration,
                    order=i + 1,
                    required_employees=1
                )
                session.add(task_part)

                logger.info(f"Создана подзадача с разной ролью: {subtask.name} (ID: {subtask.id})")

            # Если подзадачи должны выполняться последовательно, создаем зависимости между ними
            if parent_task.sequential_subtasks and len(subtask_ids) > 1:
                for i in range(1, len(subtask_ids)):
                    task_dependency = TaskDependency(
                        task_id=subtask_ids[i],
                        predecessor_id=subtask_ids[i - 1]
                    )
                    session.add(task_dependency)
                    logger.info(
                        f"Создана последовательная зависимость между подзадачами: {subtask_ids[i - 1]} -> {subtask_ids[i]}")

        elif required_employees > 1:
            # Создаем подзадачи для нескольких исполнителей одной должности
            position = task_data.get('position', '')

            for i in range(required_employees):
                subtask_name = f"{task_data['name']} - Исполнитель {i + 1}"
                subtask = Task(
                    project_id=project_id,
                    name=subtask_name,
                    duration=task_data['duration'],
                    position=position,
                    required_employees=1,
                    parent_id=parent_task.id
                )
                session.add(subtask)
                session.flush()
                subtask_ids.append(subtask.id)

                logger.info(f"Создана подзадача для исполнителя {i + 1}: {subtask.name} (ID: {subtask.id})")

            # Если подзадачи должны выполняться последовательно, создаем зависимости между ними
            if parent_task.sequential_subtasks and len(subtask_ids) > 1:
                for i in range(1, len(subtask_ids)):
                    task_dependency = TaskDependency(
                        task_id=subtask_ids[i],
                        predecessor_id=subtask_ids[i - 1]
                    )
                    session.add(task_dependency)
                    logger.info(
                        f"Создана последовательная зависимость между подзадачами: {subtask_ids[i - 1]} -> {subtask_ids[i]}")

        session.commit()
        logger.info(
            f"Создана родительская задача: {parent_task.name} (ID: {parent_task.id}) с {len(subtask_ids)} подзадачами")
        return parent_task.id, subtask_ids

    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при создании родительской/дочерних задач: {str(e)}")
        return None, []

    finally:
        session.close()


def get_task_hierarchy(project_id):
    """
    Получает иерархию задач проекта, группируя подзадачи по родительским задачам.

    Args:
        project_id: ID проекта

    Returns:
        dict: Словарь {parent_task: {info: parent_info, subtasks: [subtask_info]}}
    """
    session = Session()
    try:
        hierarchy = {}

        # Получаем все задачи проекта
        all_tasks = session.query(Task).filter(Task.project_id == project_id).all()

        # Находим родительские задачи и обычные задачи
        for task in all_tasks:
            # Если это родительская задача или у нее есть подзадачи
            if task.required_employees > 1 or task.subtasks:
                # Получаем подзадачи для этой задачи
                subtasks = session.query(Task).filter(
                    Task.parent_id == task.id
                ).all()

                # Преобразуем задачу в словарь
                task_dict = {
                    'id': task.id,
                    'name': task.name,
                    'duration': task.duration,
                    'position': task.position or '',
                    'required_employees': task.required_employees,
                    'sequential_subtasks': task.sequential_subtasks,
                    'is_parent': True
                }

                # Преобразуем подзадачи в словари
                subtasks_list = []
                for subtask in subtasks:
                    subtask_dict = {
                        'id': subtask.id,
                        'name': subtask.name,
                        'duration': subtask.duration,
                        'position': subtask.position or '',
                        'required_employees': subtask.required_employees,
                        'parent_id': task.id,
                        'is_subtask': True
                    }
                    subtasks_list.append(subtask_dict)

                # Добавляем в иерархию
                hierarchy[task.id] = {
                    'task': task_dict,
                    'subtasks': subtasks_list
                }

        # Находим обычные задачи (не родительские и не подзадачи)
        standalone_tasks = []
        for task in all_tasks:
            # Пропускаем подзадачи
            if task.parent_id is not None:
                continue

            # Пропускаем родительские задачи, которые уже обработаны
            if task.id in hierarchy:
                continue

            # Преобразуем обычную задачу в словарь
            task_dict = {
                'id': task.id,
                'name': task.name,
                'duration': task.duration,
                'position': task.position or '',
                'required_employees': task.required_employees,
                'is_parent': False,
                'is_subtask': False
            }
            standalone_tasks.append(task_dict)

        # Добавляем обычные задачи в результат
        hierarchy['standalone'] = standalone_tasks

        return hierarchy

    except Exception as e:
        logger.error(f"Ошибка при получении иерархии задач: {str(e)}")
        return {'standalone': []}

    finally:
        session.close()


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик добавления задачи."""
    logger.info("Начало обработки add_task")

    # Проверка на callback_query
    if update.callback_query:
        query = update.callback_query
        await query.answer()

        # Обработка навигационных действий
        if query.data == "add_task":
            await query.edit_message_text(
                "Добавьте информацию о задаче в формате:\n"
                "<название задачи> | <длительность в днях> | <должность исполнителя> | <количество исполнителей> | <последовательное выполнение>\n\n"
                "Например: Создание тарифов обучения | 1 | Технический специалист | 1 | нет\n\n"
                "Для создания задачи с разными ролями используйте формат:\n"
                "<название задачи> | <длительность> | роли | <роль1>:<длительность1>,<роль2>:<длительность2> | <последовательное выполнение>\n\n"
                "Например: Настройка системы | 3 | роли | Технический специалист:1,Старший технический специалист:2 | да",
                reply_markup=task_actions_keyboard()
            )
        elif query.data == "goto_dependencies":
            return await show_dependencies(update, context)
        elif query.data == "back_to_project":
            return await select_project(update, context)

        return BotStates.ADD_TASK

    # Обработка текстового сообщения с информацией о задаче
    if not update.message or not update.message.text:
        logger.error("Получен пустой текст сообщения в add_task")
        return BotStates.ADD_TASK

    message_text = update.message.text
    task_parts = [part.strip() for part in message_text.split('|')]

    # Проверяем формат сообщения
    if len(task_parts) < 3:
        await update.message.reply_text(
            "Неверный формат. Используйте:\n"
            "<название задачи> | <длительность> | <должность> | [количество] | [последовательно]\n\n"
            "Или для задач с разными ролями:\n"
            "<название задачи> | <длительность> | роли | <роль1>:<длит1>,<роль2>:<длит2> | [последовательно]"
        )
        return BotStates.ADD_TASK

    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await update.message.reply_text(
            "Ошибка: проект не выбран. Пожалуйста, вернитесь в главное меню.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Разбираем данные задачи
    task_name = task_parts[0]

    try:
        duration = int(task_parts[1])
        if duration <= 0:
            await update.message.reply_text("Длительность должна быть положительным числом.")
            return BotStates.ADD_TASK
    except ValueError:
        await update.message.reply_text("Длительность должна быть числом.")
        return BotStates.ADD_TASK

    # Определяем тип задачи
    if task_parts[2].lower() == 'роли' and len(task_parts) >= 4:
        # Задача с разными ролями
        has_multiple_roles = True
        roles_text = task_parts[3]

        # Парсим роли и их длительности
        assignee_roles = []
        for role_part in roles_text.split(','):
            if ':' in role_part:
                position, role_duration = role_part.split(':')
                try:
                    assignee_roles.append({
                        "position": position.strip(),
                        "duration": int(role_duration.strip())
                    })
                except ValueError:
                    await update.message.reply_text(f"Неверный формат длительности роли: {role_part}")
                    return BotStates.ADD_TASK

        if not assignee_roles:
            await update.message.reply_text(
                "Не удалось распознать роли. Используйте формат: роль1:длительность1,роль2:длительность2")
            return BotStates.ADD_TASK

        # Определяем, последовательно ли выполняются подзадачи
        sequential = False
        if len(task_parts) >= 5:
            sequential_text = task_parts[4].lower()
            sequential = sequential_text in ['да', 'true', '1', 'yes', 'последовательно']

        # Создаем данные задачи
        task_data = {
            'name': task_name,
            'duration': duration,
            'position': '',
            'required_employees': 1,
            'has_multiple_roles': True,
            'assignee_roles': assignee_roles,
            'sequential_subtasks': sequential
        }
    else:
        # Обычная задача или задача с несколькими исполнителями одной должности
        position = task_parts[2]

        # Определяем количество исполнителей
        required_employees = 1
        if len(task_parts) >= 4:
            try:
                required_employees = int(task_parts[3])
                if required_employees <= 0:
                    required_employees = 1
            except ValueError:
                # Если не число, считаем что это 1
                required_employees = 1

        # Определяем, последовательно ли выполняются подзадачи
        sequential = False
        if len(task_parts) >= 5:
            sequential_text = task_parts[4].lower()
            sequential = sequential_text in ['да', 'true', '1', 'yes', 'последовательно']

        # Создаем данные задачи
        task_data = {
            'name': task_name,
            'duration': duration,
            'position': position,
            'required_employees': required_employees,
            'has_multiple_roles': False,
            'sequential_subtasks': sequential
        }

    # Создаем задачу (и подзадачи, если нужно)
    parent_id, subtask_ids = create_parent_child_tasks(project_id, task_data)

    if parent_id:
        # Формируем сообщение об успешном создании
        if subtask_ids:
            roles_info = ""
            if task_data.get('has_multiple_roles'):
                roles = [f"{role['position']} ({role['duration']} дн.)" for role in task_data.get('assignee_roles', [])]
                roles_info = "\nРоли: " + ", ".join(roles)

            await update.message.reply_text(
                f"✅ Задача '{task_name}' успешно создана с {len(subtask_ids)} подзадачами.\n"
                f"Общая длительность: {duration} дн.{roles_info}\n"
                f"Последовательное выполнение: {'Да' if task_data.get('sequential_subtasks') else 'Нет'}",
                reply_markup=task_actions_keyboard()
            )
        else:
            await update.message.reply_text(
                f"✅ Задача '{task_name}' успешно создана.\n"
                f"Длительность: {duration} дн., Должность: {task_data.get('position', '')}",
                reply_markup=task_actions_keyboard()
            )

        # Обновляем список задач в контексте
        if 'tasks' not in context.user_data:
            context.user_data['tasks'] = []

        # Добавляем задачу в контекст
        context.user_data['tasks'].append({
            'id': parent_id,
            'name': task_name,
            'duration': duration,
            'position': task_data.get('position', ''),
            'required_employees': task_data.get('required_employees', 1),
            'has_multiple_roles': task_data.get('has_multiple_roles', False)
        })
    else:
        await update.message.reply_text(
            f"❌ Ошибка при создании задачи '{task_name}'. Пожалуйста, попробуйте еще раз.",
            reply_markup=task_actions_keyboard()
        )

    return BotStates.ADD_TASK

async def add_dependencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик добавления зависимостей между задачами."""
    logger.info("Начало обработки add_dependencies")

    # Обработка callback_query (нажатие на кнопку)
    if update.callback_query:
        query = update.callback_query
        await query.answer()

        if query.data == 'goto_employees':
            logger.info("Переходим к добавлению сотрудников")
            # Переход к следующему этапу - добавление сотрудников
            return await show_employees(update, context)

        elif query.data == 'back_to_tasks':
            logger.info("Возвращаемся к добавлению задач")
            return await back_to_tasks(update, context)

        elif query.data == 'add_dependency':
            # Показываем форму для добавления зависимости
            project_id = context.user_data.get('current_project_id')
            if not project_id:
                await query.edit_message_text(
                    "Ошибка: проект не выбран. Пожалуйста, вернитесь в главное меню.",
                    reply_markup=main_menu_keyboard()
                )
                return BotStates.MAIN_MENU

            project_data = get_project_data(project_id)
            if not project_data or not project_data.get('tasks'):
                await query.edit_message_text(
                    "В проекте нет задач для добавления зависимостей.",
                    reply_markup=back_to_main_keyboard()
                )
                return BotStates.MAIN_MENU

            # Формируем сообщение со списком задач
            tasks_list = "\n".join([f"{i + 1}. {task['name']}" for i, task in enumerate(project_data['tasks'])])

            await query.edit_message_text(
                f"Укажите зависимости в формате:\n<название задачи> | <зависимости через запятую>\n\n"
                f"Например: Задача 2 | Задача 1, Задача 3\n\n"
                f"Список задач:\n{tasks_list}",
                reply_markup=dependencies_actions_keyboard()
            )
            return BotStates.ADD_DEPENDENCIES

        return BotStates.ADD_DEPENDENCIES

    # Обработка текстового сообщения с зависимостями
    if not update.message or not update.message.text:
        await update.effective_chat.send_message(
            "Пожалуйста, укажите зависимости в формате: <название задачи> | <зависимости через запятую>"
        )
        return BotStates.ADD_DEPENDENCIES

    message_text = update.message.text

    # Проверяем формат сообщения
    if '|' not in message_text:
        await update.message.reply_text(
            "Неверный формат. Используйте: <название задачи> | <зависимости через запятую>",
            reply_markup=dependencies_actions_keyboard()
        )
        return BotStates.ADD_DEPENDENCIES

    # Разбираем сообщение
    parts = message_text.split('|', 1)
    task_name = parts[0].strip()

    # Получаем список предшественников
    predecessors = []
    if len(parts) > 1 and parts[1].strip():
        predecessors = [pred.strip() for pred in parts[1].split(',')]

    # Добавляем зависимости
    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await update.message.reply_text(
            "Ошибка: проект не выбран. Пожалуйста, вернитесь в главное меню.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Используем улучшенную функцию добавления зависимостей
    success = add_task_dependencies(project_id, task_name, predecessors)

    if success:
        # Проверяем наличие циклических зависимостей
        has_cycles, cycle_path = check_circular_dependencies(project_id)

        if has_cycles:
            await update.message.reply_text(
                f"⚠️ Внимание! Обнаружена циклическая зависимость: {' -> '.join(cycle_path)}.\n"
                f"Это может привести к проблемам при построении календарного плана.",
                reply_markup=dependencies_actions_keyboard()
            )
        else:
            await update.message.reply_text(
                f"✅ Зависимости для задачи '{task_name}' успешно добавлены.",
                reply_markup=dependencies_actions_keyboard()
            )
    else:
        await update.message.reply_text(
            f"❌ Ошибка при добавлении зависимостей для задачи '{task_name}'.\n"
            f"Возможно, задача не найдена или произошла другая ошибка.",
            reply_markup=dependencies_actions_keyboard()
        )

    return BotStates.ADD_DEPENDENCIES

async def add_employees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Начало обработки add_employees")
    
    if update.callback_query:
        query = update.callback_query
        logger.info(f"Получен callback_query с данными: {query.data}")
        await query.answer()
        
        if query.data in ('add_employee', 'add_employees'):
            logger.info("Начинаем процесс добавления сотрудника")
            # Получаем список всех должностей
            positions = get_all_positions()
            
            if not positions:
                await safe_edit_message_text(
                    query,
                    "В базе данных нет сохраненных должностей. Пожалуйста, добавьте сотрудника вручную.",
                    reply_markup=employees_actions_keyboard()
                )
                return BotStates.ADD_EMPLOYEES
            
            # Сохраняем список должностей в контексте
            context.user_data['available_positions'] = positions
            
            # Показываем список должностей для выбора
            await safe_edit_message_text(
                query,
                "Выберите должность сотрудника:",
                reply_markup=position_selection_keyboard(positions)
            )
            return BotStates.SELECT_POSITION
            
        elif query.data.startswith('pos_'):
            # Получаем хеш должности
            position_hash = int(query.data.replace('pos_', ''))
            
            # Находим должность по хешу
            positions = context.user_data.get('available_positions', [])
            position = next((p for p in positions if hash(p) % 1000000 == position_hash), None)
            
            if not position:
                await safe_edit_message_text(
                    query,
                    "Должность не найдена. Пожалуйста, попробуйте еще раз.",
                    reply_markup=employees_actions_keyboard()
                )
                return BotStates.ADD_EMPLOYEES
            
            logger.info(f"Выбрана должность: {position}")
            
            # Сохраняем выбранную должность в контексте
            context.user_data['selected_position'] = position
            
            # Получаем список сотрудников с этой должностью
            logger.info(f"Получаем сотрудников для должности: {position}")
            
            session = Session()
            try:
                # Query ALL employees with the given position, but use case-insensitive matching
                # This helps with potential differences in capitalization or spacing
                employees = session.query(Employee).filter(
                    Employee.position.ilike(f"%{position}%")
                ).all()
                
                logger.info(f"Найдено сотрудников: {len(employees)}")
                
                # Convert to dictionary format
                employees_data = []
                for emp in employees:
                    # Get days off
                    days_off = session.query(DayOff).filter(DayOff.employee_id == emp.id).all()
                    days_off_list = [day.day for day in days_off]
                    
                    employees_data.append({
                        'id': emp.id,
                        'name': emp.name,
                        'position': emp.position,
                        'email': emp.email,
                        'days_off': days_off_list
                    })
                
                # Now handle display based on whether we found any employees
                if not employees_data:
                    logger.warning(f"Сотрудники с должностью '{position}' не найдены в базе данных")
                    # Предлагаем добавить нового сотрудника
                    keyboard = [
                        [InlineKeyboardButton("Добавить нового сотрудника", callback_data="add_new_employee")],
                        [InlineKeyboardButton("Назад", callback_data="back_to_positions")]
                    ]
                    await safe_edit_message_text(
                        query,
                        f"Сотрудники с должностью '{position}' не найдены в базе данных. Хотите добавить нового сотрудника?",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    # Показываем список сотрудников для выбора
                    message = f"Выберите сотрудника на должность '{position}':\n\n"
                    for i, employee in enumerate(employees_data, 1):
                        days_off_str = ", ".join(employee['days_off']) if employee['days_off'] else "Без выходных"
                        message += f"{i}. {employee['name']} (Выходные: {days_off_str})\n"
                        logger.info(f"Сотрудник {i}: {employee['name']} - {employee['position']}")
                    
                    keyboard = []
                    for employee in employees_data:
                        keyboard.append([InlineKeyboardButton(
                            employee['name'],
                            callback_data=f"select_employee_{employee['id']}"
                        )])
                    keyboard.append([InlineKeyboardButton("Добавить нового сотрудника", callback_data="add_new_employee")])
                    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_positions")])
                    
                    await safe_edit_message_text(
                        query,
                        message,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return BotStates.SELECT_EMPLOYEE
            except Exception as e:
                logger.error(f"Ошибка при получении сотрудников: {str(e)}")
                await safe_edit_message_text(
                    query,
                    f"Ошибка при получении сотрудников: {str(e)}",
                    reply_markup=employees_actions_keyboard()
                )
            finally:
                session.close()
            
            return BotStates.ADD_EMPLOYEES

        elif query.data.startswith('select_employee_'):
            # Получаем ID выбранного сотрудника
            employee_id = int(query.data.replace('select_employee_', ''))
            logger.info(f"Выбран сотрудник с ID: {employee_id}")

            session = Session()
            try:
                employee = session.query(Employee).filter(Employee.id == employee_id).first()
                if not employee:
                    await safe_edit_message_text(
                        query,
                        "Сотрудник не найден. Пожалуйста, попробуйте еще раз.",
                        reply_markup=employees_actions_keyboard()
                    )
                    return BotStates.ADD_EMPLOYEES

                project_id = context.user_data.get('current_project_id')
                project = session.query(Project).get(project_id)
                if employee in project.employees:
                    await safe_edit_message_text(
                        query,
                        f"Сотрудник '{employee.name}' уже добавлен в проект!",
                        reply_markup=employees_actions_keyboard()
                    )
                    return BotStates.ADD_EMPLOYEES

                add_employee_to_project(employee.id, project.id)
                await safe_edit_message_text(
                    query,
                    f"Сотрудник '{employee.name}' успешно добавлен!",
                    reply_markup=employees_actions_keyboard()
                )
                return BotStates.ADD_EMPLOYEES
            except Exception as e:
                logger.error(f"Ошибка при добавлении сотрудника: {str(e)}")
                await safe_edit_message_text(
                    query,
                    f"Ошибка при добавлении сотрудника: {str(e)}",
                    reply_markup=employees_actions_keyboard()
                )
                return BotStates.ADD_EMPLOYEES
            finally:
                session.close()


async def calculate_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик расчета календарного плана."""
    query = update.callback_query
    await query.answer()

    await safe_edit_message_text(query, "Начинаю расчет оптимального календарного плана...")

    # Получаем данные проекта
    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await query.edit_message_text(
            "Ошибка: проект не выбран. Пожалуйста, вернитесь в главное меню.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    project_data = get_project_data(project_id)
    if not project_data:
        await query.edit_message_text(
            "Ошибка: проект не найден. Пожалуйста, вернитесь в главное меню.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Проверяем наличие задач
    if not project_data.get('tasks'):
        await query.edit_message_text(
            "В проекте нет задач для расчета календарного плана. Пожалуйста, добавьте задачи.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Добавить задачи", callback_data="add_tasks")
            ]])
        )
        return BotStates.SELECT_PROJECT

    # Проверяем наличие циклических зависимостей
    has_cycles, cycle_path = check_circular_dependencies(project_id)
    if has_cycles:
        await query.edit_message_text(
            f"⚠️ Обнаружена циклическая зависимость: {' -> '.join(cycle_path)}.\n"
            "Это препятствует построению календарного плана. Пожалуйста, исправьте зависимости.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("К зависимостям", callback_data="goto_dependencies"),
                InlineKeyboardButton("Назад", callback_data="back_to_project")
            ]])
        )
        return BotStates.SELECT_PROJECT

    # Определяем дату начала проекта
    start_date = None

    # Попытка получить дату из БД
    if project_data.get('start_date'):
        db_date = project_data['start_date']
        # Если это date, конвертируем в datetime
        if hasattr(db_date, 'year'):  # Проверяем, является ли объектом date или datetime
            from datetime import datetime
            start_date = datetime.combine(db_date, datetime.min.time())
            logger.info(f"Используем дату начала из БД: {start_date}")

    # Если нет даты в БД, смотрим в контекст
    if not start_date and 'project_start_date' in context.user_data:
        start_date = context.user_data['project_start_date']
        logger.info(f"Используем дату начала из контекста: {start_date}")

    # Если все еще нет даты, используем текущую
    if not start_date:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        context.user_data['project_start_date'] = start_date
        logger.info(f"Используем текущую дату: {start_date}")

    try:
        # Рассчитываем параметры сетевой модели
        network_parameters = calculate_network_parameters(project_data)

        # Создаем календарный план с учетом выходных и назначения сотрудников
        calendar_plan = create_calendar_plan(network_parameters, project_data, start_date)

        # Сохраняем результаты в контексте
        context.user_data['calendar_plan'] = calendar_plan

        # Генерируем диаграмму Ганта
        gantt_image = generate_gantt_chart(calendar_plan)
        gantt_buffer = io.BytesIO()
        gantt_image.save(gantt_buffer, format='PNG')
        gantt_buffer.seek(0)

        # Формируем текстовый отчет
        start_date_str = start_date.strftime('%d.%m.%Y')

        # Расчет даты окончания
        project_duration = calendar_plan.get('project_duration', 0)
        end_date = start_date + timedelta(days=project_duration)
        end_date_str = end_date.strftime('%d.%m.%Y')

        # Формируем критический путь
        critical_path_text = ""
        if calendar_plan.get('critical_path'):
            critical_path_names = [task['name'] for task in calendar_plan['critical_path']]
            critical_path_text = "Критический путь: " + " -> ".join(critical_path_names)
        else:
            critical_path_text = "Критический путь не определен"

        report = f"""
Расчет календарного плана завершен!

Дата начала проекта: {start_date_str}
Дата окончания проекта: {end_date_str}
Общая продолжительность проекта: {project_duration} дней

{critical_path_text}

Резервы времени для некритических работ:
"""

        # Добавляем информацию о резервах для некритических задач
        tasks_with_reserves = [task for task in calendar_plan['tasks'] if
                               not task.get('is_critical') and task.get('reserve', 0) > 0]
        if tasks_with_reserves:
            for task in sorted(tasks_with_reserves, key=lambda t: t.get('reserve', 0), reverse=True):
                report += f"- {task['name']}: {task.get('reserve', 0)} дней\n"
        else:
            report += "Нет задач с резервами времени.\n"

        # Отправляем диаграмму Ганта и отчет
        await query.message.reply_photo(
            photo=gantt_buffer,
            caption="Диаграмма Ганта для календарного плана"
        )

        await query.message.reply_text(
            report,
            reply_markup=plan_actions_keyboard()
        )

        return BotStates.SHOW_PLAN

    except Exception as e:
        logger.error(f"Ошибка при расчете календарного плана: {str(e)}")

        # Более подробное сообщение об ошибке
        error_msg = f"Произошла ошибка при расчете календарного плана: {str(e)}\n\n"

        if "cycle" in str(e).lower() or "цикл" in str(e).lower():
            error_msg += "Обнаружена циклическая зависимость между задачами. Пожалуйста, проверьте зависимости задач."
        else:
            error_msg += "Пожалуйста, проверьте корректность данных проекта и попробуйте снова."

        await query.edit_message_text(
            error_msg,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("К зависимостям", callback_data="goto_dependencies"),
                InlineKeyboardButton("Назад", callback_data="back_to_project")
            ]])
        )

        return BotStates.SELECT_PROJECT


async def export_to_jira(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик экспорта задач в Jira."""
    query = update.callback_query
    await query.answer()
    
    await safe_edit_message_text(query, "Экспортирую задачи в Jira...")

    # Получаем данные календарного плана
    calendar_plan = context.user_data['calendar_plan']
    for t in calendar_plan['tasks']:
        print(t['name'], t.get('is_subtask'), t.get('employee'), t.get('required_employees'))
    
    # Get individual task descriptions
    task_descriptions = context.user_data.get('task_descriptions', {})
    
    # Add task descriptions to the calendar plan
    calendar_plan['task_descriptions'] = task_descriptions

    try:
        # Создаем задачи в Jira
        jira_issues = create_jira_issues(calendar_plan)

        # Формируем отчет о созданных задачах
        issues_report = "Созданы следующие задачи в Jira:\n\n"
        for issue in jira_issues:
            issues_report += f"- {issue['key']}: {issue['summary']} ({issue['assignee']})\n"

        await query.message.reply_text(
            EXPORT_TO_JIRA_SUCCESS + "\n\n" + issues_report
        )
    except Exception as e:
        logger.error(f"Произошла ошибка: {str(e)}")
        await query.message.reply_text(
            "Произошла ошибка при экспорте задач в Jira. Пожалуйста, попробуйте позже."
        )


async def list_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик просмотра списка проектов."""
    logger.info("list_projects handler called")
    query = update.callback_query
    await query.answer()

    # Получаем ID пользователя
    user_id = update.effective_user.id

    # Получаем список проектов из БД
    projects = get_user_projects(user_id)

    if not projects:
        await safe_edit_message_text(
            query,
            "У вас пока нет проектов. Вы можете создать новый проект.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Создать проект", callback_data="create_project"),
                InlineKeyboardButton("Вернуться в меню", callback_data="back_to_main")
            ]])
        )
        return BotStates.MAIN_MENU

    # Формируем сообщение со списком проектов
    message = "📋 *Ваши проекты:*\n\n"

    # Отображаем проекты с датой создания
    for i, project in enumerate(projects):
        message += f"{i + 1}. *{project['name']}*\n"
        message += f"   Дата создания: {project['created_at']}\n"
        message += f"   Задач: {project['tasks_count']}\n\n"

    message += "Выберите проект для просмотра деталей или создайте новый."

    # Отправляем сообщение с клавиатурой выбора проекта
    await safe_edit_message_text(
        query,
        message,
        reply_markup=projects_keyboard(projects),
        parse_mode='Markdown'
    )

    return BotStates.SELECT_PROJECT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущую операцию и возвращает в главное меню."""
    try:
        # Очищаем все временные данные
        context.user_data.clear()
        
        # Отправляем сообщение об отмене
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                "Операция отменена. Возвращаюсь в главное меню.",
                reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                "Операция отменена. Возвращаюсь в главное меню.",
                reply_markup=main_menu_keyboard()
            )
            
        logger.info("Операция отменена, возврат в главное меню")
        return BotStates.MAIN_MENU
    except Exception as e:
        logger.error(f"Ошибка при отмене операции: {str(e)}")
        # В случае ошибки все равно пытаемся вернуться в главное меню
        return BotStates.MAIN_MENU


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата в главное меню."""
    logger.info("back_to_main handler called")
    query = update.callback_query
    await query.answer()

    try:
        await query.edit_message_text(
            WELCOME_MESSAGE,
            reply_markup=main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in back_to_main: {str(e)}")
        # В случае ошибки отправляем новое сообщение
        await query.message.reply_text(
            WELCOME_MESSAGE,
            reply_markup=main_menu_keyboard()
        )

    return BotStates.MAIN_MENU


async def back_to_project_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата к выбору типа проекта."""
    query = update.callback_query
    await query.answer()

    await safe_edit_message_text(
        query,
        SELECT_PROJECT_TYPE_MESSAGE,
        reply_markup=project_type_keyboard()
    )

    return BotStates.SELECT_PROJECT_TYPE


async def select_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора проекта из списка."""
    logger.info("Начало обработки select_project")
    query = update.callback_query
    await query.answer()

    # Проверяем, является ли это нажатием на кнопку добавления сотрудников
    if query.data == 'add_employees':
        logger.info("Нажата кнопка добавления сотрудников")
        project_id = context.user_data.get('current_project_id')
        if not project_id:
            logger.error("ID проекта не найден в контексте")
            await query.edit_message_text(
                "Ошибка: проект не выбран. Пожалуйста, выберите проект заново.",
                reply_markup=main_menu_keyboard()
            )
            return BotStates.MAIN_MENU

        # Загружаем существующих сотрудников
        session = Session()
        project = session.query(Project).get(project_id)
        existing_employees = project.employees if project else []
        session.close()
        logger.info(f"Найдено сотрудников: {len(existing_employees) if existing_employees else 0}")

        # Формируем сообщение
        employees_text = ""
        if existing_employees:
            employees_text = "Существующие сотрудники:\n"
            for idx, employee in enumerate(existing_employees):
                days_off_str = ", ".join(employee['days_off'])
                employees_text += f"{idx + 1}. {employee['name']} | {employee['position']} | {days_off_str}\n"
            employees_text += "\n"

        try:
            await query.edit_message_text(
                f"{employees_text}Добавьте информацию о сотрудниках.",
                reply_markup=employees_actions_keyboard()
            )
            logger.info("Сообщение с информацией о сотрудниках отправлено")
            return BotStates.ADD_EMPLOYEES
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {str(e)}")
            raise

    # Проверяем, является ли это нажатием на кнопку добавления задач
    if query.data == 'add_tasks':
        logger.info("Нажата кнопка добавления задач")
        project_id = context.user_data.get('current_project_id')
        if not project_id:
            logger.error("ID проекта не найден в контексте")
            await query.edit_message_text(
                "Ошибка: проект не выбран. Пожалуйста, выберите проект заново.",
                reply_markup=main_menu_keyboard()
            )
            return BotStates.MAIN_MENU

        # Загружаем существующие задачи
        project_data = get_project_data(project_id)
        logger.info(f"Найдено задач: {len(project_data['tasks']) if project_data and 'tasks' in project_data else 0}")

        # Формируем сообщение
        tasks_text = ""
        if project_data and project_data['tasks']:
            tasks_text = "Существующие задачи:\n"
            for idx, task in enumerate(project_data['tasks']):
                tasks_text += f"{idx + 1}. {task['name']} ({task['duration']} дн.) - {task['position']}\n"
            tasks_text += "\n"

        try:
            await query.edit_message_text(
                f"{tasks_text}Добавьте информацию о задаче в формате:\n"
                "<название задачи> | <длительность в днях> | <должность исполнителя>\n\n"
                "Например: Создание тарифов обучения | 1 | Технический специалист",
                reply_markup=task_actions_keyboard()
            )
            logger.info("Сообщение с информацией о задачах отправлено")
            return BotStates.ADD_TASK
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {str(e)}")
            raise

    # Получаем ID выбранного проекта
    project_id = int(query.data.split('_')[1])
    logger.info(f"Выбран проект с ID: {project_id}")

    # Получаем данные проекта
    project_data = get_project_data(project_id)
    logger.info(f"Получены данные проекта: {project_data['name'] if project_data else 'None'}")

    if not project_data:
        logger.error("Проект не найден")
        await safe_edit_message_text(
            query,
            "Проект не найден или был удален.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Сохраняем ID проекта в контексте
    context.user_data['current_project_id'] = int(project_id)  # Убеждаемся, что ID - целое число
    logger.info(f"ID проекта {project_id} сохранен в контексте")

    # Сохраняем задачи и сотрудников проекта в контексте
    context.user_data['tasks'] = project_data['tasks']
    context.user_data['employees'] = project_data['employees']
    logger.info(f"Сохранено {len(project_data['tasks'])} задач и {len(project_data['employees'])} сотрудников")

    # Формируем сообщение с информацией о проекте
    message = f"📊 *Проект: {project_data['name']}*\n\n"

    # Информация о задачах
    message += f"*Задачи:* {len(project_data['tasks'])}\n\n"

    if project_data['tasks']:
        message += "*Список задач:*\n"
        for i, task in enumerate(project_data['tasks'][:5]):  # Показываем только первые 5 задач
            message += f"{i + 1}. {task['name']} ({task['duration']} дн.) - {task['position']}\n"

        if len(project_data['tasks']) > 5:
            message += f"... и еще {len(project_data['tasks']) - 5} задач\n"
    else:
        message += "Задачи еще не добавлены.\n"

    message += "\n*Сотрудники:* "
    if project_data['employees']:
        message += f"{len(project_data['employees'])}\n"
    else:
        message += "пока не добавлены.\n"

    message += "\nВыберите действие:"

    # Создаем клавиатуру с действиями для проекта
    keyboard = [
        [InlineKeyboardButton("Добавить задачи", callback_data="add_tasks")],
        [InlineKeyboardButton("Добавить сотрудников", callback_data="add_employees")],
        [InlineKeyboardButton("Рассчитать календарный план", callback_data="calculate")],
        [InlineKeyboardButton("Назад к списку проектов", callback_data="list_projects")],
        [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
    ]

    try:
        logger.info("Отправка сообщения с информацией о проекте")
        await safe_edit_message_text(
            query,
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        logger.info("Сообщение успешно отправлено")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {str(e)}")
        raise

    return BotStates.SELECT_PROJECT  # Возвращаем состояние выбора проекта


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик для добавления нового пользователя в список разрешенных.
    Доступен только для администраторов.
    """
    user_id = update.effective_user.id

    # Проверяем, является ли пользователь администратором через БД
    if not is_admin_user(user_id):
        await update.message.reply_text("У вас нет прав для выполнения этой операции.")
        return

    # Получаем ID нового пользователя из аргументов команды
    if not context.args or len(context.args) < 1 or not context.args[0].isdigit():
        await update.message.reply_text(
            "Пожалуйста, укажите ID пользователя и его имя для добавления.\n"
            "Пример: /add_user 123456789 Иван Иванов"
        )
        return

    new_user_id = int(context.args[0])

    # Получаем имя пользователя, если оно указано
    user_name = None
    if len(context.args) > 1:
        user_name = " ".join(context.args[1:])

    # Проверяем, не добавлен ли пользователь уже
    if is_user_allowed(new_user_id):
        await update.message.reply_text(f"Пользователь с ID {new_user_id} уже имеет доступ.")
        return

    # Добавляем пользователя в БД
    result = add_allowed_user(
        telegram_id=new_user_id,
        name=user_name,
        added_by=user_id,
        is_admin=False
    )

    if result:
        await update.message.reply_text(
            f"Пользователь с ID {new_user_id}" +
            (f" ({user_name})" if user_name else "") +
            " успешно добавлен в список разрешенных."
        )
        logger.info(f"Добавлен новый пользователь: {new_user_id}" + (f" ({user_name})" if user_name else ""))
    else:
        await update.message.reply_text(
            f"Ошибка при добавлении пользователя с ID {new_user_id}. "
            "Возможно, пользователь уже добавлен или произошла ошибка базы данных."
        )


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик для вывода списка разрешенных пользователей.
    Доступен только для администраторов.
    """
    user_id = update.effective_user.id

    # Проверяем, является ли пользователь администратором
    if not is_admin_user(user_id):
        await update.message.reply_text("У вас нет прав для выполнения этой операции.")
        return

    # Получаем список разрешенных пользователей
    users = get_allowed_users()

    if not users:
        await update.message.reply_text("Список разрешенных пользователей пуст.")
        return

    # Формируем сообщение со списком пользователей
    message = "Список разрешенных пользователей:\n\n"

    for i, user in enumerate(users, start=1):
        admin_status = " (админ)" if user.get('is_admin') else ""
        message += f"{i}. ID: {user['telegram_id']}"

        if user.get('name'):
            message += f" - {user['name']}"

        message += admin_status

        if user.get('added_at'):
            message += f" (добавлен: {user['added_at']})"

        message += "\n"

    await update.message.reply_text(message)


async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик для удаления пользователя из списка разрешенных.
    Доступен только для администраторов.
    """
    user_id = update.effective_user.id

    # Проверяем, является ли пользователь администратором
    if not is_admin_user(user_id):
        await update.message.reply_text("У вас нет прав для выполнения этой операции.")
        return

    # Получаем ID пользователя для удаления из аргументов команды
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Пожалуйста, укажите ID пользователя для удаления.\n"
            "Пример: /remove_user 123456789"
        )
        return

    target_user_id = int(context.args[0])

    # Проверяем, является ли удаляемый пользователь администратором
    if is_admin_user(target_user_id) and target_user_id != user_id:
        await update.message.reply_text(
            "Вы не можете удалить другого администратора. "
            "Для удаления, пользователь должен сначала потерять права администратора."
        )
        return

    # Удаляем пользователя из БД
    from database.operations import remove_allowed_user
    result = remove_allowed_user(target_user_id)

    if result:
        await update.message.reply_text(f"Пользователь с ID {target_user_id} успешно удален из списка разрешенных.")
        logger.info(f"Удален пользователь: {target_user_id}")
    else:
        await update.message.reply_text(
            f"Пользователь с ID {target_user_id} не найден в списке разрешенных или произошла ошибка при удалении."
        )


def is_admin_user(user_id):
    """
    Проверяет, является ли пользователь администратором.

    Args:
        user_id: Telegram ID пользователя

    Returns:
        bool: True, если пользователь администратор, иначе False
    """
    with session_scope() as session:
        user = session.query(AllowedUser).filter(
            AllowedUser.telegram_id == user_id,
            AllowedUser.is_admin == True
        ).first()

        return user is not None


async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет пользователю его Telegram ID."""
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.first_name

    await update.message.reply_text(
        MY_ID_MESSAGE.format(
            user_id=user_id,
            user_name=user_name
        )
    )


async def show_project_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает подробную информацию о проекте."""
    query = update.callback_query
    await query.answer()

    # Получаем календарный план
    calendar_plan = context.user_data.get('calendar_plan')
    if not calendar_plan:
        await query.edit_message_text(
            "Ошибка: календарный план не найден. Сначала рассчитайте план.",
            reply_markup=plan_actions_keyboard()
        )
        return BotStates.SHOW_PLAN

    # Формируем сообщение
    message = "*Информация о проекте:*\n\n"

    # Добавляем информацию о критическом пути
    message += "*Критический путь:*\n"
    for task_name in calendar_plan['critical_path']:
        message += f"- {task_name}\n"

    # Группируем задачи по имени для выявления подзадач
    tasks_by_name = {}
    for task in calendar_plan['tasks']:
        name = task.get('name', '')

        # Убираем суффикс " - Должность" для подзадач
        base_name = name
        if ' - ' in name:
            base_name = name.split(' - ')[0]

        if base_name not in tasks_by_name:
            tasks_by_name[base_name] = []
        tasks_by_name[base_name].append(task)

    # Идентифицируем родительские задачи
    parent_tasks = {}
    standalone_tasks = []

    for task in calendar_plan['tasks']:
        if task.get('is_parent') or task.get('required_employees', 1) > 1:
            parent_tasks[task['id']] = {
                'task': task,
                'subtasks': []
            }
        elif not task.get('parent_id') and not task.get('is_subtask'):
            # Проверяем, является ли задача подзадачей (по имени)
            name = task.get('name', '')
            if ' - ' in name:
                # Это подзадача, но parent_id не установлен
                continue
            standalone_tasks.append(task)

    # Добавляем подзадачи к родительским задачам
    for name, tasks in tasks_by_name.items():
        # Если есть подзадачи (задачи с названием, начинающимся с основного имени)
        subtasks = [t for t in tasks if t.get('name', '') != name]

        # Находим родительскую задачу
        parent_task = next((t for t in tasks if t.get('name', '') == name), None)

        if parent_task and parent_task.get('id') in parent_tasks:
            parent_tasks[parent_task['id']]['subtasks'] = subtasks

    # Добавляем информацию о задачах
    message += "\n*Задачи:*\n"

    # Приоритет сортировки: критические первыми, затем по раннему старту
    all_parent_tasks = sorted(
        parent_tasks.values(),
        key=lambda x: (not x['task'].get('is_critical', False),
                       x['task'].get('start_date', datetime.now()))
    )

    # Сначала добавляем информацию о родительских задачах
    for parent_info in all_parent_tasks:
        parent = parent_info['task']
        subtasks = parent_info['subtasks']

        required_employees = parent.get('required_employees', 1)

        # Получаем название задачи
        parent_name = parent.get('name', 'Неизвестная задача')

        message += f"\n*{parent_name}* (Групповая задача"
        if required_employees > 1:
            message += f", требуется {required_employees} исполнителей"
        message += ")\n"

        # Добавляем базовую информацию о родительской задаче даже без подзадач
        if parent.get('start_date') and parent.get('end_date'):
            start_date_str = parent['start_date'].strftime('%d.%m.%Y')
            end_date_str = parent['end_date'].strftime('%d.%m.%Y')
            message += f"   - Даты: {start_date_str} — {end_date_str}\n"

        if 'duration' in parent:
            message += f"   - Длительность: {parent['duration']} дней\n"

        if parent.get('is_critical'):
            message += "   - Критическая задача\n"

        if parent.get('reserve'):
            message += f"   - Резерв: {parent['reserve']} дней\n"

        # Добавляем информацию о подзадачах если они есть
        if subtasks:
            message += "   - Подзадачи:\n"

            for subtask in subtasks:
                # Выделяем должность из имени подзадачи, если указано
                subtask_name = subtask.get('name', '')
                position = ""
                if ' - ' in subtask_name:
                    position = subtask_name.split(' - ')[1]
                    message += f"      - *{position}*:\n"
                else:
                    message += f"      - Подзадача:\n"

                # Безопасное получение имени исполнителя
                employee_name = subtask.get('employee', 'Не назначен')
                if employee_name is None:
                    employee_name = 'Не назначен'

                message += f"         Исполнитель: {employee_name}\n"

                # Безопасное форматирование дат
                if subtask.get('start_date') and subtask.get('end_date'):
                    start_date_str = subtask['start_date'].strftime('%d.%m.%Y')
                    end_date_str = subtask['end_date'].strftime('%d.%m.%Y')
                    message += f"         Даты: {start_date_str} — {end_date_str}\n"

                if 'duration' in subtask:
                    message += f"         Длительность: {subtask['duration']} дней\n"

                if subtask.get('is_critical'):
                    message += "         Критическая задача\n"

                if subtask.get('reserve'):
                    message += f"         Резерв: {subtask['reserve']} дней\n"
        else:
            # Если подзадач нет, но задача групповая, показываем сообщение
            message += "   - Подзадачи не назначены\n"

    # Затем добавляем информацию о обычных задачах
    sorted_standalone = sorted(
        standalone_tasks,
        key=lambda x: (not x.get('is_critical', False), x.get('start_date', datetime.now()))
    )

    for task in sorted_standalone:
        message += f"\n*{task.get('name', 'Неизвестная задача')}*\n"

        # Безопасное получение имени исполнителя
        employee_name = task.get('employee', 'Не назначен')
        if employee_name is None:
            employee_name = 'Не назначен'

        message += f"   - Исполнитель: {employee_name}\n"

        # Безопасное форматирование дат
        if task.get('start_date') and task.get('end_date'):
            start_date_str = task['start_date'].strftime('%d.%m.%Y')
            end_date_str = task['end_date'].strftime('%d.%m.%Y')
            message += f"   - Даты: {start_date_str} — {end_date_str}\n"

        if 'duration' in task:
            message += f"   - Длительность: {task['duration']} дней\n"

        if task.get('is_critical'):
            message += "   - Критическая задача\n"

        if task.get('reserve'):
            message += f"   - Резерв: {task['reserve']} дней\n"

    # Добавляем информацию о сотрудниках
    message += "\n*Сотрудники:*\n"
    employees = set()
    for task in calendar_plan['tasks']:
        employee = task.get('employee')
        # Добавляем проверку на None и пустое значение
        if employee and employee != "Unassigned" and employee != "Не назначен" and employee is not None:
            employees.add(employee)

    for employee in sorted(list(employees)):
        message += f"- {employee}\n"

    # Добавляем общую продолжительность проекта
    message += f"\n*Общая продолжительность проекта:* {calendar_plan['project_duration']} дней"

    try:
        await query.edit_message_text(
            message,
            reply_markup=plan_actions_keyboard(),
            parse_mode='Markdown'
        )
    except Exception as e:
        # Если сообщение слишком длинное или возникла другая ошибка
        error_message = f"Ошибка при отображении информации о проекте: {str(e)}\n\n"
        error_message += "Попробуйте воспользоваться диаграммой Ганта для визуализации проекта."
        await query.edit_message_text(
            error_message,
            reply_markup=plan_actions_keyboard()
        )

    return BotStates.SHOW_PLAN


async def back_to_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for going back to tasks."""

    def get_tasks_message(context):
        project_id = context.user_data.get('current_project_id')
        if not project_id:
            raise ValueError("Project ID not found")

        project_data = get_project_data(project_id)
        if not project_data:
            raise ValueError("Project not found")

        message = f"📊 *Проект: {project_data['name']}*\n\n"
        message += f"*Задачи:* {len(project_data['tasks'])}\n\n"

        if project_data['tasks']:
            message += "*Список задач:*\n"
            for i, task in enumerate(project_data['tasks'][:10]):  # Limit to 10 tasks to avoid long messages
                message += f"{i + 1}. {task['name']} ({task['duration']} дн.) - {task['position']}\n"

            if len(project_data['tasks']) > 10:
                message += f"...и еще {len(project_data['tasks']) - 10} задач\n"
        else:
            message += "Задачи еще не добавлены.\n"

        message += "\nДобавьте информацию о задаче в формате:\n"
        message += "<название задачи> | <длительность в днях> | <должность исполнителя>\n\n"
        message += "Например: Создание тарифов обучения | 1 | Технический специалист"

        return message

    return await handle_back_button(
        update,
        context,
        BotStates.ADD_TASK,
        get_tasks_message,
        task_actions_keyboard
    )


async def back_to_dependencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for going back to dependencies."""
    logger.info("Starting back_to_dependencies handler")
    query = update.callback_query
    await query.answer()

    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await query.edit_message_text(
            "Ошибка: проект не найден. Пожалуйста, выберите проект заново.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Get project data
    project_data = get_project_data(project_id)
    if not project_data:
        await query.edit_message_text(
            "Проект не найден или был удален.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Create message about dependencies
    message = f"📊 *Проект: {project_data['name']}*\n\n"
    message += "Укажите зависимости между задачами в формате:\n"
    message += "<название задачи> | <зависимости через запятую>\n\n"
    message += "Например: Задача 2 | Задача 1, Задача 3\n\n"
    message += "Список задач:\n"

    for i, task in enumerate(project_data['tasks']):
        message += f"{i + 1}. {task['name']}\n"

    await query.edit_message_text(
        message,
        reply_markup=dependencies_actions_keyboard(),
        parse_mode='Markdown'
    )
    return BotStates.ADD_DEPENDENCIES


async def back_to_employees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата к списку сотрудников."""
    logger.info("Начало обработки back_to_employees")

    query = update.callback_query
    await query.answer()

    # Возвращаемся к показу сотрудников
    return await show_employees(update, context)

async def back_to_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата к просмотру плана проекта."""
    query = update.callback_query
    await query.answer()

    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await query.edit_message_text(
            "Ошибка: проект не найден. Пожалуйста, выберите проект заново.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Получаем данные проекта
    project_data = get_project_data(project_id)
    if not project_data:
        await query.edit_message_text(
            "Проект не найден или был удален.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Формируем краткое сообщение о плане
    message = f"📊 *Проект: {project_data['name']}*\n\n"
    start_date = context.user_data.get('project_start_date')
    if start_date:
        message += f"*Дата начала:* {start_date.strftime('%d.%m.%Y')}\n\n"
    message += f"*Задач:* {len(project_data['tasks'])}\n*Сотрудников:* {len(project_data['employees'])}\n\n"
    message += "Выберите действие:"  

    await query.edit_message_text(
        message,
        reply_markup=plan_actions_keyboard(),
        parse_mode='Markdown'
    )
    return BotStates.SHOW_PLAN

async def preview_before_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows distribution of tasks by employees and allows editing descriptions before Jira export."""
    query = update.callback_query
    await query.answer()

    # Get calendar plan
    calendar_plan = context.user_data.get('calendar_plan')
    if not calendar_plan:
        await query.edit_message_text(
            "Error: calendar plan not found. Calculate plan first.",
            reply_markup=plan_actions_keyboard()
        )
        return BotStates.SHOW_PLAN

    # Initialize task_descriptions if it doesn't exist
    if 'task_descriptions' not in context.user_data:
        context.user_data['task_descriptions'] = {}
    
    task_descriptions = context.user_data['task_descriptions']
    
    # Group tasks by parent_task_id or by name for tasks with multiple required employees
    parent_tasks = {}
    standalone_tasks = []
    
    for task in calendar_plan['tasks']:
        if task.get('required_employees', 1) > 1:
            parent_id = task.get('parent_task_id', f"name_{task['name']}")
            if parent_id not in parent_tasks:
                parent_tasks[parent_id] = {
                    'name': task['name'],
                    'subtasks': []
                }
            parent_tasks[parent_id]['subtasks'].append(task)
        else:
            standalone_tasks.append(task)
    
    # Format message with proper grouping
    message = "*Распределение задач по сотрудникам:*\n\n"
    
    # First add group tasks
    for parent_id, parent_data in parent_tasks.items():
        task_name = parent_data['name']
        subtasks = parent_data['subtasks']
        
        message += f"*{task_name}* (Групповая задача, исполнителей: {len(subtasks)})\n"
        
        for subtask in subtasks:
            message += f"   - Исполнитель: {subtask['employee']}\n"
            message += f"   - Даты: {subtask['start_date'].strftime('%d.%m.%Y')} — {subtask['end_date'].strftime('%d.%m.%Y')}\n"
            task_id_str = str(subtask['id'])
            desc = task_descriptions.get(task_id_str, "(нет описания)")
            message += f"   - Описание: {desc}\n\n"
    
    # Then add standalone tasks
    for task in standalone_tasks:
        message += f"*{task['name']}*\n"
        message += f"   - Даты: {task['start_date'].strftime('%d.%m.%Y')} — {task['end_date'].strftime('%d.%m.%Y')}\n"
        message += f"   - Исполнитель: {task['employee']}\n"
        task_id_str = str(task['id'])
        desc = task_descriptions.get(task_id_str, "(нет описания)")
        message += f"   - Описание: {desc}\n\n"
    
    # Create keyboard buttons
    keyboard = []
    
    # Add buttons for group tasks
    for parent_id, parent_data in parent_tasks.items():
        for subtask in parent_data['subtasks']:
            keyboard.append([
                InlineKeyboardButton(f"Изменить описание: {subtask['name']} | {subtask['employee']}", 
                                     callback_data=f"edit_desc_{subtask['id']}")
            ])
    
    # Add buttons for standalone tasks
    for task in standalone_tasks:
        keyboard.append([
            InlineKeyboardButton(f"Изменить описание: {task['name']}", 
                                 callback_data=f"edit_desc_{task['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton("Экспорт в Jira", callback_data="export_jira")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_plan")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return BotStates.PREVIEW_BEFORE_EXPORT

async def edit_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        # Get task ID from callback_data
        task_id = int(query.data.replace('edit_desc_', ''))
        context.user_data['edit_desc_task_id'] = task_id
        
        await query.edit_message_text(
            f"Enter new description for task (or leave empty to remove description):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data="cancel_edit_desc")]
            ])
        )
        return BotStates.PREVIEW_BEFORE_EXPORT
    except ValueError:
        logger.error(f"Invalid task ID in callback data: {query.data}")
        await query.edit_message_text(
            "Error processing task ID. Please try again.",
            reply_markup=plan_actions_keyboard()
        )
        return BotStates.SHOW_PLAN

async def save_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет описание задачи и возвращает к предпросмотру."""
    # Не вызываем .answer() у None
    if update.callback_query:
        await update.callback_query.answer()
        # Можно добавить обработку callback, если потребуется
        return
    # Обработка текстового сообщения
    task_id = context.user_data.get('edit_desc_task_id')
    if not task_id:
        await update.message.reply_text("Ошибка: не выбрана задача для редактирования.")
        return BotStates.PREVIEW_BEFORE_EXPORT

    desc = update.message.text.strip()
    if 'task_descriptions' not in context.user_data:
        context.user_data['task_descriptions'] = {}
    if desc:
        context.user_data['task_descriptions'][str(task_id)] = desc
    else:
        context.user_data['task_descriptions'].pop(str(task_id), None)
    context.user_data.pop('edit_desc_task_id', None)

    await update.message.reply_text("Описание сохранено.")
    # Возвращаем предпросмотр
    return await preview_before_export(update, context)


def generate_project_text_report(calendar_plan):
    """
    Generates a text report of the project information.

    Args:
        calendar_plan: Calendar plan data

    Returns:
        Text report as string
    """
    report = "ИНФОРМАЦИЯ О ПРОЕКТЕ\n"
    report += "=" * 40 + "\n\n"

    # Project duration
    report += f"Общая продолжительность проекта: {calendar_plan['project_duration']} дней\n\n"

    # Critical path
    report += "КРИТИЧЕСКИЙ ПУТЬ:\n"
    report += "-" * 40 + "\n"
    if isinstance(calendar_plan['critical_path'], list):
        if calendar_plan['critical_path'] and isinstance(calendar_plan['critical_path'][0], dict):
            for task in calendar_plan['critical_path']:
                report += f"- {task['name']}\n"
        else:
            for task_name in calendar_plan['critical_path']:
                report += f"- {task_name}\n"
    report += "\n"

    # Group tasks by parent/standalone
    parent_tasks = {}
    standalone_tasks = []

    for task in calendar_plan['tasks']:
        if task.get('is_parent') or task.get('required_employees', 1) > 1:
            parent_tasks[task['id']] = {
                'task': task,
                'subtasks': []
            }
        elif not task.get('parent_id') and not task.get('is_subtask'):
            if ' - ' not in task.get('name', ''):
                standalone_tasks.append(task)

    # Add subtasks to parent tasks
    for task in calendar_plan['tasks']:
        name = task.get('name', '')
        if ' - ' in name:
            base_name = name.split(' - ')[0]

            # Find parent task by name
            for parent_id, parent_data in parent_tasks.items():
                parent_name = parent_data['task'].get('name', '')
                if parent_name == base_name:
                    parent_data['subtasks'].append(task)
                    break

    # Add tasks to report
    report += "ЗАДАЧИ:\n"
    report += "-" * 40 + "\n\n"

    # Add parent tasks with subtasks
    for parent_id, parent_data in parent_tasks.items():
        parent = parent_data['task']
        subtasks = parent_data['subtasks']

        report += f"ГРУППОВАЯ ЗАДАЧА: {parent.get('name')}\n"

        # Basic parent task info
        if parent.get('start_date') and parent.get('end_date'):
            start_date_str = parent['start_date'].strftime('%d.%m.%Y')
            end_date_str = parent['end_date'].strftime('%d.%m.%Y')
            report += f"Даты: {start_date_str} — {end_date_str}\n"

        if 'duration' in parent:
            report += f"Длительность: {parent['duration']} дней\n"

        report += f"Критическая задача: {'Да' if parent.get('is_critical') else 'Нет'}\n"

        if parent.get('reserve'):
            report += f"Резерв: {parent['reserve']} дней\n"

        # Add subtasks
        if subtasks:
            report += "\nПодзадачи:\n"

            for subtask in subtasks:
                subtask_name = subtask.get('name', '')
                if ' - ' in subtask_name:
                    position = subtask_name.split(' - ')[1]
                    report += f"  * {position}:\n"
                else:
                    report += f"  * Подзадача:\n"

                employee_name = subtask.get('employee', 'Не назначен')
                if employee_name is None:
                    employee_name = 'Не назначен'

                report += f"    Исполнитель: {employee_name}\n"

                if subtask.get('start_date') and subtask.get('end_date'):
                    start_date_str = subtask['start_date'].strftime('%d.%m.%Y')
                    end_date_str = subtask['end_date'].strftime('%d.%m.%Y')
                    report += f"    Даты: {start_date_str} — {end_date_str}\n"

                if 'duration' in subtask:
                    report += f"    Длительность: {subtask['duration']} дней\n"

                if subtask.get('is_critical'):
                    report += f"    Критическая задача: Да\n"

                if subtask.get('reserve'):
                    report += f"    Резерв: {subtask['reserve']} дней\n"

                report += "\n"
        else:
            report += "Подзадачи не назначены\n"

        report += "-" * 40 + "\n\n"

    # Add standalone tasks
    if standalone_tasks:
        report += "ОТДЕЛЬНЫЕ ЗАДАЧИ:\n"
        report += "-" * 40 + "\n\n"

        for task in standalone_tasks:
            report += f"ЗАДАЧА: {task.get('name')}\n"

            employee_name = task.get('employee', 'Не назначен')
            if employee_name is None:
                employee_name = 'Не назначен'

            report += f"Исполнитель: {employee_name}\n"

            if task.get('start_date') and task.get('end_date'):
                start_date_str = task['start_date'].strftime('%d.%m.%Y')
                end_date_str = task['end_date'].strftime('%d.%m.%Y')
                report += f"Даты: {start_date_str} — {end_date_str}\n"

            if 'duration' in task:
                report += f"Длительность: {task['duration']} дней\n"

            report += f"Критическая задача: {'Да' if task.get('is_critical') else 'Нет'}\n"

            if task.get('reserve'):
                report += f"Резерв: {task['reserve']} дней\n"

            report += "-" * 40 + "\n\n"

    # Add employee summary
    report += "СОТРУДНИКИ:\n"
    report += "-" * 40 + "\n"

    employees = set()
    for task in calendar_plan['tasks']:
        employee = task.get('employee')
        if employee and employee != "Unassigned" and employee != "Не назначен" and employee is not None:
            employees.add(employee)

    for employee in sorted(list(employees)):
        report += f"- {employee}\n"

    return report


async def export_project_info_as_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exports project information as a text file."""
    query = update.callback_query
    await query.answer()

    # Get calendar plan
    calendar_plan = context.user_data.get('calendar_plan')
    if not calendar_plan:
        await query.edit_message_text(
            "Ошибка: календарный план не найден. Сначала рассчитайте план.",
            reply_markup=plan_actions_keyboard()
        )
        return BotStates.SHOW_PLAN

    # Generate text report
    text_report = generate_project_text_report(calendar_plan)

    # Create file buffer
    buffer = io.BytesIO(text_report.encode('utf-8'))
    buffer.name = "project_info.txt"

    # Send file to user
    await query.message.reply_document(
        document=buffer,
        filename="project_info.txt",
        caption="Информация о проекте в текстовом формате"
    )

    return BotStates.SHOW_PLAN


async def handle_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE, target_state, message_function,
                             keyboard_function):
    """
    Generic handler for back buttons to ensure consistent behavior.

    Args:
        update: Update object
        context: Context object
        target_state: The state to transition to
        message_function: Function that generates the message text
        keyboard_function: Function that generates the keyboard

    Returns:
        The target state
    """
    query = update.callback_query
    await query.answer()

    try:
        # Generate message and keyboard
        message = message_function(context)
        keyboard = keyboard_function()

        # Update the message
        await safe_edit_message_text(
            query,
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return target_state
    except Exception as e:
        logger.error(f"Error in back button handler: {str(e)}")
        # Fallback to main menu on error
        await query.edit_message_text(
            "Произошла ошибка при переходе назад. Возвращаюсь в главное меню.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU


async def add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler specifically for adding a new employee."""
    logger.info("Starting add_employee handler")
    query = update.callback_query
    await query.answer()

    # Show the form for adding a new employee
    await safe_edit_message_text(
        query,
        "Добавьте информацию о сотруднике в формате:\n"
        "<имя> | <должность> | <выходные через запятую>\n\n"
        "Например: Иванов Иван | Технический специалист | Суббота, Воскресенье",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Отмена", callback_data="back_to_employees")]
        ])
    )
    return BotStates.ADD_EMPLOYEES


async def show_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список доступных должностей для выбора."""
    logger.info("Начало обработки show_positions")

    query = update.callback_query
    await query.answer()

    # Получаем список всех возможных должностей
    positions = get_all_positions()

    if not positions:
        await query.edit_message_text(
            "В базе данных нет должностей. Необходимо сначала добавить сотрудников.",
            reply_markup=employees_actions_keyboard()
        )
        return BotStates.ADD_EMPLOYEES

    # Сохраняем список должностей в контексте
    context.user_data['available_positions'] = positions

    # Формируем сообщение
    message = "Выберите должность сотрудника:\n\n"

    # Создаем клавиатуру с должностями
    keyboard = []
    for position in positions:
        # Вычисляем хеш должности для идентификации в callback_data
        position_hash = str(hash(position) % 1000000)
        keyboard.append([InlineKeyboardButton(position, callback_data=f"pos_{position_hash}")])

    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_employees")])

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return BotStates.SELECT_POSITION


async def handle_position_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for when a position is selected."""
    logger.info("Starting handle_position_selection handler")
    query = update.callback_query
    await query.answer()

    # Get the position hash from callback data
    position_hash = int(query.data.replace('pos_', ''))

    # Find the position by hash
    positions = context.user_data.get('available_positions', [])
    position = next((p for p in positions if hash(p) % 1000000 == position_hash), None)

    if not position:
        await safe_edit_message_text(
            query,
            "Должность не найдена. Пожалуйста, попробуйте еще раз.",
            reply_markup=employees_actions_keyboard()
        )
        return BotStates.ADD_EMPLOYEES

    logger.info(f"Selected position: {position}")

    # Save the selected position
    context.user_data['selected_position'] = position

    # Get employees with this position
    employees = get_employees_by_position(position=position)

    if not employees:
        # No employees found for this position
        keyboard = [
            [InlineKeyboardButton("Добавить нового сотрудника", callback_data="add_new_employee")],
            [InlineKeyboardButton("Назад", callback_data="back_to_positions")]
        ]
        await safe_edit_message_text(
            query,
            f"Сотрудники с должностью '{position}' не найдены. Хотите добавить нового сотрудника?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Show list of employees for selection
        message = f"Выберите сотрудника на должность '{position}':\n\n"
        keyboard = []

        for employee in employees:
            days_off_str = ", ".join(employee['days_off']) if employee['days_off'] else "Без выходных"
            message += f"- {employee['name']} (Выходные: {days_off_str})\n"
            keyboard.append([
                InlineKeyboardButton(employee['name'], callback_data=f"select_employee_{employee['id']}")
            ])

        keyboard.append([InlineKeyboardButton("Добавить нового сотрудника", callback_data="add_new_employee")])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_positions")])

        await safe_edit_message_text(
            query,
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    return BotStates.SELECT_EMPLOYEE


async def handle_employee_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for when an employee is selected."""
    logger.info("Starting handle_employee_selection handler")
    query = update.callback_query
    await query.answer()

    # Get employee ID from callback data
    employee_id = int(query.data.replace('select_employee_', ''))
    logger.info(f"Selected employee ID: {employee_id}")

    # Get project ID
    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await safe_edit_message_text(
            query,
            "Ошибка: не найден ID проекта. Пожалуйста, выберите проект заново.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Add employee to project
    result = add_employee_to_project(employee_id, project_id)

    if result:
        await safe_edit_message_text(
            query,
            "Сотрудник успешно добавлен в проект!",
            reply_markup=employees_actions_keyboard()
        )
    else:
        await safe_edit_message_text(
            query,
            "Ошибка при добавлении сотрудника в проект. Возможно, сотрудник уже добавлен.",
            reply_markup=employees_actions_keyboard()
        )

    return BotStates.ADD_EMPLOYEES


async def back_to_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for going back to position selection."""
    logger.info("Starting back_to_positions handler")
    query = update.callback_query
    await query.answer()

    # Get all positions again
    positions = get_all_positions()

    # Show position selection
    await safe_edit_message_text(
        query,
        "Выберите должность сотрудника:",
        reply_markup=position_selection_keyboard(positions)
    )
    return BotStates.SELECT_POSITION


async def request_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for requesting custom date input."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Введите дату начала проекта в формате ДД.ММ.ГГГГ (например, 15.05.2025).\n\n"
        "Или используйте относительный формат:\n"
        "• 'сегодня'\n"
        "• 'завтра'\n"
        "• '+N' (через N дней от текущей даты)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Отмена", callback_data="back_to_project")]
        ])
    )

    context.user_data['awaiting_custom_date'] = True
    return BotStates.SET_START_DATE


async def add_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для кнопки 'Добавить задачи'."""
    logger.info("Начало обработки add_tasks_handler")
    query = update.callback_query
    await query.answer()

    project_id = context.user_data.get('current_project_id')
    if not project_id:
        logger.error("ID проекта не найден в контексте")
        await query.edit_message_text(
            "Ошибка: проект не выбран. Пожалуйста, выберите проект заново.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Загружаем существующие задачи
    project_data = get_project_data(project_id)
    logger.info(f"Найдено задач: {len(project_data['tasks']) if project_data and 'tasks' in project_data else 0}")

    # Формируем сообщение
    tasks_text = ""
    if project_data and project_data['tasks']:
        tasks_text = "Существующие задачи:\n"
        for idx, task in enumerate(
                project_data['tasks'][:10]):  # Ограничиваем 10 задачами для предотвращения слишком длинного сообщения
            tasks_text += f"{idx + 1}. {task['name']} ({task['duration']} дн.) - {task['position']}\n"

        if len(project_data['tasks']) > 10:
            tasks_text += f"...и еще {len(project_data['tasks']) - 10} задач\n"

        tasks_text += "\n"

    try:
        await query.edit_message_text(
            f"{tasks_text}Добавьте информацию о задаче в формате:\n"
            "<название задачи> | <длительность в днях> | <должность исполнителя>\n\n"
            "Например: Создание тарифов обучения | 1 | Технический специалист",
            reply_markup=task_actions_keyboard()
        )
        logger.info("Сообщение с информацией о задачах отправлено")
        return BotStates.ADD_TASK
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {str(e)}")
        # В случае ошибки отправляем новое сообщение вместо редактирования
        await query.message.reply_text(
            "Добавьте информацию о задаче в формате:\n"
            "<название задачи> | <длительность в днях> | <должность исполнителя>\n\n"
            "Например: Создание тарифов обучения | 1 | Технический специалист",
            reply_markup=task_actions_keyboard()
        )
        return BotStates.ADD_TASK


async def assign_all_employees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды для назначения всех сотрудников на текущий проект.

    Использование: /assign_all_employees
    """
    from utils.employee_assignment import assign_all_employees_to_project

    # Проверяем, выбран ли проект
    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await update.message.reply_text(
            "Сначала выберите проект с помощью команды /list_projects"
        )
        return

    # Назначаем всех сотрудников
    count = assign_all_employees_to_project(project_id)

    if count > 0:
        await update.message.reply_text(
            f"Успешно назначено {count} сотрудников на текущий проект.\n"
            "Теперь вы можете пересчитать календарный план."
        )
    else:
        await update.message.reply_text(
            "Не удалось назначить сотрудников на проект. Проверьте лог ошибок."
        )


async def assign_all_employees_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик кнопки для назначения всех сотрудников на текущий проект.
    """
    from utils.employee_assignment import assign_all_employees_to_project

    query = update.callback_query
    await query.answer()

    # Проверяем, выбран ли проект
    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await query.edit_message_text(
            "Ошибка: проект не выбран. Пожалуйста, выберите проект заново.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Назначаем всех сотрудников
    count = assign_all_employees_to_project(project_id)

    if count > 0:
        # Получаем обновленные данные проекта
        project_data = get_project_data(project_id)

        # Формируем сообщение об успешном назначении
        message = f"✅ Успешно назначено {count} сотрудников на проект.\n\n"
        message += format_project_info(project_data, context)

        await query.edit_message_text(
            message,
            reply_markup=get_project_keyboard(project_data),
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            "❌ Не удалось назначить сотрудников на проект. Проверьте лог ошибок.",
            reply_markup=get_project_keyboard(get_project_data(project_id)),
            parse_mode='Markdown'
        )

    return BotStates.SELECT_PROJECT


async def show_dependencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает существующие зависимости между задачами проекта."""
    logger.info("Начало обработки show_dependencies")

    query = update.callback_query
    await query.answer()

    # Получаем ID проекта
    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await query.edit_message_text(
            "Ошибка: проект не выбран. Пожалуйста, вернитесь в главное меню.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Получаем данные проекта и зависимости
    project_data = get_project_data(project_id)
    dependencies = get_task_dependencies(project_id)

    if not project_data or not project_data.get('tasks'):
        await query.edit_message_text(
            "В проекте нет задач для отображения зависимостей.",
            reply_markup=back_to_main_keyboard()
        )
        return BotStates.MAIN_MENU

    # Создаем словарь id -> задача для быстрого доступа
    tasks_by_id = {task['id']: task for task in project_data['tasks']}

    # Формируем список зависимостей в читаемом виде
    message = f"📋 *Зависимости в проекте \"{project_data['name']}\"*\n\n"

    if not dependencies:
        message += "В проекте нет зависимостей между задачами.\n"
    else:
        for task_id, predecessors in dependencies.items():
            if task_id not in tasks_by_id:
                continue

            task_name = tasks_by_id[task_id]['name']
            message += f"• *{task_name}* зависит от:\n"

            for pred_id in predecessors:
                if pred_id in tasks_by_id:
                    pred_name = tasks_by_id[pred_id]['name']
                    message += f"  - {pred_name}\n"

    # Проверяем наличие циклических зависимостей
    has_cycles, cycle_path = check_circular_dependencies(project_id)
    if has_cycles:
        message += f"\n⚠️ *Обнаружена циклическая зависимость*:\n{' -> '.join(cycle_path)}\n"
        message += "Это может привести к проблемам при построении календарного плана.\n"

    # Создаем клавиатуру с действиями
    keyboard = [
        [InlineKeyboardButton("Добавить зависимость", callback_data="add_dependency")],
        [InlineKeyboardButton("К добавлению сотрудников", callback_data="goto_employees")],
        [InlineKeyboardButton("Назад к задачам", callback_data="back_to_tasks")],
        [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
    ]

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

    return BotStates.ADD_DEPENDENCIES


async def show_employees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список сотрудников проекта и предлагает добавить нового."""
    logger.info("Начало обработки show_employees")

    query = update.callback_query
    await query.answer()

    # Получаем ID проекта
    project_id = context.user_data.get('current_project_id')
    if not project_id:
        await query.edit_message_text(
            "Ошибка: проект не выбран. Пожалуйста, вернитесь в главное меню.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Получаем данные проекта
    project_data = get_project_data(project_id)
    if not project_data:
        await query.edit_message_text(
            "Ошибка: проект не найден. Пожалуйста, вернитесь в главное меню.",
            reply_markup=main_menu_keyboard()
        )
        return BotStates.MAIN_MENU

    # Формируем сообщение со списком сотрудников
    message = f"📋 *Сотрудники проекта \"{project_data['name']}\"*\n\n"

    if not project_data.get('employees'):
        message += "В проекте еще нет сотрудников.\n\n"
    else:
        message += "*Текущие сотрудники:*\n"
        for i, employee in enumerate(project_data['employees'], 1):
            days_off_str = ", ".join(employee.get('days_off', [])) if employee.get('days_off') else "Без выходных"
            message += f"{i}. *{employee['name']}* - {employee['position']}\n   Выходные: {days_off_str}\n"

    # Добавляем информацию о необходимых должностях
    required_positions = set()
    for task in project_data.get('tasks', []):
        if task.get('position'):
            required_positions.add(task['position'])

    if required_positions:
        message += "\n*Необходимые должности в проекте:*\n"
        for position in sorted(required_positions):
            message += f"- {position}\n"

    # Создаем клавиатуру с действиями
    keyboard = [
        [InlineKeyboardButton("Добавить сотрудника", callback_data="add_employee")],
        [InlineKeyboardButton("Выбрать по должности", callback_data="show_positions")],
        [InlineKeyboardButton("Назначить всех сотрудников", callback_data="assign_all_employees")],
        [InlineKeyboardButton("Рассчитать календарный план", callback_data="calculate")],
        [InlineKeyboardButton("Назад к зависимостям", callback_data="back_to_dependencies")],
        [InlineKeyboardButton("Назад к проекту", callback_data="back_to_project")],
        [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
    ]

    try:
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка при отображении сотрудников: {str(e)}")
        # В случае ошибки (например, слишком длинное сообщение) отправляем новое
        await query.message.reply_text(
            "Список сотрудников проекта",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    return BotStates.ADD_EMPLOYEES




