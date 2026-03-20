from pathlib import Path
import datetime
from datetime import time, timedelta
from schedulersV2.base import BaseScheduler
from config import settings

import logging
import requests

from typing import Optional


logger = logging.getLogger(__name__)


class DailySummarizer(BaseScheduler):

    STR_FORMAT = "%d-%m-%Y"
    def __init__(self, state_dir: Path):
        self.summary_time = self._parse_time(settings.daily_summary_time)
        self.target = self._parse_time(settings.daily_summary_time)
        super().__init__(
            name="DailySummarizer",
            state_file=state_dir / "daily_state.json"
        )

    def _run_now(self, date: datetime.datetime):
        """Запускает полный пайплайн суммаризации для периода"""
        if self._is_period_processed(date):
            logger.info(f"⏭️ {self.name}: период {date.strftime(self.STR_FORMAT)} уже обработан")
            return

        logger.info(f"🔄 {self.name}: начинаю суммаризацию периода {date.strftime(self.STR_FORMAT)}")

        try:
            # 1. Сбор данных
            data = self._collect_data(date)
            if not data.strip():
                logger.warning(f"⚠️ {self.name}: нет данных для периода {date}")
                self._mark_period_processed(date)
                return

            # 2. Формирование промпта и запрос к LLM
            prompt = self._build_prompt(data, date)
            summary = self._call_ollama(prompt, settings.ollama_model_summary)

            if not summary.strip():
                raise ValueError("Пустой ответ от LLM")

            # 3. Сохранение результата
            self._save_result(date, summary)

            # 4. Обновление состояния
            self._mark_period_processed(date)

            logger.info(f"✅ {self.name}: суммаризация {date.strftime(self.STR_FORMAT)} завершена")

        except Exception as e:
            logger.exception(f"❌ {self.name}: ошибка при суммаризации {date.strftime(self.STR_FORMAT)}: {e}")
            # Записываем ошибку в состояние для отладки
            self.state.setdefault('failed_runs', []).append({
                'period': date.strftime(self.STR_FORMAT),
                'error': str(e),
                'timestamp': datetime.datetime.now().isoformat()
            })
            self._save_state()

    def _run_missed(self, date: datetime.datetime):
        self._run_now(date)

    def _should_run(self, now: datetime.datetime) -> bool:
        """Функция проверки необходимости запуска в данный момент"""
        current_time = time(now.hour, now.minute)
        diff = abs((datetime.datetime.combine(now.date(), current_time) -
                    datetime.datetime.combine(now.date(), self.target)).total_seconds())
        return diff <= settings.diff

    def _parse_time(self, time_str: str) -> time:
        """Парсит строку "ЧЧ:ММ" в объект time"""
        h, m = map(int, time_str.split(':'))
        return time(h, m)

    def _get_missed_periods(self) -> list[str]:
        """Находит дни, когда суммаризация не была выполнена"""
        missed = []
        now = datetime.datetime.now()

        # Проверяем последние 3 дня (на случай, если бот был выключен)
        for i in range(1, settings.day_catchup_limit):
            date = now - timedelta(days=i)
            if not self._is_period_processed(date):
                # Проверяем, что время запуска для этого дня уже прошло
                run_datetime = datetime.datetime.combine(
                    date,
                    self.summary_time
                )
                if now > run_datetime:
                    missed.append(date)

        return missed

    def _is_period_processed(self, date: datetime.datetime) -> bool:
        """Проверяет, обработан ли уже данный период"""
        return date.strftime(self.STR_FORMAT) in self.state.get('processed_periods', [])

    def _collect_data(self, date: datetime.datetime) -> str:
        """Собирает обработанные заметки из ежедневного файла"""
        daily_file = self._get_daily_file_path(date)
        if not daily_file.exists():
            return ""

        with open(daily_file, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')

        return '\n'.join(lines)

    def _build_prompt(self, data: str, date: datetime.datetime) -> str:
        """Создает промпт для LLM"""
        # TODO: вынести в отдельный файл
        return (
            f"Ты — ассистент для подведения итогов дня. Проанализируй заметки за {date.strftime(self.STR_FORMAT)}.\n\n"
            f"Заметки:\n\"\"\"{data}\"\"\"\n\n"
            f"Создай краткое резюме дня в формате:\n"
            f"## 🌙 Итоги дня ({date.strftime(self.STR_FORMAT)})\n"
            f"• Главное достижение: ...\n"
            f"• Ключевой инсайт: ...\n"
            f"• Настроение: ...\n\n"
            f"Без лишних комментариев, только результат."
        )

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
                timeout=settings.llm_timeout * 2,  # TODO: навести порядок в .env
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"❌ {self.name}: Ollama error: {e}")
            raise

    def _save_result(self, date: datetime.datetime, summary: str):
        """Дописывает суммаризацию в конец ежедневного файла"""
        daily_file = self._get_daily_file_path(date)
        daily_file.parent.mkdir(parents=True, exist_ok=True)

        with open(daily_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{summary}\n")

        logging.info(f"📝 {self.name}: результат сохранён в {daily_file}")


    def _get_daily_file_path(self, date: datetime.datetime):
        return settings.path_to_journal / Path(date.strftime(self.STR_FORMAT) + ".md")

