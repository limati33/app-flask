import uuid
from werkzeug.security import generate_password_hash

# Импорт моделей из корня
from models import db, Teacher

# Импорт нормализации
from .normalization import compact_key, normalize_text, compact_key

# Настройка имени здесь
AUTO_TEACHER_NAME = "(AUTO) Unknown Teacher"

TEACHER_ALIASES = [
    "МАХА",
    "НӘСІЛ",
    "НАСИЛ",
    "ІЛЯС",
    "ИЛЬЯС",
    "ЖЕҢІС",
    "ЖЕНИС",
    "ДЮСЕМ",
    "ОМАРОВА",
    "АКИШЕВА",
    "АХМЕТОВА",
    "БАЙСЕЙТОВА",
    "БОРАНБАЕВА",
    "МҰҚАШЕВА",
    "МУКАШЕВА",
    "ШАМШИЕВА",
    "ТЕМЕНОВ",
    "МАЛАЕВА",
    "КАСЕНОВ",
    "ДЖУМАГАЗИЕВА",
    "СЕЙТОВ",
    "АКИМОВ",
    "ЕРГЕШ",
    "ҚАЙРАТ",
    "КАЙРАТ",
    "БЕРДИБАЕВА",
    "НУРБОСЫН",
    "ТУРСЫНБАЕВА",
    "СӘЛІМГЕРЕЙ",
    "САЛИМГЕРЕЙ",
    "АНАРҚҰЛ",
    "АНАРКУЛ",
    "АҒАЙДАРОВА",
    "АГАЙДАРОВА",
    "БОРАНБАЕВА",
    "БАТЫРБЕКОВ",
    "КАПТАГАЕВА",
    "САПАГОВА",
    "ПРОСКУРИН",
    "СЕЙТКАЗИЕВА",
    "ДУЙСЕКЕЕВ",
    "ТУЛЕПБЕРГЕНОВА",
    "АҒАЙДАРОВА",
    "МЕНДИГАЛИЕВА",
    "БИКЕНОВА",
    "СОНУРОВА",
    "ШУКИРБЕКОВА",
    "ЕРЖАНҚЫЗЫ",
    "ЕРЖАНКЫЗЫ",
    "МЕРИКЕНОВА",
    "НУРБЕКОВ",
    "БЕГМЕН",
    "КЕНБАЕВ",
    "МУСАБЕК",
]

def build_teacher_lookup():
    """
    Ключи:
    compact_key(вариант имени/фамилии/первых слов) -> Teacher
    """
    lookup = {}

    for t in Teacher.query.all():
        if not t.name:
            continue

        raw = normalize_text(t.name)
        parts = raw.split()

        variants = set()
        variants.add(compact_key(raw))

        if parts:
            variants.add(compact_key(parts[0]))

        if len(parts) >= 2:
            variants.add(compact_key(" ".join(parts[:2])))

        if len(parts) >= 3:
            variants.add(compact_key(" ".join(parts[:3])))

        for v in variants:
            if v:
                lookup.setdefault(v, t)

    return lookup

def find_teacher_alias(text):
    """
    Ищет преподавателя по короткому алиасу:
    "Маха" -> Teacher(name like %Маха%)
    """
    raw = normalize_text(text).upper()
    raw_key = compact_key(raw)

    for alias in sorted(TEACHER_ALIASES, key=len, reverse=True):
        alias_key = compact_key(alias)
        if alias_key and alias_key in raw_key:
            teacher = Teacher.query.filter(Teacher.name.ilike(f"%{alias}%")).first()
            if teacher:
                return teacher, alias

    return None, None

def find_teacher_in_text(text, teacher_lookup):
    """
    Пытается найти преподавателя по целой строке:
    - сначала по уже собранному lookup
    - потом по подстроке
    """
    raw = normalize_text(text)
    if not raw:
        return None, None

    raw_key = compact_key(raw)
    tokens = raw.split()

    # 1) точные/почти точные варианты из первых 1..4 слов
    for window in (4, 3, 2, 1):
        if len(tokens) < window:
            continue
        candidate = " ".join(tokens[:window])
        key = compact_key(candidate)
        if key in teacher_lookup:
            return teacher_lookup[key], candidate

    # 2) подстрока по словарю
    sorted_items = sorted(teacher_lookup.items(), key=lambda kv: len(kv[0]), reverse=True)
    for key, teacher in sorted_items:
        if key and key in raw_key:
            return teacher, teacher.name

    return None, None

def get_or_create_placeholder_teacher():
    teacher = Teacher.query.filter_by(name=AUTO_TEACHER_NAME).first()
    if teacher:
        return teacher

    try:
        ph_login = f"auto_{uuid.uuid4().hex[:8]}"
        ph_pass = generate_password_hash("auto_password")
        teacher = Teacher(
            login=ph_login,
            password=ph_pass,
            name=AUTO_TEACHER_NAME,
            subject=None,
            room=None,
            contact=None,
            avatar="default_teacher.png",
        )
        db.session.add(teacher)
        db.session.commit()
        current_app.logger.warning("Создан технический преподаватель: %s", AUTO_TEACHER_NAME)
        return teacher
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Не удалось создать технического преподавателя")
        return None
