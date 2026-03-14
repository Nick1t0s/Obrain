# schedulers/monthly.py
from pathlib import Path
from datetime import datetime, timedelta
from calendar import monthrange
import pytz

from base import BaseSummarizer
from config import settings

import logging

class MonthlySummarizer(BaseSummarizer):
    """
    Ежемесячная суммаризация.
    Запускается в настройный день месяца (или последний день).
    Обрабатывает недельные обзоры за месяц.
    """

    def __init__(self, state_dir: Path):
        self.timezone = pytz.timezone(settings.timezone)
        self.target_day = settings.monthly_review_day
        super().__init__(
            name="MonthlySummarizer",
            state_file=state_dir / "monthly_state.json"
        )

    def _should_run(self) -> bool:
        now = datetime.now(self.timezone)
        target = self.target_day

        # Если целевой день > числа дней в месяце, берём последний день
        _, last_day = monthrange(now.year, now.month)
        if target > last_day:
            target = last_day

        return now.day == target and now.hour >= 18  # После 18:00

    def _get_period_id(self) -> str:
        """Возвращает идентификатор месяца в формате 2023-10"""
        now = datetime.now(self.timezone)
        return now.strftime("%Y-%m")

    def _get_missed_periods(self) -> list[str]:
        """Находит пропущенные месяцы (последние 2)"""
        missed = []
        now = datetime.now(self.timezone)

        for months_ago in [1, 2]:
            # Вычисляем целевую дату месяцев назад
            target = now.replace(month=now.month - months_ago) if now.month > months_ago \
                else now.replace(year=now.year - 1, month=now.month - months_ago + 12)

            _, last_day = monthrange(target.year, target.month)
            day = min(self.target_day, last_day)
            period_end = target.replace(day=day)

            period_id = period_end.strftime("%Y-%m")

            if not self._is_period_processed(period_id):
                if now > period_end + timedelta(days=2):
                    missed.append(period_id)

        return missed

    def _collect_data(self, period_id: str) -> str:
        """Собирает недельные обзоры за месяц"""
        year, month = map(int, period_id.split('-'))

        collected = []
        # Перебираем все недели, которые частично попадают в месяц
        for week in range(1, 6):
            week_id = f"{year}-W{week:02d}"
            weekly_file = settings.get_weekly_note_path(week_id)

            if weekly_file.exists():
                with open(weekly_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Убираем frontmatter, берём основное содержание
                if '---\n' in content:
                    content = content.split('---\n', 2)[-1]
                collected.append(f"## {week_id}\n{content.strip()}")

        return '\n\n'.join(collected)

    def _build_prompt(self, data: str, period_id: str) -> str:
        return (
            f"Ты — стратег. Проанализируй недельные обзоры за месяц {period_id}.\n\n"
            f"Данные:\n\"\"\"{data}\"\"\"\n\n"
            f"Создай стратегическое резюме месяца:\n"
            f"## 📈 Итоги месяца {period_id}\n"
            f"### 🎯 Ключевые результаты\n- ...\n"
            f"### 🔄 Паттерны и тренды\n- ...\n"
            f"### 🚀 Приоритеты на следующий месяц\n- ...\n\n"
        )

    def _save_result(self, period_id: str, summary: str):
        """Сохраняет результат в файл месячного обзора"""
        monthly_file = settings.get_monthly_note_path(period_id)
        monthly_file.parent.mkdir(parents=True, exist_ok=True)

        with open(monthly_file, 'w', encoding='utf-8') as f:
            f.write(f"---\nperiod: {period_id}\ntype: monthly_review\n---\n\n")
            f.write(summary + "\n")

        logging.info(f"📝 {self.name}: результат сохранён в {monthly_file}")

