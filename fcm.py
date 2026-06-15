# fcm.py
import os
import json
import firebase_admin
from firebase_admin import credentials, messaging

def init_app(app):
    try:
        # 🔵 1. Берём из ENV (Render)
        if "FIREBASE_CREDENTIALS" in os.environ:
            cred_json = json.loads(os.environ["FIREBASE_CREDENTIALS"])
            cred = credentials.Certificate(cred_json)
            print("[fcm] Используется ENV credentials")

        # 🟡 2. Локальный файл (если нет ENV)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            fcm_path = os.path.join(base_dir, "firebase-service-account.json")

            print(f"[fcm] Ищем файл: {fcm_path}")

            if not os.path.exists(fcm_path):
                raise FileNotFoundError("Firebase credentials not found")

            cred = credentials.Certificate(fcm_path)
            print("[fcm] Используется локальный файл")

        # init Firebase
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        app.config['FCM_ENABLED'] = True
        print("[fcm] Firebase Admin инициализирован")

    except Exception as e:
        app.config['FCM_ENABLED'] = False
        print(f"[fcm] FCM ERROR: {e}")


def send_new_announcement_push(title: str, content: str):
    try:
        if not firebase_admin._apps:
            return None

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=(content[:120] + '...') if len(content) > 120 else content
            ),
            topic="announcements"
        )

        return messaging.send(message)

    except Exception as e:
        print(f"[fcm] ERROR announcement: {e}")
        return None


def send_personal_assignment_push(student_id, title):
    try:
        if not firebase_admin._apps:
            return None

        topic = f"student_{student_id}"

        message = messaging.Message(
            notification=messaging.Notification(
                title="📝 Новая отработка",
                body=f"Назначено задание: {title}"
            ),
            topic=topic
        )

        return messaging.send(message)

    except Exception as e:
        print(f"[fcm] ERROR personal push: {e}")
        return None


def send_submission_status_push(student_id, assignment_title, status, comment=None):
    try:
        if not firebase_admin._apps:
            return None

        topic = f"student_{student_id}"

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
            topic=topic
        )

        return messaging.send(message)

    except Exception as e:
        print(f"[fcm] ERROR status push: {e}")
        return None