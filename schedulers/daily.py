# schedulers/daily.py
from pathlib import Path
from datetime import datetime, time, timedelta
import pytz  # pip install pytz

from schedulers.base import BaseSummarizer
from config import settings

import logging

from schedulers import collector

logger = logging.getLogger(__name__)


class DailySummarizer(BaseSummarizer):
    """
    Ежедневная суммаризация.
    Запускается в настройное время (например, 23:30).
    Обрабатывает обработанные заметки из журнала за день.
    """

    def __init__(self, state_dir: Path):
        self.timezone = pytz.timezone(settings.timezone)
        self.summary_time = self._parse_time(settings.daily_summary_time)
        super().__init__(
            name="DailySummarizer",
            state_file=state_dir / "daily_state.json"
        )

    def _parse_time(self, time_str: str) -> time:
        """Парсит строку "ЧЧ:ММ" в объект time"""
        h, m = map(int, time_str.split(':'))
        return time(h, m)

    def _should_run(self) -> bool:
        now = datetime.now(self.timezone)
        current_time = now.time()

        # Проверяем, наступило ли время запуска (с допуском ±5 минут)
        target = self.summary_time
        diff = abs((datetime.combine(now.date(), current_time) -
                    datetime.combine(now.date(), target)).total_seconds())

        return diff <= 300  # 5 минут в секундах

    def _get_period_id(self) -> str:
        """Возвращает дату в формате YYYY-MM-DD"""
        return datetime.now(self.timezone).strftime("%Y-%m-%d")

    def _get_missed_periods(self) -> list[str]:
        """Находит дни, когда суммаризация не была выполнена"""
        missed = []
        now = datetime.now(self.timezone)

        # Проверяем последние 3 дня (на случай, если бот был выключен)
        for i in range(1, 4):
            date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            if not self._is_period_processed(date):
                # Проверяем, что время запуска для этого дня уже прошло
                run_datetime = datetime.combine(
                    datetime.strptime(date, "%Y-%m-%d").date(),
                    self.summary_time
                )
                run_datetime = self.timezone.localize(run_datetime)
                if now > run_datetime:
                    missed.append(date)

        return missed

    def _collect_data(self, period_id: str) -> str:
        """Собирает обработанные заметки из ежедневного файла"""
        daily_file = settings.get_daily_note_path(period_id)
        print(daily_file)
        if not daily_file.exists():
            return ""

        with open(daily_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Формат файла: #### **ВРЕМЯ**\nтекст
        lines = content.split('\n')

        return '\n'.join(lines)

    def _build_prompt(self, data: str, period_id: str) -> str:
        return (
            f"Ты — ассистент для подведения итогов дня. Проанализируй заметки за {period_id}.\n\n"
            f"Заметки:\n\"\"\"{data}\"\"\"\n\n"
            f"Создай краткое резюме дня в формате:\n"
            f"## 🌙 Итоги дня ({period_id})\n"
            f"• Главное достижение: ...\n"
            f"• Ключевой инсайт: ...\n"
            f"• Настроение: ...\n\n"
            f"Без лишних комментариев, только результат."
        )

    def _save_result(self, period_id: str, summary: str):
        """Дописывает суммаризацию в конец ежедневного файла"""
        daily_file = settings.get_daily_note_path(period_id)
        daily_file.parent.mkdir(parents=True, exist_ok=True)

        with open(daily_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{summary}\n")

        logging.info(f"📝 {self.name}: результат сохранён в {daily_file}")

        collector.collect_data(period_id)





