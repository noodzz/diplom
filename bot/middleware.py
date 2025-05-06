from telegram import Update
from telegram.ext import CallbackContext, ApplicationHandlerStop
from logger import logger
from database.operations import is_user_allowed
from bot.messages import ACCESS_DENIED_MESSAGE


async def authorization_middleware(update: Update, context: CallbackContext):
    """
    Промежуточный обработчик для проверки авторизации пользователя.
    """
    # Пропускаем обновления без пользователя
    if not update.effective_user:
        return

    user_id = update.effective_user.id

    # Команда /my_id доступна всем
    if update.message and update.message.text and update.message.text.startswith('/my_id'):
        return

    # Проверяем доступ через БД
    if not is_user_allowed(user_id):
        user_name = update.effective_user.username or update.effective_user.first_name
        logger.warning(f"Отказано в доступе: {user_id} ({user_name})")

        # Отправляем сообщение об отказе
        if update.message:
            await update.message.reply_text(
                ACCESS_DENIED_MESSAGE.format(user_id=user_id)
            )

        # Останавливаем обработку запроса
        raise ApplicationHandlerStop