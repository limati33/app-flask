# admin/ routes.py
from flask import render_template, redirect, url_for, session, request, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, Admin, Student, Group, Teacher, Schedule, Announcement, Reminder, Assignment, Submission
from datetime import date, datetime, timedelta
from . import admin_bp
import uuid
import os
from werkzeug.utils import secure_filename
from fcm import send_new_announcement_push

UPLOAD_FOLDER = "static/avatars"
UPLOAD_FOLDER_ANNOUNCEMENTS = "static/announcements"
os.makedirs(UPLOAD_FOLDER_ANNOUNCEMENTS, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
UPLOAD_FOLDER_TEACHERS = "static/avatars/teachers"
os.makedirs(UPLOAD_FOLDER_TEACHERS, exist_ok=True)

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
    
    group = Group.query.get_or_404(group_id)
    teachers = Teacher.query.all()
    
    if request.method == "POST":
        subject = request.form.get("subject")
        teacher_id = request.form.get("teacher_id")
        room = request.form.get("room")
        weekday = int(request.form.get("weekday"))
        time_start = request.form.get("time_start")
        time_end = request.form.get("time_end")
        
        new_lesson = Schedule(
            group_id=group.id,
            subject=subject,
            teacher_id=teacher_id,
            room=room,
            weekday=weekday,
            time_start=time_start,
            time_end=time_end
        )
        db.session.add(new_lesson)
        db.session.commit()
        return redirect(url_for("admin.group_schedule", group_id=group.id))  # ← исправлено
    
    return render_template("admin/add_group_schedule.html", group=group, teachers=teachers)

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
                print(f"FCM push отправлен, id: {resp}")
                flash("Объявление добавлено и пуш отправлен!", "success")
            else:
                print("Push отправка вернула None/ошибку")
                flash("Объявление добавлено, но не удалось отправить push (см. консоль).", "warning")
        else:
            print("Push уведомления отключены на сервере")
            flash("Объявление добавлено! (push отключены на сервере)", "info")

        return redirect(url_for("admin.announcements"))
        flash("Объявление добавлено!", "success")
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
@admin_bp.route("/reminders", methods=["GET", "POST"])
def reminders():
    if "admin" not in session:
        return redirect(url_for("admin.login"))

    students = Student.query.all()
    groups = Group.query.all()
    reminders = Reminder.query.order_by(Reminder.date.desc()).all()

    if request.method == "POST":
        title = request.form.get("title")
        date_str = request.form.get("date")
        time_str = request.form.get("time")  # оставляем как строку
        note = request.form.get("note")
        type_ = request.form.get("type")
        student_id = request.form.get("student_id")
        group_id = request.form.get("group_id")

        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

        if group_id:  # создаём напоминания для всех студентов группы
            group = Group.query.get(int(group_id))
            for s in group.students:
                new_r = Reminder(
                    title=title,
                    date=date_obj,
                    time=time_str,   # сохраняем строкой
                    type=type_,
                    note=note,
                    student_id=s.id
                )
                db.session.add(new_r)
        else:  # напоминание конкретному студенту
            new_r = Reminder(
                title=title,
                date=date_obj,
                time=time_str,   # сохраняем строкой
                type=type_,
                note=note,
                student_id=int(student_id) if student_id else None
            )
            db.session.add(new_r)

        db.session.commit()
        flash("Напоминание добавлено!", "success")
        return redirect(url_for("admin.reminders"))

    return render_template("admin/reminders.html", students=students, groups=groups, reminders=reminders)


# ----- Мониторинг заданий и ответов (Для Админа) -----

# Список всех заданий (отработок) от всех учителей
@admin_bp.route("/all_assignments")
def all_assignments():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    # Получаем все задания, сортируя по дате создания
    assignments = Assignment.query.order_by(Assignment.created_at.desc()).all()
    return render_template("admin/all_assignments.html", assignments=assignments)

# Список всех ответов студентов (submissions)
@admin_bp.route("/all_submissions")
def all_submissions():
    if "admin" not in session:
        return redirect(url_for("admin.login"))
    # Показываем вообще всё: кто сдал, когда, какой файл
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