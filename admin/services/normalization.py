import re
import unicodedata  # <-- Добавьте эту строку

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

def compact_key(text):
    """
    Компактный ключ для сравнения:
    - upper
    - Ё -> Е
    - удаляем всё, кроме букв/цифр/дефиса/точки
    - убираем пробелы
    """
    text = normalize_text(text).upper().replace("Ё", "Е")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^A-ZА-Я0-9\-\.]", "", text)
    return text

def normalize_group_display(name):
    if not name:
        return ""
    s = normalize_text(name).upper().replace("Ё", "Е")
    s = re.sub(r"\s+", "", s)
    return s

def normalize_time_string(s):
    s = normalize_text(s).replace(" ", "")

    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
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

def extract_time_pair_from_text(text):
    if not text:
        return None

    text = normalize_text(text)

    patterns = [
        r"(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})",
        r"(\d{3,4})\s*[-–—]\s*(\d{3,4})",
        r"(\d{4})\s*[-–—]\s*(\d{4})",
        r"(\d{1,2}:\d{2})\s*(?:до|по)\s*(\d{1,2}:\d{2})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return normalize_time_string(m.group(1)), normalize_time_string(m.group(2))

    return None

def normalize_subject_key(text):
    s = normalize_text(text).upper()
    s = s.replace("Р.О", "РО")
    s = s.replace("Р. О", "РО")
    s = s.replace("О.Н", "ОН")
    s = s.replace("О. Н", "ОН")
    s = re.sub(r"\s+", "", s)
    return s

def clean_text(value):
    if value is None:
        return ""
    s = str(value)
    s = s.replace("\xa0", " ")
    s = s.replace("−", "-").replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def normalize_group_name(name: str) -> str:
    if not name:
        return ""
    s = clean_text(name)
    s = unicodedata.normalize("NFC", s)
    s = s.strip(".,;:()[]\"'«»")
    return s.upper()
