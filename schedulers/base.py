# schedulers/base.py
import json
import logging
import requests
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from config import settings

logger = logging.getLogger(__name__)


class BaseSummarizer(ABC):
    """
    Базовый класс для периодической суммаризации.

    Особенности:
    - Сохраняет состояние в JSON (last_run, processed_items)
    - При старте выполняет пропущенные запуски (catch-up)
    - Метод tick() проверяет, пора ли запускать
    """

    # Период в секундах между проверками (для tick)
    CHECK_INTERVAL = 60  # 1 минута

    def __init__(self, name: str, state_file: Path):
        self.name = name
        self.state_file = state_file
        self.state: dict = {}

        # Загружаем или создаём состояние
        self._load_state()

        # Catch-up: выполняем пропущенные запуски при старте
        self._catch_up_missed_runs()

    def _load_state(self):
        """Загружает состояние из файла или создаёт новое"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
                logger.debug(f"📄 {self.name}: состояние загружено")
            except Exception as e:
                logger.warning(f"⚠️ {self.name}: ошибка загрузки состояния: {e}")
                self.state = self._default_state()
        else:
            self.state = self._default_state()
            self._save_state()

    def _default_state(self) -> dict:
        """Создаёт пустое состояние"""
        return {
            'last_run': None,  # ISO-строка последнего успешного запуска
            'processed_periods': [],  # Список уже обработанных периодов (например, ["2023-10-27"])
            'failed_runs': [],  # История ошибок для отладки
        }

    def _save_state(self):
        """Сохраняет состояние на диск"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
        logger.debug(f"💾 {self.name}: состояние сохранено")

    def _is_period_processed(self, period_id: str) -> bool:
        """Проверяет, обработан ли уже данный период"""
        return period_id in self.state.get('processed_periods', [])

    def _mark_period_processed(self, period_id: str):
        """Помечает период как обработанный"""
        if 'processed_periods' not in self.state:
            self.state['processed_periods'] = []
        if period_id not in self.state['processed_periods']:
            self.state['processed_periods'].append(period_id)
            self._save_state()

    def _update_last_run(self):
        """Обновляет время последнего запуска"""
        self.state['last_run'] = datetime.now().isoformat()
        self._save_state()

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        """Отправляет запрос к Ollama"""
        model = model or settings.ollama_model_summary

        try:
            response = requests.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "temperature": settings.llm_temperature,
                    "stream": False,
                    "keep_alive": 0,  # Выгружаем модель сразу
                },
                timeout=settings.llm_timeout * 2,  # Суммаризация может быть дольше
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"❌ {self.name}: Ollama error: {e}")
            raise

    @abstractmethod
    def _should_run(self) -> bool:
        """Проверяет, пора ли запускать суммаризацию (переопределить в наследнике)"""
        pass

    @abstractmethod
    def _get_period_id(self) -> str:
        """Возвращает уникальный идентификатор текущего периода (например, "2023-10-27")"""
        pass

    @abstractmethod
    def _collect_data(self, period_id: str) -> str:
        """Собирает данные для суммаризации (текст из заметок)"""
        pass

    @abstractmethod
    def _build_prompt(self, data: str, period_id: str) -> str:
        """Формирует промпт для LLM"""
        pass

    @abstractmethod
    def _save_result(self, period_id: str, summary: str):
        """Сохраняет результат суммаризации в файл"""
        pass

    def _run_summary(self, period_id: str):
        """Запускает полный пайплайн суммаризации для периода"""
        if self._is_period_processed(period_id):
            logger.info(f"⏭️ {self.name}: период {period_id} уже обработан")
            return

        logger.info(f"🔄 {self.name}: начинаю суммаризацию периода {period_id}")

        try:
            # 1. Сбор данных
            data = self._collect_data(period_id)
            if not data.strip():
                logger.warning(f"⚠️ {self.name}: нет данных для периода {period_id}")
                self._mark_period_processed(period_id)
                return

            # 2. Формирование промпта и запрос к LLM
            prompt = self._build_prompt(data, period_id)
            summary = self._call_ollama(prompt, settings.ollama_model_summary)

            if not summary.strip():
                raise ValueError("Пустой ответ от LLM")

            # 3. Сохранение результата
            self._save_result(period_id, summary)

            # 4. Обновление состояния
            self._mark_period_processed(period_id)
            self._update_last_run()

            logger.info(f"✅ {self.name}: суммаризация {period_id} завершена")

        except Exception as e:
            logger.exception(f"❌ {self.name}: ошибка при суммаризации {period_id}: {e}")
            # Записываем ошибку в состояние для отладки
            self.state.setdefault('failed_runs', []).append({
                'period': period_id,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
            self._save_state()

    def _catch_up_missed_runs(self):
        """
        При старте проверяет, не были ли пропущены запуски,
        и выполняет их (в пределах разумного лимита).
        """
        logger.info(f"🔍 {self.name}: проверка пропущенных запусков...")

        # Получаем список периодов, которые нужно обработать
        missed = self._get_missed_periods()

        if not missed:
            logger.info(f"✅ {self.name}: пропущенных запусков нет")
            return

        logger.warning(f"⚠️ {self.name}: найдено пропущенных запусков: {len(missed)}")

        # Выполняем с лимитом, чтобы не перегрузить систему при долгом простое
        MAX_CATCHUP = 3
        for i, period_id in enumerate(missed[:MAX_CATCHUP], 1):
            logger.info(f"🔄 {self.name}: catch-up [{i}/{len(missed)}] период {period_id}")
            self._run_summary(period_id)

        if len(missed) > MAX_CATCHUP:
            logger.warning(f"⚠️ {self.name}: пропущено {len(missed) - MAX_CATCHUP} запусков (лимит catch-up)")

    @abstractmethod
    def _get_missed_periods(self) -> List[str]:
        """Возвращает список периодов, которые нужно обработать (catch-up)"""
        pass

    def tick(self):
        """
        Основной метод «мегацикла».
        Вызывается периодически из главного цикла бота.
        """
        if self._should_run():
            period_id = self._get_period_id()
            self._run_summary(period_id)