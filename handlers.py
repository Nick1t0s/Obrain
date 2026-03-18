import logging
from bot import bot
from config import settings
from models import NoteMessage
from schedulers import collector

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


@bot.message_handler(commands=["change_data"])
def handle_change_data(message):
    """Обработка команды /change_data для точечного обновления базы"""

    if not settings.is_allowed_user(message.from_user.id):
        bot.reply_to(message, "⛔️ Доступ запрещён")
        return

    # Извлекаем текст после команды
    user_input = message.text.replace("/change_data", "").strip()

    if not user_input:
        bot.reply_to(
            message,
            "📝 Использование:\n`/change_data я играю в доту`\n\n"
            "Опишите факт, который нужно добавить или обновить.",
            parse_mode="Markdown"
        )
        return

    try:
        collector.change_data(user_input)

    except Exception as e:
        logger.exception(f"❌ Ошибка обновления базы: {e}")
        bot.reply_to(message, f"❌ Ошибка: {type(e).__name__}", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"Успешно обновлена база знаний")

@bot.message_handler(commands=["collect"])
def handle_collect(message):
    """Ручной запуск сбора данных за указанный день: /collect 2026-03-27"""

    if not settings.is_allowed_user(message.from_user.id):
        bot.reply_to(message, "⛔️ Доступ запрещён")
        return

    # Парсим дату из команды
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        # Если дата не указана — берём вчера
        from datetime import datetime, timedelta
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        bot.reply_to(
            message,
            f"📅 Дата не указана. Использую вчера: `{target_date}`\n"
            f"Пример: `/collect 2026-03-27`",
            parse_mode="Markdown"
        )
    else:
        target_date = parts[1].strip()

    # Валидация формата даты
    try:
        from datetime import datetime
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        bot.reply_to(
            message,
            f"❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД\n"
            f"Пример: `/collect 2026-03-27`",
            parse_mode="Markdown"
        )
        return

    try:
        logger.info(f"🔄 /collect: запускаю сбор за {target_date}")
        bot.reply_to(message, f"🔄 Обрабатываю {target_date}...")

        # 1. Собираем заметки за день


        # 2. Запускаем агрегацию
        collector.collect_data(period_id=target_date)

        # 3. Отчёт пользователю
        bot.reply_to(
            message,
            f"✅ Данные за {target_date} добавлены в базу!\n"
            f"🔍 Просмотр: `/view_data`",
            parse_mode="Markdown"
        )
        logger.info(f"✅ /collect: завершено за {target_date}")

    except TimeoutError:
        logger.error(f"⏱️ /collect: таймаут")
        bot.reply_to(message, "⏱️ Превышено время обработки. Попробуйте позже.", parse_mode="Markdown")
    except Exception as e:
        logger.exception(f"❌ /collect: ошибка {type(e).__name__}: {e}")
        bot.reply_to(message, f"❌ Ошибка: {type(e).__name__}", parse_mode="Markdown")

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