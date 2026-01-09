from flask import Blueprint, request, jsonify, url_for
from backend.middleware.auth import token_required, admin_required
from backend.models.config import SystemConfig
from backend.services.google_oauth import (
    build_google_auth_url,
    exchange_google_oauth_code,
)


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


@admin_bp.route("/google-login", methods=["GET"])
@token_required
@admin_required
def google_login(current_user):
    redirect_uri = url_for("admin.oauth2callback", _external=True)
    origin = request.host_url.rstrip("/")
    authorization_url, error = build_google_auth_url(
        current_user["email"], redirect_uri, origin
    )
    if error:
        return jsonify({"message": error}), 400
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

        redirect_uri = url_for("admin.oauth2callback", _external=True)
        origin = request.host_url.rstrip("/")
        creds, error = exchange_google_oauth_code(code, redirect_uri, origin)
        if error:
            return error

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
