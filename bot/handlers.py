from datetime import datetime

from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from logger import logger
from bot.states import BotStates
from bot.keyboards import (
    main_menu_keyboard, project_type_keyboard, templates_keyboard,
    task_actions_keyboard, dependencies_actions_keyboard,
    employees_actions_keyboard, plan_actions_keyboard, projects_keyboard,
    position_selection_keyboard
)
from bot.messages import (
    WELCOME_MESSAGE, HELP_MESSAGE, SELECT_PROJECT_TYPE_MESSAGE,
    SELECT_TEMPLATE_PROMPT, UPLOAD_CSV_PROMPT, CREATE_PROJECT_PROMPT,
    ADD_TASK_PROMPT, ADD_DEPENDENCIES_PROMPT, ADD_EMPLOYEES_PROMPT,
    PLAN_CALCULATION_START, EXPORT_TO_JIRA_SUCCESS, CSV_FORMAT_ERROR, MY_ID_MESSAGE
)
from config import ALLOWED_USERS
from database.models import AllowedUser, Employee, DayOff, Project, Task, TaskDependency, DayOff, ProjectTemplate, TaskTemplate, \
    TaskTemplateDependency
from database.operations import (
    create_new_project, add_project_task, add_task_dependencies,
    add_project_employee, add_employee_to_project, get_project_data, get_employees_by_position,
    get_project_templates, create_project_from_template, get_user_projects, get_allowed_users, add_allowed_user,
    is_user_allowed, session_scope, get_all_positions, Session
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
    await query.answer()

    # Update the message to ask for a start date
    await query.edit_message_text(
        "Укажите дату начала проекта в формате ДД.ММ.ГГГГ (например, 06.05.2025).\n\n"
        "Можно также указать 'сегодня', 'завтра' или '+N' (где N - количество дней от текущей даты).",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Сегодня", callback_data="date_today"),
            InlineKeyboardButton("Завтра", callback_data="date_tomorrow")
        ], [
            InlineKeyboardButton("Через неделю", callback_data="date_plus7"),
            InlineKeyboardButton("Через 2 недели", callback_data="date_plus14")
        ], [
            InlineKeyboardButton("Отмена", callback_data="back_to_project")
        ]])
    )

    return BotStates.SET_START_DATE


