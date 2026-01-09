from flask import Blueprint, request, jsonify, url_for
from backend.middleware.auth import token_required, admin_required
from backend.models.config import SystemConfig
import os
import json
from google_auth_oauthlib.flow import Flow


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/config", methods=["GET"])
@token_required
@admin_required
def get_config(current_user):
    config = SystemConfig.get_config()
    return jsonify(config), 200


@admin_bp.route("/config", methods=["PUT"])
@token_required
@admin_required
def update_config(current_user):
    data = request.get_json()
    SystemConfig.update_config(data)
    return jsonify({"message": "Configuration updated"}), 200


# Google OAuth Flow
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


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


@admin_bp.route("/google-login", methods=["GET"])
@token_required
@admin_required
def google_login(current_user):
    config = SystemConfig.get_config()
    client_id = config.get("google_client_id")
    client_secret = config.get("google_client_secret")

    redirect_uri = url_for("admin.oauth2callback", _external=True)
    origin = request.host_url.rstrip("/")
    client_config = _build_client_config(client_id, client_secret, redirect_uri, origin)

    if client_config:
        flow = Flow.from_client_config(client_config, SCOPES, redirect_uri=redirect_uri)
    else:
        credentials_file = _find_credentials_file()
        client_config = _load_client_config_from_file(credentials_file)
        if not client_config:
            return jsonify({"message": "Google Credentials not configured."}), 400
        flow = Flow.from_client_config(client_config, SCOPES, redirect_uri=redirect_uri)

    # Store user email in state to retrieve it in callback
    state = current_user["email"]
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return jsonify({"auth_url": authorization_url})


@admin_bp.route("/oauth2callback")
def oauth2callback():
    state = request.args.get("state")  # This is the user email we passed
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return f"Error: {error}"

    if not state:
        return "Error: User context (state) missing from callback"

    try:
        from backend.models.user import User

        config = SystemConfig.get_config()
        client_id = config.get("google_client_id")
        client_secret = config.get("google_client_secret")

        redirect_uri = url_for("admin.oauth2callback", _external=True)
        origin = request.host_url.rstrip("/")
        client_config = _build_client_config(
            client_id, client_secret, redirect_uri, origin
        )

        if client_config:
            flow = Flow.from_client_config(
                client_config, SCOPES, redirect_uri=redirect_uri
            )
        else:
            credentials_file = _find_credentials_file()
            client_config = _load_client_config_from_file(credentials_file)
            if not client_config:
                return "Authentication failed: Missing OAuth credentials file."
            flow = Flow.from_client_config(
                client_config, SCOPES, redirect_uri=redirect_uri
            )

        flow.fetch_token(code=code)
        creds = flow.credentials

        # Save token to user in DB
        User.update_google_token(state, creds.to_json())

        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <title>Google Auth</title>
  </head>
  <body>
    <div style="font-family: Arial, sans-serif; padding: 24px;">
      <h2 style="margin: 0 0 8px;">Authentication successful</h2>
      <p style="margin: 0;">You can close this window and return to the dashboard.</p>
    </div>
    <script>
      try {
        if (window.opener) {
          window.opener.postMessage({ type: "google-auth-success" }, window.location.origin);
          window.close();
        }
      } catch (e) {
        // Ignore postMessage errors; user can close manually.
      }
    </script>
  </body>
</html>"""
    except Exception as e:
        return f"Authentication failed: {e}"


@admin_bp.route("/chk_google_auth", methods=["GET"])
@token_required
def check_google_auth(current_user):
    token = current_user.get("google_token")
    return jsonify({"authenticated": bool(token)})


@admin_bp.route("/preview_docs", methods=["POST"])
@token_required
@admin_required
def preview_docs(current_user):
    from backend.services.rag import RAGService

    result = RAGService.get_drive_file_list()
    return jsonify(result), 200
