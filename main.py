# main.py
import logging
from bot import bot
from config import settings

from pathlib import Path
import schedulers.weekly
from schedulers.manager import SchedulerManager
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

    state_dir = Path(settings.path_to_summary).parent / ".scheduler_state"
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