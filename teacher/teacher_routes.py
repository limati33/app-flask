from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from models import db, Teacher, Assignment, Submission, Group, Student
from fcm import send_personal_assignment_push

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
    
    # Ищем все ответы студентов на задания, которые создал ЭТОТ учитель
    submissions = Submission.query.join(Assignment).filter(
        Assignment.teacher_id == session['teacher_id']
    ).order_by(Submission.submitted_at.desc()).all()
    
    return render_template('teacher/check_submissions.html', submissions=submissions)

# Оставляем только этот вариант
@teacher_bp.route('/submissions/<int:sub_id>/status/<string:status>')
def update_submission_status(sub_id, status):
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    
    submission = Submission.query.get_or_404(sub_id)
    
    # Проверка прав доступа: только учитель, создавший задание, может менять статус
    if submission.assignment.teacher_id == session['teacher_id']:
        submission.status = status # 'accepted' или 'rejected'
        db.session.commit()
        # По желанию можно добавить уведомление:
        # flash(f"Статус работы успешно изменен на: {status}")
    else:
        # Если учитель пытается изменить чужую работу
        flash("У вас нет прав для редактирования этой работы")
    
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
    
    groups = Group.query.all()
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        group_id = request.form.get('group_id')
        student_id = request.form.get('student_id') # Получаем ID студента
        deadline_str = request.form.get('deadline')
        
        from datetime import datetime
        deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')

        title = request.form.get('title')
        student_id = request.form.get('student_id')
        
        # 1. Сохраняем в БД
        new_task = Assignment(
            teacher_id=session['teacher_id'],
            group_id=request.form.get('group_id'),
            student_id=student_id,
            title=title,
            description=request.form.get('description'),
            deadline=datetime.strptime(request.form.get('deadline'), '%Y-%m-%dT%H:%M')
        )
        db.session.add(new_task)
        db.session.commit()

        # 2. ОТПРАВЛЯЕМ PUSH (если выбран конкретный студент)
        if student_id:
            send_personal_assignment_push(student_id, title)
        
        return redirect(url_for('teacher.dashboard'))

    return render_template('teacher/add_assignment.html', groups=groups)