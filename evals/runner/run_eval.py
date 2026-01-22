#!/usr/bin/env python3
"""
RAG Evaluation Runner

Run evaluation queries against the RAG system and report metrics to Opik.

Usage:
    python -m evals.runner.run_eval \
        --dataset evals/datasets/stock_eval_v1.jsonl \
        --user-id <firebase_user_id> \
        --k 10 \
        --opik-project internal-knowledge-assistant-evals \
        --opik-dataset stock_eval_v1
"""

from evals.runner.schema import EvalResult, EvalSample, EvalSummary
from evals.runner.metrics import compute_metrics, compute_summary
from evals.runner.adapters import RAGAdapter, OpikAdapter
from dotenv import load_dotenv
import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load environment variables

load_dotenv(REPO_ROOT / ".env")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_dataset(path: str) -> List[EvalSample]:
    """Load evaluation dataset from JSONL file."""
    samples = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                samples.append(EvalSample.from_dict(data))
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse line: %s", e)
    logger.info("Loaded %d samples from %s", len(samples), path)
    return samples


def load_file_id_mapping(dataset_dir: str) -> dict:
    """Load file ID to filename mapping."""
    mapping_path = Path(dataset_dir) / "file_id_mapping.json"
    if not mapping_path.exists():
        return {}
    with open(mapping_path, "r") as f:
        return json.load(f)


def extract_entity_names_from_mapping(mapping: dict) -> Set[str]:
    """Extract entity names from file ID mapping for entity validation."""
    entities = set()
    for filename in mapping.values():
        # Remove .docx extension and get company name
        name = filename.replace(".docx", "").replace(".pdf", "").strip()
        entities.add(name)
        # Also add parts of the name
        parts = name.split()
        if len(parts) > 1:
            entities.add(parts[0])
    return entities


def run_single_query(
    adapter: RAGAdapter,
    sample: EvalSample,
) -> EvalResult:
    """Run a single query and capture results."""
    result = EvalResult(
        sample_id=sample.id,
        query=sample.query,
        intent=sample.intent,
        expected_file_ids=sample.expected_file_ids,
    )

    try:
        response, node_ids, file_ids, latency_ms = adapter.query(sample.query)

        # Extract answer text
        if hasattr(response, "response"):
            result.answer_text = response.response or ""
        else:
            result.answer_text = str(response)

        result.retrieved_node_ids = node_ids
        result.retrieved_file_ids = file_ids
        result.citation_file_ids = file_ids  # Use retrieved as citation proxy
        result.latency_ms = latency_ms

    except Exception as e:
        logger.error("Query failed for %s: %s", sample.id, e)
        result.error = str(e)

    return result


def print_summary(summary: EvalSummary):
    """Print summary statistics to stdout."""
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total samples:       {summary.total_samples}")
    print(f"Successful:          {summary.successful_samples}")
    print(f"Failed:              {summary.failed_samples}")
    print("-" * 60)
    print(f"Mean Latency:        {summary.mean_latency_ms:.1f} ms")
    print("-" * 60)
    print("RETRIEVAL METRICS")
    print(f"  Recall@5:          {summary.mean_recall_at_5:.2%}")
    print(f"  Recall@10:         {summary.mean_recall_at_10:.2%}")
    print(f"  Recall-All@5:      {summary.mean_recall_all_at_5:.2%}")
    print(f"  Recall-All@10:     {summary.mean_recall_all_at_10:.2%}")
    print("-" * 60)
    print("CITATION COMPLIANCE")
    print(f"  Samples requiring citations: {summary.cite_samples_count}")
    print(f"  Compliance rate:   {summary.cite_compliance_rate:.2%}")
    print("-" * 60)
    print("REFUSAL CORRECTNESS")
    print(f"  Samples requiring refusal: {summary.refusal_samples_count}")
    print(f"  Correctness rate:  {summary.refusal_correctness_rate:.2%}")
    print("=" * 60)


