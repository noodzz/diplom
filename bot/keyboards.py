from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu_keyboard():
    """Клавиатура главного меню."""
    keyboard = [
        [InlineKeyboardButton("Создать проект", callback_data="create_project")],
        [InlineKeyboardButton("Мои проекты", callback_data="list_projects")],
        [InlineKeyboardButton("Справка", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def task_actions_keyboard():
    """Клавиатура действий с задачами."""
    keyboard = [
        [InlineKeyboardButton("Добавить еще задачу", callback_data="add_task")],
        [InlineKeyboardButton("Далее: Зависимости", callback_data="next")]
    ]
    return InlineKeyboardMarkup(keyboard)

def dependencies_actions_keyboard():
    """Клавиатура действий с зависимостями."""
    keyboard = [
        [InlineKeyboardButton("Добавить еще зависимость", callback_data="add_dependency")],
        [InlineKeyboardButton("Далее: Сотрудники", callback_data="next")]
    ]
    return InlineKeyboardMarkup(keyboard)

def employees_actions_keyboard():
    """Клавиатура действий с сотрудниками."""
    keyboard = [
        [InlineKeyboardButton("Добавить еще сотрудника", callback_data="add_employee")],
        [InlineKeyboardButton("Рассчитать календарный план", callback_data="calculate")]
    ]
    return InlineKeyboardMarkup(keyboard)

def plan_actions_keyboard():
    """Клавиатура действий с планом."""
    keyboard = [
        [InlineKeyboardButton("Экспорт в Jira", callback_data="export_jira")],
        [InlineKeyboardButton("Вернуться в главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def project_type_keyboard():
    """Клавиатура выбора типа проекта."""
    keyboard = [
        [InlineKeyboardButton("Использовать шаблон", callback_data="use_template")],
        [InlineKeyboardButton("Загрузить CSV", callback_data="upload_csv")],
        [InlineKeyboardButton("Вернуться в главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def templates_keyboard(templates):
    """
    Клавиатура выбора шаблона проекта.

    Args:
        templates: Список шаблонов проектов
    """
    keyboard = []

    for template in templates:
        keyboard.append([InlineKeyboardButton(template['name'], callback_data=f"template_{template['id']}")])

    keyboard.append([InlineKeyboardButton("Вернуться назад", callback_data="back_to_project_type")])

    return InlineKeyboardMarkup(keyboard)

def projects_keyboard(projects):
    """
    Клавиатура списка проектов.

    Args:
        projects: Список проектов
    """
    keyboard = []

    for project in projects:
        keyboard.append([InlineKeyboardButton(
            f"{project['name']} ({project['tasks_count']} задач)",
            callback_data=f"project_{project['id']}"
        )])

    keyboard.append([InlineKeyboardButton("Создать новый проект", callback_data="create_project")])
    keyboard.append([InlineKeyboardButton("Вернуться в главное меню", callback_data="main_menu")])

    return InlineKeyboardMarkup(keyboard)