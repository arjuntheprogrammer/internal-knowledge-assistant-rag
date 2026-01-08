from flask import Blueprint, request, jsonify, url_for, redirect
from backend.middleware.auth import token_required, admin_required
from backend.models.config import SystemConfig
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/config', methods=['GET'])
@token_required
@admin_required
def get_config(current_user):
    config = SystemConfig.get_config()
    return jsonify(config), 200

@admin_bp.route('/config', methods=['PUT'])
@token_required
@admin_required
def update_config(current_user):
    data = request.get_json()
    SystemConfig.update_config(data)
    return jsonify({'message': 'Configuration updated'}), 200

# Google OAuth Flow
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = os.path.join(os.getcwd(), 'backend', 'credentials', 'credentials.json')
TOKEN_FILE = os.path.join(os.getcwd(), 'backend', 'credentials', 'token.json')

@admin_bp.route('/google-login', methods=['GET'])
@token_required
@admin_required
def google_login(current_user):
    config = SystemConfig.get_config()
    client_id = config.get('google_client_id')
    client_secret = config.get('google_client_secret')

    flow = None

    # Priority 1: Config from UI
    if client_id and client_secret:
        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
            }
        }
        flow = Flow.from_client_config(
            client_config, SCOPES,
            redirect_uri=url_for('admin.oauth2callback', _external=True)
        )

    # Priority 2: File-based
    elif os.path.exists(CREDENTIALS_FILE):
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE, SCOPES,
            redirect_uri=url_for('admin.oauth2callback', _external=True)
        )
    else:
        return jsonify({'message': 'Google Credentials not configured.'}), 400

    # Store user email in state to retrieve it in callback
    state = current_user['email']
    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=state
    )
    return jsonify({'auth_url': authorization_url})


@admin_bp.route('/oauth2callback')
def oauth2callback():
    state = request.args.get('state') # This is the user email we passed
    code = request.args.get('code')
    error = request.args.get('error')

    if error:
        return f"Error: {error}"

    if not state:
        return "Error: User context (state) missing from callback"

    try:
        from backend.models.user import User
        config = SystemConfig.get_config()
        client_id = config.get('google_client_id')
        client_secret = config.get('google_client_secret')

        flow = None
        if client_id and client_secret:
             client_config = {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
                }
             }
             flow = Flow.from_client_config(
                client_config, SCOPES,
                redirect_uri=url_for('admin.oauth2callback', _external=True)
             )
        else:
             flow = Flow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES,
                redirect_uri=url_for('admin.oauth2callback', _external=True)
             )

        flow.fetch_token(code=code)
        creds = flow.credentials

        # Save token to user in DB
        User.update_google_token(state, creds.to_json())

        return "Authentication successful! You can close this window and return to the dashboard."
    except Exception as e:
        return f"Authentication failed: {e}"

@admin_bp.route('/chk_google_auth', methods=['GET'])
@token_required
def check_google_auth(current_user):
    token = current_user.get('google_token')
    return jsonify({'authenticated': bool(token)})

@admin_bp.route('/preview_docs', methods=['POST'])
@token_required
@admin_required
def preview_docs(current_user):
    from backend.services.rag import RAGService
    result = RAGService.get_drive_file_list()
    return jsonify(result), 200

