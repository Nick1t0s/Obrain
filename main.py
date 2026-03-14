# main.py
import logging
from bot import bot
from config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug_mode else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)


def main():
    logger.info("🚀 Запуск бота...")
    logger.info(settings)

    # Импорт хендлеров (регистрация команд)
    import handlers

    logger.info("✅ Бот готов к работе")

    # 🔹 Запуск поллинга — без лишних параметров
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        logger.info("👋 Остановка бота...")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    main()