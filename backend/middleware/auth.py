from functools import wraps
import logging
import os
from flask import request, jsonify

from backend.models.user_config import UserConfig
from backend.services.firebase_admin import verify_firebase_token

logger = logging.getLogger(__name__)


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        if not token:
            return jsonify({"message": "Token is missing!"}), 401

        try:
            decoded = verify_firebase_token(token)
        except Exception as exc:
            logger.warning("Firebase token verification failed: %s", exc)
            return jsonify({"message": "Token is invalid!", "error": str(exc)}), 401

        uid = decoded.get("uid")
        if not uid:
            return jsonify({"message": "Token is missing user context!"}), 401

        email = decoded.get("email")
        name = decoded.get("name")
        if not name and email:
            name = email.split("@", 1)[0]
        user_data = UserConfig.ensure_user(uid, email=email, name=name)
        current_user = {
            "uid": uid,
            "email": email,
            "name": user_data.get("name"),
        }
        return f(current_user, *args, **kwargs)

    return decorated
