import logging
from flask import Blueprint, request, jsonify
from backend.middleware.auth import token_required
from backend.models.user_config import UserConfig
from backend.services.rag import RAGService
from backend.services.safety import SafetyService
from backend.services.indexing_service import IndexingService, IndexingStatus
from backend.utils.user_context import build_user_context

from llama_index.core.schema import QueryBundle

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/feedback", methods=["POST"])
@token_required
def feedback(current_user):
    data = request.get_json()
    if not data or "rating" not in data:
        return jsonify({"message": "Rating is required"}), 400

    # Log feedback
    logger.info(
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
        user_context = build_user_context(
            current_user["uid"],
            email=current_user.get("email"),
            user_config=user_config,
        )
        openai_key = user_context.get("openai_api_key")
        if not openai_key:
            return jsonify({"message": "OpenAI API key is not configured."}), 400
        if not user_config.get("openai_key_valid"):
            return (
                jsonify(
                    {
                        "message": "OpenAI API key is not validated. Please test it in Settings.",
                        "needs_config": True,
                    }
                ),
                400,
            )

        drive_file_ids = user_context.get("drive_file_ids") or []
        google_token = user_context.get("google_token")
        if not google_token:
            return (
                jsonify(
                    {
                        "message": "Google Drive access is not authorized. Please connect your Drive in Settings.",
                        "needs_config": True,
                    }
                ),
                400,
            )
        if not drive_file_ids:
            return (
                jsonify(
                    {
                        "message": "Google Drive files are not selected. Please choose files in Settings.",
                        "needs_config": True,
                    }
                ),
                400,
            )

        # Check indexing status before allowing queries
        indexing_status = IndexingService.get_status(current_user["uid"])
        status = indexing_status.get("status")

        # Only block if we are indexing AND we don't have a previous successful connection.
        # This allows silent background syncs (from the scheduler) to happen without interrupting the chat.
        indexing_completed_at = user_config.get("indexing_completed_at")
        if status == IndexingStatus.PROCESSING and not indexing_completed_at:
            progress = indexing_status.get("progress", 0)
            message = indexing_status.get("message", "Processing documents...")
            return (
                jsonify(
                    {
                        "message": f"We're still getting your documents ready ({progress}% complete). {message}",
                        "indexing": True,
                        "progress": progress,
                    }
                ),
                202,
            )

        if status == IndexingStatus.PENDING:
            return (
                jsonify(
                    {
                        "message": "We haven't built your document database yet. Please go to Settings and click 'Build Database' to begin.",
                        "indexing": False,
                        "needs_config": True,
                    }
                ),
                400,
            )

        if status == IndexingStatus.FAILED:
            error_message = indexing_status.get("message", "Unknown error")
            return (
                jsonify(
                    {
                        "message": f"We ran into an issue getting your documents ready: {error_message}. Please check your connection in Settings.",
                        "indexing": False,
                        "failed": True,
                    }
                ),
                400,
            )

        # Pass user context/ACL here in future
        query_bundle = QueryBundle(
            query_str=user_message,
            custom_embedding_strs=[user_message],
        )
        response_text = RAGService.query(query_bundle, user_context)

        # Safety Check Output
        is_safe_response, reason_response = SafetyService.is_safe(
            response_text)
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
        logger.exception(f"Chat Error: {e}")
        return jsonify({"message": "Error processing request", "error": str(e)}), 500
