"""
Opik adapter for evaluation runs.
"""

from backend.utils.opik_prompts import get_or_register_prompt
from backend.utils.prompt_loader import get_prompt_spec
import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from .metrics import (
    RecallAt5Metric,
    RecallAt10Metric,
    RecallAllAt5Metric,
    RecallAllAt10Metric,
    HasSourcesMetric,
    CitationComplianceMetric,
    RefusalCorrectMetric,
)

# Add the repo root to the path for backend imports
REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

logger = logging.getLogger(__name__)

# Default Opik project for evaluations
DEFAULT_EVAL_PROJECT = "internal-knowledge-assistant-eval"


class OpikAdapter:
    """
    Adapter for logging evaluation runs to Opik using the evaluate() API.
    Creates proper Experiments that appear in the Opik Experiments tab.
    """

    def __init__(
        self,
        project_name: Optional[str] = None,
        dataset_name: str = "stock_eval_v1",
    ):
        self.project_name = project_name or os.getenv(
            "OPIK_EVAL_PROJECT_NAME", DEFAULT_EVAL_PROJECT
        )
        self.dataset_name = dataset_name
        self._client = None
        self._dataset = None
        self._enabled = self._check_enabled()

    def _check_enabled(self) -> bool:
        """Check if Opik is configured."""
        try:
            from backend.config.test_settings import test_settings
            api_key = os.getenv("OPIK_API_KEY")
            return bool(api_key) and test_settings.opik_enabled
        except ImportError:
            return bool(os.getenv("OPIK_API_KEY"))

    def _get_client(self):
        """Get or create Opik client."""
        if self._client is None and self._enabled:
            try:
                import opik
                self._client = opik.Opik()
            except Exception as e:
                logger.warning("Could not create Opik client: %s", e)
                self._enabled = False
        return self._client

    def _get_run_name(self) -> str:
        """Generate run name with timestamp and git commit."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        try:
            commit = (
                subprocess.check_output(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=REPO_ROOT,
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
        except Exception:
            commit = "unknown"
        return f"eval_{timestamp}_{commit}"

    def _get_or_create_dataset(self):
        """Get or create the Opik dataset."""
        if self._dataset is not None:
            return self._dataset

        client = self._get_client()
        if not client:
            return None

        try:
            self._dataset = client.get_or_create_dataset(
                name=self.dataset_name,
                description="RAG evaluation dataset for stock documents",
            )
            return self._dataset
        except Exception as e:
            logger.warning("Could not get/create Opik dataset: %s", e)
            return None

    def upload_dataset_items(self, samples: List[Dict[str, Any]]) -> bool:
        """Upload dataset items to Opik dataset."""
        if not self._enabled:
            return False

        dataset = self._get_or_create_dataset()
        if dataset is None:
            return False

        try:
            items = []
            for sample in samples:
                items.append({
                    "input": {
                        "id": sample.get("id", ""),
                        "query": sample.get("query", ""),
                        "intent": sample.get("intent", ""),
                    },
                    "expected_output": {
                        "expected_file_ids": sample.get("expected_file_ids", []),
                        "must_cite": sample.get("must_cite", False),
                        "required_citations_count": sample.get("required_citations_count", 0),
                        "must_refuse": sample.get("must_refuse", False),
                        "is_out_of_scope": sample.get("is_out_of_scope", False),
                    },
                    "metadata": {
                        "answer_style": sample.get("answer_style", "paragraph"),
                        "max_entities": sample.get("max_entities", 0),
                        "no_external_knowledge": sample.get("no_external_knowledge", True),
                        "allowed_uncertainty": sample.get("allowed_uncertainty", False),
                    },
                })
            dataset.insert(items)
            logger.info("Uploaded %d items to Opik dataset: %s",
                        len(items), self.dataset_name)
            return True
        except Exception as e:
            logger.warning("Failed to upload dataset items: %s", e)
            return False

    async def run_evaluation(
        self,
        rag_adapter: Any,
        samples: List[Dict[str, Any]],
        experiment_name: Optional[str] = None,
    ) -> Optional[str]:
        """Run evaluation using Opik's evaluate() API."""
        if not self._enabled:
            logger.info("Opik logging disabled, skipping")
            return None

        try:
            from opik.evaluation import evaluate

            self.upload_dataset_items(samples)
            dataset = self._get_or_create_dataset()
            if dataset is None:
                return None

            run_name = experiment_name or self._get_run_name()

            def sync_evaluation_task(dataset_item):
                query = dataset_item.get("input", {}).get("query", "")
                sample_id = dataset_item.get("input", {}).get("id", "")
                response, node_ids, file_ids, latency_ms = rag_adapter.query(
                    query)
                llm_data = getattr(response, "metadata", {}
                                   ).get("llm_output_obj", {})
                return {
                    "output": llm_data.get("answer_md", str(response)),
                    "sample_id": sample_id,
                    "retrieved_file_ids": file_ids,
                    "retrieved_node_ids": node_ids,
                    "latency_ms": latency_ms,
                    "structured": {
                        "refused": llm_data.get("refused", False),
                        "refusal_reason": llm_data.get("refusal_reason", "unknown"),
                        "citations_count": len(llm_data.get("citations", [])),
                        "is_structured": bool(llm_data)
                    }
                }

            prompt_spec = get_prompt_spec("rag_system")
            opik_prompt = get_or_register_prompt(prompt_spec)

            evaluate(
                dataset=dataset,
                task=sync_evaluation_task,
                scoring_metrics=[
                    RecallAt5Metric(),
                    RecallAt10Metric(),
                    RecallAllAt5Metric(),
                    RecallAllAt10Metric(),
                    HasSourcesMetric(),
                    CitationComplianceMetric(),
                    RefusalCorrectMetric(),
                ],
                experiment_name=run_name,
                project_name=self.project_name,
                prompt=opik_prompt,
                task_threads=10
            )

            logger.info("Opik experiment created: %s", run_name)
            return run_name
        except Exception as e:
            logger.error("Failed to run Opik evaluation: %s", e)
            return None

    @property
    def enabled(self) -> bool:
        return self._enabled
