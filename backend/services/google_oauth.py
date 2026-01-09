import json
import os

from google_auth_oauthlib.flow import Flow

from backend.models.config import SystemConfig

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def build_google_auth_url(user_email, redirect_uri, origin):
    flow = _build_flow(redirect_uri, origin)
    if not flow:
        return None, "Google Credentials not configured."

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=user_email,
        prompt="consent",
    )
    return authorization_url, None


def exchange_google_oauth_code(code, redirect_uri, origin):
    flow = _build_flow(redirect_uri, origin)
    if not flow:
        return None, "Authentication failed: Missing OAuth credentials file."

    flow.fetch_token(code=code)
    return flow.credentials, None


def _build_flow(redirect_uri, origin):
    config = SystemConfig.get_config()
    client_id = config.get("google_client_id")
    client_secret = config.get("google_client_secret")

    client_config = _build_client_config(client_id, client_secret, redirect_uri, origin)
    if not client_config:
        credentials_file = _find_credentials_file()
        client_config = _load_client_config_from_file(credentials_file)

    if not client_config:
        return None

    return Flow.from_client_config(client_config, SCOPES, redirect_uri=redirect_uri)


def _find_credentials_file():
    candidates = [
        os.path.join(os.getcwd(), "backend", "credentials", "client_secrets.json"),
        os.path.join(os.getcwd(), "backend", "credentials", "credentials.json"),
        os.path.join(os.getcwd(), "client_secrets.json"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _load_client_config_from_file(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r") as handle:
            data = json.load(handle)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    if "web" in data:
        return {"web": data["web"]}
    if "installed" in data:
        return {"installed": data["installed"]}

    return None


def _build_client_config(client_id, client_secret, redirect_uri, origin):
    if not client_id or not client_secret:
        return None
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [redirect_uri],
            "javascript_origins": [origin],
        }
    }
