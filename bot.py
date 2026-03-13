import telebot
from config import settings
import logging

logger = logging.getLogger(__name__)

# ✅ Глобальный экземпляр бота
bot = telebot.TeleBot(settings.bot_token, parse_mode="Markdown")

logger.info("✅ Telegram бот инициализирован")