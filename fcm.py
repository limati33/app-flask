# fcm.py
import os
import firebase_admin
from firebase_admin import credentials, messaging

FCM_SERVICE_FILENAME = "firebase-service-account.json"

def init_app(app):
    """
    Инициализация Firebase Admin SDK.
    Ищет firebase-service-account.json в корне проекта (рядом с admin_app.py).
    """
    # Путь: папка, где находится admin_app.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    fcm_path = os.path.join(base_dir, FCM_SERVICE_FILENAME)

    print(f"[fcm] Ищем файл: {fcm_path}")  # ← отладка

    if os.path.exists(fcm_path):
        try:
            cred = credentials.Certificate(fcm_path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            app.config['FCM_ENABLED'] = True
            print(f"[fcm] Firebase Admin УСПЕШНО инициализирован: {fcm_path}")
        except Exception as e:
            app.config['FCM_ENABLED'] = False
            print(f"[fcm] ОШИБКА инициализации Firebase: {e}")
    else:
        app.config['FCM_ENABLED'] = False
        print(f"[fcm] ФАЙЛ НЕ НАЙДЕН: {fcm_path} — FCM ОТКЛЮЧЁН")

#Работает admin_app.py -> admin/routes.py
def send_new_announcement_push(title: str, content: str):
    try:
        if not firebase_admin._apps:
            print("[fcm] Firebase Admin SDK не инициализирован — пуш пропущен")
            return None

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=(content[:120] + '...') if len(content) > 120 else content
            ),
            topic="announcements"
        )
        print(f"[fcm] Отправка FCM: title='{title}'")
        resp = messaging.send(message)
        print(f"[fcm] УСПЕШНО отправлено! message_id: {resp}")
        return resp
    except Exception as e:
        print(f"[fcm] ОШИБКА отправки FCM: {e}")
        import traceback; traceback.print_exc()
        return None

#Не работает teacher/teacher_routes.py
def send_personal_assignment_push(student_id, title):
    """Отправляет уведомление конкретному студенту на его тему"""
    try:
        if not firebase_admin._apps:
            print("[fcm] Firebase не инициализирован — пуш отменен")
            return None

        # Топик должен быть уникальным для каждого студента
        topic_name = f"student_{student_id}"

        message = messaging.Message(
            notification=messaging.Notification(
                title="📝 Новая отработка",
                body=f"Назначено задание: {title}"
            ),
            topic=topic_name
        )
        
        resp = messaging.send(message)
        print(f"[fcm] Успешно отправлено студенту {student_id}: {resp}")
        return resp
    except Exception as e:
        print(f"[fcm] Ошибка отправки личного пуша: {e}")
        return None

#Не работает teacher/teacher_routes.py
def send_submission_status_push(student_id, assignment_title, status, comment=None):
    try:
        if not firebase_admin._apps:
            print("[fcm] Firebase не инициализирован — пуш отменен")
            return None

        topic_name = f"student_{student_id}"

        if status == "accepted":
            title = "✅ Работа принята"
            body = f"Задание «{assignment_title}» принято"
        else:
            title = "❌ Работа отклонена"
            body = f"Задание «{assignment_title}» отклонено"
            if comment:
                body += f": {comment[:80]}"

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            topic=topic_name
        )

        resp = messaging.send(message)
        print(f"[fcm] Пуш о статусе отправлен студенту {student_id}")
        return resp

    except Exception as e:
        print(f"[fcm] Ошибка отправки пуша статуса: {e}")
        return None
