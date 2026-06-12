import re
import pdfplumber
from datetime import date

# Импорт из корня
from models import db, Group

# Если нужна нормализация групп
# from services.group_helpers import normalize_group_name

def parse_weekly_pdf_to_events(pdf_file):
    """
    Возвращает список:
    [
        {
            "group_id": 1,
            "group_name": "П23-3А",
            "title": "ПСН",
            "date": date(2025, 9, 1),
            "week": 1
        },
        ...
    ]

    Коды оставляются как есть: ПСН, ҚА, ЛПС, ОН4.3 и т.д.
    """
    groups = Group.query.all()
    groups_sorted = sorted(
        [(normalize_group_name(g.name), g) for g in groups],
        key=lambda x: len(x[0]),
        reverse=True
    )

    events = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []

            for table in tables:
                if not table:
                    continue

                header_idx, week_cols = find_week_header(table)
                if header_idx is None or not week_cols:
                    continue

                for row in table[header_idx + 1:]:
                    cells = [clean_text(c) for c in row]
                    if not any(cells):
                        continue

                    row_text = " ".join(cells)
                    group = find_group_in_text(row_text, groups_sorted)
                    if not group:
                        continue

                    for col_idx, week_num in week_cols:
                        if col_idx >= len(cells):
                            continue

                        cell_text = clean_text(cells[col_idx])

                        if not cell_text:
                            continue
                        if cell_text in {"=", "::", ":", "-", "—"}:
                            continue
                        if re.fullmatch(r"\d{1,2}", cell_text):
                            continue

                        event_date = SEMESTER_START_DATE + timedelta(weeks=week_num - 1)

                        events.append({
                            "group_id": group.id,
                            "group_name": group.name,
                            "title": cell_text,   # оставляем как есть
                            "date": event_date,
                            "week": week_num
                        })

    return events


def save_pdf_events_as_reminders(events):
    created = 0
    skipped = 0

    for ev in events:
        group = Group.query.get(ev["group_id"])
        if not group:
            skipped += 1
            continue

        if not group.students:
            skipped += 1
            continue

        for student in group.students:
            exists = Reminder.query.filter_by(
                student_id=student.id,
                group_id=group.id,
                title=ev["title"],
                date=ev["date"]
            ).first()

            if exists:
                skipped += 1
                continue

            db.session.add(Reminder(
                student_id=student.id,
                group_id=group.id,
                title=ev["title"],
                date=ev["date"],
                time=None,
                type="График учебного процесса",
                note=f"Неделя {ev['week']}"
            ))
            created += 1

    db.session.commit()
    return created, skipped

def find_week_header(table):
    """
    Ищет строку, где много чисел 1..52 — это заголовок недель.
    Возвращает (row_index, [(col_index, week_number), ...]) или (None, []).
    """
    best_row_idx = None
    best_week_cols = []

    for row_idx, row in enumerate(table):
        week_cols = []
        for col_idx, cell in enumerate(row):
            s = clean_text(cell)
            if re.fullmatch(r"\d{1,2}", s):
                n = int(s)
                if 1 <= n <= 52:
                    week_cols.append((col_idx, n))

        if len(week_cols) > len(best_week_cols):
            best_row_idx = row_idx
            best_week_cols = week_cols

    if best_row_idx is not None and len(best_week_cols) >= 10:
        return best_row_idx, best_week_cols

    return None, []

def find_group_in_text(text, groups_sorted):
    """
    groups_sorted: [(normalized_group_name, Group), ...] sorted by length desc
    """
    norm_text = normalize_group_name(text)
    for norm_group, group_obj in groups_sorted:
        if norm_group and norm_group in norm_text:
            return group_obj
    return None
