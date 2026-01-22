# create_admin.py
from werkzeug.security import generate_password_hash
from models import db, Admin
from flask import Flask
import getpass
import pwinput

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///college.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def main():
    with app.app_context():
        name = input("Имя админа: ")
        password = pwinput.pwinput("Пароль: ", mask="*")
        hashed = generate_password_hash(password)
        
        if Admin.query.filter_by(name=name).first():
            print("Админ с таким именем уже существует!")
            return
        
        admin = Admin(name=name, password=hashed)
        db.session.add(admin)
        db.session.commit()
        print(f"Админ {name} успешно добавлен!")

if __name__ == "__main__":
    main()
