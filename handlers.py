import logging
from bot import bot
from config import settings
from models import NoteMessage

logger = logging.getLogger(__name__)


# ==========================================
# 🚀 КОМАНДА /START
# ==========================================

@bot.message_handler(commands=["start"])
def handle_start(message):
    """Обработчик команды /start"""

    # Проверка доступа (даже для start)
    if not settings.is_allowed_user(message.from_user.id):
        logger.warning(f"⚠️ Попытка доступа от неизвестного пользователя: {message.from_user.id}")
        bot.reply_to(
            message,
            "⛔️ У вас нет доступа к этому боту.\n\n"
            "Это приватный бот для личного использования."
        )
        return

    welcome_text = (
        f"👋 **Привет, {message.from_user.first_name}!**\n\n"
        f"Я — твой персональный ассистент для ведения заметок.\n\n"
        f"📝 **Что я умею:**\n"
        f"• Принимаю текстовые заметки\n"
        f"• Расшифровываю голосовые сообщения (ГС)\n"
        f"• Обрабатываю текст через AI (убираю воду, выделяю суть)\n"
        f"• Сохраняю всё в твою Obsidian-базу\n\n"
        f"📂 **Куда сохраняю:**\n"
        f"• Сырые заметки → `raw_data.md`\n"
        f"• Обработанные → `Журнал по дням/YYYY-MM-DD.md`\n\n"
        f"⌨️ **Доступные команды:**\n"
        f"/start — Запустить бота и показать это сообщение\n"
        f"/help — Подробная справка\n"
        f"/status — Статус системы (пути, модели)\n\n"
        f"🎤 **Просто отправь мне текст или голосовое сообщение,**\n"
        f"и я запишу его в заметки!"
    )

    bot.reply_to(message, welcome_text, parse_mode="Markdown")
    logger.info(f"✅ Команда /start от пользователя {message.from_user.id}")


# ==========================================
# ❓ КОМАНДА /HELP
# ==========================================

@bot.message_handler(commands=["help"])
def handle_help(message):
    """Обработчик команды /help"""

    if not settings.is_allowed_user(message.from_user.id):
        return

    help_text = (
        "📖 **Справка по боту**\n\n"
        "🎙️ **Голосовые сообщения:**\n"
        "Просто отправь ГС — я расшифрую его через Whisper, "
        "обработаю через LLM и сохраню в журнал.\n\n"
        "📝 **Текстовые заметки:**\n"
        "Отправь текст — я сделаю его лаконичным и сохраню.\n\n"
        "⚙️ **Автоматизация:**\n"
        "• В конце дня → суммари дня\n"
        "• В конце недели → суммари недели\n"
        "• В конце месяца → суммари месяца\n\n"
        "🔒 **Безопасность:**\n"
        "Бот работает только с твоим аккаунтом. "
        "Все данные хранятся локально в твоей Obsidian-базе."
    )

    bot.reply_to(message, help_text, parse_mode="Markdown")
    logger.info(f"✅ Команда /help от пользователя {message.from_user.id}")


# ==========================================
# 🔧 КОМАНДА /STATUS
# ==========================================

@bot.message_handler(commands=["status"])
def handle_status(message):
    """Обработчик команды /status — показывает текущий конфиг"""

    if not settings.is_allowed_user(message.from_user.id):
        return

    status_text = (
        "🔧 **Статус системы**\n\n"
        f"🤖 Ollama: `{settings.ollama_base_url}`\n"
        f"🧠 Модель (очистка): `{settings.ollama_model_clean}`\n"
        f"🧠 Модель (суммари): `{settings.ollama_model_summary}`\n\n"
        f"🎤 Whisper: `{settings.whisper_model}` ({settings.whisper_device})\n\n"
        f"📂 Raw: `{settings.path_to_raw}`\n"
        f"📂 Journal: `{settings.path_to_journal}`\n"
        f"📂 Summary: `{settings.path_to_summary}`\n\n"
        f"🕐 Часовой пояс: `{settings.timezone}`\n"
        f"🔍 Debug: `{settings.debug_mode}`"
    )

    bot.reply_to(message, status_text, parse_mode="Markdown")
    logger.info(f"✅ Команда /status от пользователя {message.from_user.id}")


@bot.message_handler(content_types=['text', 'voice'], func=lambda m: True)
def handle_message(message):
    logger.info(f"📨 Получено сообщение: type=text:{bool(message.text)}, voice:{bool(message.voice)}, from:{message.from_user.id}")

    # 1. Проверка доступа
    if not settings.is_allowed_user(message.from_user.id):
        bot.reply_to(message, "⛔️ Доступ запрещён")
        return
    # 2. Сохраняем сообщение
    note = NoteMessage(message)

    # 3. Запускаем полный пайплайн
    note.run()

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