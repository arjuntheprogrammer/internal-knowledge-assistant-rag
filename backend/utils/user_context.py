"""Helpers for building and validating user context payloads."""

from typing import Optional

from backend.models.user_config import UserConfig


def build_user_context(
    user_id: str,
    *,
    email: Optional[str] = None,
    user_config: Optional[dict] = None,
    overrides: Optional[dict] = None,
) -> dict:
    """Build a standardized user context dict for indexing/query flows."""
    config = user_config or UserConfig.get_user(user_id) or {}
    context = {
        "uid": user_id,
        "email": email or config.get("email"),
        "openai_api_key": config.get("openai_api_key"),
        "drive_folder_id": config.get("drive_folder_id"),
        "google_token": config.get("google_token"),
    }
    if overrides:
        context.update(overrides)
    return context


def is_user_context_ready(user_context: dict) -> bool:
    """Return True if context has the minimum fields required to index."""
    return bool(
        user_context.get("openai_api_key")
        and user_context.get("drive_folder_id")
        and user_context.get("google_token")
    )
