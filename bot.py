# bot.py
import telebot
import requests
from telebot import apihelper
from config import settings
import logging

logger = logging.getLogger(__name__)


def _build_proxy_url() -> str | None:
    """Собирает URL прокси. Гарантированно использует socks5h:// для DNS-резолвинга через прокси."""
    if not settings.proxy_host or not settings.proxy_port:
        return None

    # 🔹 КРИТИЧНО: Всегда используем 'h' для резолвинга DNS через прокси
    proxy_type = settings.proxy_type
    if proxy_type == "socks5":
        proxy_type = "socks5h"  # ← Авто-исправление!
    elif proxy_type == "socks4":
        proxy_type = "socks4a"  # Аналог для SOCKS4

    auth = ""
    if settings.proxy_login and settings.proxy_password:
        auth = f"{settings.proxy_login}:{settings.proxy_password}@"

    return f"{proxy_type}://{auth}{settings.proxy_host}:{settings.proxy_port}"

def _configure_telebot():
    """Настраивает telebot: прокси и таймауты"""

    # 🔹 1. Прокси
    if settings.proxy_host and settings.proxy_port:
        # socks5h:// — резолвит DNS через прокси (обходит блокировки)
        proxy_url = _build_proxy_url()

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