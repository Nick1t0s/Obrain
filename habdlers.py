import logging
from bot import bot
from config import settings
from models import NoteMessage

logger = logging.getLogger(__name__)


@bot.message_handler(func=lambda m: True)
def handle_message(message):
    # 1. Проверка доступа
    if not settings.is_allowed_user(message.from_user.id):
        bot.reply_to(message, "⛔️ Доступ запрещён")
        return

    # 2. Сохраняем сообщение
    note = NoteMessage(message)

    # 3. Игнорируем пустые
    if note.is_empty:
        return

    note.run()  # Запускаем полный пайплайн

    # 4. Сохраняем сырую запись
    try:
        with open(settings.path_to_raw, "a", encoding="utf-8") as f:
            f.write(note.format_raw_entry())
        logger.debug(f"💾 Raw сохранён: {settings.path_to_raw}")
    except Exception as e:
        logger.error(f"❌ Ошибка записи raw: {e}")
        bot.send_message(settings.telegram_log_chat_id, f"❌ Ошибка raw: {e}")

    # 5. Сохраняем обработанную запись (если готова)
    if note.is_ready:
        try:
            daily_path = settings.get_daily_note_path(note.date_str)
            with open(daily_path, "a", encoding="utf-8") as f:
                f.write(note.format_processed_entry())
            logger.debug(f"📝 Journal обновлён: {daily_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка записи journal: {e}")
            bot.send_message(settings.telegram_log_chat_id, f"❌ Ошибка journal: {e}")

    # 6. Ответ пользователю
    preview = (note.processed_text or note.raw_text)[:150]
    suffix = "..." if len(note.processed_text or note.raw_text) > 150 else ""
    bot.reply_to(message, f"✅ Записал:\n_{preview}{suffix}_", parse_mode="Markdown")