"""
RAG Prompt Library Inspector.

This tool provides a terminal-based dashboard to view the status of all available
prompts in the local library. It displays their version, hash, filesystem path,
and whether they have been synchronized with the Opik Prompt Library in the current
environment context.

Usage:
    PYTHONPATH=. python scripts/view_prompts.py
"""

from backend.utils.prompt_loader import PromptLoader
from backend.utils.opik_prompts import _opik_prompt_cache
import os
import sys
import json
from rich.console import Console
from rich.table import Table

# Add repo root to path to allow importing backend modules
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)


def main():
    """
    Main entry point for the prompt library inspector.
    Scans the prompt directory and displays a status table.
    """
    console = Console()
    loader = PromptLoader()

    # Create a nice UI table using 'rich'
    table = Table(title="RAG Prompt Library Status")
    table.add_column("Prompt Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Hash (Short)", style="magenta")
    table.add_column("Path", style="dim")
    table.add_column("Opik Sync", style="yellow")

    # Locate the central prompt directory
    prompt_dir = loader.PROMPT_DIR
    if not os.path.exists(prompt_dir):
        console.print(f"[red]Prompt directory not found: {prompt_dir}[/]")
        return

    # Iterate through all markdown files in the prompts folder
    for filename in sorted(os.listdir(prompt_dir)):
        # Exclude documentation like README.md from the prompt library view
        if filename.endswith(".md") and filename != "README.md":
            name = filename[:-3]
            try:
                # Retrieve the full specification for the prompt
                spec = loader.get(name)

                # Check if this specific hash is already in the in-memory Opik cache
                is_synced = "✅" if f"{spec.name}:{spec.hash}" in _opik_prompt_cache else "⏳"

                table.add_row(
                    spec.name,
                    spec.version,
                    spec.hash[:8],
                    os.path.relpath(spec.path),
                    is_synced
                )
            except Exception as e:
                table.add_row(name, "[red]Error[/]", "", str(e), "❌")

    console.print(table)

    # Display information about available few-shot examples
    examples_dir = loader.EXAMPLES_DIR
    if os.path.exists(examples_dir):
        console.print(
            f"\n[bold]Few-Shot Examples in {os.path.relpath(examples_dir)}:[/]")
        for f in sorted(os.listdir(examples_dir)):
            if f.endswith(".json"):
                console.print(f" - {f}")


if __name__ == "__main__":
    main()
