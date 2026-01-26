"""
Opik Prompt Synchronization Script.

This script iterates through the local prompts directory, loads each prompt
version and hash, and ensures they are registered in the Opik Prompt Library.
It handles versioning based on 'prompts/versions.json' and skips non-prompt
documentation files like README.md.

Usage:
    PYTHONPATH=. python scripts/sync_prompts_to_opik.py
"""

from backend.utils.opik_prompts import get_or_register_prompt
from backend.utils.prompt_loader import PromptLoader
import os
import sys
import logging

# Add repo root to path to allow importing backend modules
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync_prompts")


def main():
    """
    Main entry point for syncing prompts to Opik.
    Requires OPIK_API_KEY to be set in the environment.
    """
    if not os.getenv("OPIK_API_KEY"):
        print("ERROR: OPIK_API_KEY not set in environment or .env file.")
        sys.exit(1)

    loader = PromptLoader()
    prompt_dir = loader.PROMPT_DIR

    print(f"Syncing prompts from {prompt_dir} to Opik...")

    synced_count = 0
    # List of files to ignore that might live in the prompts/ directory
    IGNORE_FILES = {"README.md", "versions.json"}

    for filename in sorted(os.listdir(prompt_dir)):
        # Only process markdown files that aren't on the ignore list
        if filename.endswith(".md") and filename not in IGNORE_FILES:
            name = filename[:-3]
            try:
                # Load the full prompt specification (text, version, hash)
                spec = loader.get(name)
                print(
                    f" - Registering {spec.name} (v{spec.version})...", end="", flush=True)

                # Register or retrieve the prompt from Opik Library
                opik_prompt = get_or_register_prompt(spec)
                if opik_prompt:
                    print(" ✅ Done")
                    synced_count += 1
                else:
                    print(" ❌ Failed (check logs)")
            except Exception as e:
                print(f" ❌ Error loading {name}: {e}")

    print(
        f"\nSuccessfully synced {synced_count} prompts to Opik (ignored {len(IGNORE_FILES)} documentation/metadata files).")


if __name__ == "__main__":
    main()
