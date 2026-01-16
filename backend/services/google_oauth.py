import json
import os

from google_auth_oauthlib.flow import Flow

from backend.services.rag.rag_google_drive import resolve_credentials_path

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.readonly",
]


def build_google_auth_url(user_id, redirect_uri, origin):
    flow = _build_flow(redirect_uri, origin)
    if not flow:
        return None, "Google Credentials not configured."

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=user_id,
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
    credentials_file = resolve_credentials_path()
    client_config = _load_client_config_from_file(credentials_file)

    if not client_config:
        return None

    return Flow.from_client_config(client_config, SCOPES, redirect_uri=redirect_uri)


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


def refresh_google_credentials(credentials_json):
    """
    Load credentials from JSON and refresh them if expired.
    Returns (creds, was_refreshed)
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not credentials_json:
        return None, False

    try:
        if isinstance(credentials_json, str):
            credentials_data = json.loads(credentials_json)
        else:
            credentials_data = credentials_json

        creds = Credentials.from_authorized_user_info(credentials_data, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            return creds, True

        return creds, False
    except Exception:
        return None, False
