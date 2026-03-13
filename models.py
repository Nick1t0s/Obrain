import os
import gc
import tempfile
import logging
from datetime import datetime
from typing import Optional

import telebot
from faster_whisper import WhisperModel

from config import settings

logger = logging.getLogger(__name__)


class NoteMessage:
    """
    Обёртка над сообщением Telegram.
    Поддерживает: текстовые сообщения и голосовые (ГС).
    НЕ поддерживает: аудиофайлы, документы, видео.

    Память VRAM очищается сразу после транскрибации.
    """

    def __init__(self, message: telebot.types.Message):
        self._message = message
        self._user_id = message.from_user.id
        self._date = datetime.fromtimestamp(message.date)

        # Контент
        self.raw_text: Optional[str] = None
        self.is_voice: bool = False
        self.is_text: bool = False

        # Метаданные
        self.timestamp_str: str = self._date.strftime("[%Y-%m-%d %H:%M]")
        self.date_str: str = self._date.strftime("%Y-%m-%d")
        self.voice_duration: Optional[int] = None  # Длительность ГС в секундах

        # Парсинг при инициализации
        self._parse_content()

    def _parse_content(self):
        """Определяет тип и извлекает контент. Только текст или ГС."""

        # 🔹 Текстовое сообщение
        if text := self._message.text:
            self.is_text = True
            self.raw_text = text.strip()
            logger.debug(f"📝 Текст: {self.raw_text[:60]}...")
            return

        # 🔹 Голосовое сообщение (ГС) — именно то, что нужно
        if voice := self._message.voice:
            self.is_voice = True
            self.voice_duration = voice.duration
            self._process_voice_message(voice)
            return

        # 🔹 Всё остальное — игнорируем
        logger.debug(f"⚠️ Пропущен неподдерживаемый тип сообщения от {self._user_id}")
        self.raw_text = ""

    def _process_voice_message(self, voice: telebot.types.Voice):
        """Скачивает и транскрибирует ГС. Очищает память после."""

        # Проверка размера
        if voice.file_size > settings.get_max_file_size_bytes():
            logger.warning(f"❌ ГС слишком большое: {voice.file_size / 1024 / 1024:.1f} МБ")
            self.raw_text = "[Ошибка: ГС слишком большое]"
            return

        bot = telebot.TeleBot(settings.bot_token)
        temp_path = None

        try:
            # Скачивание
            file_info = bot.get_file(voice.file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                tmp.write(bot.download_file(file_info.file_path))
                temp_path = tmp.name

            logger.debug(f"🎤 ГС загружено: {temp_path}, {voice.duration}с")

            # Транскрибация
            self.raw_text = self._transcribe_with_whisper(temp_path)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки ГС: {e}")
            self.raw_text = f"[Ошибка: {type(e).__name__}]"

        finally:
            # Удаление временного файла
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
                logger.debug(f"🗑️ Удалён временный файл: {temp_path}")

    def _transcribe_with_whisper(self, audio_path: str) -> str:
        """
        Транскрибирует аудио через faster-whisper.
        Модель загружается и выгружается в рамках этого вызова.
        """
        model = None
        try:
            # Загрузка модели в память
            model = WhisperModel(
                settings.whisper_model_name,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
            logger.debug(f"🧠 Whisper загружен: {settings.whisper_model_name}")

            # Транскрибация
            segments, _ = model.transcribe(
                audio_path,
                language=settings.whisper_language,
                beam_size=5,
                vad_filter=True,  # Отсечение тишины
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            text = " ".join(seg.text for seg in segments).strip()
            logger.info(f"✅ Транскрибация: {len(text)} символов")
            return text

        except Exception as e:
            logger.error(f"❌ Whisper error: {e}")
            return f"[Whisper error: {str(e)}]"

        finally:
            # === 🧹 ОЧИСТКА ПАМЯТИ (КРИТИЧНО) ===
            if model is not None:
                del model  # Удаляем объект модели

            gc.collect()  # Сборка мусора

            # Очистка кэша CUDA, если torch доступен
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.debug("🧹 CUDA cache cleared")
            except ImportError:
                pass

            logger.debug("🧹 Память освобождена после транскрибации")

    # ==========================================
    # 📦 ПУБЛИЧНЫЙ ИНТЕРФЕЙС
    # ==========================================

    def format_for_raw_log(self) -> str:
        """Формат для записи в raw_data.md"""
        type_mark = "🎤" if self.is_voice else "📝"
        duration_info = f" ({self.voice_duration}с)" if self.voice_duration else ""
        return f"{self.timestamp_str}{duration_info} {type_mark} {self.raw_text}\n"

    def to_llm_context(self) -> dict:
        """Словарь для отправки в LLM"""
        return {
            "timestamp": self.timestamp_str,
            "date": self.date_str,
            "type": "voice" if self.is_voice else "text",
            "duration_sec": self.voice_duration if self.is_voice else None,
            "text": self.raw_text,
        }

    def is_empty(self) -> bool:
        """Проверка, есть ли полезный контент"""
        return not self.raw_text or not self.raw_text.strip()

    def __str__(self) -> str:
        icon = "🎤" if self.is_voice else "📝"
        return f"{icon} NoteMessage[{self.date_str}] ({len(self.raw_text or '')} chars)"

    def __repr__(self) -> str:
        return self.__str__()