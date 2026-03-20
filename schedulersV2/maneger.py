# schedulers/manager.py
import time
import logging
from pathlib import Path

from schedulersV2.daily import DailySummarizer
from schedulersV2.weekly import WeeklySummarizer
from schedulersV2.monthly import MonthlySummarizer
from config import settings

logger = logging.getLogger(__name__)


class SchedulerManager:
    """
    «Мегацикл»: управляет всеми планировщиками суммаризации.

    Использование:
        manager = SchedulerManager(state_dir)
        while True:
            manager.tick()
            time.sleep(60)
    """

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Инициализируем планировщики
        self.summarizers = [
            DailySummarizer(self.state_dir),
            WeeklySummarizer(self.state_dir),
            MonthlySummarizer(self.state_dir),
            # YearlySummarizer(self.state_dir),  # Можно добавить по аналогии
        ]

        logger.info(f"✅ SchedulerManager: инициализировано {len(self.summarizers)} планировщиков")

    def tick(self):
        """
        Основной метод цикла.
        Вызывает tick() у каждого планировщика.
        """
        for summarizer in self.summarizers:
            try:
                summarizer.tick()
            except Exception as e:
                logger.exception(f"❌ Ошибка в {summarizer.name}.tick(): {e}")

    def run_loop(self, interval: int = 60):
        """
        Запускает бесконечный цикл с интервалом проверки.
        Блокирующий вызов.
        """
        logger.info(f"🔄 SchedulerManager: запуск цикла (интервал {interval}с)")

        try:
            while True:
                self.tick()
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("👋 SchedulerManager: останов по Ctrl+C")