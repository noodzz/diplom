# main.py
from bot.middleware import authorization_middleware
from logger import logger  # Изменен импорт
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    Application,
    ContextTypes
)
from bot.handlers import (
    start, help_command,
    select_project_type, use_template, select_template, upload_csv, process_csv,
    create_project, add_task, list_projects, add_dependencies,
    add_employees, calculate_plan, export_to_jira, cancel,
    back_to_main, back_to_project_type, select_project, process_start_date, add_user, list_users, remove_user,
    get_my_id, set_project_start_date, show_project_info, back_to_tasks, back_to_dependencies, back_to_employees,
    back_to_plan,
    edit_task_description, save_task_description, preview_before_export, export_project_info_as_file, show_positions,
    add_employee, handle_position_selection, handle_employee_selection, back_to_positions, request_custom_date,
    add_tasks_handler, assign_all_employees_command, assign_all_employees_callback, show_dependencies
)
from bot.states import BotStates
from config import BOT_TOKEN
from database.operations import init_db
from bot.keyboards import main_menu_keyboard
import os
from PIL import ImageFont

def main():
    """Запуск бота."""
    logger.info("Запуск бота...")
    
    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    init_db()
    logger.info("База данных инициализирована")

    # Создание приложения и добавление обработчиков
    logger.info("Создание приложения...")
    application = Application.builder().token(BOT_TOKEN).build()
    logger.info("Приложение создано")

    # Добавляем middleware для авторизации
    logger.info("Добавление middleware для авторизации...")
    application.add_handler(MessageHandler(filters.ALL, authorization_middleware), group=-999)
    logger.info("Middleware добавлен")

    # Обработчик ошибок
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик ошибок."""
        logger.error(f"Произошла ошибка: {context.error}")
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Произошла ошибка. Попробуйте использовать команду /cancel для сброса состояния.",
                    reply_markup=main_menu_keyboard()
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения об ошибке: {str(e)}")

    # Добавляем обработчик ошибок
    logger.info("Добавление обработчика ошибок...")
    application.add_error_handler(error_handler)
    logger.info("Обработчик ошибок добавлен")

    # Основной обработчик диалогов
    logger.info("Настройка обработчика диалогов...")
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            BotStates.MAIN_MENU: [
                CallbackQueryHandler(select_project_type, pattern='^create_project$'),
                CallbackQueryHandler(list_projects, pattern='^list_projects$'),
                CallbackQueryHandler(help_command, pattern='^help$'),
                CallbackQueryHandler(get_my_id, pattern='^my_id$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.SELECT_PROJECT_TYPE: [
                CallbackQueryHandler(use_template, pattern='^use_template$'),
                CallbackQueryHandler(upload_csv, pattern='^upload_csv$'),
                CallbackQueryHandler(back_to_main, pattern='^back_to_main$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.SELECT_TEMPLATE: [
                CallbackQueryHandler(select_template, pattern=r'^template_\d+$'),
                CallbackQueryHandler(back_to_project_type, pattern='^back_to_project_type$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.UPLOAD_CSV: [
                MessageHandler(filters.Document.ALL, process_csv),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_csv),
                CallbackQueryHandler(back_to_project_type, pattern='^back_to_project_type$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.CREATE_PROJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_project),
                CallbackQueryHandler(select_project_type, pattern='^create_project$'),
                CallbackQueryHandler(set_project_start_date, pattern='^set_start_date$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.ADD_TASK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_task),
                CallbackQueryHandler(add_tasks_handler, pattern='^add_tasks$'),
                CallbackQueryHandler(show_dependencies, pattern='^goto_dependencies$'),
                CallbackQueryHandler(calculate_plan, pattern='^calculate$'),
                CallbackQueryHandler(back_to_main, pattern='^main_menu$'),
                CallbackQueryHandler(back_to_project_type, pattern='^back_to_project_type$'),
                CallbackQueryHandler(select_project, pattern='^back_to_project$'),
                CallbackQueryHandler(set_project_start_date, pattern='^set_start_date$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.ADD_DEPENDENCIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_dependencies),
                CallbackQueryHandler(add_employees, pattern='^goto_employees$'),
                CallbackQueryHandler(add_dependencies, pattern='^add_dependency$'),
                CallbackQueryHandler(select_project, pattern=r'^project_\d+$'),
                CallbackQueryHandler(back_to_tasks, pattern='^back_to_tasks$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.ADD_EMPLOYEES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_employees),  # Keep original handler for text input
                CallbackQueryHandler(add_employee, pattern='^add_employee$'),
                CallbackQueryHandler(show_positions, pattern='^add_employees$'),
                CallbackQueryHandler(calculate_plan, pattern='^calculate$'),
                CallbackQueryHandler(back_to_dependencies, pattern='^back_to_dependencies$'),
                CallbackQueryHandler(back_to_main, pattern='^main_menu$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.SELECT_POSITION: [
                CallbackQueryHandler(handle_position_selection, pattern='^pos_'),
                CallbackQueryHandler(back_to_employees, pattern='^back_to_employees$'),
                CallbackQueryHandler(cancel, pattern='^cancel$')
            ],
            BotStates.SELECT_EMPLOYEE: [
                CallbackQueryHandler(handle_employee_selection, pattern='^select_employee_'),
                CallbackQueryHandler(back_to_positions, pattern='^back_to_positions$'),
                CallbackQueryHandler(add_employee, pattern='^add_new_employee$'),
                CallbackQueryHandler(cancel, pattern='^cancel$')
            ],
            BotStates.ADD_EMPLOYEE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_employees),
                CallbackQueryHandler(add_employees, pattern='^cancel_add_employee$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.ADD_EMPLOYEE_POSITION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_employees),
                CallbackQueryHandler(add_employees, pattern='^cancel_add_employee$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.ADD_EMPLOYEE_DAYS_OFF: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_employees),
                CallbackQueryHandler(add_employees, pattern='^cancel_add_employee$'),
                CallbackQueryHandler(add_employees, pattern='^no_days_off$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.SHOW_PLAN: [
                CallbackQueryHandler(export_to_jira, pattern='^export_jira$'),
                CallbackQueryHandler(show_project_info, pattern='^show_project_info$'),
                CallbackQueryHandler(export_project_info_as_file, pattern='^export_project_info$'),  # Add this line
                CallbackQueryHandler(preview_before_export, pattern='^preview_before_export$'),
                CallbackQueryHandler(back_to_plan, pattern='^back_to_plan$'),
                CallbackQueryHandler(back_to_main, pattern='^main_menu$'),
                CallbackQueryHandler(back_to_employees, pattern='^back_to_employees$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.SET_START_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_start_date),
                CallbackQueryHandler(process_start_date, pattern='^date_'),
                CallbackQueryHandler(request_custom_date, pattern='^date_custom$'),
                CallbackQueryHandler(select_project, pattern='^back_to_project$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.SELECT_PROJECT: [
                CallbackQueryHandler(select_project, pattern=r'^project_\d+$'),
                CallbackQueryHandler(add_tasks_handler, pattern='^add_tasks$'),
                CallbackQueryHandler(add_employees, pattern='^add_employees$'),
                CallbackQueryHandler(assign_all_employees_callback, pattern='^assign_all_employees$'),
                CallbackQueryHandler(set_project_start_date, pattern='^set_start_date$'),
                CallbackQueryHandler(calculate_plan, pattern='^calculate$'),
                CallbackQueryHandler(back_to_main, pattern='^main_menu$'),
                CallbackQueryHandler(back_to_main, pattern='^back_to_main$'),
                CallbackQueryHandler(select_project_type, pattern='^create_project$'),
                CommandHandler('cancel', cancel)
            ],
            BotStates.PREVIEW_BEFORE_EXPORT: [
                CallbackQueryHandler(edit_task_description, pattern='^edit_desc_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_task_description),
                CallbackQueryHandler(export_to_jira, pattern='^export_jira$'),
                CallbackQueryHandler(back_to_plan, pattern='^back_to_plan$'),
                CallbackQueryHandler(cancel, pattern='^cancel_edit_desc$'),
                CommandHandler('cancel', cancel)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="conversation_handler",
        persistent=False,
        allow_reentry=True
    )
    logger.info("Обработчик диалогов настроен")

    application.add_handler(conv_handler)
    logger.info("Обработчик диалогов добавлен")

    # Команды для управления пользователями
    logger.info("Добавление команд управления пользователями...")
    application.add_handler(CommandHandler('assign_all_employees', assign_all_employees_command))
    application.add_handler(CommandHandler('add_user', add_user))
    application.add_handler(CommandHandler('list_users', list_users))
    application.add_handler(CommandHandler('remove_user', remove_user))
    logger.info("Команды управления пользователями добавлены")

    # Запуск бота
    logger.info("Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    if os.name == 'nt':  # Windows
        font_path = 'C:\\Windows\\Fonts\\arial.ttf'
    else:  # macOS/Linux
        font_path = '/Library/Fonts/Arial.ttf'

    font = ImageFont.truetype(font_path, size=12)
    main()