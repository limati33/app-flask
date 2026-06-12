import json
from flask import current_app

from .ai_client import chat, AI_MODEL


def _extract_json_array(text: str):
    """
    На случай, если модель вернула текст вокруг JSON.
    """
    if not text:
        return []

    text = text.strip()

    # ```json ... ```
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start != -1 and end != -1 and end > start:
            block = text[start:end].split("\n", 1)
            if len(block) == 2:
                text = block[1].strip()

    # Оставляем только массив, если он есть
    first = text.find("[")
    last = text.rfind("]")
    if first != -1 and last != -1 and last > first:
        text = text[first:last + 1]

    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def parse_lesson_with_ai(entries_list: list) -> list:
    """
    entries_list:
    [
        {"room": "...", "time_start": "...", "time_end": "...", "raw": "..."},
        ...
    ]

    returns:
    [
        {
            "group_raw": "...",
            "teacher_raw": "...",
            "subject_raw": "...",
            "time_start": "...",
            "time_end": "...",
            "raw": "..."
        }
    ]
    """
    if not entries_list:
        return []

    prompt = f"""
Ты парсер расписания колледжа.

Входные данные (JSON массив):
{json.dumps(entries_list, ensure_ascii=False, indent=2)}

Задача:
Для каждой записи извлеки:
- group_raw
- teacher_raw
- subject_raw
- time_start
- time_end
- raw

Правила:
- если в одной строке несколько групп — раздели на отдельные объекты
- если данных нет — ставь null
- не выдумывай данные
- возвращай только JSON массив

ФОРМАТ ОТВЕТА:
[
  {{
    "group_raw": "...",
    "teacher_raw": "...",
    "subject_raw": "...",
    "time_start": "08:00",
    "time_end": "09:30",
    "raw": "..."
  }}
]
"""

    try:
        text = chat(
            [
                {"role": "system", "content": "Отвечай строго JSON массивом."},
                {"role": "user", "content": prompt},
            ],
            model=AI_MODEL,
        )

        current_app.logger.info("OLLAMA RAW: %s", text)

        if not text:
            return []

        data = _extract_json_array(text)
        return data if isinstance(data, list) else []

    except Exception as e:
        current_app.logger.exception("AI parse error: %s", e)
        return []


def parse_multiple_lessons_with_ai(entries_list: list):
    return parse_lesson_with_ai(entries_list)