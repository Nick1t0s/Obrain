import os
from pathlib import Path
from typing import Optional, Literal
from datetime import time
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

from dotenv import load_dotenv
load_dotenv(dotenv_path=ENV_FILE, override=True)

class Settings(BaseSettings):
    """
    Класс конфигурации приложения.
    Автоматически загружает переменные из .env и валидирует их.
    """

    # ==========================================
    # 🔐 TELEGRAM
    # ==========================================
    bot_token: str = Field(..., description="Токен Telegram бота")
    telegram_user_id: int = Field(..., description="ID владельца бота")
    telegram_log_chat_id: Optional[int] = Field(None, description="ID чата для логов")

    # ==========================================
    # 📂 PATHS (OBSIDIAN)
    # ==========================================
    path_to_raw: Path = Field(..., description="Путь к файлу сырых заметок")
    path_to_journal: Path = Field(..., description="Путь к папке ежедневных заметок")
    path_to_summary: Path = Field(..., description="Путь к папке суммари")

    # ==========================================
    # 🤖 LLM (OLLAMA)
    # ==========================================
    ollama_base_url: str = Field("http://127.0.0.1:11434", description="URL Ollama API")
    ollama_model_clean: str = Field("llama3:8b", description="Модель для очистки текста")
    ollama_model_summary: str = Field("llama3:8b", description="Модель для суммари")
    llm_temperature: float = Field(0.3, ge=0.0, le=1.0, description="Температура генерации")
    llm_timeout: int = Field(120, gt=0, description="Таймаут запроса LLM (сек)")
    # 0 = выгрузить сразу после запроса (рекомендуется для экономии VRAM)
    # -1 = держать бесконечно
    # 5 = стандартное поведение Ollama
    ollama_keep_alive: int = Field(0, ge=-1, description="Время жизни модели в VRAM (мин)")

    # ==========================================
    # 🎙️ WHISPER (TRANSCRIPTION)
    # ==========================================
    whisper_model: str = Field("large-v3", description="Модель Whisper для транскрибации")
    whisper_device: Literal["cpu", "cuda", "auto"] = Field("cuda", description="Устройство для Whisper")
    whisper_compute_type: Literal["int8", "int8_float16", "float16", "float32"] = Field(
        "int8_float16", description="Тип вычислений для Whisper (экономия VRAM)"
    )
    whisper_language: str = Field("ru", description="Язык по умолчанию для транскрибации")

    # ==========================================
    # ⏰ SCHEDULE
    # ==========================================
    daily_summary_time: str = Field("23:30", description="Время суммари дня (ЧЧ:ММ)")
    weekly_review_day: int = Field(7, ge=1, le=7, description="День недели (1=Пн, 7=Вс)")
    monthly_review_day: int = Field(31, ge=1, le=31, description="День месяца")

    # ==========================================
    # 🎙️ MEDIA
    # ==========================================
    max_file_size_mb: int = Field(20, gt=0, description="Макс. размер файла (МБ)")

    # ==========================================
    # 🛠️ SYSTEM
    # ==========================================
    debug_mode: bool = Field(False, description="Режим отладки")
    timezone: str = Field("Europe/Moscow", description="Часовой пояс")

    # ==========================================
    # 🌐 PROXY
    # ==========================================
    proxy_type: str = Field("socks5", description="Тип прокси: socks5, http, https")
    proxy_host: Optional[str] = Field(None, description="Хост прокси")
    proxy_port: Optional[int] = Field(None, description="Порт прокси")
    proxy_login: Optional[str] = Field(None, description="Логин прокси")
    proxy_password: Optional[str] = Field(None, description="Пароль прокси")

    # Таймауты для нестабильного соединения
    telegram_timeout: int = Field(30, ge=10, le=120, description="Таймаут запросов Telegram (сек)")
    telegram_long_polling_timeout: int = Field(60, ge=30, le=300, description="Таймаут длинного опроса")

    # Настройки для загрузки из .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Игнорировать регистр имен переменных
        extra="ignore"  # Игнорировать лишние переменные в .env
    )

    # ==========================================
    # 🔍 ВАЛИДАТОРЫ
    # ==========================================

    @field_validator('bot_token')
    @classmethod
    def check_bot_token(cls, v):
        if not v or v == "sa" or len(v) < 10:
            raise ValueError("⚠️ BOT_TOKEN не настроен или невалиден!")
        return v

    @field_validator('ollama_base_url')
    @classmethod
    def fix_url_slashes(cls, v):
        # Исправляем частую ошибку с обратными слэшами
        return v.replace("\\", "/")

    @field_validator('daily_summary_time')
    @classmethod
    def validate_time_format(cls, v):
        try:
            time.fromisoformat(v)
        except ValueError:
            raise ValueError("⚠️ DAILY_SUMMARY_TIME должен быть в формате ЧЧ:ММ (например, 23:30)")
        return v

    @field_validator('whisper_model')
    @classmethod
    def validate_whisper_model(cls, v):
        """Проверяет название модели Whisper"""
        valid_models = [
            "tiny", "tiny.en",
            "base", "base.en",
            "small", "small.en",
            "medium", "medium.en",
            "large", "large-v1", "large-v2", "large-v3", "large-v3-turbo"
        ]
        if v not in valid_models:
            # Не блокируем, но предупреждаем о кастомной модели
            print(f"⚠️ Whisper: модель '{v}' не в списке стандартных. Убедитесь, что она установлена.")
        return v

    @model_validator(mode='after')
    def create_directories(self):
        """Автоматически создает папки, если они не существуют"""
        self.path_to_journal.mkdir(parents=True, exist_ok=True)
        self.path_to_summary.mkdir(parents=True, exist_ok=True)

        # Убедимся, что родительская папка для raw файла существует
        self.path_to_raw.parent.mkdir(parents=True, exist_ok=True)
        return self

    # ==========================================
    # 🛠️ HELPER МЕТОДЫ
    # ==========================================

    def get_daily_note_path(self, date_str: str) -> Path:
        """
        Генерирует путь к файлу ежедневной заметки.
        :param date_str: Дата в формате YYYY-MM-DD
        """
        return self.path_to_journal / f"{date_str}.md"

    def get_weekly_note_path(self, week_str: str) -> Path:
        """
        Генерирует путь к файлу недельного обзора.
        :param week_str: Неделя в формате 2023-W43
        """
        return self.path_to_summary / "Weekly" / f"{week_str}.md"

    def get_monthly_note_path(self, month_str: str) -> Path:
        """
        Генерирует путь к файлу месячного обзора.
        :param month_str: Месяц в формате 2023-10
        """
        return self.path_to_summary / "Monthly" / f"{month_str}.md"

    def get_max_file_size_bytes(self) -> int:
        """Возвращает максимальный размер файла в байтах"""
        return self.max_file_size_mb * 1024 * 1024

    def is_allowed_user(self, user_id: int) -> bool:
        """Проверяет, имеет ли пользователь доступ к боту"""
        return user_id == self.telegram_user_id

    @property
    def ollama_models(self) -> list[str]:
        """Список всех используемых моделей"""
        return [self.ollama_model_clean, self.ollama_model_summary]

    @property
    def whisper_model_name(self) -> str:
        """
        Возвращает имя модели Whisper в формате для faster-whisper.
        Заменяет ':' на '-', если модель указана в стиле Ollama.
        """
        return self.whisper_model.replace(":", "-")

    def __str__(self) -> str:
        """Красивый вывод конфигурации для логов"""
        return (
            f"⚙️ Конфигурация загружена:\n"
            f"  • Бот: {'✅' if self.bot_token else '❌'}\n"
            f"  • User ID: {self.telegram_user_id}\n"
            f"  • Raw: {self.path_to_raw}\n"
            f"  • Journal: {self.path_to_journal}\n"
            f"  • Summary: {self.path_to_summary}\n"
            f"  • Ollama: {self.ollama_base_url}\n"
            f"  • Ollama Models: {', '.join(self.ollama_models)}\n"
            f"  • Whisper: {self.whisper_model} ({self.whisper_device}, {self.whisper_compute_type})\n"
            f"  • Debug: {self.debug_mode}"
        )


# ==========================================
# 🚀 ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ==========================================
# Импортируйте settings в любом месте проекта: from config import settings

try:
    settings = Settings()
    print("✅ Конфигурация успешно загружена")
    print(settings)
except Exception as e:
    print(f"❌ Ошибка загрузки конфигурации: {e}")
    raise