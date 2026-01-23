"""
Adapters for RAG query engine and Opik integration.
"""

from llama_index.core.schema import QueryBundle
from llama_index.core.base.response.schema import Response
from llama_index.core import VectorStoreIndex
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Add the repo root to the path for backend imports
REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


logger = logging.getLogger(__name__)

# Default Opik project for evaluations
DEFAULT_EVAL_PROJECT = "internal-knowledge-assistant-eval"


class RAGAdapter:
    """
    Adapter to run queries through the RAG system.
    Supports two modes:
    - Option A: Use existing services (real index from vector store)
    - Option B: Direct rebuild from vector store
    """

    def __init__(self, user_id: str, openai_api_key: Optional[str] = None):
        self.user_id = user_id
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._index = None
        self._bm25_nodes = None
        self._service_context = None
        self._query_engine = None

    def _get_service_context(self):
        """Get LlamaIndex settings/service context."""
        if self._service_context is None:
            from backend.services.rag.rag_context import get_service_context

            self._service_context = get_service_context(
                self.openai_api_key, user_id=self.user_id
            )
        return self._service_context

    def _get_vector_store(self):
        """Get Milvus vector store."""
        from backend.services.rag.rag_milvus import get_milvus_vector_store

        return get_milvus_vector_store(user_id=self.user_id)

    def _rebuild_index(self) -> Optional[VectorStoreIndex]:
        """Rebuild index from vector store."""
        try:
            vector_store = self._get_vector_store()
            if not vector_store:
                logger.warning(
                    "No vector store available for user %s", self.user_id)
                return None

            settings = self._get_service_context()
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                callback_manager=settings.callback_manager,
            )
            logger.info("Successfully rebuilt index for user %s", self.user_id)
            return index
        except Exception as e:
            logger.error("Failed to rebuild index: %s", e)
            return None

    def _try_existing_services(self) -> bool:
        """Try to use existing RAG services (Option A)."""
        try:
            from backend.services.rag import RAGService

            index = RAGService.get_index(self.user_id)
            if index is not None:
                self._index = index
                self._bm25_nodes = RAGService.get_bm25_nodes(self.user_id)
                return True

            # Try to rebuild from vector store
            index = self._rebuild_index()
            if index is not None:
                self._index = index
                RAGService._index_by_user[self.user_id] = index
                return True
            return False
        except Exception as e:
            logger.warning("Could not use existing services: %s", e)
            return False

    def initialize(self) -> bool:
        """Initialize the adapter, prefer Option A, fallback to Option B."""
        if self._try_existing_services():
            logger.info("Using existing RAG services (Option A)")
            return True

        # Fallback: direct rebuild
        logger.info("Falling back to direct rebuild (Option B)")
        self._index = self._rebuild_index()
        return self._index is not None

    def query(self, query_str: str) -> Tuple[Any, List[str], List[str], float]:
        """
        Run a query through the production RAGService and return results.
        This ensures evaluation is as realistic as possible by using the
        exact production stack (including routing and lazy loading).
        """
        from backend.services.rag import RAGService

        user_context = {
            "uid": self.user_id,
            "openai_api_key": self.openai_api_key
        }

        start_time = time.time()
        result = RAGService.query(
            query_str, user_context, return_structured=True)
        llm = result.get("llm", {})
        latency_ms = (time.time() - start_time) * 1000

        from llama_index.core.base.response.schema import Response
        from llama_index.core.schema import NodeWithScore, TextNode

        source_nodes = []
        hits = result.get("retrieval", {}).get("hits", [])
        for hit in hits:
            source_nodes.append(NodeWithScore(
                node=TextNode(id_=hit["node_id"], text=hit.get(
                    "text", ""), metadata={"file_id": hit["file_id"]}),
                score=hit.get("score")
            ))

        response = Response(
            response=llm.get("answer_md", ""),
            source_nodes=source_nodes,
            metadata={"llm_output_obj": llm}
        )

        # Extract node IDs and file IDs from source nodes
        node_ids = []
        file_ids = []
        seen_file_ids = set()

        source_nodes = getattr(response, "source_nodes", [])
        if source_nodes:
            for node_with_score in source_nodes:
                node = getattr(node_with_score, "node", None)
                if node:
                    node_id = getattr(node, "node_id", None) or getattr(
                        node, "id_", None)
                    if node_id:
                        node_ids.append(node_id)

                    metadata = getattr(node, "metadata", {}) or {}
                    file_id = metadata.get(
                        "file_id") or metadata.get("file id")
                    if file_id and file_id not in seen_file_ids:
                        file_ids.append(file_id)
                        seen_file_ids.add(file_id)

        # For metric functions that expect a string, ensure response is string-ifiable
        # or has a .response attribute
        return response, node_ids, file_ids, latency_ms


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
        api_key = os.getenv("OPIK_API_KEY")
        enabled_env = os.getenv("OPIK_ENABLED", "true").lower()
        return bool(api_key) and enabled_env not in ("false", "0", "no")

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
        """
        Upload dataset items (the eval queries) to Opik dataset.
        """
        if not self._enabled:
            return False

        dataset = self._get_or_create_dataset()
        if dataset is None:
            return False

        try:
            # Prepare dataset items
            items = []
            for sample in samples:
                items.append(
                    {
                        "input": {
                            "id": sample.get("id", ""),
                            "query": sample.get("query", ""),
                            "intent": sample.get("intent", ""),
                        },
                        "expected_output": {
                            "expected_file_ids": sample.get("expected_file_ids", []),
                            "must_cite": sample.get("must_cite", False),
                            "required_citations_count": sample.get(
                                "required_citations_count", 0
                            ),
                            "must_refuse": sample.get("must_refuse", False),
                            "is_out_of_scope": sample.get("is_out_of_scope", False),
                        },
                        "metadata": {
                            "answer_style": sample.get("answer_style", "paragraph"),
                            "max_entities": sample.get("max_entities", 0),
                            "no_external_knowledge": sample.get(
                                "no_external_knowledge", True
                            ),
                            "allowed_uncertainty": sample.get(
                                "allowed_uncertainty", False
                            ),
                        },
                    }
                )

            # Insert items into dataset
            dataset.insert(items)
            logger.info(
                "Uploaded %d items to Opik dataset: %s", len(
                    items), self.dataset_name
            )
            return True
        except Exception as e:
            logger.warning("Failed to upload dataset items: %s", e)
            return False

    def run_evaluation(
        self,
        rag_adapter: "RAGAdapter",
        samples: List[Dict[str, Any]],
        compute_metrics_fn,
        experiment_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Run evaluation using Opik's evaluate() API.
        This creates a proper Experiment in Opik.

        Returns the experiment ID if successful.
        """
        if not self._enabled:
            logger.info("Opik logging disabled, skipping")
            return None

        try:
            import opik
            from opik.evaluation import evaluate
            from opik.evaluation.metrics import base_metric, score_result

            # Upload dataset items first
            self.upload_dataset_items(samples)

            dataset = self._get_or_create_dataset()
            if dataset is None:
                return None

            run_name = experiment_name or self._get_run_name()

            # Define the evaluation task that calls our RAG system
            def evaluation_task(dataset_item: Dict[str, Any]) -> Dict[str, Any]:
                query = dataset_item.get("input", {}).get("query", "")
                sample_id = dataset_item.get("input", {}).get("id", "")

                try:
                    response, node_ids, file_ids, latency_ms = rag_adapter.query(
                        query)

                    # Extract data for metrics
                    llm_data = getattr(response, "metadata", {}).get(
                        "llm_output_obj", {})
                    answer_text = llm_data.get("answer_md", str(response))
                    refused = llm_data.get("refused", False)
                    refusal_reason = llm_data.get("refusal_reason", "unknown")
                    citations_count = len(llm_data.get("citations", []))

                    return {
                        "output": answer_text,
                        "sample_id": sample_id,
                        "retrieved_file_ids": file_ids,
                        "retrieved_node_ids": node_ids,
                        "latency_ms": latency_ms,
                        "structured": {
                            "refused": refused,
                            "refusal_reason": refusal_reason,
                            "citations_count": citations_count,
                            "is_structured": bool(llm_data)
                        }
                    }
                except Exception as e:
                    logger.error("Query failed for %s: %s", sample_id, e)
                    return {
                        "output": "",
                        "sample_id": sample_id,
                        "retrieved_file_ids": [],
                        "retrieved_node_ids": [],
                        "latency_ms": 0,
                        "error": str(e),
                    }

            from .opik_metrics import (
                RecallAt5Metric,
                RecallAt10Metric,
                RecallAllAt5Metric,
                RecallAllAt10Metric,
                HasSourcesMetric,
                CitationComplianceMetric,
                RefusalCorrectMetric,
            )

            # Run the evaluation
            result = evaluate(
                dataset=dataset,
                task=evaluation_task,
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
            )

            logger.info(
                "Opik experiment created: %s in project %s",
                run_name,
                self.project_name,
            )
            return run_name

        except Exception as e:
            logger.error("Failed to run Opik evaluation: %s", e)
            import traceback

            traceback.print_exc()
            return None

    def log_evaluation_run(
        self,
        results: List[Dict[str, Any]],
        summary: Dict[str, Any],
        samples: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Log evaluation results to Opik using traces (fallback method).
        Use run_evaluation() for proper Experiments.
        """
        if not self._enabled:
            logger.info("Opik logging disabled, skipping")
            return False

        client = self._get_client()
        if not client:
            return False

        run_name = self._get_run_name()

        try:
            # Create dataset and upload items if provided
            dataset = self._get_or_create_dataset()
            if dataset is None:
                return False

            # Upload dataset items (eval queries) if provided
            if samples:
                self.upload_dataset_items(samples)

            # Log each result as a trace
            for result in results:
                try:
                    trace = client.trace(
                        name=f"eval_{result.get('sample_id', 'unknown')}",
                        project_name=self.project_name,
                        input={"query": result.get("query", "")},
                        output={"answer": result.get("answer_text", "")},
                        metadata={
                            "run_name": run_name,
                            "dataset": self.dataset_name,
                            "sample_id": result.get("sample_id"),
                            "intent": result.get("intent"),
                            "expected_file_ids": result.get("expected_file_ids", []),
                            "retrieved_file_ids": result.get("retrieved_file_ids", []),
                            "recall_at_5": result.get("recall_at_5", 0),
                            "recall_at_10": result.get("recall_at_10", 0),
                            "has_sources_section": result.get(
                                "has_sources_section", False
                            ),
                            "citation_count": result.get("citation_count", 0),
                            "refusal_detected": result.get("refusal_detected", False),
                            "refusal_correct": result.get("refusal_correct"),
                            "latency_ms": result.get("latency_ms", 0),
                            "error": result.get("error"),
                        },
                    )
                    trace.end()
                except Exception as e:
                    logger.warning(
                        "Failed to log trace for %s: %s", result.get(
                            "sample_id"), e
                    )

            # Log summary as a separate trace
            try:
                summary_trace = client.trace(
                    name=f"eval_summary_{run_name}",
                    project_name=self.project_name,
                    input={"run_name": run_name, "dataset": self.dataset_name},
                    output=summary,
                    metadata={"type": "summary", "run_name": run_name},
                )
                summary_trace.end()
            except Exception as e:
                logger.warning("Failed to log summary trace: %s", e)

            logger.info(
                "Logged %d results to Opik project: %s", len(
                    results), self.project_name
            )
            return True

        except Exception as e:
            logger.error("Failed to log to Opik: %s", e)
            return False

    @property
    def enabled(self) -> bool:
        return self._enabled
