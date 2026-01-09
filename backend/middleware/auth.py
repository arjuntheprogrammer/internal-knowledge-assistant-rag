from functools import wraps
from flask import request, jsonify, current_app
import jwt
from backend.models.user import User


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]

        if not token:
            return jsonify({"message": "Token is missing!"}), 401

        try:
            data = jwt.decode(
                token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
            )
            current_user = User.get_by_email(data["email"])
            if not current_user:
                return jsonify({"message": "User not found!"}), 401
        except Exception as e:
            return jsonify({"message": "Token is invalid!"}), 401

        return f(current_user, *args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.get("role") != "admin":
            return jsonify({"message": "Admin privilege required!"}), 403
        return f(current_user, *args, **kwargs)

    return decorated
