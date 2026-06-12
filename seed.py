import random
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash

from app import app
from models import *

# --- ДАННЫЕ (Оставляем те же, что вы присылали) ---
ROOMS = ["ГК 100", "ГК 101", "ГК 102", "ГК 103", "ГК 104", "ГК 106", "ГК 108", "ГК 202", "ГК 205", "ГК 206", "ГК 209", "ГК 211", "ГК 300а", "ГК 300б", "ГК 301", "ГК 302", "ГК 303", "ГК 306", "ГК 307а", "ГК 307б", "ГК 400", "ГК 403", "ГК 404", "ГК 406", "ГК 409", "МК 131", "МК 132", "МК 133", "МК 135", "МК 136", "МК 137", "МК 138", "IT 119", "IT 120б", "IT 124", "IT 126", "IT 127", "IT 128", "IT 129", "Спорт зал 1"]

GROUP_NAMES = ["Web25-1А", "Web25-1Б", "ТЗИ25-1", "Т25-1", "П25-1А", "П25-1Б", "П25-1В", "П25-1Г", "П25-1ДК", "ИС25-1А", "ИС25-1Б", "С25-1", "ТМ25-1", "РЭТ25-1", "П23-3Е", "П22-4А", "ТЗИ24-2", "П23-3Г", "П24-2ЖК", "П22-4В", "П22-4Д", "П24-2А", "П22-4Г", "П23-3Д", "П23-3Б", "П22-4ЕК", "П23-3ЖК", "ИС23-3А", "Т22-4Б", "П24-2Б", "РЭТ24-2", "Т25-4В", "П24-2В", "П24-2Г", "ИС23-3Б", "ИС24-2", "П22-4Б", "П24-2Д", "П22-4ЖК", "П23-3А", "П22-4ЗК", "Т25-4Г"]

TEACHERS_DATA = [("Маха", "Математика"), ("Оразымбетова", "Всемирная история"), ("Өміржан О.Н", "Спецпредмет"), ("Жеңіснұр", "Химия"), ("Дюсембекова", "Каз. язык и литература"), ("Ільясқызы", "Биология"), ("Нурекенова", "История Казахстана"), ("Байсейтова", "Всемирная история"), ("Сейсекулова", "Математика"), ("Сонурова", "Русский язык и литература"), ("Ержанқызы", "Физика"), ("Шукирбекова", "Русский язык и литература"), ("Омарова", "Английский язык"), ("Лесбек Р.О", "Спецпредмет"), ("Каптагаева", "Информатика"), ("Боранбаева", "Информатика"), ("Нурбосын Р.О", "Спецпредмет"), ("Бикенова Р.О", "Спецпредмет"), ("Қали Р.О", "Спецпредмет"), ("Қайрат О.Н", "Спецпредмет"), ("Мұқашева", "Информатика"), ("Нургалиева Р.О", "Спецпредмет"), ("Бердибаева О.Н", "Спецпредмет"), ("Шамшиева", "Информатика"), ("Сейтказиева О.Н", "Спецпредмет"), ("Баситова", "Всемирная история"), ("Нурмуханбетов", "НВП"), ("Теменов", "НВП"), ("Малаева", "Русский язык"), ("Ахметова", "Каз. язык"), ("Акишева", "Английский язык"), ("Кожагулова", "Всемирная история"), ("Касенов", "Физика"), ("Джумагазиева", "Математика"), ("Батырбеков", "Информатика"), ("Ергеш Р.О", "Спецпредмет"), ("Ахмет Р.О", "Спецпредмет"), ("Сәлімгерей Р.О", "Спецпредмет"), ("Дүйсекеев Р.О", "Спецпредмет"), ("Тулепбергенова Р.О", "Спецпредмет"), ("Ағайдарова Р.О", "Спецпредмет"), ("Мендигалиева Р.О", "Спецпредмет"), ("Сейтов Р.О", "Спецпредмет"), ("Акимов Р.О", "Спецпредмет"), ("Баданова Р.О", "Спецпредмет"), ("Мерикенова", "Физика"), ("Турсынбаева Р.О", "Спецпредмет"), ("Анарқұл Р.О", "Спецпредмет"), ("Қалым О.Н", "Спецпредмет"), ("Сүйіндік Р.О", "Спецпредмет"), ("Ауезхан Р.О", "Спецпредмет"), ("Проскурин Р.О", "Спецпредмет"), ("Сапагова", "Спецпредмет"), ("Нурбеков", "Физкультура"), ("Бегмен", "Физкультура"), ("Кенбаев", "Физкультура"), ("Мұсабек", "Физкультура")]

