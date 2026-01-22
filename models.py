# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Group(db.Model):
    __tablename__ = "groups"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    curator_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=True)
    curator = db.relationship("Teacher", backref="curated_groups", lazy=True)
    students = db.relationship("Student", backref="group", lazy=True)
    schedule = db.relationship("Schedule", backref="group", lazy=True)

class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)  # ФИО
    avatar = db.Column(db.String(200), nullable=True)
    password = db.Column(db.String(200), nullable=False)  # хранить хэш
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    reminders = db.relationship("Reminder", backref="student", lazy=True)

class Teacher(db.Model):
    __tablename__ = "teachers"
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(50), unique=True, nullable=False) # Добавлено
    password = db.Column(db.String(200), nullable=False) # Добавлено
    name = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=True)
    room = db.Column(db.String(20), nullable=True)
    contact = db.Column(db.String(100), nullable=True)
    avatar = db.Column(db.String(200), nullable=True)
    schedule = db.relationship("Schedule", backref="teacher", lazy=True)

class Schedule(db.Model):
    __tablename__ = "schedule"
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)
    room = db.Column(db.String(20), nullable=True)
    weekday = db.Column(db.Integer, nullable=False)  # 1-7
    time_start = db.Column(db.String(10), nullable=False)
    time_end = db.Column(db.String(10), nullable=False)

class Announcement(db.Model):
    __tablename__ = "announcements"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.Column(db.String(100), nullable=True)
    photo_filename = db.Column(db.String(255), nullable=True)

class Reminder(db.Model):
    __tablename__ = "reminders"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(10), nullable=True)
    type = db.Column(db.String(50), nullable=True)
    note = db.Column(db.Text, nullable=True)

class Assignment(db.Model):
    __tablename__ = "assignments"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    attachment = db.Column(db.String(255), nullable=True)
    group = db.relationship("Group", backref="group_assignments") 
    teacher = db.relationship("Teacher", backref="teacher_assignments")
    student = db.relationship("Student", backref="personal_assignments")
    submissions = db.relationship("Submission", backref="assignment", lazy=True)

class Submission(db.Model):
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    student = db.relationship("Student", backref="my_submissions")
    assignment_obj = db.relationship("Assignment", backref="all_submissions") 
    answer_text = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(255), nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="pending")

class Admin(db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # хранить хэш
