from flask import Blueprint, request, jsonify
from backend.middleware.auth import token_required
from backend.services.rag import RAGService
from backend.services.safety import SafetyService

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/feedback', methods=['POST'])
@token_required
def feedback(current_user):
    data = request.get_json()
    if not data or 'rating' not in data:
        return jsonify({'message': 'Rating is required'}), 400

    # Log feedback to DB or LangSmith here
    print(f"Feedback received from {current_user['email']}: {data['rating']} (MessageID: {data.get('message_id')})")

    return jsonify({'message': 'Feedback received'}), 200

@chat_bp.route('/message', methods=['POST'])
@token_required
def chat(current_user):
    data = request.get_json()
    if not data or not data.get('message'):
        return jsonify({'message': 'Message is required'}), 400

    user_message = data['message']

    # Safety Check Input
    is_safe, reason = SafetyService.is_safe(user_message)
    if not is_safe:
        return jsonify({'message': f"Safety Violation: {reason}"}), 400

    try:
        # Pass user context/ACL here in future
        response_text = RAGService.query(user_message)

        # Safety Check Output
        is_safe_response, reason_response = SafetyService.is_safe(response_text)
        if not is_safe_response:
            response_text = "[REDACTED due to safety policy]"

        return jsonify({
            'response': response_text,
            'citations': [], # Placeholder for future citations
            'message_id': 'mock-id-123' # Placeholder
        }), 200
    except Exception as e:

        print(f"Chat Error: {e}")
        return jsonify({'message': 'Error processing request', 'error': str(e)}), 500
