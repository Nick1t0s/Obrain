# bot.py
import telebot
import requests
from telebot import apihelper
from config import settings
import logging

logger = logging.getLogger(__name__)


def _configure_telebot():
    """Настраивает telebot: прокси и таймауты"""

    # 🔹 1. Прокси
    if settings.proxy_host and settings.proxy_port:
        auth = ""
        if settings.proxy_login and settings.proxy_password:
            auth = f"{settings.proxy_login}:{settings.proxy_password}@"

        # socks5h:// — резолвит DNS через прокси (обходит блокировки)
        proxy_url = f"{settings.proxy_type}h://{auth}{settings.proxy_host}:{settings.proxy_port}"

        session = requests.Session()
        session.proxies = {'http': proxy_url, 'https': proxy_url}
        apihelper.session = session

        logger.info(f"🌐 Прокси активирован: {proxy_url}")

    # 🔹 2. Таймауты
    apihelper.API_TIMEOUT = int(settings.telegram_timeout)
    apihelper.REQUEST_TIMEOUT = int(settings.telegram_timeout)
    apihelper.CONNECT_TIMEOUT = int(settings.telegram_timeout)

    logger.info(f"⏱️ Таймауты API: {apihelper.API_TIMEOUT}с")


# 🔹 Применяем настройки ДО создания бота
_configure_telebot()

# 🔹 Создаём бота — ТОЛЬКО токен и parse_mode!
bot = telebot.TeleBot(
    token=settings.bot_token,
    parse_mode="Markdown"
    # ❌ Никаких proxy=, timeout=, use_threads= здесь!
)

logger.info("✅ Telegram бот инициализирован")