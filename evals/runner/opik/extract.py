"""
Utility to extract Opik experiment results programmatically.

Usage:
    conda run -n internal-knowledge-assistant python -m evals.runner.opik.extract --list-experiments
    conda run -n internal-knowledge-assistant python -m evals.runner.opik.extract --experiment-name eval_20260126_081337
"""

from dotenv import load_dotenv
from typing import Optional
from datetime import datetime
import sys
import os
import logging
import json
import argparse

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Load environment variables from .env
load_dotenv(os.path.join(REPO_ROOT, ".env"))

logger = logging.getLogger(__name__)


def get_opik_client():
    try:
        import opik
        return opik.Opik()
    except ImportError:
        logger.error("Opik SDK not installed.")
        sys.exit(1)


def list_recent_experiments(project_name: str = "internal-knowledge-assistant-eval", limit: int = 10):
    print(f"\n📊 To list experiments, use the Opik UI at:")
    print(f"https://www.comet.com/opik/arjun-gupta/projects")
    print(f"\nOr provide a specific --experiment-name to extract its results.")


def extract_results(
    experiment_name: Optional[str] = None,
    experiment_id: Optional[str] = None,
    project_name: str = "internal-knowledge-assistant-eval",
    output_file: Optional[str] = None
):
    client = get_opik_client()

    if experiment_id:
        experiment = client.get_experiment_by_id(experiment_id)
    elif experiment_name:
        experiment = client.get_experiment_by_name(name=experiment_name)
    else:
        logger.error(
            "Must provide either --experiment-name or --experiment-id")
        return None

    print(f"\n🔍 Extracting items from experiment: {experiment.name}")
    items = experiment.get_items(truncate=False)

    results = {
        "experiment_id": experiment.id,
        "experiment_name": experiment.name,
        "project_name": project_name,
        "extracted_at": datetime.utcnow().isoformat(),
        "total_items": len(items),
        "items": []
    }

    for item in items:
        item_data = {
            "id": getattr(item, 'id', None),
            "input": getattr(item, 'input', {}),
            "output": getattr(item, 'output', {}),
            "expected_output": getattr(item, 'expected_output', {}),
            "feedback_scores": [],
            "trace_id": getattr(item, 'trace_id', None),
        }
        if hasattr(item, 'feedback_scores') and item.feedback_scores:
            for score in item.feedback_scores:
                item_data["feedback_scores"].append({
                    "name": score.get("name") if isinstance(score, dict) else getattr(score, 'name', None),
                    "value": score.get("value") if isinstance(score, dict) else getattr(score, 'value', None),
                    "reason": score.get("reason") if isinstance(score, dict) else getattr(score, 'reason', None),
                })
        results["items"].append(item_data)

    metrics_summary = {}
    for item in results["items"]:
        for score in item["feedback_scores"]:
            name = score["name"]
            if name not in metrics_summary:
                metrics_summary[name] = []
            if score["value"] is not None:
                metrics_summary[name].append(score["value"])

    results["summary_metrics"] = {}
    for name, values in metrics_summary.items():
        if values:
            results["summary_metrics"][name] = {
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "count": len(values)
            }

    print(f"\n✅ Extracted {len(items)} items")
    for name, stats in results["summary_metrics"].items():
        print(f"  {name}: Mean {stats['mean']:.4f}")

    if output_file:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"💾 Saved to: {output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Extract Opik experiment results")
    parser.add_argument("--experiment-name", help="Experiment name")
    parser.add_argument("--experiment-id", help="Experiment ID")
    parser.add_argument(
        "--project-name", default="internal-knowledge-assistant-eval")
    parser.add_argument("--list-experiments", action="store_true")
    parser.add_argument("--output-file", help="Output JSON path")

    args = parser.parse_args()
    if args.list_experiments:
        list_recent_experiments(project_name=args.project_name)
    else:
        extract_results(args.experiment_name, args.experiment_id,
                        args.project_name, args.output_file)


if __name__ == "__main__":
    main()
