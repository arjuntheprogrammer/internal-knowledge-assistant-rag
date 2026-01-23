import os
import json
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)


@dataclass
class PromptSpec:
    name: str
    version: str
    text: str
    hash: str
    path: str


class PromptLoader:
    _instance = None
    _cache: Dict[str, PromptSpec] = {}

    # Prompts now at repo root
    PROMPT_DIR = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "prompts"))
    VERSION_FILE = os.path.join(PROMPT_DIR, "versions.json")
    EXAMPLES_DIR = os.path.join(PROMPT_DIR, "examples")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptLoader, cls).__new__(cls)
        return cls._instance

    def _get_hash(self, text: str) -> str:
        # Normalize whitespace for deterministic hashing (ignore just reformatting)
        normalized = re.sub(r"\s+", " ", text).strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, name: str) -> PromptSpec:
        """Load a prompt by name (e.g., 'rag_system')."""
        if name in self._cache:
            return self._cache[name]

        # Load versions
        versions = {}
        if os.path.exists(self.VERSION_FILE):
            try:
                with open(self.VERSION_FILE, "r") as f:
                    versions = json.load(f)
            except Exception as e:
                logger.warning("Failed to load versions.json: %s", e)

        filename = f"{name}.md" if not name.endswith(".md") else name
        file_path = os.path.join(self.PROMPT_DIR, filename)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        with open(file_path, "r") as f:
            text = f.read()

        # Strip .md for version lookup
        version_key = name[:-3] if name.endswith(".md") else name
        spec = PromptSpec(
            name=name,
            version=versions.get(version_key, "unknown"),
            text=text,
            hash=self._get_hash(text),
            path=file_path
        )

        self._cache[name] = spec
        return spec

    def load_examples(self, name: str) -> List[Dict[str, Any]]:
        """Load few-shot examples for a prompt if they exist."""
        filename = f"{name}.json" if not name.endswith(".json") else name
        file_path = os.path.join(self.EXAMPLES_DIR, filename)

        if not os.path.exists(file_path):
            return []

        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load examples from %s: %s", file_path, e)
            return []


def load_prompt(name: str) -> str:
    """Convenience function to get prompt text."""
    return PromptLoader().get(name).text


def get_prompt_spec(name: str) -> PromptSpec:
    """Convenience function to get full spec."""
    return PromptLoader().get(name)


def load_examples(name: str) -> List[Dict[str, Any]]:
    """Convenience function to get examples."""
    return PromptLoader().load_examples(name)
