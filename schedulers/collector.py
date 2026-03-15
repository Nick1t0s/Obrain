# collectors/collector.py
import logging
from pathlib import Path
from typing import Optional

import requests

from config import settings

logger = logging.getLogger(__name__)


class Collector:
    def __init__(self):
        self.path_to_data = settings.path_to_data

    def change_data(self, data: str):
        """Точечное обновление базы знаний по запросу пользователя"""
        try:
            logger.info(f"🔄 change_ начинаю: '{data[:50]}...'")

            data_have = self._read_data()
            prompt = self._build_change_data_prompt(data, data_have)

            response = requests.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model_summary,
                    "system": "Ты — редактор базы знаний. Обновляешь хранилище новыми данными, сохраняя структуру. Не добавляешь от себя комментарии.",
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": 0
                },
                timeout=120,  # 🔹 Таймаут 2 минуты
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            ans = response.json().get("response", "").strip()
            if not ans:
                raise ValueError("Пустой ответ от LLM")

            with open(self.path_to_data, "w", encoding="utf-8") as file:
                file.write(ans)

            logger.info("✅ Успешное ручное обновление базы знаний")

        except requests.exceptions.Timeout:
            logger.error("⏱️ Таймаут запроса к Ollama")
            raise
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Не удалось подключиться к Ollama: {settings.ollama_base_url}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка в change_ {type(e).__name__}: {e}")
            raise

    def collect_data(self, period_id: str):
        """
        Сбор и агрегация новых заметок в базу знаний.
        Запускается периодически планировщиками.
        """
        new_notes = self._get_data(period_id, period_id)
        try:
            logger.info(f"🔄 _collect_ период={period_id}")

            if not new_notes.strip():
                logger.info("⏭️ Нет новых заметок для сбора")
                return

            data_have = self._read_data()
            print(data_have)
            prompt = self._build_collect_data_prompt(new_notes, period_id, data_have)

            response = requests.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model_summary,
                    "system": "Ты — аналитик базы знаний. Агрегируешь заметки в структурированное хранилище.",
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": 0
                },
                timeout=120,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            ans = response.json().get("response", "").strip()
            if not ans:
                raise ValueError("Пустой ответ от LLM")

            with open(self.path_to_data, "w", encoding="utf-8") as file:
                file.write(ans)

            logger.info(f"✅ _collect_ период {period_id} завершён")

        except Exception as e:
            logger.error(f"❌ Ошибка в _collect_ {type(e).__name__}: {e}")
            raise

    def _get_data(self, start_date: str, end_date: str) -> str:
        """
        Собирает обработанные заметки из ежедневного журнала за период.

        :param start_date: Дата начала (формат: %Y-%m-%d)
        :param end_date: Дата конца (формат: %Y-%m-%d)
        :return: Объединённый текст заметок
        """
        from datetime import datetime, timedelta

        collected = []
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            daily_file = settings.get_daily_note_path(date_str)

            if daily_file.exists():
                with open(daily_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Извлекаем только обработанные блоки (#### **ВРЕМЯ**)
                lines = [line for line in content.split('\n') if not line.startswith('#### **')]
                if lines:
                    collected.append(f"## {date_str}\n" + '\n'.join(lines))

            current += timedelta(days=1)

        result = '\n\n'.join(collected)
        logger.debug(f"📥 _get_ собрано: {len(collected)} дней, {len(result)} символов")
        return result

    def _read_data(self) -> str:
        """Читает текущее содержимое базы знаний"""
        try:
            # Создаём файл, если не существует
            self.path_to_data.parent.mkdir(parents=True, exist_ok=True)
            if not self.path_to_data.exists():
                with open(self.path_to_data, 'w', encoding='utf-8') as f:
                    f.write("# 🧠 Личная база знаний\n\n")
                logger.info(f"📄 Создан новый файл базы: {self.path_to_data}")

            with open(self.path_to_data, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            logger.error(f"❌ Ошибка чтения файла: {e}")
            raise

    @staticmethod
    def _build_collect_data_prompt(data: str, period_id: str, data_have: str) -> str:
        return (
            f"Ты — ассистент для ведения базы знаний. Твоя задача — обновить существующее хранилище новыми данными за период {period_id}.\n\n"
            f"📥 ВХОДНЫЕ ДАННЫЕ:\n"
            f"1. Новые заметки за период:\n\"\"\"{data}\"\"\"\n\n"
            f"2. Текущее состояние хранилища:\n\"\"\"{data_have}\"\"\"\n\n"
            f"🎯 ЗАДАЧА:\n"
            f"1. ✅ ДОБАВЬ: новую информацию из заметок в соответствующие разделы.\n"
            f"2. ✅ ОБНОВИ: существующие данные, если есть противоречия или уточнения.\n"
            f"3. ✅ ИСПРАВЬ: ошибки оформления, опечатки, дубликаты.\n"
            f"4. ❌ НЕ УДАЛЯЙ: данные, о которых ничего не сказано в новых заметках.\n"
            f"5. ❌ НЕ ДОБАВЛЯЙ: от себя комментарии, выводы, рассуждения.\n\n"
            f"📋 ФОРМАТ ВЫВОДА:\n"
            f"Используй иерархическую структуру заголовков:\n"
            f"## Тема\n"
            f"### Подтема\n"
            f"#### Детали\n"
            f"Текст содержания...\n\n"
            f"⚠️ ПРАВИЛА:\n"
            f"- Сохраняй существующую структуру разделов, если нет причин для изменений.\n"
            f"- Если новая информация не подходит ни в один раздел — создай новый.\n"
            f"- Пиши кратко, по делу, без воды.\n"
            f"- Язык ответа: русский.\n\n"
            f"🔹 ПРИМЕР:\n"
            f"Вход (новые заметки): \"Завершил транскрибацию ГС. Ошибка с CUDA исправлена.\"\n"
            f"Вход (хранилище): \"## Разработка\\n### Бот\\nВ процессе транскрибация\"\n"
            f"Выход:\n"
            f"## Разработка\\n### Бот\\nТранскрибация ГС завершена. Ошибка с CUDA исправлена.\n\n"
            f"🚀 ТВОЙ ОТВЕТ (только обновлённое хранилище, без комментариев):"
        )

    @staticmethod
    def _build_change_data_prompt(data: str, data_have: str) -> str:
        """Формирует промпт для точечного обновления базы знаний"""
        return (
            f"Ты — ассистент для управления личной базой знаний. Твоя задача — точечно обновить хранилище на основе одного факта от пользователя.\n\n"
            f"📥 ВХОДНЫЕ ДАННЫЕ:\n"
            f"1. Новый факт от пользователя:\n\"\"\"{data}\"\"\"\n\n"
            f"2. Текущее хранилище:\n\"\"\"{data_have}\"\"\"\n\n"
            f"🎯 ЗАДАЧА:\n"
            f"1. ✅ ОПРЕДЕЛИ: к какой теме/разделу относится новый факт.\n"
            f"2. ✅ ДОБАВЬ: новую информацию в соответствующий раздел.\n"
            f"3. ✅ ОБНОВИ: если есть противоречие со старыми данными — замени их.\n"
            f"4. ❌ НЕ ТРОГАЙ: все остальные разделы, о которых ничего не сказано.\n"
            f"5. ❌ НЕ УДАЛЯЙ: данные, которые не противоречат новому факту.\n"
            f"6. ❌ НЕ ДОБАВЛЯЙ: от себя комментарии, выводы, предположения.\n\n"
            f"📋 ФОРМАТ ВЫВОДА:\n"
            f"Используй иерархическую структуру заголовков:\n"
            f"## Тема\n"
            f"### Подтема\n"
            f"Текст...\n\n"
            f"⚠️ ПРАВИЛА:\n"
            f"- Если раздела для новой темы нет — создай его.\n"
            f"- Сохраняй существующую структуру остальных разделов без изменений.\n"
            f"- Пиши кратко, по делу, без воды.\n"
            f"- Язык ответа: русский.\n"
            f"- Верни ТОЛЬКО обновлённое хранилище, без комментариев до и после.\n\n"
            f"🔹 ПРИМЕР:\n"
            f"Вход: 'у меня есть девушка'\n"
            f"Хранилище: '## Работа\\n### Проект\\nВ разработке'\n"
            f"Выход: '## Работа\\n### Проект\\nВ разработке\\n\\n## Личное\\n### Отношения\\nЕсть девушка'\n\n"
            f"🚀 ТВОЙ ОТВЕТ (только обновлённое хранилище):"
        )


# Глобальный экземпляр
collector = Collector()
