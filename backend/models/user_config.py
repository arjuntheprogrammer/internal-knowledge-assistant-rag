from datetime import datetime

from backend.services.firebase_admin import get_firestore_client


class UserConfig:
    COLLECTION = "users"

    @classmethod
    def ensure_user(cls, uid, email=None, name=None):
        db = get_firestore_client()
        doc_ref = db.collection(cls.COLLECTION).document(uid)
        snapshot = doc_ref.get()
        now = datetime.utcnow()
        if not snapshot.exists:
            doc_ref.set(
                {
                    "email": email,
                    "name": name,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return doc_ref.get().to_dict()
        updates = {}
        data = snapshot.to_dict() or {}
        if email and data.get("email") != email:
            updates["email"] = email
        if name and data.get("name") != name:
            updates["name"] = name
        if updates:
            updates["updated_at"] = now
            doc_ref.set(updates, merge=True)
            data.update(updates)
        return data

    @classmethod
    def get_user(cls, uid):
        db = get_firestore_client()
        snapshot = db.collection(cls.COLLECTION).document(uid).get()
        return snapshot.to_dict() if snapshot.exists else None

    @classmethod
    def update_config(cls, uid, data):
        db = get_firestore_client()
        update_data = {k: v for k, v in data.items() if v is not None}
        update_data["updated_at"] = datetime.utcnow()
        db.collection(cls.COLLECTION).document(uid).set(update_data, merge=True)
        return update_data

    @classmethod
    def set_google_token(cls, uid, token_json):
        return cls.update_config(
            uid,
            {
                "google_token": token_json,
                "drive_test_success": False,
            },
        )

    @classmethod
    def get_google_token(cls, uid):
        user = cls.get_user(uid) or {}
        return user.get("google_token")

    @classmethod
    def list_users_with_drive(cls):
        db = get_firestore_client()
        results = []
        for doc in db.collection(cls.COLLECTION).stream():
            data = doc.to_dict() or {}
            if data.get("drive_folder_id"):
                data["uid"] = doc.id
                results.append(data)
        return results
