import re

from flask import Blueprint, request, jsonify, url_for
from openai import OpenAI

from backend.middleware.auth import token_required
from backend.models.user_config import UserConfig
from backend.services.google_oauth import (
    build_google_auth_url,
    exchange_google_oauth_code,
)
from backend.services.rag import RAGService
from backend.services.rag import rag_google_drive
from backend.services.indexing_service import IndexingService, IndexingStatus
from backend.utils.time_utils import format_dt, utc_now
from backend.utils.user_context import build_user_context


config_bp = Blueprint("config", __name__)


def _normalize_drive_folder_id(value):
    if not value:
        return None
    text = value.strip()
    match = re.search(
        r"drive\\.google\\.com/drive/(?:u/\\d+/)?folders/([a-zA-Z0-9_-]+)",
        text,
        re.I,
    )
    return match.group(1) if match else text


@config_bp.route("", methods=["GET"])
@token_required
def get_config(current_user):
    user = UserConfig.get_user(current_user["uid"]) or {}
    openai_key = user.get("openai_api_key")
    key_first4 = openai_key[:4] if openai_key and len(openai_key) >= 8 else None
    key_last4 = openai_key[-4:] if openai_key and len(openai_key) >= 8 else None
    openai_key_valid = bool(user.get("openai_key_valid"))
    openai_key_validated_at = (
        user.get("openai_key_validated_at") if openai_key_valid else None
    )
    drive_test_success = bool(user.get("drive_test_success"))
    drive_folder_id = user.get("drive_folder_id")
    drive_test_folder_id = (
        user.get("drive_test_folder_id") if drive_test_success else None
    )
    drive_tested_at = user.get("drive_tested_at") if drive_test_success else None
    if drive_test_folder_id and drive_test_folder_id != drive_folder_id:
        drive_test_success = False
        drive_tested_at = None
    response = {
        "openai_model": "gpt-4.1-mini",
        "drive_folder_id": drive_folder_id,
        "drive_authenticated": bool(user.get("google_token")),
        "has_openai_key": bool(openai_key),
        "openai_key_first4": key_first4,
        "openai_key_last4": key_last4,
        "openai_key_valid": openai_key_valid,
        "openai_key_validated_at": format_dt(openai_key_validated_at),
        "drive_test_success": drive_test_success,
        "drive_tested_at": format_dt(drive_tested_at),
        "drive_test_folder_id": drive_test_folder_id,
    }
    return jsonify(response), 200


@config_bp.route("", methods=["PUT"])
@token_required
def update_config(current_user):
    data = request.get_json() or {}
    existing = UserConfig.get_user(current_user["uid"]) or {}
    update_data = {}
    openai_key = data.get("openai_api_key")
    if openai_key:
        update_data["openai_api_key"] = openai_key.strip()
    drive_folder_id = _normalize_drive_folder_id(data.get("drive_folder_id"))
    if drive_folder_id is not None:
        update_data["drive_folder_id"] = drive_folder_id.strip() or None
    if "openai_api_key" in update_data and update_data.get(
        "openai_api_key"
    ) != existing.get("openai_api_key"):
        update_data["openai_key_valid"] = False
    if "drive_folder_id" in update_data and update_data.get(
        "drive_folder_id"
    ) != existing.get("drive_folder_id"):
        update_data["drive_test_success"] = False
        update_data["drive_tested_at"] = None
        update_data["drive_test_folder_id"] = None
        update_data["drive_folder_checksum"] = None
        update_data["drive_file_count"] = 0
    if update_data:
        UserConfig.update_config(current_user["uid"], update_data)
        if update_data.get("openai_api_key") != existing.get(
            "openai_api_key"
        ) or update_data.get("drive_folder_id") != existing.get("drive_folder_id"):
            RAGService.reset_user_cache(current_user["uid"])
        if (
            "drive_folder_id" in update_data
            and update_data.get("drive_folder_id") is None
            and existing.get("drive_folder_id")
        ):
            _purge_drive_documents(current_user["uid"])
    return jsonify({"message": "Configuration updated"}), 200


@config_bp.route("/test-openai", methods=["POST"])
@token_required
def test_openai(current_user):
    data = request.get_json() or {}
    api_key = (data.get("openai_api_key") or "").strip()
    if not api_key:
        user = UserConfig.get_user(current_user["uid"]) or {}
        api_key = user.get("openai_api_key")
        if not api_key:
            return jsonify({"message": "OpenAI API key is required."}), 400
    try:
        client = OpenAI(api_key=api_key)
        client.models.list()
        UserConfig.update_config(
            current_user["uid"],
            {
                "openai_api_key": api_key,
                "openai_key_valid": True,
                "openai_key_validated_at": utc_now(),
            },
        )
        return jsonify({"success": True}), 200
    except Exception as exc:
        UserConfig.update_config(
            current_user["uid"],
            {
                "openai_api_key": api_key,
                "openai_key_valid": False,
            },
        )
        return jsonify({"success": False, "message": str(exc)}), 400


