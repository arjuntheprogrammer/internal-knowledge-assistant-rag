"""
Utility to manage Opik datasets (list, info, clear, sync).

Usage:
    conda run -n internal-knowledge-assistant python -m evals.runner.opik.manage --list
    conda run -n internal-knowledge-assistant python -m evals.runner.opik.manage --dataset-name stock_eval_v1 --sync evals/datasets/stock_eval_v1.jsonl
"""

import argparse
import json
import logging
import os
import sys
from dotenv import load_dotenv

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

load_dotenv(os.path.join(REPO_ROOT, ".env"))
logger = logging.getLogger(__name__)


def get_opik_client():
    try:
        import opik
        return opik.Opik()
    except ImportError:
        logger.error("Opik SDK not installed.")
        sys.exit(1)


def list_datasets():
    client = get_opik_client()
    datasets = client.get_datasets()
    print(f"\n📊 Available Opik Datasets:")
    print(f"{'Name':<40} {'Items':<10}")
    print("-" * 60)
    for ds in datasets:
        print(f"{ds.name:<40} {ds.dataset_items_count:<10}")


def get_info(name):
    client = get_opik_client()
    try:
        ds = client.get_dataset(name=name)
        items = ds.get_items()
        print(f"\n📁 Dataset: {ds.name} (Items: {len(items) if items else 0})")
    except Exception as e:
        logger.error(f"Failed: {e}")


def sync_dataset(name, local_file):
    client = get_opik_client()
    samples = []
    with open(local_file, "r") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    ds = client.get_or_create_dataset(name=name)
    ds.clear()

    items = []
    for s in samples:
        items.append({
            "input": {"id": s.get("id"), "query": s.get("query"), "intent": s.get("intent")},
            "expected_output": {
                "expected_file_ids": s.get("expected_file_ids"),
                "must_cite": s.get("must_cite"),
                "required_citations_count": s.get("required_citations_count"),
                "must_refuse": s.get("must_refuse"),
                "is_out_of_scope": s.get("is_out_of_scope")
            },
            "metadata": {
                "answer_style": s.get("answer_style"),
                "max_entities": s.get("max_entities")
            }
        })
    ds.insert(items)
    print(f"✅ Sync complete for {name} ({len(items)} items).")


def main():
    parser = argparse.ArgumentParser(description="Manage Opik Datasets")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dataset-name")
    parser.add_argument("--info", action="store_true")
    parser.add_argument("--sync", metavar="JSONL_FILE")

    args = parser.parse_args()
    if args.list:
        list_datasets()
    elif args.dataset_name:
        if args.info:
            get_info(args.dataset_name)
        elif args.sync:
            sync_dataset(args.dataset_name, args.sync)


if __name__ == "__main__":
    main()
