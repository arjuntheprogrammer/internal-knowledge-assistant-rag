"""
Secret Manager Integration for Production.

This module loads all application secrets from a single consolidated
JSON secret stored in Google Cloud Secret Manager.

In production, the secret is mounted as a file at /secrets/app/secrets.json
The JSON contains all configuration including nested JSON for credentials.
"""

import json
import os
import tempfile
from functools import lru_cache


@lru_cache(maxsize=1)
def load_app_secrets() -> dict:
    """
    Load and parse the consolidated app secrets.

    Returns a dict with all secret values. Nested JSON objects
    (like Firebase and Google OAuth credentials) are returned as dicts.
    """
    secrets_path = os.getenv("APP_SECRETS_PATH", "/secrets/app/secrets.json")

    if not os.path.exists(secrets_path):
        # Not in production or secrets not mounted
        return {}

    try:
        with open(secrets_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load app secrets: {e}")
        return {}


def get_secret(key: str, default=None):
    """Get a single secret value by key."""
    secrets = load_app_secrets()
    return secrets.get(key, default)


def write_credentials_file(key: str, target_path: str) -> bool:
    """
    Write a nested JSON credential (like Firebase or Google OAuth)
    to a file for libraries that require a file path.

    Args:
        key: The key in the secrets dict (e.g., "FIREBASE_ADMIN_CREDENTIALS")
        target_path: Where to write the credentials file

    Returns:
        True if successful, False otherwise
    """
    secrets = load_app_secrets()
    creds = secrets.get(key)

    if not creds:
        return False

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w") as f:
            if isinstance(creds, dict):
                json.dump(creds, f)
            else:
                f.write(str(creds))
        return True
    except Exception as e:
        print(f"Warning: Failed to write credentials file: {e}")
        return False


def setup_production_environment():
    """
    Set up the production environment by:
    1. Loading consolidated secrets
    2. Writing credential files for services that need file paths
    3. Setting environment variables for other secrets

    Call this once at application startup in production.
    """
    secrets = load_app_secrets()

    if not secrets:
        print("No consolidated secrets found - using environment variables")
        return

    print("Setting up production environment from consolidated secrets...")

    # Write Firebase credentials to a temp file
    firebase_creds = secrets.get("FIREBASE_ADMIN_CREDENTIALS")
    if firebase_creds:
        firebase_path = "/tmp/firebase-creds.json"
        if write_credentials_file("FIREBASE_ADMIN_CREDENTIALS", firebase_path):
            os.environ["FIREBASE_ADMIN_CREDENTIALS_PATH"] = firebase_path
            print(f"  ✓ Firebase credentials written to {firebase_path}")

    # Write Google OAuth credentials to a temp file
    google_oauth = secrets.get("GOOGLE_OAUTH_CLIENT")
    if google_oauth:
        google_path = "/tmp/google-oauth-creds.json"
        if write_credentials_file("GOOGLE_OAUTH_CLIENT", google_path):
            os.environ["GOOGLE_OAUTH_CLIENT_PATH"] = google_path
            print(f"  ✓ Google OAuth credentials written to {google_path}")

    # Set simple environment variables
    env_mappings = {
        "MILVUS_URI": "MILVUS_URI",
        "MILVUS_TOKEN": "MILVUS_TOKEN",
        "MILVUS_COLLECTION": "MILVUS_COLLECTION",
        "OPIK_API_KEY": "OPIK_API_KEY",
        "OPIK_PROJECT_NAME": "OPIK_PROJECT_NAME",
        "OPIK_ENABLED": "OPIK_ENABLED",
        "GOOGLE_PICKER_API_KEY": "GOOGLE_PICKER_API_KEY",
        "SECRET_KEY": "SECRET_KEY",
        "FIRESTORE_DB": "FIRESTORE_DB",
        # Firebase Client Config
        "FIREBASE_API_KEY": "FIREBASE_API_KEY",
        "FIREBASE_AUTH_DOMAIN": "FIREBASE_AUTH_DOMAIN",
        "FIREBASE_PROJECT_ID": "FIREBASE_PROJECT_ID",
        "FIREBASE_STORAGE_BUCKET": "FIREBASE_STORAGE_BUCKET",
        "FIREBASE_MESSAGING_SENDER_ID": "FIREBASE_MESSAGING_SENDER_ID",
        "FIREBASE_APP_ID": "FIREBASE_APP_ID",
        "FIREBASE_MEASUREMENT_ID": "FIREBASE_MEASUREMENT_ID",
    }

    for secret_key, env_var in env_mappings.items():
        value = secrets.get(secret_key)
        if value and not os.getenv(env_var):
            os.environ[env_var] = str(value)

    print("  ✓ Environment variables configured from secrets")
