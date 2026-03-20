import os
import sys
def _fix_proxy_schemes():
    """Исправляет socks:// и socks5:// → socks5h:// во всех proxy-переменных"""
    for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
        val = os.environ.get(var, '')
        if val:
            # socks:// → socks5h://
            if val.startswith('socks://'):
                fixed = val.replace('socks://', 'socks5h://', 1)
                os.environ[var] = fixed
                print(f"🔧 Fixed {var}: socks:// → socks5h://", file=sys.stderr)
            # socks5:// → socks5h:// (если нет 'h')
            elif val.startswith('socks5://') and not val.startswith('socks5h://'):
                fixed = val.replace('socks5://', 'socks5h://', 1)
                os.environ[var] = fixed
                print(f"🔧 Fixed {var}: socks5:// → socks5h://", file=sys.stderr)

# Вызываем ДО всего
_fix_proxy_schemes()

# 🔹 Также включаем offline-режим для HuggingFace
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


import logging
from bot import bot
from config import settings

from pathlib import Path
import schedulers.weekly
from schedulersV2.manager import SchedulerManager
import time

logging.basicConfig(
    level=logging.DEBUG if settings.debug_mode else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)


def main():
    logger.info("🚀 Запуск бота...")
    logger.info(settings)

    state_dir = Path("states")
    scheduler = SchedulerManager(state_dir)

    # Импорт хендлеров (регистрация команд)
    import handlers

    logger.info("✅ Бот готов к работе")

    # 🔹 Запуск поллинга — без лишних параметров
    try:
        import threading
        bot_thread = threading.Thread(target=bot.infinity_polling, daemon=True)
        bot_thread.start()

        while True:
            scheduler.tick()
            time.sleep(60)  # Проверка каждую минуту
    except KeyboardInterrupt:
        logger.info("👋 Остановка бота...")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    main()