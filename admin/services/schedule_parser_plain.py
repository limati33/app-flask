import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from itertools import zip_longest
from docx import Document

try:
    # Reuse your existing normalizer if it is available in the project.
    from .normalization import normalize_text
except Exception:
    import unicodedata

    def normalize_text(text):
        if text is None:
            return ""
        text = unicodedata.normalize("NFKC", str(text))
        text = text.replace("\u00A0", " ")
        text = text.replace("\u2007", " ")
        text = text.replace("\u202F", " ")
        text = text.replace("−", "-").replace("—", "-").replace("–", "-")
        text = re.sub(r"\s+", " ", text)
        return text.strip()


GROUP_TOKEN_RE = re.compile(
    r"\b(?:[A-ZА-ЯЁІӘҒҚҢӨҰҮҺ]{1,10}\s*)?\d{2}\s*-\s*\d+[A-ZА-ЯЁІӘҒҚҢӨҰҮҺA-Za-z0-9]{0,6}\b",
    re.IGNORECASE,
)

DATE_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4})")

TIME_PATTERNS = [
    r"(\d{1,2}[:.]\d{2})\s*[-–—]\s*(\d{1,2}[:.]\d{2})",
    r"(\d{3,4})\s*[-–—]\s*(\d{3,4})",
    r"(\d{1,2}[:.]\d{2})\s*(?:до|по)\s*(\d{1,2}[:.]\d{2})",
]


def normalize_time_string(s: str) -> str:
    s = normalize_text(s).replace(" ", "")

    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", s)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return f"{h:02d}:{mm:02d}"
        return s

    m = re.fullmatch(r"(\d{3,4})", s)
    if m:
        digits = m.group(1).zfill(4)
        h = int(digits[:2])
        mm = int(digits[2:])
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return f"{h:02d}:{mm:02d}"
        return s

    return s


def extract_time_pair_from_text(text: str) -> Optional[Tuple[str, str]]:
    if not text:
        return None

    text = normalize_text(text)

    for pattern in TIME_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return normalize_time_string(m.group(1)), normalize_time_string(m.group(2))

    return None


def extract_group_from_text(text: str) -> Tuple[Optional[str], str]:
    text = normalize_text(text)
    if not text:
        return None, ""

    m = GROUP_TOKEN_RE.search(text)
    if not m:
        return None, text

    group = m.group(0).strip()
    remainder = (text[:m.start()] + " " + text[m.end():]).strip()
    remainder = re.sub(r"\s+", " ", remainder)
    return group, remainder


def parse_cell_multi_entries(cell_text: str) -> List[Dict[str, str]]:
    text = normalize_text(cell_text)
    if not text:
        return []

    # Разбиваем по строкам (полезно, если в ячейке несколько пар через Enter)
    lines = [normalize_text(x) for x in re.split(r"[\r\n]+", text) if normalize_text(x)]
    entries = []

    for line in lines:
        # Ищем ВСЕ группы в строке
        matches = list(GROUP_TOKEN_RE.finditer(line))
        
        if not matches:
            continue

        # Собираем список найденных групп
        groups = [m.group(0).strip() for m in matches]

        # Вырезаем названия групп из строки, чтобы оставить только предмет/учителя
        raw_text = line
        for g in groups:
            raw_text = raw_text.replace(g, "")

        # Убираем лишние слэши, запятые и пробелы по краям
        raw_text = re.sub(r"^[ /;,\-]+|[ /;,\-]+$", "", raw_text).strip()
        raw_text = re.sub(r"\s+", " ", raw_text)

        # Создаем запись для каждой найденной группы с общим текстом предмета
        for g in groups:
            entries.append({
                "group_raw": g,
                "raw": raw_text
            })

    return entries


def detect_schedule_date(doc: Document) -> Optional[str]:
    """
    Returns first date found in the document in DD.MM.YYYY form.
    """
    for paragraph in doc.paragraphs:
        text = normalize_text(paragraph.text)
        if not text:
            continue
        m = DATE_RE.search(text)
        if m:
            return m.group(1)
    return None


