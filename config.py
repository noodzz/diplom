import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Отладочный вывод
print("DATABASE_URL из .env:", os.getenv("DATABASE_URL"))

# Токен Telegram бота
BOT_TOKEN = os.getenv("BOT_TOKEN")

ALLOWED_USERS = [
    6633100206,  
]

# Настройки Jira
JIRA_URL = os.getenv("JIRA_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

# Настройки базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///calendar_bot.db")
print("Итоговый DATABASE_URL:", DATABASE_URL)