async def process_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the start date input from user."""
    from datetime import datetime, timedelta

    if update.callback_query:
        # Handle quick date selections
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
        elif query.data == "back_to_project":
            # User canceled, go back to project view
            return await select_project(update, context)

        # Store the date in context
        context.user_data['project_start_date'] = start_date

        # Return to project view with confirmation
        project_id = context.user_data.get('current_project_id')
        if project_id:
            await show_project_with_message(
                query,
                context,
                project_id,
                f"Дата начала проекта установлена: {start_date.strftime('%d.%m.%Y')}"
            )
        else:
            await query.edit_message_text(
                f"Дата начала проекта установлена: {start_date.strftime('%d.%m.%Y')}",
                reply_markup=main_menu_keyboard()
            )
        return BotStates.ADD_TASK
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

        # Confirm the date setting
        await update.message.reply_text(
            f"Дата начала проекта установлена: {start_date.strftime('%d.%m.%Y')}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Рассчитать календарный план", callback_data="calculate")
            ], [
                InlineKeyboardButton("Назад к проекту", callback_data="back_to_project")
            ]])
        )
        return BotStates.ADD_TASK

    except (ValueError, IndexError):
        # Handle invalid date format
        await update.message.reply_text(
            "Неверный формат даты. Пожалуйста, укажите дату в формате ДД.ММ.ГГГГ (например, 06.05.2025) "
            "или используйте 'сегодня', 'завтра' или '+N' дней.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Отмена", callback_data="back_to_project")
            ]])
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

    await query.edit_message_text(
        f"{message}\n\n{project_info}",
        reply_markup=get_project_keyboard(project_data),
        parse_mode='Markdown'
    )
    return BotStates.ADD_TASK


def format_project_info(project_data, context):
    """Format project information including start date if set."""
    # Basic project info
    message = f"📊 *Проект: {project_data['name']}*\n\n"

    # Add start date if set
    start_date = context.user_data.get('project_start_date')
    if start_date:
        message += f"*Дата начала:* {start_date.strftime('%d.%m.%Y')}\n\n"

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
    """Обработчик создания нового проекта."""
    query = update.callback_query

    if query and query.data == 'create_project':
        await query.answer()
        # Переходим к выбору типа проекта
        return await select_project_type(update, context)

    # Если пришел текст с названием проекта
    project_name = update.message.text

    # Проверяем, какой способ создания проекта был выбран
    if 'template_id' in context.user_data:
        # Создаем проект на основе шаблона
        template_id = context.user_data['template_id']
        project_id = create_project_from_template(template_id, project_name)

        # Сохраняем ID проекта в контексте
        context.user_data['current_project_id'] = project_id

        # Получаем данные проекта
        project_data = get_project_data(project_id)

        # Сохраняем задачи в контексте
        context.user_data['tasks'] = project_data['tasks']

        # Получаем базовый проект с сотрудниками
        base_project = get_project_data(1)  # Предполагается, что базовый проект имеет ID=1

        # Если есть базовый проект и в нем есть сотрудники
        if base_project and base_project['employees']:
            # Копируем сотрудников из базового проекта в новый проект
            for employee in base_project['employees']:
                add_employee_to_project(employee['id'], project_id)

            # Обновляем данные проекта после добавления сотрудников
            project_data = get_project_data(project_id)

            # Сохраняем сотрудников в контексте
            context.user_data['employees'] = project_data['employees']

            # Переходим сразу к расчету плана, так как у нас есть все необходимые данные
            await update.message.reply_text(
                f"Проект '{project_name}' создан на основе шаблона. Сотрудники автоматически добавлены из базового проекта. Теперь вы можете рассчитать календарный план."
            )

            # Создаем клавиатуру с действиями для проекта
            keyboard = [
                [InlineKeyboardButton("Рассчитать календарный план", callback_data="calculate")],
                [InlineKeyboardButton("Редактировать задачи", callback_data="edit_tasks")],
                [InlineKeyboardButton("Редактировать сотрудников", callback_data="edit_employees")],
                [InlineKeyboardButton("Вернуться в главное меню", callback_data="main_menu")]
            ]

            await update.message.reply_text(
                f"Выберите дальнейшие действия:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            return BotStates.ADD_TASK

        # Если нет базового проекта или в нем нет сотрудников, запрашиваем добавление сотрудников
        await update.message.reply_text(
            f"Проект '{project_name}' создан на основе шаблона. Теперь добавьте информацию о сотрудниках.\n\n{ADD_EMPLOYEES_PROMPT}"
        )
        return BotStates.ADD_EMPLOYEES

    elif 'csv_tasks' in context.user_data:
        # Create project from CSV tasks
        csv_tasks = context.user_data['csv_tasks']

        # Use the new function instead of manually creating tasks
        project_id = create_project_from_tasks(project_name, csv_tasks)

        if not project_id:
            await update.message.reply_text("Error creating project from CSV. Please try again.")
            return BotStates.CREATE_PROJECT

        # Save project ID in context
        context.user_data['current_project_id'] = project_id

        # Get project data to update context
        project_data = get_project_data(project_id)
        context.user_data['tasks'] = project_data['tasks']

        keyboard = [
            [InlineKeyboardButton("Add employees", callback_data="add_employees")],
            [InlineKeyboardButton("Calculate calendar plan", callback_data="calculate")],
            [InlineKeyboardButton("Return to main menu", callback_data="main_menu")]
        ]

        await update.message.reply_text(
            f"Project '{project_name}' successfully created from CSV! Choose next action:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return BotStates.SELECT_PROJECT

    else:
        # Обычное создание проекта
        project_id = create_new_project(project_name)

        # Сохраняем ID проекта в контексте
        context.user_data['current_project_id'] = project_id
        context.user_data['tasks'] = []

        await update.message.reply_text(
            f"Проект '{project_name}' создан. Теперь добавьте задачи.\n\n{ADD_TASK_PROMPT}"
        )
        return BotStates.ADD_TASK


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик добавления задачи."""
    task_data = update.message.text.split('|')

    if len(task_data) != 3:
        await update.message.reply_text(
            f"Неверный формат. Пожалуйста, используйте формат:\n{ADD_TASK_PROMPT}"
        )
        return BotStates.ADD_TASK

    task_name = task_data[0].strip()
    try:
        duration = int(task_data[1].strip())
    except ValueError:
        await update.message.reply_text("Длительность должна быть целым числом дней.")
        return BotStates.ADD_TASK

    position = task_data[2].strip()

    # Добавляем задачу в БД
    project_id = context.user_data['current_project_id']
    task_id = add_project_task(project_id, task_name, duration, position, required_employees=1)

    # Сохраняем задачу в контексте
    if 'tasks' not in context.user_data:
        context.user_data['tasks'] = []
    context.user_data['tasks'].append({
        'id': task_id,
        'name': task_name,
        'duration': duration,
        'position': position
    })

    await update.message.reply_text(
        f"Задача '{task_name}' добавлена. Добавьте еще задачу или перейдите к указанию зависимостей.",
        reply_markup=task_actions_keyboard()
    )
    return BotStates.ADD_TASK


