from backend.utils.opik_prompts import _opik_prompt_cache
from backend.utils.prompt_loader import PromptLoader
import os
import sys
import json
from rich.console import Console
from rich.table import Table

# Add repo root to path
sys.path.append(os.getcwd())


def main():
    console = Console()
    loader = PromptLoader()

    table = Table(title="RAG Prompt Library Status")
    table.add_column("Prompt Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Hash (Short)", style="magenta")
    table.add_column("Path", style="dim")
    table.add_column("Opik Sync", style="yellow")

    # Identify prompt files
    prompt_dir = loader.PROMPT_DIR
    if not os.path.exists(prompt_dir):
        console.print(f"[red]Prompt directory not found: {prompt_dir}[/]")
        return

    for filename in sorted(os.listdir(prompt_dir)):
        if filename.endswith(".md"):
            name = filename[:-3]
            try:
                spec = loader.get(name)
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

    # Check for examples
    examples_dir = loader.EXAMPLES_DIR
    if os.path.exists(examples_dir):
        console.print(
            f"\n[bold]Few-Shot Examples in {os.path.relpath(examples_dir)}:[/]")
        for f in sorted(os.listdir(examples_dir)):
            if f.endswith(".json"):
                console.print(f" - {f}")


if __name__ == "__main__":
    main()
