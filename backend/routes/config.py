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


def _build_step_statuses(user, indexing_status: dict) -> dict:
    api_key = user.get("openai_api_key")
    api_key_valid = bool(user.get("openai_key_valid"))
    if api_key_valid:
        api_status = {"status": "COMPLETED", "message": "API key validated."}
    elif api_key:
        api_status = {"status": "FAILED", "message": "API key not validated."}
    else:
        api_status = {"status": "PENDING", "message": "API key required."}

    drive_auth = bool(user.get("google_token"))
    drive_files = user.get("drive_file_ids") or []
    drive_folder = bool(user.get("drive_folder_id"))
    has_drive_source = bool(drive_files or drive_folder)
    if drive_auth and has_drive_source:
        file_count = len(drive_files) if drive_files else "folder"
        drive_status = {
            "status": "COMPLETED",
            "message": f"Drive authorized with {file_count} files selected." if drive_files else "Drive authorized and folder selected.",
        }
    else:
        drive_status = {
            "status": "PENDING",
            "message": "Authorize Drive and select files.",
        }

    build_status = {
        "status": indexing_status.get("status", IndexingStatus.PENDING),
        "message": indexing_status.get("message") or "Build the database.",
    }

    return {
        "api_key": api_status,
        "drive": drive_status,
        "build": build_status,
    }


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
    indexing_status = IndexingService.get_status(
        current_user["uid"], user=user)
    openai_key = user.get("openai_api_key")
    key_first4 = openai_key[:4] if openai_key and len(
        openai_key) >= 8 else None
    key_last4 = openai_key[-4:] if openai_key and len(
        openai_key) >= 8 else None
    openai_key_valid = bool(user.get("openai_key_valid"))
    openai_key_validated_at = (
        user.get("openai_key_validated_at") if openai_key_valid else None
    )
    drive_test_success = bool(user.get("drive_test_success"))
    drive_folder_id = user.get("drive_folder_id")
    drive_test_folder_id = (
        user.get("drive_test_folder_id") if drive_test_success else None
    )
    drive_tested_at = user.get(
        "drive_tested_at") if drive_test_success else None
    if drive_test_folder_id and drive_test_folder_id != drive_folder_id:
        drive_test_success = False
        drive_tested_at = None
    steps = _build_step_statuses(user, indexing_status)
    config_ready = all(
        step.get("status") == "COMPLETED" for step in steps.values()
    )
    drive_file_ids = user.get("drive_file_ids") or []
    drive_file_names = user.get("drive_file_names") or []
    response = {
        "openai_model": "gpt-4.1-mini",
        "drive_folder_id": drive_folder_id,
        "drive_file_ids": drive_file_ids,
        "drive_file_names": drive_file_names,
        "drive_file_count": len(drive_file_ids),
        "drive_authenticated": bool(user.get("google_token")),
        "has_openai_key": bool(openai_key),
        "openai_key_first4": key_first4,
        "openai_key_last4": key_last4,
        "openai_key_valid": openai_key_valid,
        "openai_key_validated_at": format_dt(openai_key_validated_at),
        "drive_test_success": drive_test_success,
        "drive_tested_at": format_dt(drive_tested_at),
        "drive_test_folder_id": drive_test_folder_id,
        "indexing": indexing_status,
        "steps": steps,
        "config_ready": config_ready,
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

    # Handle drive_folder_id (legacy)
    drive_folder_id = _normalize_drive_folder_id(data.get("drive_folder_id"))
    if drive_folder_id is not None:
        update_data["drive_folder_id"] = drive_folder_id.strip() or None

    # Handle drive_file_ids (new drive.file scope)
    if "drive_file_ids" in data:
        file_ids = data.get("drive_file_ids") or []
        update_data["drive_file_ids"] = file_ids if isinstance(
            file_ids, list) else []
    if "drive_file_names" in data:
        file_names = data.get("drive_file_names") or []
        update_data["drive_file_names"] = file_names if isinstance(
            file_names, list) else []

    if "openai_api_key" in update_data and update_data.get(
        "openai_api_key"
    ) != existing.get("openai_api_key"):
        update_data["openai_key_valid"] = False

    # Check if drive files have changed
    files_changed = False
    if "drive_file_ids" in update_data:
        old_files = existing.get("drive_file_ids") or []
        new_files = update_data.get("drive_file_ids") or []
        files_changed = set(old_files) != set(new_files)

    if "drive_folder_id" in update_data and update_data.get(
        "drive_folder_id"
    ) != existing.get("drive_folder_id"):
        update_data["drive_test_success"] = False
        update_data["drive_tested_at"] = None
        update_data["drive_test_folder_id"] = None
        update_data["drive_folder_checksum"] = None
        update_data["drive_file_count"] = 0

    if files_changed:
        update_data["drive_test_success"] = False
        update_data["drive_tested_at"] = None
        update_data["drive_files_checksum"] = None
        update_data["drive_file_count"] = len(
            update_data.get("drive_file_ids") or [])

    if update_data:
        UserConfig.update_config(current_user["uid"], update_data)
        config_changed = (
            update_data.get("openai_api_key") != existing.get("openai_api_key")
            or update_data.get("drive_folder_id") != existing.get("drive_folder_id")
            or files_changed
        )
        if config_changed:
            RAGService.reset_user_cache(current_user["uid"])
            IndexingService.reset_indexing(current_user["uid"])

        # Check if all drive data is being removed
        removing_folder = (
            "drive_folder_id" in update_data
            and update_data.get("drive_folder_id") is None
            and existing.get("drive_folder_id")
        )
        removing_files = (
            "drive_file_ids" in update_data
            and not update_data.get("drive_file_ids")
            and existing.get("drive_file_ids")
        )
        if removing_folder or removing_files:
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

    # Parse the token to check scopes
    if isinstance(token_json, str):
        try:
            token_data = json.loads(token_json)
        except Exception:
            token_data = {}
    else:
        token_data = token_json or {}

    # Check if the token has the correct scope (drive.file)
    token_scopes = token_data.get("scopes") or []
    has_drive_file_scope = any("drive.file" in scope for scope in token_scopes)
    has_old_readonly_scope = any(
        "drive.readonly" in scope for scope in token_scopes)

    if has_old_readonly_scope and not has_drive_file_scope:
        return jsonify({
            "error": "Please re-authorize Google Drive to use the updated permissions.",
            "needs_reauth": True,
        }), 400

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
                creds_data = json.load(f)
                web_creds = creds_data.get(
                    "web") or creds_data.get("installed") or {}
                client_id = web_creds.get("client_id")
                # Extract numeric app ID from client_id (format: 123456789-xxx.apps.googleusercontent.com)
                if client_id and "-" in client_id:
                    app_id = client_id.split("-")[0]
        except Exception:
            pass

    # Include the origin in the response for the picker
    origin = request.host_url.rstrip("/")

    return jsonify(
        {
            "apiKey": api_key,
            "accessToken": access_token,
            "clientId": client_id,
            "appId": app_id,
            "origin": origin,
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
            jsonify(
                {"success": False, "message": "Drive folder ID not configured."}),
            400,
        )
    previous_folder_id = user.get("drive_folder_id")
    previous_checksum = user.get("drive_folder_checksum")
    if payload.get("drive_folder_id"):
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

    result["indexing_started"] = False
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
    Remove the Google Drive folder/files configuration and clear associated data.
    """
    user_id = current_user["uid"]

    # 1. Clear Drive config in Firestore
    UserConfig.update_config(
        user_id,
        {
            "drive_folder_id": None,
            "drive_file_ids": [],
            "drive_file_names": [],
            "drive_test_success": False,
            "drive_tested_at": None,
            "drive_test_folder_id": None,
            "drive_folder_checksum": None,
            "drive_files_checksum": None,
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


@config_bp.route("/start-indexing", methods=["POST"])
@token_required
def start_indexing(current_user):
    """
    Start background document indexing.

    This triggers the indexing process immediately.
    """
    user_config = UserConfig.get_user(current_user["uid"]) or {}

    user_context = build_user_context(
        current_user["uid"],
        email=current_user.get("email"),
        user_config=user_config,
    )

    # Don't force re-indexing if already COMPLETED
    result = IndexingService.start_indexing(
        user_context, force=False, inline=True
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


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

    # Force indexing even if already COMPLETED
    result = IndexingService.start_indexing(
        user_context, force=True, inline=True
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@config_bp.route("/build-database", methods=["POST"])
@token_required
def build_database(current_user):
    """
    Build or rebuild the document database.
    """
    user_id = current_user["uid"]

    RAGService.reset_user_cache(user_id)
    user_config = UserConfig.get_user(user_id) or {}
    user_context = build_user_context(
        user_id,
        email=current_user.get("email"),
        user_config=user_config,
    )

    result = IndexingService.start_indexing(
        user_context, force=True, inline=True)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code
