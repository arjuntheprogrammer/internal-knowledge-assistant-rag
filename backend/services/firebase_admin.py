import os

import firebase_admin
from firebase_admin import auth, credentials, firestore


_app = None
_db = None
_cred = None
_project_id = None


def _load_credentials():
    cred_path = os.getenv("FIREBASE_ADMIN_CREDENTIALS_PATH")
    if not cred_path or not os.path.exists(cred_path):
        raise ValueError("Firebase credentials not configured.")
    return credentials.Certificate(cred_path)


def _ensure_firestore_client():
    global _db
    if _db is not None:
        return _db

    database_id = os.getenv("FIRESTORE_DB")
    if database_id:
        try:
            from google.cloud import firestore as gc_firestore

            creds = None
            if _cred is not None:
                try:
                    creds = _cred.get_credential()
                except Exception:
                    creds = None
            project = _project_id
            try:
                _db = gc_firestore.Client(
                    project=project, credentials=creds, database=database_id
                )
            except TypeError:
                _db = gc_firestore.Client(project=project, credentials=creds)
            return _db
        except Exception:
            _db = None

    _db = firestore.client()
    return _db


def initialize_firebase():
    global _app, _db, _cred, _project_id
    if _app:
        _ensure_firestore_client()
        return _app

    try:
        _app = firebase_admin.get_app()
        if _cred is None:
            _cred = _load_credentials()
            _project_id = getattr(_cred, "project_id", None)
        _ensure_firestore_client()
        return _app
    except ValueError:
        _app = None

    _cred = _load_credentials()
    _project_id = getattr(_cred, "project_id", None)
    _app = firebase_admin.initialize_app(_cred)
    _ensure_firestore_client()
    return _app


def get_firestore_client():
    if _db is None:
        initialize_firebase()
    return _db


def verify_firebase_token(id_token):
    initialize_firebase()
    return auth.verify_id_token(id_token)
