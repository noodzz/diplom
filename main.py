# main.py
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    Application
)
from bot.handlers import (
    start, help_command,
    select_project_type, use_template, select_template, upload_csv, process_csv,
    create_project, add_task, list_projects, add_dependencies,
    add_employees, calculate_plan, export_to_jira, cancel,
    back_to_main, back_to_project_type
)
from bot.states import BotStates
from config import BOT_TOKEN
from database.operations import init_db

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


def main():
    """Запуск бота."""
    # Инициализация базы данных
    init_db()

    # Создание приложения и добавление обработчиков
    application = Application.builder().token(BOT_TOKEN).build()

    # Основной обработчик диалогов
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            BotStates.MAIN_MENU: [
                CallbackQueryHandler(select_project_type, pattern='^create_project$'),
                CallbackQueryHandler(list_projects, pattern='^list_projects$'),
                CallbackQueryHandler(help_command, pattern='^help$'),
            ],
            BotStates.SELECT_PROJECT_TYPE: [
                CallbackQueryHandler(use_template, pattern='^use_template$'),
                CallbackQueryHandler(upload_csv, pattern='^upload_csv$'),
                CallbackQueryHandler(back_to_main, pattern='^back_to_main$'),
            ],
            BotStates.SELECT_TEMPLATE: [
                CallbackQueryHandler(select_template, pattern='^template_'),
                CallbackQueryHandler(back_to_project_type, pattern='^back_to_project_type$'),
            ],
            BotStates.UPLOAD_CSV: [
                MessageHandler(filters.DOCUMENT, process_csv),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_csv),
            ],
            BotStates.CREATE_PROJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_project)
            ],
            BotStates.ADD_TASK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_task),
                CallbackQueryHandler(add_dependencies, pattern='^next$')
            ],
            BotStates.ADD_DEPENDENCIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_dependencies),
                CallbackQueryHandler(add_employees, pattern='^next$')
            ],
            BotStates.ADD_EMPLOYEES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_employees),
                CallbackQueryHandler(calculate_plan, pattern='^calculate$')
            ],
            BotStates.SHOW_PLAN: [
                CallbackQueryHandler(export_to_jira, pattern='^export_jira$'),
                CallbackQueryHandler(start, pattern='^main_menu$')
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)

    # Запуск бота
    logger.info("Бот запущен и готов к работе!")
    application.run_polling()


if __name__ == '__main__':
    main()