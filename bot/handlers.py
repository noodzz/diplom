from telegram import Update, InputFile
from telegram.ext import ContextTypes, ConversationHandler
from bot.states import BotStates
from bot.keyboards import (
    main_menu_keyboard, project_type_keyboard, templates_keyboard,
    task_actions_keyboard, dependencies_actions_keyboard,
    employees_actions_keyboard, plan_actions_keyboard
)
from bot.messages import (
    WELCOME_MESSAGE, HELP_MESSAGE, SELECT_PROJECT_TYPE_MESSAGE,
    SELECT_TEMPLATE_PROMPT, UPLOAD_CSV_PROMPT, CREATE_PROJECT_PROMPT,
    ADD_TASK_PROMPT, ADD_DEPENDENCIES_PROMPT, ADD_EMPLOYEES_PROMPT,
    PLAN_CALCULATION_START, EXPORT_TO_JIRA_SUCCESS, CSV_FORMAT_ERROR
)
from database.operations import (
    create_new_project, add_project_task, add_task_dependencies,
    add_project_employee, get_project_data, get_employees_by_position,
    get_project_templates, create_project_from_template
)
from utils.csv_import import create_project_from_csv, parse_csv_tasks
from planning.network import calculate_network_parameters
from planning.calendar import create_calendar_plan
from planning.visualization import generate_gantt_chart
from jira_integration.issue_creator import create_jira_issues
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
        await query.edit_message_text(
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

    await query.edit_message_text(
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

    await query.edit_message_text(CREATE_PROJECT_PROMPT)

    return BotStates.CREATE_PROJECT


async def upload_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик загрузки CSV-файла."""
    query = update.callback_query

    if query:
        await query.answer()
        await query.edit_message_text(UPLOAD_CSV_PROMPT)

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

        await update.message.reply_text(
            f"Проект '{project_name}' создан на основе шаблона. Теперь добавьте информацию о сотрудниках.\n\n{ADD_EMPLOYEES_PROMPT}"
        )
        return BotStates.ADD_EMPLOYEES

    elif 'csv_tasks' in context.user_data:
        # Создаем проект на основе CSV
        csv_tasks = context.user_data['csv_tasks']

        # Создаем новый проект
        project_id = create_new_project(project_name)

        # Сохраняем ID проекта в контексте
        context.user_data['current_project_id'] = project_id

        # Словарь для соответствия названия задачи -> ID созданной задачи
        task_name_map = {}

        # Добавляем задачи в БД и сохраняем в контексте
        context.user_data['tasks'] = []

        for task_data in csv_tasks:
            task_id = add_project_task(
                project_id,
                task_data['name'],
                task_data['duration'],
                task_data['position']
            )

            task_name_map[task_data['name']] = task_id

            context.user_data['tasks'].append({
                'id': task_id,
                'name': task_data['name'],
                'duration': task_data['duration'],
                'position': task_data['position']
            })

        # Добавляем зависимости между задачами
        for task_data in csv_tasks:
            if 'predecessors' in task_data and task_data['predecessors']:
                for predecessor_name in task_data['predecessors']:
                    if predecessor_name in task_name_map:
                        add_task_dependencies(
                            task_name_map[task_data['name']],
                            task_name_map[predecessor_name]
                        )

        await update.message.reply_text(
            f"Проект '{project_name}' создан на основе CSV. Теперь добавьте информацию о сотрудниках.\n\n{ADD_EMPLOYEES_PROMPT}"
        )
        return BotStates.ADD_EMPLOYEES

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
    task_id = add_project_task(project_id, task_name, duration, position)

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
        await query.edit_message_text(
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
    """Обработчик добавления сотрудников."""
    query = update.callback_query

    if query and query.data == 'next':
        await query.answer()

        # Получаем ID проекта
        project_id = context.user_data['current_project_id']

        # Загружаем существующих сотрудников
        existing_employees = get_employees_by_position(project_id)

        # Если есть существующие сотрудники, показываем их
        employees_text = ""
        if existing_employees:
            employees_text = "Существующие сотрудники:\n"
            for idx, employee in enumerate(existing_employees):
                days_off_str = ", ".join(employee['days_off'])
                employees_text += f"{idx + 1}. {employee['name']} | {employee['position']} | {days_off_str}\n"

            # Сохраняем сотрудников в контексте
            context.user_data['employees'] = existing_employees

            employees_text += "\nВы можете добавить новых сотрудников или перейти к расчету календарного плана.\n\n"

        await query.edit_message_text(
            f"{employees_text}Добавьте информацию о сотрудниках.\n\n{ADD_EMPLOYEES_PROMPT}",
            reply_markup=employees_actions_keyboard()
        )
        return BotStates.ADD_EMPLOYEES

    # Если пришел текст с информацией о сотруднике
    employee_data = update.message.text.split('|')

    if len(employee_data) != 3:
        await update.message.reply_text(
            f"Неверный формат. Пожалуйста, используйте формат:\n{ADD_EMPLOYEES_PROMPT}"
        )
        return BotStates.ADD_EMPLOYEES

    name = employee_data[0].strip()
    position = employee_data[1].strip()
    days_off = [day.strip() for day in employee_data[2].split(',')]

    # Добавляем сотрудника в БД
    project_id = context.user_data['current_project_id']
    employee_id = add_project_employee(project_id, name, position, days_off)

    # Сохраняем сотрудника в контексте
    if 'employees' not in context.user_data:
        context.user_data['employees'] = []
    context.user_data['employees'].append({
        'id': employee_id,
        'name': name,
        'position': position,
        'days_off': days_off
    })

    await update.message.reply_text(
        f"Сотрудник '{name}' добавлен. Добавьте еще сотрудника или рассчитайте календарный план.",
        reply_markup=employees_actions_keyboard()
    )
    return BotStates.ADD_EMPLOYEES


async def calculate_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик расчета календарного плана."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(PLAN_CALCULATION_START)

    # Получаем данные проекта из БД
    project_id = context.user_data['current_project_id']
    project_data = get_project_data(project_id)

    # Если нет сотрудников в проекте, используем сотрудников из контекста
    if not project_data['employees'] and 'employees' in context.user_data:
        project_data['employees'] = context.user_data['employees']

    # Рассчитываем параметры сетевой модели
    network_parameters = calculate_network_parameters(project_data)

    # Создаем календарный план с учетом выходных дней
    calendar_plan = create_calendar_plan(network_parameters, project_data)

    # Сохраняем результаты в контексте
    context.user_data['calendar_plan'] = calendar_plan

    # Генерируем изображение диаграммы Ганта
    gantt_image = generate_gantt_chart(calendar_plan)
    gantt_buffer = io.BytesIO()
    gantt_image.save(gantt_buffer, format='PNG')
    gantt_buffer.seek(0)

    # Формируем текстовый отчет
    critical_path_text = "Критический путь: " + " -> ".join([task['name'] for task in calendar_plan['critical_path']])
    project_duration = calendar_plan['project_duration']

    report = f"""
Расчет календарного плана завершен!

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

    await query.edit_message_text("Экспортирую задачи в Jira...")

    # Получаем данные календарного плана
    calendar_plan = context.user_data['calendar_plan']

    # Создаем задачи в Jira
    jira_issues = create_jira_issues(calendar_plan)

    # Формируем отчет о созданных задачах
    issues_report = "Созданы следующие задачи в Jira:\n\n"
    for issue in jira_issues:
        issues_report += f"- {issue['key']}: {issue['summary']} ({issue['assignee']})\n"

    await query.message.reply_text(
        EXPORT_TO_JIRA_SUCCESS + "\n\n" + issues_report,
        reply_markup=main_menu_keyboard()
    )

    return BotStates.MAIN_MENU


async def list_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик просмотра списка проектов."""
    # TODO: Реализовать вывод списка проектов из БД
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Функция просмотра списка проектов находится в разработке.",
        reply_markup=main_menu_keyboard()
    )

    return BotStates.MAIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущую операцию и возвращает в главное меню."""
    await update.message.reply_text(
        "Операция отменена. Возвращаюсь в главное меню.",
        reply_markup=main_menu_keyboard()
    )
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

    await query.edit_message_text(
        SELECT_PROJECT_TYPE_MESSAGE,
        reply_markup=project_type_keyboard()
    )

    return BotStates.SELECT_PROJECT_TYPE