@config_bp.route("/drive-auth-url", methods=["GET"])
@token_required
def drive_auth_url(current_user):
    redirect_uri = url_for("config.drive_oauth_callback", _external=True)
    origin = request.host_url.rstrip("/")
    authorization_url, error = build_google_auth_url(
        current_user["uid"], redirect_uri, origin
    )
    if error:
        return jsonify({"message": error}), 400
    return jsonify({"auth_url": authorization_url})


@config_bp.route("/drive-oauth-callback")
def drive_oauth_callback():
    state = request.args.get("state")
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return f"Error: {error}"

    if not state:
        return "Error: User context (state) missing from callback"

    try:
        redirect_uri = url_for("config.drive_oauth_callback", _external=True)
        origin = request.host_url.rstrip("/")
        creds, error = exchange_google_oauth_code(code, redirect_uri, origin)
        if error:
            return error

        UserConfig.set_google_token(state, creds.to_json())

        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <title>Google Auth</title>
  </head>
  <body>
    <div style="font-family: Arial, sans-serif; padding: 24px;">
      <h2 style="margin: 0 0 8px;">Authentication successful</h2>
      <p style="margin: 0;">You can close this window and return to the app.</p>
    </div>
    <script>
      try {
        if (window.opener) {
          window.opener.postMessage({ type: "google-auth-success" }, window.location.origin);
          window.close();
        } else {
          setTimeout(() => {
            window.location.href = "/configure";
          }, 800);
        }
      } catch (e) {
        // Ignore postMessage errors; user can close manually.
      }
    </script>
  </body>