FIRST_NAMES = ["Али", "Санжар", "Диас", "Аружан", "Алина", "Мадина", "Ерасыл", "Нурасыл", "Айгерим", "Бекарыс"]
LAST_NAMES = ["Ахметов", "Омаров", "Ким", "Иванов", "Алиев", "Сапаров", "Болатов", "Ержанов", "Сериков"]

def random_student_name():
    return f"{random.choice(LAST_NAMES)} {random.choice(FIRST_NAMES)}"

def seed():
    with app.app_context():
        # Полная очистка
        db.session.remove()
        db.drop_all()
        db.create_all()

        print("🚀 Начало заполнения базы данных...")

        try:
            # ================== ADMIN ==================
            admin = Admin(
                name="admin",
                password=generate_password_hash("admin")
            )
            db.session.add(admin)

            # ================== TEACHERS ==================
            teachers_list = []
            for idx, (t_name, t_subj) in enumerate(TEACHERS_DATA):
                teacher = Teacher(
                    login=f"teacher{idx+1}",
                    password=generate_password_hash("1234"),
                    name=t_name,
                    subject=t_subj,
                    room=random.choice(ROOMS),
                    contact=f"t{idx+1}@college.kz"
                )
                teachers_list.append(teacher)

            db.session.add_all(teachers_list)
            db.session.commit()
            print(f"✅ Создано {len(teachers_list)} преподавателей.")

            # ================== GROUPS ==================
            groups_list = []
            for g_name in GROUP_NAMES:
                # Используем teacher.id
                curator = random.choice(teachers_list)
                group = Group(
                    name=g_name,
                    curator_id=curator.id # Используем ID, а не объект
                )
                groups_list.append(group)

            db.session.add_all(groups_list)
            db.session.commit()
            print(f"✅ Создано {len(groups_list)} групп.")

            # ================== STUDENTS ==================
            students_list = []
            student_counter = 1
            
            # Важно: groups_list после commit может быть expired, 
            # но так как мы только что их создали и сессия та же, можно использовать.
            # Для надежности можно пройтись по ID.
            
            for group in groups_list:
                for _ in range(random.randint(15, 25)):
                    student = Student(
                        login=f"student{student_counter}",
                        name=random_student_name(),
                        password=generate_password_hash("1234"),
                        group_id=group.id  # ВАЖНО: Используем ID
                    )
                    students_list.append(student)
                    student_counter += 1

            db.session.add_all(students_list)
            db.session.commit()
            print(f"✅ Создано {len(students_list)} студентов.")

            # ================== ASSIGNMENTS ==================
            assignments = []
            for _ in range(50): 
                teacher = random.choice(teachers_list)
                group = random.choice(groups_list)
                
                assignment = Assignment(
                    teacher_id=teacher.id, # Используем ID
                    group_id=group.id,     # Используем ID
                    title=f"Задание: {teacher.subject}",
                    description="Подготовить конспект и решить задачи.",
                    deadline=datetime.now() + timedelta(days=random.randint(2, 10)),
                    teacher_name=teacher.name # Для упрощения отображения, если поле есть
                )
                assignments.append(assignment)

            db.session.add_all(assignments)
            db.session.commit()
            print(f"✅ Создано {len(assignments)} заданий.")

            # ================== SUBMISSIONS ==================
            for assignment in assignments[:20]:
                # Ищем студентов этой группы (запрос к БД надежнее фильтрации списка)
                group_students_ids = [s.id for s in students_list if s.group_id == assignment.group_id]
                
                if not group_students_ids: continue

                # 3-5 студентов
                sample_size = min(len(group_students_ids), random.randint(3, 5))
                selected_student_ids = random.sample(group_students_ids, k=sample_size)

                for s_id in selected_student_ids:
                    db.session.add(
                        Submission(
                            assignment_id=assignment.id,
                            student_id=s_id,
                            answer_text="Работу выполнил.",
                            status=random.choice(["pending", "accepted", "rejected"])
                        )
                    )

            db.session.commit()
            print("✅ Все данные успешно созданы (Студенты, Задания, Ответы)!")

        except Exception as e:
            db.session.rollback()
            print(f"❌ ОШИБКА: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    seed()