async def add_dependencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик добавления зависимостей между задачами."""
    query = update.callback_query

    if query and query.data == 'next':
        await query.answer()
        await safe_edit_message_text(
            query,
            f"Укажите зависимости между задачами.\n\n{ADD_DEPENDENCIES_PROMPT}"
        )
        # Отправляем список задач для удобства
        tasks_text = "Список задач:\n"
        for idx, task in enumerate(context.user_data['tasks']):
            tasks_text += f"{idx + 1}. {task['name']}\n"

        await query.message.reply_text(tasks_text)
        return BotStates.ADD_DEPENDENCIES

    # Если пришел текст с зависимостями
    if not update.message.text:
        await update.message.reply_text(
            f"Неверный формат. Пожалуйста, используйте формат:\n{ADD_DEPENDENCIES_PROMPT}"
        )
        return BotStates.ADD_DEPENDENCIES

    if '|' not in update.message.text:
        await update.message.reply_text(
            "Не указаны зависимости для задачи. Переходим к следующему этапу.",
            reply_markup=dependencies_actions_keyboard()
        )
        return BotStates.ADD_DEPENDENCIES

    deps_data = update.message.text.split('|')
    task_name = deps_data[0].strip()

    # Находим задачу по имени
    task_id = None
    for task in context.user_data['tasks']:
        if task['name'] == task_name:
            task_id = task['id']
            break

    if not task_id:
        await update.message.reply_text(f"Задача '{task_name}' не найдена. Попробуйте снова.")
        return BotStates.ADD_DEPENDENCIES

    # Парсим предшествующие задачи
    if len(deps_data) > 1:
        predecessors = [pred.strip() for pred in deps_data[1].split(',')]

        # Находим ID предшествующих задач
        predecessor_ids = []
        for pred_name in predecessors:
            for task in context.user_data['tasks']:
                if task['name'] == pred_name:
                    predecessor_ids.append(task['id'])
                    break

        # Добавляем зависимости в БД
        for pred_id in predecessor_ids:
            add_task_dependencies(task_id, pred_id)

    await update.message.reply_text(
        f"Зависимости для задачи '{task_name}' добавлены. Добавьте еще зависимости или перейдите к добавлению сотрудников.",
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

    await safe_edit_message_text(query, PLAN_CALCULATION_START)

    # Получаем данные проекта из БД
    project_id = context.user_data['current_project_id']
    project_data = get_project_data(project_id)

    # Если нет сотрудников в проекте, используем сотрудников из контекста
    if not project_data['employees'] and 'employees' in context.user_data:
        project_data['employees'] = context.user_data['employees']

    # Рассчитываем параметры сетевой модели
    network_parameters = calculate_network_parameters(project_data)

    # Get the start date from context or use today
    start_date = context.user_data.get('project_start_date')

    # Создаем календарный план с учетом выходных дней и стартовой даты
    calendar_plan = create_calendar_plan(network_parameters, project_data, start_date)

    # Сохраняем результаты в контексте
    context.user_data['calendar_plan'] = calendar_plan

    # Генерируем изображение диаграммы Ганта
    gantt_image = generate_gantt_chart(calendar_plan)
    gantt_buffer = io.BytesIO()
    gantt_image.save(gantt_buffer, format='PNG')
    gantt_buffer.seek(0)

    # Format start and end dates for the report
    start_date_str = start_date.strftime('%d.%m.%Y') if start_date else "не указана"

    # Calculate end date based on start date and project duration
    if start_date and 'project_duration' in calendar_plan:
        from datetime import timedelta
        end_date = start_date + timedelta(days=calendar_plan['project_duration'])
        end_date_str = end_date.strftime('%d.%m.%Y')
    else:
        end_date_str = "не определена"

    # Формируем текстовый отчет
    if calendar_plan['critical_path'] and isinstance(calendar_plan['critical_path'][0], dict):
        # Если critical_path содержит словари, извлекаем имена задач
        critical_path_text = "Критический путь: " + " -> ".join(
            [task['name'] for task in calendar_plan['critical_path']])
    elif calendar_plan['critical_path'] and isinstance(calendar_plan['critical_path'][0], str):
        # Если critical_path уже содержит строки (имена задач)
        critical_path_text = "Критический путь: " + " -> ".join(calendar_plan['critical_path'])
    else:
        # Если critical_path пуст или имеет неожиданный формат
        critical_path_text = "Критический путь не определен"

    project_duration = calendar_plan['project_duration']

    report = f"""