def save_results(
    results: List[EvalResult],
    summary: EvalSummary,
    output_dir: Path,
    timestamp: str,
):
    """Save results to files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save detailed results
    results_path = output_dir / f"{timestamp}_results.jsonl"
    with open(results_path, "w") as f:
        for result in results:
            f.write(json.dumps(result.to_dict()) + "\n")
    logger.info("Saved results to %s", results_path)

    # Save summary
    summary_path = output_dir / f"{timestamp}_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary.to_dict(), f, indent=2)
    logger.info("Saved summary to %s", summary_path)


def main():
    parser = argparse.ArgumentParser(description="Run RAG evaluation")
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="Path to JSONL dataset file",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=os.getenv("EVAL_USER_ID", "NUsot0aGhVMGEEnu9RujAPSRXtv2"),
        help="Firebase user ID for retrieval context (default: NUsot0aGhVMGEEnu9RujAPSRXtv2)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=10,
        help="Top-k for retrieval metrics (default: 10)",
    )
    parser.add_argument(
        "--opik-project",
        type=str,
        default=None,
        help="Opik project name (default: from env)",
    )
    parser.add_argument(
        "--opik-dataset",
        type=str,
        default="stock_eval_v1",
        help="Opik dataset name (default: stock_eval_v1)",
    )
    parser.add_argument(
        "--no-opik",
        action="store_true",
        help="Disable Opik logging",
    )
    parser.add_argument(
        "--openai-key",
        type=str,
        default=None,
        help="OpenAI API key (default: from env)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of samples to run (for testing)",
    )
    parser.add_argument(
        "--use-opik-experiment",
        action="store_true",
        default=True,
        help="Use Opik's evaluate() API for proper Experiments (default: True)",
    )

    args = parser.parse_args()

    # Validate dataset path
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error("Dataset not found: %s", dataset_path)
        sys.exit(1)

    # Load dataset
    samples = load_dataset(str(dataset_path))
    if not samples:
        logger.error("No samples loaded from dataset")
        sys.exit(1)

    if args.limit:
        samples = samples[: args.limit]
        logger.info("Limited to %d samples", len(samples))

    # Load file ID mapping for entity validation
    dataset_dir = dataset_path.parent
    file_id_mapping = load_file_id_mapping(str(dataset_dir))
    allowed_entities = extract_entity_names_from_mapping(file_id_mapping)

    # Initialize RAG adapter
    logger.info("Initializing RAG adapter for user: %s", args.user_id)
    rag_adapter = RAGAdapter(user_id=args.user_id,
                             openai_api_key=args.openai_key)
    if not rag_adapter.initialize():
        logger.error("Failed to initialize RAG adapter")
        sys.exit(1)

    # Initialize Opik adapter
    opik_adapter = None
    if not args.no_opik:
        opik_adapter = OpikAdapter(
            project_name=args.opik_project,
            dataset_name=args.opik_dataset,
        )
        if opik_adapter.enabled:
            logger.info("Opik logging enabled (project: %s)",
                        opik_adapter.project_name)
        else:
            logger.info("Opik not configured, logging disabled")

    # Run evaluation
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    results: List[EvalResult] = []

    # Check if we should use Opik experiment evaluation
    use_opik_experiment = (
        opik_adapter
        and opik_adapter.enabled
        and args.use_opik_experiment
    )

    if use_opik_experiment:
        # Use Opik's evaluate() API for proper Experiments
        logger.info("Running evaluation using Opik Experiment API...")
        sample_dicts = [
            {
                "id": s.id,
                "query": s.query,
                "intent": s.intent,
                "expected_file_ids": s.expected_file_ids,
                "must_cite": s.must_cite,
                "required_citations_count": s.required_citations_count,
                "answer_style": s.answer_style,
                "max_entities": s.max_entities,
                "is_out_of_scope": s.is_out_of_scope,
                "must_refuse": s.must_refuse,
                "no_external_knowledge": s.no_external_knowledge,
                "allowed_uncertainty": s.allowed_uncertainty,
            }
            for s in samples
        ]

        experiment_name = opik_adapter.run_evaluation(
            rag_adapter=rag_adapter,
            samples=sample_dicts,
            compute_metrics_fn=compute_metrics,
            experiment_name=f"eval_{timestamp}",
        )

        if experiment_name:
            logger.info("Opik experiment created: %s", experiment_name)
        else:
            logger.warning(
                "Opik experiment creation failed, falling back to manual evaluation")
            use_opik_experiment = False

    if not use_opik_experiment:
        # Manual evaluation loop (fallback or when Opik is disabled)
        logger.info("Starting manual evaluation of %d samples...", len(samples))
        for idx, sample in enumerate(samples, 1):
            logger.info("[%d/%d] Running: %s", idx, len(samples), sample.id)

            result = run_single_query(rag_adapter, sample)

            # Compute metrics
            result = compute_metrics(sample, result, allowed_entities)
            results.append(result)

            # Progress update
            if result.error:
                logger.warning("  Error: %s", result.error)
            else:
                logger.info(
                    "  Recall@5=%.2f Recall@10=%.2f Latency=%.0fms",
                    result.recall_at_5,
                    result.recall_at_10,
                    result.latency_ms,
                )

        # Compute summary
        summary = compute_summary(results, samples)

        # Print summary
        print_summary(summary)

        # Save results
        output_dir = REPO_ROOT / "evals" / "runs"
        save_results(results, summary, output_dir, timestamp)

        # Log to Opik using traces (if experiment mode wasn't used)
        if opik_adapter and opik_adapter.enabled:
            result_dicts = [r.to_dict() for r in results]
            sample_dicts = [
                {
                    "id": s.id,
                    "query": s.query,
                    "intent": s.intent,
                    "expected_file_ids": s.expected_file_ids,
                    "must_cite": s.must_cite,
                    "required_citations_count": s.required_citations_count,
                    "answer_style": s.answer_style,
                    "max_entities": s.max_entities,
                    "is_out_of_scope": s.is_out_of_scope,
                    "must_refuse": s.must_refuse,
                    "no_external_knowledge": s.no_external_knowledge,
                    "allowed_uncertainty": s.allowed_uncertainty,
                }
                for s in samples
            ]
            opik_adapter.log_evaluation_run(
                result_dicts, summary.to_dict(), sample_dicts
            )

    logger.info("Evaluation complete!")

    # Return code depends on whether we have a summary (manual mode) or not (opik experiment mode)
    if use_opik_experiment:
        return 0  # Success if experiment was created
    return 0 if summary.failed_samples == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
