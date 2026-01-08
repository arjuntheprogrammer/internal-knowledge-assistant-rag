from werkzeug.security import generate_password_hash, check_password_hash
from backend.services.db import Database
from datetime import datetime
import uuid

class User:
    def __init__(self, email, password, name, role='user'):
        self.email = email
        self.password_hash = generate_password_hash(password)
        self.name = name
        self.role = role
        self.created_at = datetime.utcnow()
        self._id = uuid.uuid4().hex

    def save(self):
        db = Database.get_db()
        if db.users.find_one({'email': self.email}):
            return False

        user_data = {
            '_id': self._id,
            'email': self.email,
            'password_hash': self.password_hash,
            'name': self.name,
            'role': self.role,
            'created_at': self.created_at
        }
        db.users.insert_one(user_data)
        return True

    @staticmethod
    def get_by_email(email):
        db = Database.get_db()
        return db.users.find_one({'email': email})

    @staticmethod
    def verify_password(stored_password_hash, password):
        return check_password_hash(stored_password_hash, password)

    @staticmethod
    def create_admin_if_not_exists():
        db = Database.get_db()
        if not db.users.find_one({'email': 'admin@gmail.com'}):
            admin = User('admin@gmail.com', 'admin@gmail.com', 'Admin', 'admin')
            admin.save()
            print("Admin user created")
