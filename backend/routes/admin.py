from flask import Blueprint, request, jsonify
from backend.middleware.auth import token_required, admin_required
from backend.models.config import SystemConfig

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
    return jsonify({'message': 'Configuration updated successfully'}), 200
