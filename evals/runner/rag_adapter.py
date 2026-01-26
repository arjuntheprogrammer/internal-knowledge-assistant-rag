"""
RAG adapter for evaluation runs.
Provides a unified interface to the production RAG system.
"""

from backend.utils.opik_prompts import get_or_register_prompt
from backend.utils.prompt_loader import get_prompt_spec
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


# Note: OpikAdapter has been moved to .opik.adapter
