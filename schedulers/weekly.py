# schedulers/weekly.py
from pathlib import Path
from datetime import datetime, timedelta
import pytz

from base import BaseSummarizer
from config import settings

import logging

class WeeklySummarizer(BaseSummarizer):
    """
    Еженедельная суммаризация.
    Запускается в настройный день недели (1=Пн, 7=Вс).
    Обрабатывает ежедневные суммаризации за неделю.
    """

    def __init__(self, state_dir: Path):
        self.timezone = pytz.timezone(settings.timezone)
        self.target_weekday = settings.weekly_review_day  # 1-7
        super().__init__(
            name="WeeklySummarizer",
            state_file=state_dir / "weekly_state.json"
        )

    def _should_run(self) -> bool:
        now = datetime.now(self.timezone)
        # isoweekday(): Пн=1, Вс=7
        return now.isoweekday() == self.target_weekday and now.hour >= 20  # После 20:00

    def _get_period_id(self) -> str:
        """Возвращает идентификатор недели в формате 2023-W43"""
        now = datetime.now(self.timezone)
        iso_cal = now.isocalendar()
        return f"{iso_cal[0]}-W{iso_cal[1]:02d}"

    def _get_missed_periods(self) -> list[str]:
        """Находит пропущенные недели (последние 2)"""
        missed = []
        now = datetime.now(self.timezone)

        for weeks_ago in [1, 2]:
            # Вычисляем дату целевого дня недели (например, воскресенья) недель назад
            target_date = now - timedelta(weeks=weeks_ago)
            # Корректируем до нужного дня недели
            days_diff = target_date.isoweekday() - self.target_weekday
            period_end = target_date - timedelta(days=days_diff)

            period_id = f"{period_end.year}-W{period_end.isocalendar()[1]:02d}"

            if not self._is_period_processed(period_id):
                # Проверяем, что неделя уже закончилась
                if now > period_end + timedelta(days=1):
                    missed.append(period_id)

        return missed

    def _collect_data(self, period_id: str) -> str:
        """Собирает блоки "Итоги дня" из ежедневных файлов за неделю"""
        # Получаем даты всех дней недели
        year, week = period_id.split('-W')
        year, week = int(year), int(week)

        # Первый день недели (Пн)
        start = datetime.strptime(f'{year}-W{week:02d}-1', "%Y-W%W-%w")
        dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

        collected = []
        for date in dates:
            daily_file = settings.get_daily_note_path(date)
            if daily_file.exists():
                with open(daily_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Ищем блок "## 🌙 Итоги дня"
                if "## 🌙 Итоги дня" in content:
                    # Извлекаем блок (упрощённо: до следующего ##)
                    parts = content.split("## 🌙 Итоги дня")
                    if len(parts) > 1:
                        block = parts[1].split("##")[0].strip()
                        collected.append(f"[{date}]\n{block}")

        return '\n\n'.join(collected)

    def _build_prompt(self, data: str, period_id: str) -> str:
        return (
            f"Ты — аналитик продуктивности. Проанализируй итоги дней за неделю {period_id}.\n\n"
            f"Данные:\n\"\"\"{data}\"\"\"\n\n"
            f"Создай структурированное резюме недели:\n"
            f"## 📊 Обзор недели {period_id}\n"
            f"### 🏆 Достижения\n- ...\n"
            f"### 📉 Проблемы\n- ...\n"
            f"### 🎯 Фокус на следующую неделю\n- ...\n\n"
            f"Только факты и выводы, без воды."
        )

    def _save_result(self, period_id: str, summary: str):
        """Сохраняет результат в файл недельного обзора"""
        weekly_file = settings.get_weekly_note_path(period_id)
        weekly_file.parent.mkdir(parents=True, exist_ok=True)

        with open(weekly_file, 'w', encoding='utf-8') as f:
            f.write(f"---\nperiod: {period_id}\ntype: weekly_review\n---\n\n")
            f.write(summary + "\n")

        logging.info(f"📝 {self.name}: результат сохранён в {weekly_file}")