def parse_schedule_plain(filepath: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Plain parser without AI.

    Returns:
      entries: [
        {
          "date": "25.05.2026",
          "weekday": 1,
          "room": "ГК 102",
          "time_start": "08:00",
          "time_end": "09:30",
          "group_raw": "П25-1Г",
          "raw": "Дюсембекова каз.яз. и лит",
          "source_text": "... original cell text ..."
        },
        ...
      ]
      stats: counters
    """
    doc = Document(filepath)

    stats = {
        "tables": 0,
        "rows": 0,
        "cells": 0,
        "entries": 0,
        "skipped_no_time": 0,
        "skipped_no_group": 0,
        "skipped_empty": 0,
    }

    entries: List[Dict[str, Any]] = []

    date_str = detect_schedule_date(doc)
    weekday = None
    if date_str:
        try:
            weekday = datetime.strptime(date_str, "%d.%m.%Y").weekday() + 1
        except Exception:
            weekday = None

    for table in doc.tables:
        stats["tables"] += 1

        if len(table.rows) < 2:
            continue

        header = table.rows[0]
        column_times: Dict[int, Tuple[str, str]] = {}

        # ВАЖНО: start=1, потому что 0-я колонка — это аудитория/room
        for i, cell in enumerate(header.cells[1:], start=1):
            times = extract_time_pair_from_text(normalize_text(cell.text))
            if times:
                column_times[i] = times

        for row in table.rows[1:]:
            stats["rows"] += 1
            cells = row.cells

            if len(cells) < 2:
                stats["skipped_empty"] += 1
                continue

            room_name = normalize_text(cells[0].text).strip()
            if not room_name or room_name.upper() in ("АУД", "AUD"):
                continue

            room_name = re.sub(r"^([A-ZА-ЯЁ]{1,3})(\d+)", r"\1 \2", room_name, flags=re.IGNORECASE)
            room_name = re.sub(r"\s+", " ", room_name).strip()

            # Группируем содержимое по временному слоту
            timeslot_texts: Dict[Tuple[str, str], List[str]] = {}
            seen_cell_ids = set()

            # ВАЖНО: идём по cells[1:], потому что cells[0] — room
            for i, cell in enumerate(cells[1:], start=1):
                if i not in column_times:
                    continue

                # Защита от дублей из-за merged-ячеек Word
                tc = getattr(cell, "_tc", None)
                cell_id = id(tc) if tc is not None else id(cell)
                if cell_id in seen_cell_ids:
                    continue
                seen_cell_ids.add(cell_id)

                t = column_times[i]
                cell_text = normalize_text(cell.text)

                if not cell_text:
                    continue

                if t not in timeslot_texts:
                    timeslot_texts[t] = []
                timeslot_texts[t].append(cell_text)

            for (time_start, time_end), texts in timeslot_texts.items():
                if not texts:
                    stats["skipped_empty"] += 1
                    continue

                stats["cells"] += 1

                # Склеиваем строки построчно, если в нескольких ячейках внутри слота
                # содержатся параллельные записи через Enter
                cell_lines_list = [
                    re.split(r"[\r\n]+", txt.strip())
                    for txt in texts
                    if txt.strip()
                ]

                combined_lines = []
                for line_tuple in zip_longest(*cell_lines_list, fillvalue=""):
                    line = " ".join(part for part in line_tuple if part).strip()
                    if line:
                        combined_lines.append(line)

                combined_text = "\n".join(combined_lines).strip()
                if not combined_text:
                    stats["skipped_empty"] += 1
                    continue

                # Пытаемся извлечь несколько групп из текста
                cell_entries = parse_cell_multi_entries(combined_text)

                if not cell_entries:
                    group_raw, raw = extract_group_from_text(combined_text)
                    if not group_raw:
                        stats["skipped_no_group"] += 1
                        continue

                    entries.append({
                        "date": date_str,
                        "weekday": weekday,
                        "room": room_name,
                        "time_start": time_start,
                        "time_end": time_end,
                        "group_raw": group_raw,
                        "raw": raw,
                        "source_text": combined_text,
                    })
                    stats["entries"] += 1
                    continue

                for item in cell_entries:
                    group_raw = (item.get("group_raw") or "").strip()
                    raw = (item.get("raw") or "").strip()

                    if not group_raw:
                        stats["skipped_no_group"] += 1
                        continue

                    entries.append({
                        "date": date_str,
                        "weekday": weekday,
                        "room": room_name,
                        "time_start": time_start,
                        "time_end": time_end,
                        "group_raw": group_raw,
                        "raw": raw,
                        "source_text": combined_text,
                    })
                    stats["entries"] += 1

    return entries, stats


def parse_schedule_plain_to_entries(filepath: str) -> List[Dict[str, Any]]:
    entries, _ = parse_schedule_plain(filepath)
    return entries


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python schedule_parser_plain.py <file.docx>")
        raise SystemExit(1)

    result, stats = parse_schedule_plain(sys.argv[1])
    print(json.dumps({"stats": stats, "entries": result}, ensure_ascii=False, indent=2))
