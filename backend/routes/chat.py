from flask import Blueprint, request, jsonify
from backend.middleware.auth import token_required
from backend.models.user_config import UserConfig
from backend.services.rag import RAGService
from backend.services.safety import SafetyService
from backend.services.indexing_service import IndexingService, IndexingStatus

from llama_index.core.schema import QueryBundle

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/feedback", methods=["POST"])
@token_required
def feedback(current_user):
    data = request.get_json()
    if not data or "rating" not in data:
        return jsonify({"message": "Rating is required"}), 400

    # Log feedback to DB or LangSmith here
    print(
        f"Feedback received from {current_user['email']}: {data['rating']} (MessageID: {data.get('message_id')})"
    )

    return jsonify({"message": "Feedback received"}), 200


@chat_bp.route("/message", methods=["POST"])
@token_required
def chat(current_user):
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"message": "Message is required"}), 400

    user_message = data["message"]

    # Safety Check Input
    is_safe, reason = SafetyService.is_safe(user_message)
    if not is_safe:
        return jsonify({"message": f"Safety Violation: {reason}"}), 400

    try:
        user_config = UserConfig.get_user(current_user["uid"]) or {}
        openai_key = user_config.get("openai_api_key")
        if not openai_key:
            return jsonify({"message": "OpenAI API key is not configured."}), 400

        drive_folder_id = user_config.get("drive_folder_id")
        google_token = user_config.get("google_token")
        if not drive_folder_id:
            return jsonify({"message": "Google Drive folder ID is not configured."}), 400
        if not google_token:
            return jsonify({"message": "Google Drive access is not authorized."}), 400

        # Check indexing status before allowing queries
        indexing_status = IndexingService.get_status(current_user["uid"])
        status = indexing_status.get("status")

        if status == IndexingStatus.INDEXING:
            progress = indexing_status.get("progress", 0)
            message = indexing_status.get("message", "Processing documents...")
            return jsonify({
                "message": f"Documents are still being indexed ({progress}% complete). {message}",
                "indexing": True,
                "progress": progress,
            }), 202  # 202 Accepted - request understood but processing not complete

        if status == IndexingStatus.PENDING:
            return jsonify({
                "message": "Your documents haven't been indexed yet. Please go to Settings and click 'Start Indexing' to begin.",
                "indexing": False,
                "needs_indexing": True,
            }), 400

        if status == IndexingStatus.FAILED:
            error_message = indexing_status.get("message", "Unknown error")
            return jsonify({
                "message": f"Document indexing failed: {error_message}. Please try re-indexing from Settings.",
                "indexing": False,
                "failed": True,
            }), 400

        # Pass user context/ACL here in future
        query_bundle = QueryBundle(
            query_str=user_message,
            custom_embedding_strs=[user_message],
        )
        response_text = RAGService.query(
            query_bundle,
            {
                "uid": current_user["uid"],
                "email": current_user.get("email"),
                "openai_api_key": openai_key,
                "drive_folder_id": drive_folder_id,
                "google_token": google_token,
            },
        )

        # Safety Check Output
        is_safe_response, reason_response = SafetyService.is_safe(response_text)
        if not is_safe_response:
            response_text = "[REDACTED due to safety policy]"

        return (
            jsonify(
                {
                    "response": response_text,
                    "citations": [],  # Placeholder for future citations
                    "message_id": "mock-id-123",  # Placeholder
                }
            ),
            200,
        )
    except Exception as e:

        print(f"Chat Error: {e}")
        return jsonify({"message": "Error processing request", "error": str(e)}), 500
