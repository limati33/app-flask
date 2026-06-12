# admin/routes.py
import pdfplumber
import json
import re
from docx import Document
from flask import render_template, redirect, url_for, session, request, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, Admin, Student, Group, Teacher, Schedule, Announcement, Reminder, Assignment, Submission
from datetime import date, datetime, timedelta, time as datetime_time
from . import admin_bp
import uuid
import os
from werkzeug.utils import secure_filename
from fcm import send_new_announcement_push
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
import unicodedata


# ПОДКЛЮЧЕНИЕ ВАШИХ НОВЫХ СЕРВИСОВ:
from .services.ai_client import AI_ENABLED, AI_MODEL
from .services.ai_parser import parse_lesson_with_ai
from .services.pdf_parser import parse_weekly_pdf_to_events
from .services.group_helpers import get_or_create_group, extract_group_from_text
from .services.teacher_helpers import get_or_create_placeholder_teacher
from .services.normalization import normalize_text
from .services.schedule_parser import parse_and_save_schedule
from .services.schedule_parser_plain import parse_schedule_plain

# Опции поведения, специфичные для самих роутов (если остались)
AUTO_CREATE_MISSING_TEACHER = True

# === конфигурация загрузок/папок ===
UPLOAD_FOLDER = "static/avatars"
UPLOAD_FOLDER_SCHEDULE = "static/schedule"
UPLOAD_FOLDER_ANNOUNCEMENTS = "static/announcements"
os.makedirs(UPLOAD_FOLDER_ANNOUNCEMENTS, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_SCHEDULE, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
UPLOAD_FOLDER_TEACHERS = "static/avatars/teachers"
os.makedirs(UPLOAD_FOLDER_TEACHERS, exist_ok=True)

# === поведение парсера (опции) ===
# Если True — при отсутствии найденного преподавателя будет создан "технический" преподаватель
AUTO_CREATE_MISSING_TEACHER = True
AUTO_TEACHER_NAME = "(AUTO) Unknown Teacher"
AUTO_CREATE_MISSING_GROUP = True

# ----- Авторизация -----
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name")
        password = request.form.get("password")
        admin = Admin.query.filter_by(name=name).first()
        if admin and check_password_hash(admin.password, password):
            session["admin"] = admin.name
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Неверные данные")
    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin.login"))

# ----- Главная админ-панель -----
@admin_bp.route("/")
def dashboard():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    return render_template("admin/dashboard.html",
                           Student=Student,
                           Teacher=Teacher,
                           Assignment=Assignment,
                           Submission=Submission)

# ----- Управление студентами -----
# Список студентов
@admin_bp.route("/students")
def students():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    students = Student.query.all()
    return render_template("admin/students.html", students=students)

# Добавить нового студента
@admin_bp.route("/students/add", methods=["GET", "POST"])
def add_student():
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    groups = Group.query.all()

    if request.method == "POST":
        login = request.form.get("login")
        name = request.form.get("name")
        password = generate_password_hash(request.form.get("password"))

        # --- Определяем группу ---
        group_id = request.form.get("group_id")
        new_group_name = request.form.get("new_group")

        if new_group_name:
            existing_group = Group.query.filter_by(name=new_group_name).first()
            if existing_group:
                group_id = existing_group.id
            else:
                new_group = Group(name=new_group_name)
                db.session.add(new_group)
                db.session.commit()
                group_id = new_group.id

        if not group_id:
            flash("Выберите группу или создайте новую!")
            return redirect(url_for("admin.add_student"))

        # --- Аватар ---
        avatar_file = request.files.get("avatar")
        avatar_filename = "default_avatar.png"
        if avatar_file and avatar_file.filename:
            ext = avatar_file.filename.rsplit(".", 1)[-1].lower()
            avatar_filename = f"{uuid.uuid4().hex}.{ext}"
            avatar_path = os.path.join(UPLOAD_FOLDER, avatar_filename)
            avatar_file.save(avatar_path)

        student = Student(
            login=login,
            name=name,
            password=password,
            group_id=group_id,
            avatar=avatar_filename
        )
        db.session.add(student)
        db.session.commit()
        return redirect(url_for("admin.students"))

    return render_template("admin/add_student.html", groups=groups)


# Редактировать студента
@admin_bp.route("/students/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    student = Student.query.get_or_404(id)
    groups = Group.query.all()

    if request.method == "POST":
        student.login = request.form.get("login")
        student.name = request.form.get("name")

        group_id = request.form.get("group_id")
        if group_id:
            student.group_id = group_id

        password = request.form.get("password")
        if password:
            student.password = generate_password_hash(password)

        # --- Аватар ---
        avatar_file = request.files.get("avatar")
        if avatar_file and avatar_file.filename:
            ext = avatar_file.filename.rsplit(".", 1)[-1].lower()
            avatar_filename = f"{uuid.uuid4().hex}.{ext}"
            avatar_path = os.path.join(UPLOAD_FOLDER, avatar_filename)
            avatar_file.save(avatar_path)
            student.avatar = avatar_filename  # <- исправлено на правильное поле

        db.session.commit()
        return redirect(url_for("admin.students"))

    return render_template("admin/edit_student.html", student=student, groups=groups)

# Удалить студента
@admin_bp.route("/students/delete/<int:id>", methods=["POST"])
def delete_student(id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    student = Student.query.get_or_404(id)
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for("admin.students"))

# ----- Управление группами -----
@admin_bp.route("/groups")
def groups():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    groups = Group.query.all()
    return render_template("admin/groups.html", groups=groups)


@admin_bp.route("/group/<int:group_id>/schedule")
def group_schedule(group_id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    group = Group.query.get_or_404(group_id)
    schedule = Schedule.query.filter_by(group_id=group_id).order_by(Schedule.weekday, Schedule.time_start).all()
    return render_template("admin/group_schedule.html", group=group, schedule=schedule)

@admin_bp.route("/group/<int:group_id>/schedule/add", methods=["GET", "POST"])
def add_group_schedule(group_id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    groups = Group.query.all()
    teachers = Teacher.query.all()
    group = Group.query.get(group_id) if group_id != 0 else None

    if request.method == "POST":
        group_id = int(request.form.get("group_id"))

        new_lesson = Schedule(
            group_id=group_id,
            subject=request.form.get("subject"),
            teacher_id=request.form.get("teacher_id"),
            room=request.form.get("room"),
            weekday=int(request.form.get("weekday")),
            time_start=request.form.get("time_start"),
            time_end=request.form.get("time_end")
        )

        db.session.add(new_lesson)
        db.session.commit()

        return redirect(url_for("admin.group_schedule", group_id=group_id))

    return render_template(
        "admin/add_group_schedule.html",
        group=group,
        groups=groups,
        teachers=teachers
    )

@admin_bp.route("/group/<int:group_id>/schedule/edit/<int:schedule_id>", methods=["GET", "POST"])
def edit_group_schedule(group_id, schedule_id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    schedule = Schedule.query.get_or_404(schedule_id)
    group = Group.query.get_or_404(group_id)
    teachers = Teacher.query.all()

    if request.method == "POST":
        schedule.subject = request.form.get("subject")
        schedule.teacher_id = request.form.get("teacher_id")
        schedule.room = request.form.get("room")
        schedule.weekday = int(request.form.get("weekday"))
        schedule.time_start = request.form.get("time_start")
        schedule.time_end = request.form.get("time_end")

        db.session.commit()
        return redirect(url_for("admin.group_schedule", group_id=group.id))  # ← исправлено

    return render_template("admin/edit_group_schedule.html", schedule=schedule, group=group, teachers=teachers)

# ----- Управление расписанием -----
@admin_bp.route("/schedule")
def schedule():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    groups = Group.query.all()
    return render_template("admin/schedule_groups.html", groups=groups)

# -@admin_bp.route("/schedule")
def schedule():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    groups = Group.query.all()
    return render_template("admin/schedule_groups.html", groups=groups)


@admin_bp.route("/schedule/upload", methods=["GET", "POST"])
def upload_schedule():
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    if request.method == "POST":
        file = request.files.get("schedule_file")

        if not file or not file.filename.lower().endswith(".docx"):
            flash("Пожалуйста, загрузите файл .docx", "danger")
            return redirect(request.url)

        parser_mode = request.form.get("parser_mode", "simple")

        filename = secure_filename(file.filename)
        save_path = os.path.join(UPLOAD_FOLDER_SCHEDULE, filename)

        os.makedirs(os.path.dirname(save_path) or UPLOAD_FOLDER_SCHEDULE, exist_ok=True)
        file.save(save_path)

        try:
            # ==============================
            # SIMPLE PARSER
            # ==============================
            if parser_mode == "simple":
                from admin.services.schedule_parser_plain import parse_schedule_plain

                parsed_data, stats = parse_schedule_plain(save_path)

                created = 0
                updated = 0
                skipped = 0

                # Берём любого преподавателя, чтобы не падать на nullable=False
                teacher = Teacher.query.first()

                # Если преподавателей нет вообще — создаём техническую запись
                # ВАЖНО: если у Teacher есть обязательные поля кроме name,
                # заполни их здесь.
                if teacher is None:
                    teacher = Teacher(name="AUTO_IMPORT")
                    db.session.add(teacher)
                    db.session.flush()

                for item in parsed_data:
                    group_name = (item.get("group_raw") or "").strip()
                    subject = (item.get("raw") or "").strip()
                    room = (item.get("room") or "").strip() or None
                    weekday = item.get("weekday")
                    time_start = (item.get("time_start") or "").strip()
                    time_end = (item.get("time_end") or "").strip()

                    if not group_name or not weekday or not time_start or not time_end:
                        skipped += 1
                        continue

                    group = Group.query.filter_by(name=group_name).first()
                    if not group:
                        current_app.logger.warning("Group not found: %s", group_name)
                        skipped += 1
                        continue

                    exists = Schedule.query.filter_by(
                        group_id=group.id,
                        weekday=weekday,
                        time_start=time_start,
                        time_end=time_end,
                        room=room
                    ).first()

                    if exists:
                        exists.subject = subject or exists.subject
                        exists.teacher_id = teacher.id
                        exists.room = room
                        updated += 1
                    else:
                        db.session.add(Schedule(
                            group_id=group.id,
                            subject=subject if subject else "—",
                            teacher_id=teacher.id,
                            room=room,
                            weekday=weekday,
                            time_start=time_start,
                            time_end=time_end
                        ))
                        created += 1

                db.session.commit()

                current_app.logger.info("Simple parser entries: %s", len(parsed_data))
                current_app.logger.info("Simple parser stats: %s", stats)

                flash(
                    f"Простой парсер завершён. "
                    f"Добавлено: {created}, "
                    f"обновлено: {updated}, "
                    f"пропущено: {skipped}.",
                    "success"
                )

                for item in parsed_data[:10]:
                    current_app.logger.info("PARSED: %s", item)

            # ==============================
            # AI PARSER
            # ==============================
            else:
                from admin.services.schedule_parser import parse_and_save_schedule

                stats, preview_items = parse_and_save_schedule(save_path)

                flash(
                    f"Импорт завершён: "
                    f"добавлено {stats['created']}, "
                    f"обновлено {stats['updated']}, "
                    f"пропущено {stats['skipped']}, "
                    f"ошибок {stats['errors']}.",
                    "success"
                )

                current_app.logger.info("Schedule import stats: %s", stats)

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Ошибка при обработке файла расписания")

            flash(
                f"Ошибка при обработке файла: {str(e)}",
                "danger"
            )

        finally:
            if os.path.exists(save_path):
                os.remove(save_path)

        return redirect(url_for("admin.schedule"))

    return render_template("admin/upload_schedule.html")

@admin_bp.route("/test_ai")
def test_ai():
    try:
        from .services.ai_client import AI_CLIENT, AI_MODEL
        from google.genai import types

        response = AI_CLIENT.models.generate_content(
            model=AI_MODEL,
            contents="Ответь только JSON-объектом: {\"ok\": true}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )

        return {
            "success": True,
            "response": response.text
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def extract_json_from_text(text):
    """
    Gemini иногда оборачивает JSON в ```json
    или пишет текст до/после.
    """

    if not text:
        return None

    text = text.strip()

    # ```json ... ```
    code_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    # ищем массив
    array_match = re.search(r"(\[.*\])", text, re.DOTALL)
    if array_match:
        text = array_match.group(1)

    # ищем объект
    object_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if object_match and not text.startswith("["):
        text = object_match.group(1)

    try:
        return json.loads(text)
    except Exception:
        return None

# =========================
# OPTIONAL LEGACY HELPER
# =========================

def save_lesson_to_db(weekday, time_start, time_end, room, group_name, teacher_lastname, subject):
    group = Group.query.filter_by(name=group_name).first()
    if not group:
        print(f"Группа {group_name} не найдена. Пропуск.")
        return

    teacher = Teacher.query.filter(Teacher.name.ilike(f"%{teacher_lastname}%")).first()
    if not teacher:
        print(f"Учитель {teacher_lastname} не найден.")
        return

    exists = Schedule.query.filter_by(
        group_id=group.id,
        weekday=weekday,
        time_start=time_start
    ).first()

    if exists:
        exists.subject = subject
        exists.teacher_id = teacher.id
        exists.room = room
        exists.time_end = time_end
    else:
        # Получаем "заглушку" преподавателя один раз перед циклом
        placeholder_teacher = get_or_create_placeholder_teacher()

        # ... внутри цикла, где создаешь объекты ...
        new_schedule = Schedule(
            group_id=group.id,
            subject=item.get("raw"), # Теперь здесь лежит весь сырой текст
            teacher_id=placeholder_teacher.id, # Привязываем к авто-преподавателю
            room=room_value,
            weekday=current_weekday,
            time_start=time_start,
            time_end=time_end
        )
        db.session.add(new_schedule)

    db.session.commit()

# ----- Управление преподавателями -----
# Список преподавателей
@admin_bp.route("/teachers")
def teachers():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    teachers = Teacher.query.all()
    return render_template("admin/teachers.html", teachers=teachers)


# Добавить преподавателя
@admin_bp.route("/teachers/add", methods=["GET", "POST"])
def add_teacher():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    groups = Group.query.all()

    if request.method == "POST":
        # Читаем логин и пароль из формы
        login = request.form.get("login")
        raw_password = request.form.get("password")

        name = request.form.get("name")
        subject = request.form.get("subject")
        room = request.form.get("room")
        contact = request.form.get("contact")
        curator_group_id = request.form.get("curator_group_id")

        # Хэшируем пароль перед сохранением
        hashed_password = generate_password_hash(raw_password)

        # --- Аватар ---
        avatar_file = request.files.get("avatar")
        avatar_filename = "default_teacher.png"
        if avatar_file and avatar_file.filename:
            ext = avatar_file.filename.rsplit(".", 1)[-1].lower()
            avatar_filename = f"{uuid.uuid4().hex}.{ext}"
            avatar_path = os.path.join(UPLOAD_FOLDER_TEACHERS, avatar_filename)
            avatar_file.save(avatar_path)

        # Добавляем login и password в объект
        teacher = Teacher(
            login=login,
            password=hashed_password,
            name=name,
            subject=subject,
            room=room,
            contact=contact,
            avatar=avatar_filename
        )
        db.session.add(teacher)
        db.session.commit()

        if curator_group_id:
            group = Group.query.get(int(curator_group_id))
            group.curator_id = teacher.id
            db.session.commit()

        return redirect(url_for("admin.teachers"))
    return render_template("admin/add_teacher.html", groups=groups)

# Редактировать преподавателя
@admin_bp.route("/teachers/edit/<int:teacher_id>", methods=["GET", "POST"])
def edit_teacher(teacher_id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    teacher = Teacher.query.get_or_404(teacher_id)
    groups = Group.query.all()

    if request.method == "POST":
        # Обновляем основные данные
        teacher.login = request.form.get("login") # Теперь логин редактируемый
        teacher.name = request.form.get("name")
        teacher.subject = request.form.get("subject")
        teacher.room = request.form.get("room")
        teacher.contact = request.form.get("contact")

        # Обновляем пароль, только если поле не пустое
        new_password = request.form.get("password")
        if new_password:
            teacher.password = generate_password_hash(new_password)

        # --- Аватар ---
        avatar_file = request.files.get("avatar")
        if avatar_file and avatar_file.filename:
            if teacher.avatar and teacher.avatar != "default_teacher.png":
                old_path = os.path.join(UPLOAD_FOLDER_TEACHERS, teacher.avatar)
                if os.path.exists(old_path):
                    os.remove(old_path)

            ext = avatar_file.filename.rsplit(".", 1)[-1].lower()
            avatar_filename = f"{uuid.uuid4().hex}.{ext}"
            avatar_path = os.path.join(UPLOAD_FOLDER_TEACHERS, avatar_filename)
            avatar_file.save(avatar_path)
            teacher.avatar = avatar_filename

        # --- Куратор ---
        curator_group_id = request.form.get("curator_group_id")
        # Сначала убираем его как куратора у всех групп
        for g in groups:
            if g.curator_id == teacher.id:
                g.curator_id = None
        # Назначаем новой группе, если выбрана
        if curator_group_id:
            group = Group.query.get(int(curator_group_id))
            group.curator_id = teacher.id

        db.session.commit()
        flash("Данные преподавателя обновлены", "success")
        return redirect(url_for("admin.teachers"))

    return render_template("admin/edit_teacher.html", teacher=teacher, groups=groups)

# Удалить преподавателя
@admin_bp.route("/teachers/delete/<int:teacher_id>")
def delete_teacher(teacher_id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    teacher = Teacher.query.get_or_404(teacher_id)

    # удаляем аватар, если не дефолтный
    if teacher.avatar and teacher.avatar != "default_teacher.png":
        avatar_path = os.path.join(UPLOAD_FOLDER_TEACHERS, teacher.avatar)
        if os.path.exists(avatar_path):
            os.remove(avatar_path)

    db.session.delete(teacher)
    db.session.commit()
    return redirect(url_for("admin.teachers"))

# ----- Управление объявлениями -----
@admin_bp.route("/announcements")
def announcements():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements.html", announcements=announcements)

# создать
@admin_bp.route("/announcements/create", methods=["GET", "POST"])
def create_announcement():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]

        photo_file = request.files.get("photo")
        photo_filename = None
        if photo_file and photo_file.filename:
            ext = photo_file.filename.rsplit(".", 1)[-1].lower()
            photo_filename = f"{uuid.uuid4().hex}.{ext}"
            path = os.path.join(UPLOAD_FOLDER_ANNOUNCEMENTS, photo_filename)
            photo_file.save(path)

        new_announcement = Announcement(
            title=title,
            content=content,
            author=session.get("admin"),
            photo_filename=photo_filename
        )
        db.session.add(new_announcement)
        db.session.commit()

        if current_app.config.get('FCM_ENABLED', False):
            resp = send_new_announcement_push(title, content)
            if resp:
                current_app.logger.info("FCM push отправлен, id: %s", resp)
                flash("Объявление добавлено и пуш отправлен!", "success")
            else:
                current_app.logger.warning("Push отправка вернула None/ошибку")
                flash("Объявление добавлено, но не удалось отправить push (см. консоль).", "warning")
        else:
            current_app.logger.info("Push уведомления отключены на сервере")
            flash("Объявление добавлено! (push отключены на сервере)", "info")

        return redirect(url_for("admin.announcements"))
    return render_template("admin/add_announcement.html")

# редактировать
@admin_bp.route("/announcements/<int:id>/edit", methods=["GET", "POST"])
def edit_announcement(id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    announcement = Announcement.query.get_or_404(id)

    if request.method == "POST":
        announcement.title = request.form["title"]
        announcement.content = request.form["content"]

        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename:
            # удалить старое фото
            if announcement.photo_filename:
                old_path = os.path.join(UPLOAD_FOLDER_ANNOUNCEMENTS, announcement.photo_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)

            ext = photo_file.filename.rsplit(".", 1)[-1].lower()
            photo_filename = f"{uuid.uuid4().hex}.{ext}"
            path = os.path.join(UPLOAD_FOLDER_ANNOUNCEMENTS, photo_filename)
            photo_file.save(path)
            announcement.photo_filename = photo_filename

        db.session.commit()
        flash("Объявление обновлено!", "success")
        return redirect(url_for("admin.announcements"))

    return render_template("admin/edit_announcement.html", announcement=announcement)


# удалить
@admin_bp.route("/announcements/<int:id>/delete", methods=["POST"])
def delete_announcement(id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    announcement = Announcement.query.get_or_404(id)

    # удалить фото, если есть
    if announcement.photo_filename:
        photo_path = os.path.join(UPLOAD_FOLDER_ANNOUNCEMENTS, announcement.photo_filename)
        if os.path.exists(photo_path):
            os.remove(photo_path)

    db.session.delete(announcement)
    db.session.commit()
    flash("Объявление удалено!", "danger")
    return redirect(url_for("admin.announcements"))

# напоминание
# =========================
# helpers for PDF schedule
# =========================
SEMESTER_START_DATE = date(2025, 9, 1)  # старт учебного года для перевода недель в даты

# =========================
# reminders
# =========================
@admin_bp.route("/reminders", methods=["GET", "POST"])
def reminders():
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    students = Student.query.order_by(Student.name).all()
    groups = Group.query.order_by(Group.name).all()
    reminders = Reminder.query.order_by(Reminder.date.desc()).all()

    if request.method == "POST":
        title = clean_text(request.form.get("title"))
        date_str = request.form.get("date")
        time_str = clean_text(request.form.get("time")) or None
        note = clean_text(request.form.get("note")) or None
        type_ = clean_text(request.form.get("type")) or None
        student_id = request.form.get("student_id") or None
        group_id = request.form.get("group_id") or None

        if not title or not date_str:
            flash("Название и дата обязательны.", "danger")
            return redirect(url_for("admin.reminders"))

        if not student_id and not group_id:
            flash("Нужно выбрать студента или группу.", "danger")
            return redirect(url_for("admin.reminders"))

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Некорректная дата.", "danger")
            return redirect(url_for("admin.reminders"))

        try:
            if group_id:
                group = Group.query.get(int(group_id))
                if not group:
                    flash("Группа не найдена.", "danger")
                    return redirect(url_for("admin.reminders"))

                if not group.students:
                    flash("В выбранной группе нет студентов.", "warning")
                    return redirect(url_for("admin.reminders"))

                for s in group.students:
                    exists = Reminder.query.filter_by(
                        student_id=s.id,
                        group_id=group.id,
                        title=title,
                        date=date_obj
                    ).first()
                    if exists:
                        continue

                    db.session.add(Reminder(
                        student_id=s.id,
                        group_id=group.id,
                        title=title,
                        date=date_obj,
                        time=time_str,
                        type=type_,
                        note=note
                    ))
            else:
                student = Student.query.get(int(student_id))
                if not student:
                    flash("Студент не найден.", "danger")
                    return redirect(url_for("admin.reminders"))

                exists = Reminder.query.filter_by(
                    student_id=student.id,
                    group_id=student.group_id,
                    title=title,
                    date=date_obj
                ).first()
                if not exists:
                    db.session.add(Reminder(
                        student_id=student.id,
                        group_id=student.group_id,
                        title=title,
                        date=date_obj,
                        time=time_str,
                        type=type_,
                        note=note
                    ))

            db.session.commit()
            flash("Напоминание добавлено!", "success")
            return redirect(url_for("admin.reminders"))

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Ошибка при добавлении напоминания")
            flash(f"Ошибка: {str(e)}", "danger")
            return redirect(url_for("admin.reminders"))

    return render_template("admin/reminders.html", students=students, groups=groups, reminders=reminders)


@admin_bp.route("/upload_reminder", methods=["GET", "POST"])
def upload_reminder():
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    groups = Group.query.order_by(Group.name).all()

    if request.method == "POST":
        if "pdf_file" not in request.files:
            flash("Файл не найден в запросе.", "danger")
            return redirect(url_for("admin.reminders"))

        file = request.files["pdf_file"]

        if file.filename == "":
            flash("Файл не выбран.", "danger")
            return redirect(url_for("admin.reminders"))

        if not file.filename.lower().endswith(".pdf"):
            flash("Пожалуйста, загрузите PDF-файл.", "danger")
            return redirect(url_for("admin.reminders"))

        # group_id не обязателен: PDF содержит все группы
        group_id = request.form.get("group_id")
        only_group = None
        if group_id:
            only_group = Group.query.get(int(group_id))
            if not only_group:
                flash("Выбранная группа не найдена.", "danger")
                return redirect(url_for("admin.reminders"))

        try:
            events = parse_weekly_pdf_to_events(file.stream)

            if only_group:
                events = [e for e in events if e["group_id"] == only_group.id]

            if not events:
                flash("Не удалось распознать события из PDF.", "warning")
                return redirect(url_for("admin.reminders"))

            created, skipped = save_pdf_events_as_reminders(events)

            flash(
                f"PDF обработан. Добавлено: {created}. Пропущено/дубликатов: {skipped}.",
                "success"
            )
            return redirect(url_for("admin.reminders"))

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Ошибка при чтении PDF графика")
            flash(f"Ошибка при чтении PDF: {str(e)}", "danger")
            return redirect(url_for("admin.reminders"))

    return render_template("admin/reminders.html", groups=groups)

# ----- Мониторинг заданий и ответов (Для Админа) -----

# Список всех заданий (отработок) от всех учителей
@admin_bp.route("/all_assignments")
def all_assignments():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    assignments = Assignment.query.order_by(Assignment.created_at.desc()).all()
    return render_template("admin/all_assignments.html", assignments=assignments)

# Список всех ответов студентов (submissions)
@admin_bp.route("/all_submissions")
def all_submissions():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    submissions = Submission.query.order_by(Submission.submitted_at.desc()).all()
    return render_template("admin/all_submissions.html", submissions=submissions)

# Удаление задания админом (если учитель накосячил)
@admin_bp.route("/assignment/delete/<int:id>", methods=["POST"])
def delete_assignment(id):
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    task = Assignment.query.get_or_404(id)
    # При удалении задания удалятся и все submissions (если настроен cascade)
    # или их нужно удалить вручную:
    Submission.query.filter_by(assignment_id=id).delete()
    db.session.delete(task)
    db.session.commit()
    flash("Задание и все ответы удалены", "danger")
    return redirect(url_for("admin.all_assignments"))
