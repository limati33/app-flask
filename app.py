# app.py
from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from datetime import datetime, timedelta, date
import os
from calendar import monthcalendar, day_name, month_name
from collections import defaultdict
from urllib.parse import urljoin
from models import db, Student, Group, Schedule, Announcement, Reminder, Teacher, Assignment, AssignmentFile, Submission
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import json
from fcm import init_app as init_fcm
from werkzeug.utils import secure_filename


app = Flask(__name__)

# Конфиг
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///college.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'supersecretkey123')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'supersecretkey123')
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
app.config["JWT_HEADER_NAME"] = "Authorization"
app.config["JWT_HEADER_TYPE"] = "Bearer"

# Загрузка + ограничение размера (например 30MB)
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'static/submissions')
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  # 300 MB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализация расширений
db.init_app(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)
init_fcm(app)

app.config['AVATAR_UPLOAD_FOLDER'] = os.environ.get('AVATAR_UPLOAD_FOLDER', 'static/uploads/avatars')
os.makedirs(app.config['AVATAR_UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'docx', 'zip', 'mp4', 'webm'}

# Регистрируем блюпринты после инициализации (чтобы они могли безопасно использовать db и т.д.)
from teacher.teacher_routes import teacher_bp
app.register_blueprint(teacher_bp)

from admin import admin_bp
app.register_blueprint(admin_bp, url_prefix="/admin")

# ---- Вспомогательные функции ----
def _get_jwt_student_id():
    """
    Возвращает student_id как int из токена или None, если невалиден.
    Используем повсеместно в защищённых роутингах.
    """
    identity = get_jwt_identity()
    if identity is None:
        return None
    try:
        return int(identity)
    except (ValueError, TypeError):
        return None

def get_current_student():
    sid = _get_jwt_student_id()
    if sid is None:
        return None
    return Student.query.get(sid)
@app.route("/uploads/avatars/<path:filename>")
def uploaded_avatar(filename):
    return send_from_directory(app.config["AVATAR_UPLOAD_FOLDER"], filename)
@app.route("/healthz")
def health():
    return "ok"

# --- Веб-часть (оставляем как есть) ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_input = request.form.get("login")
        password = request.form.get("password")

        # 1. Проверяем, не студент ли это
        student = Student.query.filter_by(login=login_input).first()
        if student and check_password_hash(student.password, password):
            session.clear() # Очищаем старую сессию
            session['student_id'] = student.id
            session['role'] = 'student'
            return redirect(url_for("profile"))

        # 2. Если не студент, проверяем, не учитель ли это
        teacher = Teacher.query.filter_by(login=login_input).first()
        if teacher and check_password_hash(teacher.password, password):
            session.clear()
            session['teacher_id'] = teacher.id
            session['role'] = 'teacher'
            # Перенаправляем в личный кабинет учителя (Blueprint 'teacher')
            return redirect(url_for("teacher.dashboard"))

        # 3. Если никто не подошел
        error = "Неверный логин или пароль"
        return render_template("login.html", error=error)

    return render_template("login.html", error=None)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if 'student_id' not in session:
        return redirect(url_for("login"))

    student = Student.query.get_or_404(session['student_id'])
    group_students = Student.query.filter_by(group_id=student.group_id).all()

    if request.method == "POST":
        new_password = request.form.get("new_password")
        if new_password:
            student.password = generate_password_hash(new_password)
            db.session.commit()
            return redirect(url_for("profile"))

    return render_template("profile.html", student=student, group_students=group_students)

@app.route("/logout")
def logout():
    session.pop('student_id', None)
    return redirect(url_for("login"))

@app.route("/schedule")
def schedule():
    if 'student_id' not in session:
        return redirect(url_for("login"))

    student = Student.query.get(session['student_id'])
    group = student.group

    today = date.today()

    WEEKDAYS_RU = {
        1: "Понедельник",
        2: "Вторник",
        3: "Среда",
        4: "Четверг",
        5: "Пятница",
        6: "Суббота",
        7: "Воскресенье"
    }

    days = []
    for offset, label in [(-1, "Вчера"), (0, "Сегодня"), (1, "Завтра")]:
        target_date = today + timedelta(days=offset)
        weekday = target_date.isoweekday()
        weekday_name = WEEKDAYS_RU[weekday]

        schedule_list = []
        if group:
            schedule_list = Schedule.query.filter_by(
                group_id=group.id, weekday=weekday
            ).order_by(Schedule.time_start).all()

        days.append({
            "label": label,
            "date": target_date,
            "weekday_name": weekday_name,
            "schedule": schedule_list
        })

    return render_template("schedule.html", days=days)

@app.route("/announcements")
def announcements():
    if 'student_id' not in session:
        return redirect(url_for("login"))

    announcements_list = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("announcements.html", announcements=announcements_list)

@app.route("/calendar", methods=["GET", "POST"])
def calendar():
    if 'student_id' not in session:
        return redirect(url_for("login"))

    student = Student.query.get(session['student_id'])
    today = date.today()

    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)

    if request.method == "POST":
        title = request.form.get("title")
        date_str = request.form.get("date")
        time_str = request.form.get("time")
        type_ = request.form.get("type")
        note = request.form.get("note")
        if title and date_str:
            try:
                event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                new_reminder = Reminder(
                    student_id=student.id,
                    title=title,
                    date=event_date,
                    time=time_str if time_str else None,
                    type=type_ if type_ else None,
                    note=note if note else None
                )
                db.session.add(new_reminder)
                db.session.commit()
                return redirect(url_for("calendar", year=event_date.year, month=event_date.month))
            except ValueError:
                flash("Неверный формат даты", "error")

    reminders = Reminder.query.filter_by(student_id=student.id).all()

    return render_template("calendar.html",
                           reminders=reminders,
                           today=today,
                           year=year,
                           month=month)

@app.route("/student/<int:student_id>/settings", methods=["GET", "POST"])
def student_settings(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == "POST":
        new_password = request.form.get("new_password")
        if new_password:
            student.password = generate_password_hash(new_password)
            db.session.commit()
            flash("Пароль обновлён!", "success")
            return redirect(url_for("student_settings", student_id=student.id))
    return render_template("settings.html", student=student)

@app.route("/teachers")
def teachers():
    if "student_id" not in session:
        return redirect(url_for("login"))
    teachers = Teacher.query.all()
    return render_template("teachers.html", teachers=teachers)

@app.route("/")
def index():
    if 'student_id' in session:
        return redirect(url_for("profile"))
    return redirect(url_for("login"))

# --- API: Логин (возвращает JWT-токен) ---
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    login_input = data.get("login")
    password = data.get("password")
    student = Student.query.filter_by(login=login_input).first()
    if student and check_password_hash(student.password, password):
        # identity => строка, чтобы совместимо с JWT v4+
        access_token = create_access_token(identity=str(student.id))
        return jsonify({"token": access_token})
    return jsonify({"message": "Неверный логин или пароль"}), 401

# --- API: Профиль ---
@app.route("/api/profile", methods=["GET"])
@jwt_required()
def api_profile():
    try:
        student_id = _get_jwt_student_id()
        if student_id is None:
            return jsonify({"message": "Invalid token identity"}), 401

        student = Student.query.get_or_404(student_id)
        group_students = Student.query.filter_by(group_id=student.group_id).all()

        # === Функция формирования полного URL аватара ===
        def get_avatar_url(avatar_path: str | None) -> str | None:
            if not avatar_path:
                return None

            avatar = avatar_path.strip().replace("\\", "/")

            if avatar.startswith(("http://", "https://")):
                return avatar

            if avatar.startswith("/"):
                return urljoin(request.host_url, avatar.lstrip("/"))

            return urljoin(request.host_url, f"uploads/avatars/{avatar}")

        # Твой профиль
        profile_data = {
            "id": student.id,
            "name": student.name,
            "avatar": get_avatar_url(student.avatar),
            "login": student.login,
            "group": student.group.name if student.group else None,
            # === Главное изменение здесь ===
            "group_students": [
                {
                    "id": s.id,
                    "name": s.name,
                    "avatar": get_avatar_url(s.avatar)
                }
                for s in group_students
            ],
            # Куратор (добавляем, чтобы показывался на профиле)
            "curator": None
        }

        if student.group and student.group.curator:
            curator = student.group.curator
            profile_data["curator"] = {
                "id": curator.id,
                "name": curator.name,
                "avatar": get_avatar_url(curator.avatar)
            }

        app.logger.debug(f"/api/profile -> profile_data: {profile_data}")
        return jsonify(profile_data)

    except Exception as e:
        app.logger.exception("Error in /api/profile")
        return jsonify({"message": f"Server error: {str(e)}"}), 500

@app.route("/api/profile/avatar", methods=["POST"])
@jwt_required()
def api_upload_profile_avatar():
    student_id = _get_jwt_student_id()
    if student_id is None:
        return jsonify({"success": False, "message": "Invalid token identity"}), 401

    student = Student.query.get(student_id)
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    if "avatar" not in request.files:
        return jsonify({"success": False, "message": "Файл не передан"}), 400

    file = request.files["avatar"]

    if not file.filename:
        return jsonify({"success": False, "message": "Пустое имя файла"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Недопустимый формат файла"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower()
    filename = secure_filename(f"student_{student.id}_{int(datetime.utcnow().timestamp())}.{ext}")
    save_path = os.path.join(app.config["AVATAR_UPLOAD_FOLDER"], filename)
    file.save(save_path)

    student.avatar = filename
    db.session.commit()

    avatar_url = urljoin(request.host_url, f"uploads/avatars/{filename}")

    return jsonify({
        "success": True,
        "message": "Фото профиля обновлено",
        "avatar": avatar_url
    })

# --- API: Расписание ---
@app.route("/api/schedule", methods=["GET"])
@jwt_required()
def api_schedule():
    student_id = _get_jwt_student_id()
    if student_id is None:
        return jsonify({"message": "Invalid token identity"}), 401

    student = Student.query.get(student_id)
    if not student:
        return jsonify({"message": "Student not found"}), 404

    group = student.group
    today = date.today()

    WEEKDAYS_RU = {
        1: "Понедельник",
        2: "Вторник",
        3: "Среда",
        4: "Четверг",
        5: "Пятница",
        6: "Суббота",
        7: "Воскресенье"
    }

    days = []
    for offset, label in [(-1, "Вчера"), (0, "Сегодня"), (1, "Завтра")]:
        target_date = today + timedelta(days=offset)
        weekday = target_date.isoweekday()
        weekday_name = WEEKDAYS_RU[weekday]

        schedule_list = []
        if group:
            schedule_list = Schedule.query.filter_by(
                group_id=group.id, weekday=weekday
            ).order_by(Schedule.time_start).all()

        serialized_schedule = [{
            "id": sch.id,
            "subject": sch.subject,
            "time_start": sch.time_start,
            "time_end": sch.time_end,
            "teacher": sch.teacher.name if sch.teacher else None,
            "room": sch.room if sch.room else None,
            "group_id": sch.group_id,
            "teacher_id": sch.teacher_id,
            "weekday": sch.weekday
        } for sch in schedule_list]

        days.append({
            "label": label,
            "date": target_date.isoformat(),
            "weekday_name": weekday_name,
            "schedule": serialized_schedule
        })

    return jsonify({"days": days})

# --- API: Объявления ---
@app.route("/api/announcements", methods=["GET"])
@jwt_required()
def api_announcements():
    student_id = _get_jwt_student_id()
    if student_id is None:
        return jsonify({"message": "Invalid token identity"}), 401

    announcements_list = Announcement.query.order_by(Announcement.created_at.desc()).all()
    serialized_announcements = []
    for ann in announcements_list:
        photo_url = None
        if ann.photo_filename:
            # абсолютный URL (например http://10.49.216.60:5000/uploads/photo.jpg)
            photo_url = request.host_url.rstrip("/") + "/static/announcements/" + ann.photo_filename

        serialized_announcements.append({
            "id": ann.id,
            "title": ann.title,
            "content": ann.content,
            "created_at": ann.created_at.isoformat(),
            "photo_url": photo_url
        })

    return jsonify({"announcements": serialized_announcements})

@app.route("/api/announcements", methods=["POST"])
@jwt_required()
def api_add_announcement():
    data = request.get_json()
    title = data.get("title")
    content = data.get("content")
    
    if not title or not content:
        return jsonify({"message": "Не хватает данных"}), 400

    new_ann = Announcement(title=title, content=content, created_at=datetime.utcnow())
    db.session.add(new_ann)
    db.session.commit()

    # Отправка уведомления
    send_new_announcement_push(title, content)

    return jsonify({"message": "Объявление добавлено", "id": new_ann.id}), 201

# --- API: Напоминания (календарь) ---
@app.route("/api/reminders", methods=["GET", "POST"])
@jwt_required()
def api_reminders():
    student_id = _get_jwt_student_id()
    if student_id is None:
        return jsonify({"message": "Invalid token identity"}), 401

    if request.method == "GET":
        reminders = Reminder.query.filter_by(student_id=student_id).all()
        serialized_reminders = [{
            "id": rem.id,
            "title": rem.title,
            "date": rem.date.isoformat(),
            "time": rem.time,
            "type": rem.type,
            "note": rem.note
        } for rem in reminders]
        return jsonify({"reminders": serialized_reminders})

    elif request.method == "POST":
        data = request.get_json()
        title = data.get("title")
        date_str = data.get("date")
        time_str = data.get("time")
        type_ = data.get("type")
        note = data.get("note")
        if title and date_str:
            try:
                event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                new_reminder = Reminder(
                    student_id=student_id,
                    title=title,
                    date=event_date,
                    time=time_str,
                    type=type_,
                    note=note
                )
                db.session.add(new_reminder)
                db.session.commit()
                return jsonify({"message": "Напоминание добавлено", "id": new_reminder.id}), 201
            except ValueError:
                return jsonify({"message": "Неверный формат даты"}), 400
        return jsonify({"message": "Недостаточно данных"}), 400

# --- API: Преподаватели ---
@app.route("/api/teachers", methods=["GET"])
@jwt_required()
def api_teachers():
    student_id = _get_jwt_student_id()
    if student_id is None:
        return jsonify({"message": "Invalid token identity"}), 401

    teachers = Teacher.query.all()
    serialized_teachers = []

    for t in teachers:
        clean_avatar_url = None

        # Восстанавливаем генерацию ссылок на аватарки
        if t.avatar:
            avatar_file = os.path.basename(t.avatar.replace("\\", "/"))
            clean_avatar_url = url_for(
                "static",
                filename=f"avatars/teachers/{avatar_file}",
                _external=True
            )

        serialized_teachers.append({
            "id": t.id,
            "name": t.name,
            "subject": t.subject,
            "contact": t.contact,
            "room": t.room,  # КРИТИЧЕСКИ ВАЖНО: возвращаем кабинет!
            "avatar": clean_avatar_url,
            "avatar_url": clean_avatar_url
        })

    return jsonify({"teachers": serialized_teachers})

@app.route('/api/change_password', methods=['POST'])
@jwt_required()
def change_password():
    data = request.json
    new_password = data.get("new_password")

    student_id = _get_jwt_student_id()
    if student_id is None:
        return jsonify({"error": "Unauthorized"}), 401

    student = Student.query.get(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    if not new_password or len(new_password) < 4:
        return jsonify({"error": "Пароль слишком короткий"}), 400

    student.password = generate_password_hash(new_password)
    db.session.commit()

    return jsonify({"message": "Пароль успешно изменён"})

# --- API: Задания (Отработки) ---
@app.route("/api/assignments/my", methods=["GET"])
@jwt_required()
def get_my_assignments():
    student_id = _get_jwt_student_id()
    if student_id is None:
        return jsonify({
            "success": False,
            "message": "Invalid token identity"
        }), 401

    student = Student.query.get(student_id)
    if not student:
        return jsonify({
            "success": False,
            "message": "Студент не найден"
        }), 404

    assignments = (
        Assignment.query
        .filter_by(group_id=student.group_id)
        .order_by(Assignment.deadline.asc())
        .all()
    )

    result = []

    for task in assignments:
        # 📎 файлы задания
        attachments = []
        files_q = AssignmentFile.query.filter_by(assignment_id=task.id).all()
        for af in files_q:
            attachments.append({
                "filename": af.filename,
                "url": urljoin(
                    request.host_url,
                    f"static/uploads/assignments/{task.id}_{af.filename}"
                )
            })

        submission = Submission.query.filter_by(
            assignment_id=task.id,
            student_id=student.id
        ).first()

        status = submission.status if submission else "pending"

        # ❗ принятые не показываем
        if status == "accepted":
            continue

        deadline_str = (
            task.deadline.strftime("%Y-%m-%d %H:%M")
            if task.deadline else None
        )

        result.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "deadline": deadline_str,
            "status": status,                     # pending / rejected
            "teacher_name": task.teacher.name if task.teacher else "Учитель",
            "attachments": attachments,

            # 👇 важно для Android
            "teacher_comment": (
                submission.teacher_comment
                if submission and status == "rejected"
                else None
            )
        })

    return jsonify({
        "success": True,
        "assignments": result
    })

def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXTENSIONS

@app.route("/api/submissions", methods=["POST"])
@jwt_required()
def submit_assignment():
    current_user_id = _get_jwt_student_id()
    if current_user_id is None:
        return jsonify({"success": False, "message": "Invalid token identity"}), 401

    assignment_id_raw = request.form.get("assignment_id") or request.form.get("id")
    answer_text = request.form.get("answer_text") or request.form.get("text")

    if not assignment_id_raw:
        return jsonify({"success": False, "message": "Нет ID задания"}), 400

    try:
        assignment_id = int(assignment_id_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Неверный ID задания"}), 400

    # Проверим, существует ли задание
    assignment = Assignment.query.get(assignment_id)
    if not assignment:
        return jsonify({"success": False, "message": "Задание не найдено"}), 404

    SUBMISSION_FOLDER = app.config['UPLOAD_FOLDER']
    os.makedirs(SUBMISSION_FOLDER, exist_ok=True)

    files = request.files.getlist("files")
    saved_files = []

    for f in files:
        if f and f.filename:
            # Проверка расширения
            if not allowed_file(f.filename):
                app.logger.warning(f"Недопустимое расширение файла: {f.filename}")
                continue

            safe_name = secure_filename(f"sub_{assignment_id}_{current_user_id}_{f.filename}")
            dest = os.path.join(SUBMISSION_FOLDER, safe_name)

            try:
                f.save(dest)
                if os.path.getsize(dest) > 0:
                    saved_files.append(safe_name)
                    app.logger.info(f"Файл сохранен: {safe_name}")
                else:
                    os.remove(dest)
                    app.logger.warning(f"Удален пустой файл: {safe_name}")
            except Exception as e:
                app.logger.exception(f"Ошибка сохранения файла {f.filename}: {e}")

    file_path_db = json.dumps(saved_files, ensure_ascii=False) if saved_files else None

    submission = Submission.query.filter_by(assignment_id=assignment_id, student_id=current_user_id).first()
    if not submission:
        submission = Submission(
            assignment_id=assignment_id,
            student_id=current_user_id,
            answer_text=answer_text,
            file_path=file_path_db,
            status="pending",
            submitted_at=datetime.utcnow()
        )
        db.session.add(submission)
    else:
        submission.answer_text = answer_text
        if file_path_db:
            submission.file_path = file_path_db
        submission.status = "pending"
        submission.submitted_at = datetime.utcnow()

    db.session.commit()

    return jsonify({"success": True, "message": "Работа отправлена!", "files": saved_files})

# def get_user_from_token(token):
#     # Убираем "Bearer " если есть
#     if token.startswith("Bearer "):
#         token = token[7:]
    
#     # Здесь ищем пользователя по токену (пример, если токен хранится в users)
#     user = User.query.filter_by(token=token).first()
#     return user

# @app.before_request
# def log_headers():
#     print("Headers:", dict(request.headers))
#     print("Authorization header:", request.headers.get("Authorization"))

@app.errorhandler(422)
def handle_unprocessable_entity(err):
    print("422 ERROR:", err)
    return jsonify({"message": "Invalid token format"}), 422

# --- Запуск ---
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    # Для стабильного работы в разработке можно отключить reloader:
    app.run(host="0.0.0.0", debug=True, use_reloader=False, port=5000)