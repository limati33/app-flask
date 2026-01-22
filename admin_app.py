# admin_app.py
from flask import Flask
from models import db
from admin import admin_bp
from fcm import init_app  # ← импортируем

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///college.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "super-secret-key"

db.init_app(app)
app.register_blueprint(admin_bp, url_prefix="/admin")

# Инициализируем FCM
init_app(app)  # ← ВОТ ТУТ!

@app.route("/")
def index():
    return "Главная страница для студентов"

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5050)