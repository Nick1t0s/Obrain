import os
import gc
import tempfile
import logging
import requests
from datetime import datetime
from typing import Optional
import telebot


from faster_whisper import WhisperModel
from bot import bot  # Импортируем глобальный экземпляр
from config import settings

logger = logging.getLogger(__name__)


class NoteMessage:
    """
    Инкапсулирует обработку сообщения от пользователя.

    Публичный API:
        - run() -> self: запускает полный пайплайн (транскрибация + LLM)
        - Атрибуты: raw_text, processed_text, date_str, timestamp_str

    Свойства (read-only):
        - is_empty, is_ready, is_voice, is_text
    """

    def __init__(self, message: telebot.types.Message):
        # 🔹 Базовые данные
        self._message = message
        self._user_id: int = message.from_user.id
        self._date: datetime = datetime.fromtimestamp(message.date)

        # 🔹 Контент (заполняется в процессе)
        self.raw_text: Optional[str] = None  # Сырой текст
        self.processed_text: Optional[str] = None  # Текст после LLM

        # 🔹 Флаги состояния
        self._is_voice: bool = False
        self._is_text: bool = False
        self._transcribed: bool = False
        self._llm_processed: bool = False

        # 🔹 Метаданные
        self.timestamp_str: str = self._date.strftime("%H:%M")
        self.date_str: str = self._date.strftime("%d-%m-%Y")
        self.voice_duration: Optional[int] = None

        # 🔹 Инициализация: парсинг типа сообщения
        self._parse_content()

    # ==========================================
    # 📦 СВОЙСТВА (@property)
    # ==========================================

    @property
    def is_empty(self) -> bool:
        return not self.raw_text or not self.raw_text.strip()

    @property
    def is_ready(self) -> bool:
        return bool(self.processed_text and self.processed_text.strip())

    @property
    def is_voice(self) -> bool:
        return self._is_voice

    @property
    def is_text(self) -> bool:
        return self._is_text

    @property
    def user_id(self) -> int:
        return self._user_id

    # ==========================================
    # 🚀 ПУБЛИЧНЫЙ МЕТОД
    # ==========================================

    def run(self):
        # Шаг 1: Транскрибация (если ГС)
        if self._is_voice and not self._transcribed:
            self._transcribe()

        """Запускает полный пайплайн обработки"""
        if self.is_empty:
            logger.warning("⚠️ run() вызван для пустого сообщения")
            return self

        # Шаг 2: Обработка через LLM (если есть текст)
        if self.raw_text and not self._llm_processed and not self.is_empty:
            self._process_with_ollama()

    # ==========================================
    # 🔒 ПРИВАТНЫЕ МЕТОДЫ
    # ==========================================

    def _parse_content(self):

        if text := self._message.text:
            self._is_text = True
            self.raw_text = text.strip()
            logger.debug(f"📝 Текст: {self.raw_text[:60]}...")

        elif voice := self._message.voice:
            self._is_voice = True
            self.voice_duration = voice.duration
            logger.debug(f"🎤 Получено ГС: {voice.duration}с")
        else:
            logger.debug(f"⚠️ Неподдерживаемый тип сообщения от {self._user_id}")
            self.raw_text = ""

    def _transcribe(self):
        """Скачивает и транскрибирует ГС"""
        if not self._is_voice or self._transcribed:
            return

        voice = self._message.voice
        if voice.file_size > settings.get_max_file_size_bytes():
            logger.warning(f"❌ ГС слишком большое: {voice.file_size / 1024 / 1024:.1f} МБ")
            self.raw_text = "[Ошибка: файл слишком большой]"
            self._transcribed = True
            return

        temp_path = None
        try:
            file_info = bot.get_file(voice.file_id)  # Используем глобальный bot
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                tmp.write(bot.download_file(file_info.file_path))
                temp_path = tmp.name

            self.raw_text = self._transcribe_with_whisper(temp_path)
            self._transcribed = True
            logger.info(f"✅ Транскрибация завершена")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки ГС: {e}")
            self.raw_text = f"[Ошибка: {type(e).__name__}]"

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _transcribe_with_whisper(self, audio_path: str) -> str:
        model = None
        try:
            model = WhisperModel(
                settings.whisper_model_name,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
            segments, _ = model.transcribe(
                audio_path,
                language=settings.whisper_language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)

            )
            return " ".join(seg.text for seg in segments).strip()

        except Exception as e:
            logger.error(f"❌ Whisper error: {e}")
            return f"[Whisper error: {str(e)}]"

        finally:
            if model is not None:
                del model
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    def _process_with_ollama(self):
        """Отправляет сырой текст в Ollama с принудительной выгрузкой модели"""
        if not self.raw_text or self._llm_processed:
            return

        prompt = self._build_cleaning_prompt()

        try:
            response = requests.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model_clean,
                    "prompt": prompt,
                    "temperature": settings.llm_temperature,
                    "stream": False,
                    "keep_alive": settings.ollama_keep_alive,  # 🔹 ГЛАВНОЕ ИЗМЕНЕНИЕ
                },
                timeout=settings.llm_timeout,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()

            self.processed_text = result.get("response", "").strip()
            self._llm_processed = True
            logger.info(f"✅ LLM обработка завершена (модель выгружена через {settings.ollama_keep_alive} мин)")

        except Exception as e:
            logger.error(f"❌ Ollama API error: {e}")
            self.processed_text = f"[LLM error: {type(e).__name__}]"

    def _build_cleaning_prompt(self) -> str:
        """Формирует промпт для очистки текста с сохранением деталей"""
        meta = f"Дата: {self.date_str}, Время: {self.timestamp_str}, Тип: {'голос' if self.is_voice else 'текст'}"
        return (
            f"Ты — функция обработки текста, а не чат-бот. Твоя задача — вернуть ТОЛЬКО очищенный текст заметки.\n\n"
            f"Контекст: {meta}\n\n"
            f"Сырой текст:\n\"\"\"{self.raw_text}\"\"\"\n\n"
            f"🛡️ ПРАВИЛА ОБРАБОТКИ:\n"
            f"1. ✅ СОХРАНЯЙ:\n"
            f"   - Все факты, имена, числа, даты.\n"
            f"   - Статусы и степень выполнения (например: 'наполовину', 'в процессе', 'начал').\n"
            f"   - Суть и смысл исходного сообщения.\n\n"
            f"2. ❌ УДАЛЯЙ:\n"
            f"   - Слова-паразиты, повторы, приветствия.\n"
            f"   - Ошибки транскрибации и опечатки.\n\n"
            f"3. 🚫 СТРОГИЙ ЗАПРЕТ:\n"
            f"   - НЕ пиши вводные фразы ('Обработанный текст:', 'Вот результат:').\n"
            f"   - НЕ пиши комментарии о своей работе ('Я реализовал...', 'Текст лаконичен...').\n"
            f"   - НЕ добавляй кавычки, markdown-блоки или пояснения.\n"
            f"   - НЕ общайся с пользователем.\n\n"
            f"4. 📝 ПРИМЕРЫ (FEW-SHOT):\n"
            f"   Вход: 'ну короче наполовину написал бота сегодня'\n"
            f"   Выход: Наполовину написал бота сегодня\n\n"
            f"   Вход: 'встреча с Олегом в 15:00, надо не забыть'\n"
            f"   Выход: Встреча с Олегом в 15:00\n\n"
            f"   Вход: 'купил молоко и хлеб, еще нужно яйца'\n"
            f"   Выход: Купил молоко и хлеб. Нужно купить яйца\n\n"
            f"5. 🎯 ФОРМАТ ОТВЕТА:\n"
            f"   - ТОЛЬКО чистый текст заметки.\n"
            f"   - Никаких преамбул и постскриптумов.\n"
            f"   - Язык: русский.\n\n"
            f"Твой ответ:"
        )

    # ==========================================
    # 📦 ФОРМАТИРОВАНИЕ
    # ==========================================

    def format_raw_entry(self) -> str:
        type_mark = "🎤" if self.is_voice else "📝"
        duration = f" ({self.voice_duration}с)" if self.voice_duration else ""
        return f"{self.timestamp_str}{duration} {type_mark} {self.raw_text}\n"

    def format_processed_entry(self) -> str:
        return f"#### **{self.timestamp_str}**\n{self.processed_text}\n"

    def __str__(self) -> str:
        status = "✅" if self.is_ready else "⏳" if self.raw_text else "❌"
        icon = "🎤" if self.is_voice else "📝"
        return f"{status} {icon} NoteMessage[{self.date_str}]"

    def __repr__(self) -> str:
        return self.__str__()