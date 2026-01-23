import os
import json
import hashlib
import logging
from dataclasses import dataclass
from typing import Dict, Optional

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

    # New location as per PRD
    PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
    VERSION_FILE = os.path.join(PROMPT_DIR, "versions.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptLoader, cls).__new__(cls)
        return cls._instance

    def _get_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

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

        spec = PromptSpec(
            name=name,
            version=versions.get(name, "unknown"),
            text=text,
            hash=self._get_hash(text),
            path=file_path
        )

        self._cache[name] = spec
        return spec


def load_prompt(name: str) -> str:
    """Convenience function to get prompt text."""
    return PromptLoader().get(name).text


def get_prompt_spec(name: str) -> PromptSpec:
    """Convenience function to get full spec."""
    return PromptLoader().get(name)