Расчет календарного плана завершен!

Дата начала проекта: {start_date_str}
Дата окончания проекта: {end_date_str}
Общая продолжительность проекта: {project_duration} дней

{critical_path_text}

Резервы времени для некритических работ:
"""

    for task in calendar_plan['tasks']:
        if task['is_critical']:
            continue
        report += f"- {task['name']}: {task['reserve']} дней\n"

    # Отправляем отчет и диаграмму
    await query.message.reply_photo(
        photo=gantt_buffer,
        caption="Диаграмма Ганта для календарного плана"
    )

    await query.message.reply_text(
        report,
        reply_markup=plan_actions_keyboard()
    )

    return BotStates.SHOW_PLAN

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
                InlineKeyboardButton("Вернуться в меню", callback_data="main_menu")
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
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
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

    # Организуем задачи для отображения
    tasks_by_id = {task['id']: task for task in calendar_plan['tasks']}

    # Находим родительские задачи и их подзадачи
    parent_tasks = {}
    standalone_tasks = []

    for task in calendar_plan['tasks']:
        if task.get('is_parent'):
            parent_tasks[task['id']] = {
                'task': task,
                'subtasks': []
            }
        elif not task.get('parent_id') and not task.get('is_subtask'):
            standalone_tasks.append(task)

    # Добавляем подзадачи к родительским задачам
    for task in calendar_plan['tasks']:
        parent_id = task.get('parent_id')
        if parent_id and parent_id in parent_tasks:
            parent_tasks[parent_id]['subtasks'].append(task)

    # Сортируем родительские задачи и их подзадачи
    sorted_parents = sorted(
        parent_tasks.values(),
        key=lambda x: x['task'].get('start_date', datetime.now())
    )

    # Сортируем обычные задачи
    sorted_standalone = sorted(
        standalone_tasks,
        key=lambda x: x.get('start_date', datetime.now())
    )

    # Добавляем информацию о задачах
    message += "\n*Задачи:*\n"

    # Сначала добавляем информацию о родительских задачах
    for parent_info in sorted_parents:
        parent = parent_info['task']
        subtasks = parent_info['subtasks']

        required_employees = parent.get('required_employees', 1)

        message += f"\n*{parent['name']}* (Групповая задача"
        if required_employees > 1:
            message += f", требуется {required_employees} исполнителей"
        message += ")\n"

        # Добавляем информацию о подзадачах
        for subtask in subtasks:
            # Безопасное получение имени исполнителя
            employee_name = subtask.get('employee', 'Не назначен')
            if employee_name is None:
                employee_name = 'Не назначен'

            message += f"   - Исполнитель: {employee_name}\n"

            # Безопасное форматирование дат
            start_date_str = subtask['start_date'].strftime('%d.%m.%Y') if subtask.get(
                'start_date') else 'Не определена'
            end_date_str = subtask['end_date'].strftime('%d.%m.%Y') if subtask.get('end_date') else 'Не определена'
            message += f"   - Даты: {start_date_str} — {end_date_str}\n"

            message += f"   - Длительность: {subtask['duration']} дней\n"
            if subtask.get('is_critical'):
                message += "   - Критическая задача\n"
            if subtask.get('reserve'):
                message += f"   - Резерв: {subtask['reserve']} дней\n"

    # Затем добавляем информацию о обычных задачах
    for task in sorted_standalone:
        message += f"\n*{task['name']}*\n"

        # Безопасное получение имени исполнителя
        employee_name = task.get('employee', 'Не назначен')
        if employee_name is None:
            employee_name = 'Не назначен'

        message += f"   - Исполнитель: {employee_name}\n"

        # Безопасное форматирование дат
        start_date_str = task['start_date'].strftime('%d.%m.%Y') if task.get('start_date') else 'Не определена'
        end_date_str = task['end_date'].strftime('%d.%m.%Y') if task.get('end_date') else 'Не определена'
        message += f"   - Даты: {start_date_str} — {end_date_str}\n"

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
        if employee and employee != "Unassigned" and employee != "Не назначен":
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
    """Обработчик возврата к задачам."""
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

    # Формируем сообщение с информацией о задачах
    message = f"📊 *Проект: {project_data['name']}*\n\n"
    message += f"*Задачи:* {len(project_data['tasks'])}\n\n"

    if project_data['tasks']:
        message += "*Список задач:*\n"
        for i, task in enumerate(project_data['tasks']):
            message += f"{i + 1}. {task['name']} ({task['duration']} дн.) - {task['position']}\n"
    else:
        message += "Задачи еще не добавлены.\n"

    message += "\nДобавьте информацию о задаче в формате:\n"
    message += "<название задачи> | <длительность в днях> | <должность исполнителя>\n\n"
    message += "Например: Создание тарифов обучения | 1 | Технический специалист"

    await query.edit_message_text(
        message,
        reply_markup=task_actions_keyboard(),
        parse_mode='Markdown'
    )
    return BotStates.ADD_TASK

async def back_to_dependencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата к зависимостям."""
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

    # Формируем сообщение с информацией о зависимостях
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
    """Обработчик возврата к сотрудникам."""
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

    # Формируем сообщение с информацией о сотрудниках
    message = f"📊 *Проект: {project_data['name']}*\n\n"
    message += f"*Сотрудники:* {len(project_data['employees'])}\n\n"

    if project_data['employees']:
        message += "*Список сотрудников:*\n"
        for i, employee in enumerate(project_data['employees'], 1):
            days_off_str = ", ".join(employee['days_off']) if employee['days_off'] else "Без выходных"
            message += f"{i}. {employee['name']} - {employee['position']} (Выходные: {days_off_str})\n"
    else:
        message += "Сотрудники еще не добавлены.\n"

    message += "\nДобавьте информацию о сотруднике в формате:\n"
    message += "<имя> | <должность> | <выходные через запятую>\n\n"
    message += "Например: Иванов Иван | Технический специалист | Суббота, Воскресенье"

    await query.edit_message_text(
        message,
        reply_markup=employees_actions_keyboard(),
        parse_mode='Markdown'
    )
    return BotStates.ADD_EMPLOYEES

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
