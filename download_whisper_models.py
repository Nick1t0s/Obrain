"""
Скрипт для предзагрузки моделей Whisper.
Полезно для первичной настройки, чтобы избежать задержек при первом использовании.
"""

import os
import sys
import logging
from pathlib import Path
from typing import List

# Добавляем корень проекта в path для импортов
sys.path.insert(0, str(Path(__file__).parent))

from faster_whisper import WhisperModel

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ==========================================
# 📦 СПИСОК МОДЕЛЕЙ ДЛЯ ЗАГРУЗКИ
# ==========================================

# Основные модели (рекомендуемые)
RECOMMENDED_MODELS = [
    "large-v3",  # Лучшее качество (рекомендуется для продакшена)
    "medium",  # Хороший баланс качество/скорость
    "small",  # Быстрая модель для тестов
]

# Все доступные модели (если нужно всё)
ALL_MODELS = [
    "tiny", "tiny.en",
    "base", "base.en",
    "small", "small.en",
    "medium", "medium.en",
    "large", "large-v1", "large-v2", "large-v3", "large-v3-turbo"
]


# Модели из конфига (если есть .env)
def get_models_from_env() -> List[str]:
    """Читает модель из .env файла"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        model = os.getenv("WHISPER_MODEL", "")
        if model:
            return [model]
    except Exception as e:
        logger.warning(f"⚠️ Не удалось прочитать .env: {e}")
    return []


# ==========================================
# 🚀 ФУНКЦИИ ЗАГРУЗКИ
# ==========================================

def download_model(model_name: str, device: str = "cpu") -> bool:
    """
    Загружает модель Whisper.

    :param model_name: Название модели (например, "large-v3")
    :param device: Устройство для проверки ("cpu" безопаснее для загрузки)
    :return: True если успешно, False если ошибка
    """
    try:
        logger.info(f"⏳ Загрузка модели: {model_name}")

        # Инициализация модели (триггерит загрузку)
        # Используем cpu для загрузки, чтобы не занимать GPU зря
        model = WhisperModel(
            model_name,
            device=device,
            compute_type="int8",  # Минимальные требования для загрузки
        )

        # Проверка работоспособности (короткий тест)
        # model.model is not None означает, что модель загружена в память

        logger.info(f"✅ Модель {model_name} успешно загружена")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки {model_name}: {e}")
        return False


def verify_model(model_name: str) -> bool:
    """
    Проверяет, что модель доступна для использования.
    """
    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        del model
        return True
    except Exception:
        return False


# ==========================================
# 🎯 ГЛАВНАЯ ФУНКЦИЯ
# ==========================================

def main():
    logger.info("🚀 Предзагрузка моделей Whisper")
    logger.info("=" * 50)

    # Определяем, какие модели загружать
    models_to_download = []

    # Приоритет 1: Модели из .env
    # env_models = get_models_from_env()
    # if env_models:
    #     models_to_download.extend(env_models)
    #     logger.info(f"📄 Модели из .env: {env_models}")

    # Приоритет 2: Рекомендуемые (если в .env пусто)
    if not models_to_download:
        models_to_download = ALL_MODELS
        logger.info(f"📄 Используем рекомендуемые модели: {models_to_download}")

    # Статистика
    total = len(models_to_download)
    success = 0
    failed = 0

    logger.info(f"📦 Всего моделей для загрузки: {total}")
    logger.info("=" * 50)

    # Загрузка каждой модели
    for i, model_name in enumerate(models_to_download, 1):
        logger.info(f"[{i}/{total}] Обработка: {model_name}")

        # Проверка, загружена ли уже
        if verify_model(model_name):
            logger.info(f"✓ Модель {model_name} уже доступна (пропущено)")
            success += 1
            continue

        # Загрузка
        if download_model(model_name, device="cpu"):
            success += 1
        else:
            failed += 1

        # Разделитель
        if i < total:
            logger.info("-" * 50)

    # Итоговый отчет
    logger.info("=" * 50)
    logger.info("📊 ИТОГОВЫЙ ОТЧЕТ")
    logger.info("=" * 50)
    logger.info(f"✅ Успешно: {success}/{total}")
    logger.info(f"❌ Ошибки: {failed}/{total}")

    if failed > 0:
        logger.warning("⚠️ Некоторые модели не загрузились. Проверьте логи выше.")
        sys.exit(1)
    else:
        logger.info("🎉 Все модели успешно загружены!")
        sys.exit(0)


if __name__ == "__main__":
    main()