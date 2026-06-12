from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from models import db, Teacher, Assignment, AssignmentFile, Submission, Group, Student
from fcm import send_personal_assignment_push, send_submission_status_push
import json

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')

@teacher_bp.route('/dashboard')
def dashboard():
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    
    teacher = Teacher.query.get(session['teacher_id'])
    # Получаем статистику для этого учителя
    assignments_count = Assignment.query.filter_by(teacher_id=teacher.id).count()
    pending_submissions = Submission.query.join(Assignment).filter(
        Assignment.teacher_id == teacher.id, 
        Submission.status == 'pending'
    ).count()

    return render_template('teacher/dashboard.html', 
                           teacher=teacher, 
                           assignments_count=assignments_count,
                           pending_submissions=pending_submissions)


@teacher_bp.route('/assignments')
def my_assignments():
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    
    # Показываем задания только этого учителя
    tasks = Assignment.query.filter_by(teacher_id=session['teacher_id']).all()
    return render_template('teacher/my_assignments.html', tasks=tasks)

# 1. Просмотр всех присланных ответов студентов
@teacher_bp.route('/submissions')
def check_submissions():
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    
    submissions = Submission.query.join(Assignment).filter(
        Assignment.teacher_id == session['teacher_id']
    ).order_by(Submission.submitted_at.desc()).all()
    
    # Преобразуем JSON-строку file_path в список sub.files, чтобы шаблон мог спокойно итерироваться
    for sub in submissions:
        files = []
        if getattr(sub, 'file_path', None):
            try:
                if isinstance(sub.file_path, str):
                    parsed = json.loads(sub.file_path)  # '[]', 'null' -> parsed может быть list или None
                else:
                    parsed = sub.file_path  # если уже список
                # Нормализуем — хотим только список строк
                if isinstance(parsed, list):
                    # уберём None и приведём все элементы к строкам
                    files = [str(f) for f in parsed if f is not None]
                else:
                    files = []
            except Exception:
                files = []
        else:
            files = []
        # Добавляем атрибут, доступный в шаблоне
        sub.files = files

    return render_template('teacher/check_submissions.html', submissions=submissions)

# Оставляем только этот вариант
@teacher_bp.route('/submissions/<int:sub_id>/status/<string:status>', methods=["POST", "GET"])
def update_submission_status(sub_id, status):
    print(
        f"[teacher] update_submission_status: "
        f"sub_id={sub_id}, status={status}, method={request.method}"
    )

    if 'teacher_id' not in session:
        return redirect(url_for('login'))

    submission = Submission.query.get_or_404(sub_id)

    # проверка прав
    if submission.assignment.teacher_id != session['teacher_id']:
        flash("У вас нет прав для редактирования этой работы")
        return redirect(url_for('teacher.check_submissions'))

    # защита от мусора
    if status not in ("accepted", "rejected"):
        flash("Некорректный статус")
        return redirect(url_for('teacher.check_submissions'))

    submission.status = status

    # ✅ если отклонено — сохраняем причину
    if status == "rejected":
        comment = request.form.get("comment")
        submission.teacher_comment = comment if comment else None
    else:
        submission.teacher_comment = None

    db.session.commit()
    print("[teacher] sending status push...")

    # 🔔 PUSH студенту
    send_submission_status_push(
        student_id=submission.student_id,
        assignment_title=submission.assignment.title,
        status=status,
        comment=submission.teacher_comment
    )

    return redirect(url_for('teacher.check_submissions'))


@teacher_bp.route('/get_students/<int:group_id>')
def get_students(group_id):
    if 'teacher_id' not in session:
        return jsonify([]), 403
    students = Student.query.filter_by(group_id=group_id).all()
    # Возвращаем список словарей с id и именем
    return jsonify([{'id': s.id, 'name': s.name} for s in students])


@teacher_bp.route('/assignments/add', methods=['GET', 'POST'])
def add_assignment():
    if 'teacher_id' not in session:
        return redirect(url_for('login'))

    from datetime import datetime
    import os
    import logging
    from werkzeug.utils import secure_filename

    UPLOAD_FOLDER = 'static/uploads/assignments'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    groups = Group.query.all()

    if request.method == 'POST':
        logging.info('📩 Получен POST /assignments/add')

        title = request.form.get('title')
        description = request.form.get('description')
        group_id = request.form.get('group_id')
        student_id = request.form.get('student_id')
        deadline = datetime.strptime(
            request.form.get('deadline'),
            '%Y-%m-%dT%H:%M'
        )

        files = request.files.getlist('attachments[]')
        logging.info(f'📎 Получено файлов: {len(files)}')

        # 1) Создаём Assignment и сразу коммитим, чтобы получить id
        assignment = Assignment(
            teacher_id=session['teacher_id'],
            group_id=group_id,
            student_id=student_id,
            title=title,
            description=description,
            deadline=deadline
        )

        db.session.add(assignment)
        db.session.commit()  # чтобы появился assignment.id

        # 2) Сохраняем файлы и создаём записи в assignment_files
        saved_filenames = []
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                stored_name = f'{assignment.id}_{filename}'
                filepath = os.path.join(UPLOAD_FOLDER, stored_name)

                file.save(filepath)
                logging.info(f'✅ Файл сохранён: {filepath}')

                db.session.add(AssignmentFile(
                    assignment_id=assignment.id,
                    filename=filename,   # оригинальное имя
                    filepath=filepath    # реальный путь на диске
                ))

                # В attachment будем сохранять относительный путь/имя,
                # можно сохранять только filename или stored_name
                saved_filenames.append(filename)

        # 3) Записываем JSON-список имён в поле assignment.attachment
        try:
            if saved_filenames:
                assignment.attachment = json.dumps(saved_filenames, ensure_ascii=False)
            else:
                assignment.attachment = None
        except Exception as e:
            logging.exception("Ошибка сериализации attachment: %s", e)

        db.session.commit()

        # PUSH
        # if student_id:
        send_personal_assignment_push(student_id, title)

        logging.info('🎉 Задание успешно создано')

        return redirect(url_for('teacher.dashboard'))

    return render_template(
        'teacher/add_assignment.html',
        groups=groups
    )
