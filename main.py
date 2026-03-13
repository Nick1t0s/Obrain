import logging
from bot import bot
from config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO if not settings.debug_mode else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)


def main():
    logger.info("🚀 Запуск бота...")
    logger.info(settings)  # Вывод конфига в лог

    # Импорт хендлеров (чтобы зарегистрировать их в боте)
    import handlers

    logger.info("✅ Бот готов к работе")
    bot.infinity_polling()


if __name__ == "__main__":
    main()