</html>"""
    except Exception as exc:
        return f"Authentication failed: {exc}"


@config_bp.route("/drive-auth-status", methods=["GET"])
@token_required
def drive_auth_status(current_user):
    token = UserConfig.get_google_token(current_user["uid"])
    return jsonify({"authenticated": bool(token)})


@config_bp.route("/picker-config", methods=["GET"])
@token_required
def get_picker_config(current_user):
    """
    Get configuration needed for Google Picker.
    Returns the API key and user's OAuth access token.
    """
    import os
    import json

    api_key = os.getenv("GOOGLE_PICKER_API_KEY")
    if not api_key:
        return jsonify({"error": "Picker API key not configured"}), 500

    # Get the user's OAuth token
    token_json = UserConfig.get_google_token(current_user["uid"])
    if not token_json:
        return jsonify({"error": "Google Drive not authorized"}), 400

    from backend.services.google_oauth import refresh_google_credentials

    creds, refreshed = refresh_google_credentials(token_json)

    if not creds:
        return jsonify({"error": "Invalid or expired Google Drive session"}), 400

    if refreshed:
        UserConfig.set_google_token(current_user["uid"], creds.to_json())

    access_token = creds.token

    # Get the OAuth client ID from credentials file
    client_id = None
    app_id = None
    creds_path = os.getenv("GOOGLE_OAUTH_CLIENT_PATH")
    if creds_path and os.path.exists(creds_path):
        try:
            with open(creds_path, "r") as f:
                creds = json.load(f)
                web_creds = creds.get("web") or creds.get("installed") or {}
                client_id = web_creds.get("client_id")
                # Extract numeric app ID from client_id (format: 123456789-xxx.apps.googleusercontent.com)
                if client_id and "-" in client_id:
                    app_id = client_id.split("-")[0]
        except Exception:
            pass

    return jsonify(
        {
            "apiKey": api_key,
            "accessToken": access_token,
            "clientId": client_id,
            "appId": app_id,
        }
    )


@config_bp.route("/test-drive", methods=["POST"])
@token_required
def test_drive(current_user):
    user = UserConfig.get_user(current_user["uid"]) or {}
    payload = request.get_json(silent=True) or {}
    drive_folder_id = _normalize_drive_folder_id(
        payload.get("drive_folder_id") or user.get("drive_folder_id")
    )
    if not drive_folder_id:
        return (
            jsonify({"success": False, "message": "Drive folder ID not configured."}),
            400,
        )
    previous_folder_id = user.get("drive_folder_id")
    previous_checksum = user.get("drive_folder_checksum")
    drive_folder_changed = False
    if payload.get("drive_folder_id"):
        drive_folder_changed = drive_folder_id != previous_folder_id
        UserConfig.update_config(
            current_user["uid"],
            {
                "drive_folder_id": drive_folder_id,
                "drive_test_success": False,
                "drive_tested_at": None,
                "drive_test_folder_id": None,
            },
        )
    result = RAGService.get_drive_file_list(
        user_id=current_user["uid"],
        drive_folder_id=drive_folder_id,
    )
    checksum = None
    if result.get("success"):
        checksum = rag_google_drive.get_folder_checksum(
            user_id=current_user["uid"],
            drive_folder_id=drive_folder_id,
            token_json=user.get("google_token"),
        )
    UserConfig.update_config(
        current_user["uid"],
        {
            "drive_test_success": bool(result.get("success")),
            "drive_tested_at": utc_now() if result.get("success") else None,
            "drive_test_folder_id": drive_folder_id if result.get("success") else None,
            "drive_folder_checksum": checksum if result.get("success") else None,
            "drive_file_count": (
                result.get("file_count", 0) if result.get("success") else 0
            ),
        },
    )

    # Auto-start indexing if Drive test was successful
    indexing_started = False
    if result.get("success"):
        # Get fresh user config with updated values
        updated_user = UserConfig.get_user(current_user["uid"]) or {}
        openai_key = updated_user.get("openai_api_key")

        if openai_key:
            indexing_state = IndexingService.get_status(current_user["uid"])
            current_status = indexing_state.get("status")
            should_index = drive_folder_changed
            if current_status in (IndexingStatus.PENDING, IndexingStatus.FAILED):
                should_index = True
            elif not drive_folder_changed:
                if checksum and previous_checksum:
                    should_index = checksum != previous_checksum
                else:
                    should_index = True
            user_context = build_user_context(
                current_user["uid"],
                email=current_user.get("email"),
                user_config=updated_user,
                overrides={"drive_folder_id": drive_folder_id},
            )
            if should_index:
                indexing_result = IndexingService.start_indexing(
                    user_context, force=True, inline=True
                )
                indexing_started = indexing_result.get("success", False)

    result["indexing_started"] = indexing_started
    return jsonify(result), 200


def _purge_drive_documents(user_id):
    IndexingService.reset_indexing(user_id)
    RAGService.reset_user_cache(user_id)
    try:
        vector_store = RAGService.get_vector_store(user_id)
        if vector_store:
            client = getattr(vector_store, "client", None)
            collection_name = getattr(vector_store, "collection_name", None)
            if client and collection_name:
                client.delete(
                    collection_name=collection_name, filter=f"user_id == '{user_id}'"
                )
    except Exception:
        pass


@config_bp.route("/remove-drive", methods=["POST"])
@token_required
def remove_drive(current_user):
    """
    Remove the Google Drive folder configuration and clear associated manual data.
    """
    user_id = current_user["uid"]

    # 1. Clear Drive config in Firestore
    UserConfig.update_config(
        user_id,
        {
            "drive_folder_id": None,
            "drive_test_success": False,
            "drive_tested_at": None,
            "drive_test_folder_id": None,
            "drive_folder_checksum": None,
            "drive_file_count": 0,
        },
    )

    _purge_drive_documents(user_id)

    return (
        jsonify(
            {"success": True, "message": "Drive folder and associated data removed."}
        ),
        200,
    )


@config_bp.route("/indexing-status", methods=["GET"])
@token_required
def get_indexing_status(current_user):
    """Get the current indexing status for the user."""
    status = IndexingService.get_status(current_user["uid"])
    return jsonify(status), 200


@config_bp.route("/start-indexing", methods=["POST"])
@token_required
def start_indexing(current_user):
    """
    Start background document indexing.

    This triggers the indexing process in a background thread.
    The client should poll /indexing-status to monitor progress.
    """
    user_config = UserConfig.get_user(current_user["uid"]) or {}

    user_context = build_user_context(
        current_user["uid"],
        email=current_user.get("email"),
        user_config=user_config,
    )

    # Don't force re-indexing if already READY
    result = IndexingService.start_indexing(
        user_context, force=False, inline=True
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@config_bp.route("/indexing-ready", methods=["GET"])
@token_required
def is_indexing_ready(current_user):
    """Quick check if the index is ready for queries."""
    is_ready = IndexingService.is_ready(current_user["uid"])
    status = IndexingService.get_status(current_user["uid"])
    return (
        jsonify(
            {
                "ready": is_ready,
                "status": status["status"],
                "message": status["message"],
                "document_count": status["document_count"],
                "file_count": status.get("file_count", 0),
            }
        ),
        200,
    )


@config_bp.route("/re-index", methods=["POST"])
@token_required
def re_index(current_user):
    """
    Force a re-index of all documents.

    This clears the in-memory cache and starts fresh indexing.
    """
    user_id = current_user["uid"]

    # Clear the in-memory cache
    RAGService.reset_user_cache(user_id)

    # Get user config and start indexing
    user_config = UserConfig.get_user(user_id) or {}

    user_context = build_user_context(
        user_id,
        email=current_user.get("email"),
        user_config=user_config,
    )

    # Force indexing even if already READY
    result = IndexingService.start_indexing(
        user_context, force=True, inline=True
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code
