"""
Prompt Loader Utility.

Loads prompt files from the prompts/ directory with versioning and hashing
for Opik tracking and reproducibility.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Repository root
REPO_ROOT = Path(__file__).parent.parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"


@dataclass
class PromptSpec:
    """Specification for a loaded prompt."""
    name: str
    version: str
    text: str
    hash: str
    path: str

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "version": self.version,
            "hash": self.hash,
            "path": self.path,
        }


class PromptLoader:
    """
    Loads and manages prompts from the prompts/ directory.

    Prompts are loaded from markdown files and versioned via versions.json.
    Each prompt is hashed for tracking in Opik.
    """

    _instance: Optional["PromptLoader"] = None
    _cache: Dict[str, PromptSpec] = {}
    _versions: Dict[str, str] = {}

    # Valid prompt keys
    VALID_KEYS = {
        "shared_json_schema",
        "rag_default_json",
        "rag_list_json",
        "rag_refine_json",
        "casual_json",
    }

    def __new__(cls) -> "PromptLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_versions()
        return cls._instance

    def _load_versions(self) -> None:
        """Load version strings from versions.json."""
        versions_path = PROMPTS_DIR / "versions.json"
        if versions_path.exists():
            try:
                with open(versions_path, "r") as f:
                    self._versions = json.load(f)
                logger.info("Loaded prompt versions: %s", self._versions)
            except Exception as e:
                logger.warning("Failed to load versions.json: %s", e)
                self._versions = {}
        else:
            logger.warning("versions.json not found at %s", versions_path)
            self._versions = {}

    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of prompt text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def get(self, prompt_key: str) -> PromptSpec:
        """
        Get a prompt specification by key.

        Args:
            prompt_key: One of the valid prompt keys (e.g., 'rag_default_json')

        Returns:
            PromptSpec with name, version, text, hash, and path

        Raises:
            ValueError: If prompt_key is invalid
            FileNotFoundError: If prompt file does not exist
        """
        if prompt_key not in self.VALID_KEYS:
            raise ValueError(
                f"Invalid prompt key: {prompt_key}. "
                f"Valid keys: {self.VALID_KEYS}"
            )

        # Return cached if available
        if prompt_key in self._cache:
            return self._cache[prompt_key]

        # Load from file
        prompt_path = PROMPTS_DIR / f"{prompt_key}.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        with open(prompt_path, "r") as f:
            text = f.read()

        version = self._versions.get(prompt_key, "unknown")
        prompt_hash = self._compute_hash(text)

        spec = PromptSpec(
            name=prompt_key,
            version=version,
            text=text,
            hash=prompt_hash,
            path=str(prompt_path),
        )

        self._cache[prompt_key] = spec
        logger.debug(
            "Loaded prompt %s (version=%s, hash=%s)",
            prompt_key, version, prompt_hash
        )

        return spec

    def get_combined(self, *prompt_keys: str) -> PromptSpec:
        """
        Get multiple prompts combined into one.

        The schema prompt is typically prepended to task-specific prompts.

        Args:
            *prompt_keys: Keys to combine (e.g., 'shared_json_schema', 'rag_default_json')

        Returns:
            Combined PromptSpec with merged text
        """
        specs = [self.get(key) for key in prompt_keys]

        combined_text = "\n\n".join(spec.text for spec in specs)
        combined_name = "+".join(spec.name for spec in specs)
        combined_version = "+".join(spec.version for spec in specs)
        combined_hash = self._compute_hash(combined_text)

        return PromptSpec(
            name=combined_name,
            version=combined_version,
            text=combined_text,
            hash=combined_hash,
            path=",".join(spec.path for spec in specs),
        )

    def clear_cache(self) -> None:
        """Clear the prompt cache (useful for testing/reloading)."""
        self._cache.clear()
        self._load_versions()


# Convenience function
@lru_cache(maxsize=32)
def get_prompt(prompt_key: str) -> PromptSpec:
    """Get a prompt by key (cached)."""
    return PromptLoader().get(prompt_key)


def get_rag_prompt(is_list_query: bool = False) -> PromptSpec:
    """
    Get the appropriate RAG prompt based on query type.

    Args:
        is_list_query: Whether this is a list enumeration query

    Returns:
        Combined PromptSpec with schema + task prompt
    """
    loader = PromptLoader()
    task_key = "rag_list_json" if is_list_query else "rag_default_json"
    return loader.get_combined("shared_json_schema", task_key)


def get_refine_prompt() -> PromptSpec:
    """Get the RAG refine prompt."""
    loader = PromptLoader()
    return loader.get_combined("shared_json_schema", "rag_refine_json")


def get_casual_prompt() -> PromptSpec:
    """Get the casual chat prompt."""
    loader = PromptLoader()
    return loader.get_combined("shared_json_schema", "casual_json")
