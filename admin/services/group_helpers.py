import re
from flask import current_app
from sqlalchemy import func

from models import db, Group
from .normalization import normalize_text, compact_key, normalize_group_display

AUTO_CREATE_MISSING_GROUP = True

GROUP_PATTERNS = [
    r"\b[A-Za-zА-Яа-яЁё]{1,10}\s*\d{2}\s*-\s*\d+[A-Za-zА-Яа-яЁё0-9]{0,4}\b"
]

def extract_group_from_text(text):
    text = normalize_text(text)
    if not text:
        return None, text

    best = None

    for pattern in GROUP_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidate = m.group(0)
            if best is None or m.start() > best[0]:
                best = (m.start(), m.end(), candidate)

    if best:
        start, end, candidate = best
        remainder = (text[:start] + " " + text[end:]).strip()
        remainder = re.sub(r"\s+", " ", remainder)
        return candidate, remainder

    return None, text

def split_cell_entries(cell_text):
    text = normalize_text(cell_text)
    if not text:
        return []

    lines = [normalize_text(x) for x in re.split(r"[\r\n]+", text) if normalize_text(x)]
    if not lines:
        return []

    entries = []
    current = []

    for line in lines:
        current.append(line)

        grp, _ = extract_group_from_text(line)
        if grp:
            entries.append(" ".join(current))
            current = []

    if current:
        entries.append(" ".join(current))

    return entries

def parse_cell_multi_entries(cell_text):
    text = normalize_text(cell_text)
    if not text:
        return []

    entries = []
    matches = list(re.finditer(GROUP_PATTERNS[0], text, re.IGNORECASE))

    if not matches:
        return []

    last_idx = 0
    current_lesson_text = "Занятие"

    for m in matches:
        group_name = m.group(0)
        start, end = m.start(), m.end()

        chunk = text[last_idx:start]
        chunk = re.sub(r'^[\s,/;|\-]+', '', chunk)
        chunk = re.sub(r'[\s,/;|\-]+$', '', chunk)
        chunk = chunk.strip()

        if chunk:
            current_lesson_text = chunk

        entries.append({
            "group_raw": group_name,
            "remainder": current_lesson_text
        })

        last_idx = end

    return entries

def get_or_create_group(group_raw, group_lookup):
    if not group_raw:
        return None

    display_name = normalize_group_display(group_raw)
    key = compact_key(display_name)

    if key in group_lookup:
        return group_lookup[key]

    for k, g in group_lookup.items():
        if k == key:
            return g

    if AUTO_CREATE_MISSING_GROUP and display_name:
        try:
            existing = Group.query.filter(
                func.upper(func.replace(Group.name, " ", "")) == display_name
            ).first()
            if existing:
                group_lookup[key] = existing
                return existing

            new_group = Group(name=display_name)
            db.session.add(new_group)
            db.session.flush()
            group_lookup[key] = new_group
            current_app.logger.warning("Автоматически создана группа: %s", display_name)
            return new_group
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Не удалось создать группу: %s", display_name)

    return None

def build_group_lookup():
    lookup = {}
    for g in Group.query.all():
        if not g.name:
            continue
        key = compact_key(g.name)
        if key:
            lookup[key] = g
    return lookup