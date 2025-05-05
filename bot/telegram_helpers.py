# bot/telegram_helpers.py
import logging
import telegram
from telegram import Update, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def safe_edit_message_text(query, text, reply_markup=None, parse_mode=None):
    """
    Safely edits a message text, handling the "Message is not modified" error.

    Args:
        query: The callback query containing the message to edit
        text: The new text for the message
        reply_markup: Optional inline keyboard markup
        parse_mode: Optional parse mode for formatting (e.g., 'Markdown', 'HTML')

    Returns:
        True if successful, False if there was a "Message is not modified" error
    """
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            # This is fine, the message is already showing the desired content
            logger.debug("Message is already showing the desired content, skipping edit")
            return False
        else:
            # For other errors, log and re-raise
            logger.error(f"Error editing message: {str(e)}")
            raise
    except Exception as e:
        logger.error(f"Unexpected error editing message: {str(e)}")
        raise


async def safe_send_message(chat_id, text, bot, reply_markup=None, parse_mode=None):
    """
    Safely sends a message, handling potential exceptions.

    Args:
        chat_id: ID of the chat to send message to
        text: Text of the message
        bot: Bot instance
        reply_markup: Optional inline keyboard markup
        parse_mode: Optional parse mode for text formatting

    Returns:
        The sent message if successful, None otherwise
    """
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return None