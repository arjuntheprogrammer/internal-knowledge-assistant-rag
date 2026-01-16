"""
Opik Tracing Integration for LlamaIndex.

Debug, evaluate, and monitor your LLM applications, RAG systems,
and agentic workflows with tracing, eval metrics, and production-ready dashboards.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_opik_callback_handler(user_id: Optional[str] = None):
    """
    Get Opik callback handler for LlamaIndex tracing.
    Returns None if Opik is disabled or not configured.
    """
    # Check if Opik is enabled
    opik_enabled = os.getenv("OPIK_ENABLED", "true").lower() not in {"0", "false", "no"}
    api_key = os.getenv("OPIK_API_KEY")

    if not opik_enabled or not api_key:
        logger.debug("Opik tracing disabled or API key not configured")
        return None

    try:
        from opik.integrations.llama_index import LlamaIndexCallbackHandler

        project_name = os.getenv("OPIK_PROJECT_NAME", "internal-knowledge-assistant")

        # Create handler with optional metadata
        handler = LlamaIndexCallbackHandler(
            project_name=project_name,
        )
        logger.info("Opik tracing initialized for project: %s", project_name)
        return handler
    except ImportError:
        logger.warning("llama-index-callbacks-opik not installed")
        return None
    except Exception as exc:
        logger.warning("Failed to initialize Opik: %s", exc)
        return None
