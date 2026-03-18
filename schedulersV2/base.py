import datetime

from abc import ABC, abstractmethod

from config import settings
import logging
from pathlib import Path
import json
import datetime

from typing import List

logger = logging.getLogger(__name__)


class BaseScheduler(ABC):

    CHECK_INTERVAL = 60  # TODO: вынести в .env

    def __init__(self, name: str, state_file: Path):
        self.name = name
        self.state_file = state_file
        self.state: dict = {}

        self._load_state()

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

    def _catch_up_missed_runs(self):
        """При старте проверяет, не были ли пропущены запуски и выполняет их"""
        logger.info(f"🔍 {self.name}: проверка пропущенных запусков...")
        missed = self._get_missed_periods()

        if not missed:
            logger.info(f"✅ {self.name}: пропущенных запусков нет")
            return

        logger.warning(f"⚠️ {self.name}: найдено пропущенных запусков: {len(missed)}")

        MAX_CATCHUP = 3 # TODO: вынести env
        for i, period_id in enumerate(missed[:MAX_CATCHUP], 1):
            logger.info(f"🔄 {self.name}: catch-up [{i}/{len(missed)}] период {period_id}")
            self._run_missed(period_id)

        if len(missed) > MAX_CATCHUP:
            logger.warning(f"⚠️ {self.name}: пропущено {len(missed) - MAX_CATCHUP} запусков (лимит catch-up)")

    def tick(self):
        now = datetime.datetime.now()
        if self._should_run(now):
            self._run_now(now)

    @abstractmethod
    def _should_run(self, now: datetime.datetime) -> bool:
        """Функция проверки необходимости запуска в данный момент"""
        pass

    @abstractmethod
    def _get_missed_periods(self) -> List[datetime.datetime]:
        """Возвращает список дней(т.е. периодов), которые нужно обработать (catch-up)"""
        pass

    @abstractmethod
    def _run_missed(self, date: datetime.datetime):
        """Функция обработки пропущенного дня"""
        pass

    @abstractmethod
    def _run_now(self, date: datetime.datetime):
        """Функция обработки текущего дня"""

