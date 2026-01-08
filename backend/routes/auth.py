from flask import Blueprint, request, jsonify, current_app
from backend.models.user import User
import jwt
import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({'message': 'Missing required fields'}), 400

    user = User(
        email=data['email'],
        password=data['password'],
        name=data['name']
    )

    if user.save():
        return jsonify({'message': 'User created successfully'}), 201
    else:
        return jsonify({'message': 'User already exists'}), 409

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Missing credentials'}), 400

    user_data = User.get_by_email(data['email'])
    if not user_data:
        return jsonify({'message': 'Invalid credentials'}), 401

    if User.verify_password(user_data['password_hash'], data['password']):
        token = jwt.encode({
            'email': user_data['email'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, current_app.config['SECRET_KEY'], algorithm="HS256")

        return jsonify({
            'token': token,
            'user': {
                'email': user_data['email'],
                'name': user_data['name'],
                'role': user_data['role']
            }
        }), 200

    return jsonify({'message': 'Invalid credentials'}), 401
