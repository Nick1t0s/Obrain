# schedulers/weekly.py
from pathlib import Path
from datetime import datetime, timedelta, date
import pytz

from schedulers.base import BaseSummarizer
from config import settings

import logging

logger = logging.getLogger(__name__)


class WeeklySummarizer(BaseSummarizer):
    """
    Еженедельная суммаризация.
    Запускается в настройный день недели (1=Пн, 7=Вс).
    Обрабатывает ежедневные суммаризации за неделю.
    """

    def __init__(self, state_dir: Path):
        self.timezone = pytz.timezone(settings.timezone)
        self.target_weekday = settings.weekly_review_day  # 1=Пн ... 7=Вс
        super().__init__(
            name="WeeklySummarizer",
            state_file=state_dir / "weekly_state.json"
        )

    # ==========================================
    # 🔧 ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ==========================================

    def _get_week_range(self, ref_date: datetime) -> tuple[date, date]:
        """
        Вычисляет начало и конец недели для заданной даты.
        Неделя заканчивается в self.target_weekday (например, в воскресенье).

        :return: (start_date, end_date) как объекты date
        """
        # Находим, сколько дней прошло с последнего target_weekday
        days_since_target = (ref_date.isoweekday() - self.target_weekday) % 7

        # Конец недели — ближайший target_weekday в прошлом (включая сегодня)
        end_date = (ref_date - timedelta(days=days_since_target)).date()
        # Начало недели — 6 дней до конца
        start_date = end_date - timedelta(days=6)

        return start_date, end_date

    def _format_period_id(self, start: date, end: date) -> str:
        """
        Формирует внутренний ID периода для хранения.
        Формат: YYYY-MM-DD_YYYY-MM-DD (безопасен для имён файлов)
        """
        return f"{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}"

    def _format_period_display(self, period_id: str) -> str:
        """
        Конвертирует внутренний ID в читаемый формат.
        Вход: "2023-03-23_2023-03-30"
        Выход: "23.03 - 30.03"
        """
        try:
            start_str, end_str = period_id.split('_')
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
            return f"{start.strftime('%d.%m')} - {end.strftime('%d.%m')}"
        except Exception as e:
            logger.warning(f"⚠️ Ошибка форматирования периода '{period_id}': {e}")
            return period_id  # Фоллбэк: возвращаем как есть

    # ==========================================
    # 🎯 АБСТРАКТНЫЕ МЕТОДЫ (реализация)
    # ==========================================

    def _should_run(self) -> bool:
        """Проверяет, пора ли запускать суммаризацию"""
        now = datetime.now(self.timezone)
        # Запускаем в целевой день недели после 20:00
        return now.isoweekday() == self.target_weekday and now.hour >= 20

    def _get_period_id(self) -> str:
        """Возвращает внутренний идентификатор текущей недели"""
        now = datetime.now(self.timezone)
        start, end = self._get_week_range(now)
        return self._format_period_id(start, end)

    def _get_missed_periods(self) -> list[str]:
        """Находит пропущенные недели (последние 2) для catch-up"""
        missed = []
        now = datetime.now(self.timezone)

        for weeks_ago in [1, 2]:
            ref_date = now - timedelta(weeks=weeks_ago)
            start, end = self._get_week_range(ref_date)
            period_id = self._format_period_id(start, end)

            if not self._is_period_processed(period_id):
                # Проверяем, что неделя точно закончилась (+6 часов буфер)
                if now.date() > end + timedelta(hours=6):
                    missed.append(period_id)

        return missed

    def _collect_data(self, period_id: str) -> str:
        """Собирает блоки 'Итоги дня' из ежедневных файлов за неделю"""
        # Парсим период из внутреннего ID
        try:
            start_str, end_str = period_id.split('_')
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга period_id '{period_id}': {e}")
            return ""

        collected = []
        current = start_date

        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            daily_file = settings.get_daily_note_path(date_str)

            if daily_file.exists():
                with open(daily_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Ищем блок "## 🌙 Итоги дня"
                if "## 🌙 Итоги дня" in content:
                    parts = content.split("## 🌙 Итоги дня")
                    if len(parts) > 1:
                        # Извлекаем блок до следующего заголовка ##
                        block = parts[1].split("\n##")[0].strip()
                        day_display = current.strftime('%d.%m')
                        collected.append(f"[{day_display}] {block}")

            current += timedelta(days=1)

        return '\n\n'.join(collected)

    def _build_prompt(self, data: str, period_id: str) -> str:
        """Формирует промпт для LLM с читаемым периодом"""
        display_period = self._format_period_display(period_id)

        return (
            f"Ты — аналитик продуктивности. Проанализируй итоги дней за период {display_period}.\n\n"
            f"Данные:\n\"\"\"{data}\"\"\"\n\n"
            f"Создай структурированное резюме:\n"
            f"## 📊 Обзор недели ({display_period})\n"
            f"### 🏆 Достижения\n- ...\n"
            f"### 📉 Проблемы\n- ...\n"
            f"### 🎯 Фокус на следующую неделю\n- ...\n\n"
            f"Только факты и выводы, без воды. Язык: русский."
        )

    def _save_result(self, period_id: str, summary: str):
        """Сохраняет результат в файл недельного обзора"""
        # Используем внутренний period_id для имени файла (безопасно для ФС)
        weekly_file = settings.path_to_summary / "Weekly" / f"{period_id}.md"
        weekly_file.parent.mkdir(parents=True, exist_ok=True)

        display_period = self._format_period_display(period_id)

        with open(weekly_file, 'w', encoding='utf-8') as f:
            # Frontmatter с обоими форматами
            f.write(f"---\nperiod: {period_id}\nperiod_display: '{display_period}'\ntype: weekly_review\n---\n\n")
            # Заголовок с читаемым периодом
            f.write(f"# 📊 Обзор недели: {display_period}\n\n")
            f.write(summary + "\n")

        logger.info(f"📝 {self.name}: результат сохранён в {weekly_file}")