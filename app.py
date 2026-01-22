# app.py
from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from datetime import datetime, timedelta, date
import os
from calendar import monthcalendar, day_name, month_name
from collections import defaultdict
from urllib.parse import urljoin
from models import db, Student, Group, Schedule, Announcement, Reminder, Teacher, Assignment, Submission
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import json
from fcm import init_app as init_fcm
from teacher.teacher_routes import teacher_bp # Импортируй новый блюпринт
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.register_blueprint(teacher_bp)    # Зарегистрируй его
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///college.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'supersecretkey123'  # строка, которая не меняется
app.config['JWT_SECRET_KEY'] = 'supersecretkey123'  # Тот же секрет для JWT (можно другой, но сильный)

# Явно указываем, где искать токен и тип заголовка
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
app.config["JWT_HEADER_NAME"] = "Authorization"
app.config["JWT_HEADER_TYPE"] = "Bearer"

UPLOAD_FOLDER = 'static/submissions'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)  # Инициализация JWT
init_fcm(app)

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

        # --- сформировать корректный avatar_url ---
        avatar_url = None
        if student.avatar:
            avatar = student.avatar.strip()
            # если уже абсолютный URL — используем как есть
            if avatar.startswith("http://") or avatar.startswith("https://"):
                avatar_url = avatar
            else:
                # Если в базе хранится относительный путь (например "uploads/avatars/x.png" или "/uploads/avatars/x.png"
                # — собираем абсолютный URL на основе request.host_url
                # Пример: http://10.49.216.60:5000/uploads/avatars/x.png
                path = avatar
                if not path.startswith("/"):
                    # попробуем предположить папку: измени при необходимости
                    path = f"/static/avatars/{path}"
                avatar_url = urljoin(request.host_url, path.lstrip("/"))

        profile_data = {
            "id": student.id,
            "name": student.name,
            "avatar": avatar_url,
            "login": student.login,
            "group": student.group.name if student.group else None,
            "group_students": [{"id": s.id, "name": s.name} for s in group_students]
        }

        app.logger.debug(f"/api/profile -> profile_data: {profile_data}")
        return jsonify(profile_data)
    except Exception as e:
        app.logger.exception("Error in /api/profile")
        return jsonify({"message": f"Server error: {str(e)}"}), 500

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
    serialized_teachers = [{
        "id": t.id,
        "name": t.name,
        "subject": t.subject,
        "contact": t.contact,
        "avatar": t.avatar,
        "avatar_url": f"{request.host_url}static/avatars/teachers/{t.avatar or 'default.png'}"
    } for t in teachers]
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
@jwt_required() # Убедись, что используешь JWT
def get_my_assignments():
    current_user_id = get_jwt_identity() # ID студента из токена
    student = Student.query.get(current_user_id)
    
    if not student:
        return jsonify({"success": False, "message": "Студент не найден"}), 404

    # Ищем задания для группы студента
    # Сортируем: сначала те, у которых дедлайн ближе
    assignments = Assignment.query.filter_by(group_id=student.group_id)\
        .order_by(Assignment.deadline.asc()).all()
    
    result = []
    for task in assignments:
        # Проверяем, сдал ли студент уже это задание
        submission = Submission.query.filter_by(assignment_id=task.id, student_id=student.id).first()
        status = submission.status if submission else "pending"
        
        # Если задание еще не принято (pending или rejected) или вообще не сдано — добавляем в список
        if status != "accepted":
            result.append({
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "deadline": task.deadline.strftime("%Y-%m-%d %H:%M"),
                "status": status, # pending, rejected, accepted
                "teacher_name": task.teacher.name if task.teacher else "Учитель"
            })

    return jsonify({
        "success": True, 
        "assignments": result
    })

@app.route("/api/submissions", methods=["POST"])
@jwt_required()
def submit_assignment():
    current_user_id = get_jwt_identity()
    
    assignment_id = request.form.get("assignment_id")
    answer_text = request.form.get("answer_text")
    # Нужно сделать цикл:
    files = request.files.getlist("files") # Получаем список
    for file in files:
        if file:
            filename = secure_filename(f"sub_{assignment_id}_{current_user_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            # Здесь логика сохранения путей в базу (возможно, нужно изменить БД, чтобы хранить несколько путей)

    if not assignment_id:
        return jsonify({"success": False, "message": "Нет ID задания"}), 400

    filename = None
    if file:
        filename = secure_filename(f"sub_{assignment_id}_{current_user_id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    submission = Submission.query.filter_by(
        assignment_id=assignment_id, 
        student_id=current_user_id
    ).first()

    if not submission:
        submission = Submission(
            assignment_id=assignment_id,
            student_id=current_user_id,
            answer_text=answer_text,
            file_path=filename,
            status="pending"
        )
        db.session.add(submission)
    else:
        submission.answer_text = answer_text
        if filename: submission.file_path = filename
        submission.status = "pending"
        submission.submitted_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"success": True, "message": "Работа отправлена!"})

def get_user_from_token(token):
    # Убираем "Bearer " если есть
    if token.startswith("Bearer "):
        token = token[7:]
    
    # Здесь ищем пользователя по токену (пример, если токен хранится в users)
    user = User.query.filter_by(token=token).first()
    return user

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