import logging
import os
from typing import Optional, Any
from .prompt_loader import PromptSpec

logger = logging.getLogger(__name__)

# Cache to avoid repeated registration calls in the same process
_opik_prompt_cache = {}


def get_or_register_prompt(prompt_spec: PromptSpec) -> Optional[Any]:
    """
    Registers a prompt in the Opik Prompt Library and returns the Opik Prompt object.
    Uses hashing to avoid redundant registrations.
    """
    cache_key = f"{prompt_spec.name}:{prompt_spec.hash}"
    if cache_key in _opik_prompt_cache:
        return _opik_prompt_cache[cache_key]

    try:
        import opik
        from opik import Prompt

        # Check if Opik is configured
        if not os.getenv("OPIK_API_KEY"):
            return None

        # Opik Prompt class handles creation/retrieval automatically
        opik_prompt = Prompt(
            name=prompt_spec.name,
            prompt=prompt_spec.text,
            metadata={
                "version": prompt_spec.version,
                "hash": prompt_spec.hash,
                "path": prompt_spec.path,
            }
        )

        _opik_prompt_cache[cache_key] = opik_prompt
        logger.info("Synchronized prompt with Opik Library: %s (v%s)",
                    prompt_spec.name, prompt_spec.version)
        return opik_prompt

    except ImportError:
        logger.debug("Opik SDK not installed, skipping prompt registration.")
        return None
    except Exception as e:
        logger.warning("Failed to register prompt in Opik: %s", e)
        return None


def link_prompts_to_current_trace(prompts: list):
    """Links multiple opik.Prompt objects to the current active trace."""
    try:
        from opik.opik_context import update_current_trace
        valid_prompts = [p for p in prompts if p is not None]
        if valid_prompts:
            update_current_trace(prompts=valid_prompts)
    except Exception:
        pass
