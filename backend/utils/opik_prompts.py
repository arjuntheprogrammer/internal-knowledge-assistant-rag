"""
Opik Prompt Library Integration.

Registers prompts in Opik's Prompt Library and provides tracking.
"""

import logging
import subprocess
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.utils.prompt_loader import PromptSpec

logger = logging.getLogger(__name__)

# Cache for registered Opik prompts
_opik_prompt_cache: Dict[str, Any] = {}


def _get_git_commit() -> str:
    """Get current git commit SHA (short form)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def register_prompt_in_opik(prompt_spec: "PromptSpec") -> Optional[Any]:
    """
    Register a prompt in Opik's Prompt Library.

    Uses opik.Prompt class which automatically creates/updates the prompt
    in the Opik Prompt Library UI.

    Args:
        prompt_spec: PromptSpec from prompt_loader

    Returns:
        opik.Prompt object if successful, None otherwise
    """
    cache_key = f"{prompt_spec.name}:{prompt_spec.hash}"

    # Return cached if already registered
    if cache_key in _opik_prompt_cache:
        return _opik_prompt_cache[cache_key]

    try:
        from opik import Prompt

        # Create prompt in Opik (or get existing if same content)
        opik_prompt = Prompt(
            name=prompt_spec.name,
            prompt=prompt_spec.text,
            metadata={
                "version": prompt_spec.version,
                "hash": prompt_spec.hash,
                "path": prompt_spec.path,
                "git_commit": _get_git_commit(),
            }
        )

        _opik_prompt_cache[cache_key] = opik_prompt
        logger.info(
            "Registered prompt in Opik: %s (v%s, hash=%s)",
            prompt_spec.name, prompt_spec.version, prompt_spec.hash[:8]
        )
        return opik_prompt

    except ImportError:
        logger.debug("Opik not available, skipping prompt registration")
        return None
    except Exception as e:
        logger.warning("Failed to register prompt in Opik: %s", e)
        return None


def get_prompt_metadata(prompt_spec: "PromptSpec") -> dict:
    """
    Get prompt metadata dict for attaching to traces.

    Args:
        prompt_spec: PromptSpec from prompt_loader

    Returns:
        Dict with prompt metadata keys
    """
    return {
        "prompt.name": prompt_spec.name,
        "prompt.version": prompt_spec.version,
        "prompt.hash": prompt_spec.hash,
    }


def sync_all_prompts_to_opik() -> Dict[str, bool]:
    """
    Synchronize all prompts from the prompts/ directory to Opik.

    Call this at application startup to ensure all prompts are registered.

    Returns:
        Dict mapping prompt names to success status
    """
    results = {}

    try:
        from backend.utils.prompt_loader import PromptLoader

        loader = PromptLoader()

        for key in loader.VALID_KEYS:
            try:
                spec = loader.get(key)
                opik_prompt = register_prompt_in_opik(spec)
                results[key] = opik_prompt is not None
            except Exception as e:
                logger.warning("Failed to sync prompt %s: %s", key, e)
                results[key] = False

        # Also sync combined prompts
        from backend.utils.prompt_loader import get_rag_prompt, get_casual_prompt, get_refine_prompt

        for name, spec in [
            ("rag_default_combined", get_rag_prompt(is_list_query=False)),
            ("rag_list_combined", get_rag_prompt(is_list_query=True)),
            ("casual_combined", get_casual_prompt()),
            ("refine_combined", get_refine_prompt()),
        ]:
            try:
                opik_prompt = register_prompt_in_opik(spec)
                results[name] = opik_prompt is not None
            except Exception as e:
                logger.warning(
                    "Failed to sync combined prompt %s: %s", name, e)
                results[name] = False

    except ImportError as e:
        logger.warning("Cannot sync prompts - missing dependencies: %s", e)

    return results
