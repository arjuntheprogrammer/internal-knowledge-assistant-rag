import re
import logging
from typing import List, Tuple, Any

from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.base.response.schema import Response
from llama_index.core.postprocessor import LLMRerank
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter

from .retrievers import HybridRetriever
from .prompt_loader import load_prompt, get_prompt_spec
from .opik_prompts import get_or_register_prompt
from .schemas.llm_output import LLMOutput
from .structured_output import parse_structured_output, repair_llm_json, get_safe_llm_output

logger = logging.getLogger(__name__)


class CasualQueryEngine(BaseQueryEngine):
    def __init__(self, llm, callback_manager):
        super().__init__(callback_manager)
        self._llm = llm
        self._opik_prompts = []
        self._load_prompts()

    def _load_prompts(self):
        # Load and register prompts
        system_spec = get_prompt_spec("casual_system")
        schema_spec = get_prompt_spec("output_schema.md")

        self._opik_prompts = [
            get_or_register_prompt(system_spec),
            get_or_register_prompt(schema_spec)
        ]

        self._system_prompt = system_spec.text
        self._schema_prompt = schema_spec.text

    @property
    def opik_prompts(self):
        return self._opik_prompts

    def _query(self, query_bundle: QueryBundle):
        full_prompt = f"{self._system_prompt}\n\n{self._schema_prompt}\n\nUser Question: {query_bundle.query_str}"

        try:
            # We use structured_predict if available, otherwise manual
            if hasattr(self._llm, "structured_predict"):
                llm_output = self._llm.structured_predict(
                    LLMOutput, PromptTemplate(full_prompt))
            else:
                raw_response = self._llm.complete(full_prompt).text
                try:
                    llm_output = parse_structured_output(
                        raw_response, LLMOutput)
                except Exception:
                    llm_output = repair_llm_json(
                        self._llm, raw_response, LLMOutput)
        except Exception as e:
            logger.error("Casual query failed: %s", e)
            llm_output = get_safe_llm_output(intent="casual")

        # Return a response object with the Pydantic model in metadata
        return Response(llm_output.answer_md, metadata={"llm_output": llm_output})

    async def _aquery(self, query_bundle: QueryBundle):
        return self._query(query_bundle)

    def _get_prompt_modules(self) -> dict:
        return {}


class LazyRAGQueryEngine(BaseQueryEngine):
    def __init__(self, llm, callback_manager, service, user_context):
        super().__init__(callback_manager)
        self._llm = llm
        self._callback_manager = callback_manager
        self._service = service
        self._user_context = user_context
        self._last_opik_prompts = []

    @property
    def opik_prompts(self):
        return self._last_opik_prompts

    def _query(self, query_bundle: QueryBundle):
        user_id = self._user_context.get("uid")
        index = self._service.get_index(user_id)

        if not index:
            from backend.services.indexing_service import IndexingService, IndexingStatus
            status_info = IndexingService.get_status(user_id)
            if status_info.get("status") == IndexingStatus.COMPLETED:
                index = self._rebuild_index_from_vector_store(user_id)

            if not index:
                llm_output = get_safe_llm_output(
                    intent="rag", refusal_reason="unknown")
                llm_output.answer_md = ("I'm sorry, I'm still connecting to your documents. "
                                        "Please go to Settings and click 'Connect Google Drive'.")
                return Response(llm_output.answer_md, metadata={"llm_output": llm_output})

        query_engine, opik_prompts = build_rag_query_engine(
            query_bundle=query_bundle,
            llm=self._llm,
            callback_manager=self._callback_manager,
            index=index,
            bm25_nodes=self._service.get_bm25_nodes(user_id),
            user_id=user_id,
        )
        self._last_opik_prompts = opik_prompts

        # Capture the response
        response = query_engine.query(query_bundle)

        # The underlying RetrieverQueryEngine uses standard prompts.
        # We need to wrap the response into our LLMOutput.
        # However, since we want the LLM to produce JSON, we should have customized the
        # text_qa_template to include the JSON rules.

        # Let's extract the LLMOutput from the response string if the LLM followed instructions
        raw_text = response.response or ""
        try:
            llm_output = parse_structured_output(raw_text, LLMOutput)
        except Exception:
            try:
                llm_output = repair_llm_json(self._llm, raw_text, LLMOutput)
            except Exception:
                llm_output = get_safe_llm_output(intent="rag")
                llm_output.answer_md = raw_text  # Use raw if it failed but we have text

        response.metadata["llm_output"] = llm_output
        return response

    def _rebuild_index_from_vector_store(self, user_id: str):
        from llama_index.core import VectorStoreIndex
        try:
            vector_store = self._service.get_vector_store(user_id)
            if not vector_store:
                return None
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                callback_manager=self._callback_manager,
            )
            self._service._index_by_user[user_id] = index
            return index
        except Exception as e:
            logger.error("Failed to rebuild index: %s", e)
            return None

    async def _aquery(self, query_bundle: QueryBundle):
        return self._query(query_bundle)

    def _get_prompt_modules(self) -> dict:
        return {}


def build_rag_query_engine(query_bundle, llm, callback_manager, index, bm25_nodes, user_id=None):
    query_text = query_bundle.query_str or str(query_bundle)
    is_list_query = bool(
        re.search(r"\b(list|all|show|enumerate|provide|give me)\b", query_text, re.I))

    # Retriever settings
    vector_top_k = 24 if is_list_query else 6
    bm25_top_k = 24 if is_list_query else 6
    max_results = 30 if is_list_query else 10

    retriever_opts = {"similarity_top_k": vector_top_k}
    if user_id:
        retriever_opts["filters"] = MetadataFilters(
            filters=[ExactMatchFilter(key="user_id", value=user_id)])

    vector_retriever = index.as_retriever(**retriever_opts)
    bm25_retriever = None
    if bm25_nodes:
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=bm25_nodes, similarity_top_k=min(bm25_top_k, len(bm25_nodes)))

    hybrid_retriever = HybridRetriever(
        vector_retriever=vector_retriever,
        bm25_retriever=bm25_retriever,
        max_results=max_results,
        callback_manager=callback_manager,
        bm25_weight=1.2 if is_list_query else 1.0,
    )

    # Load prompts
    system_spec = get_prompt_spec("rag_system")
    schema_spec = get_prompt_spec("output_schema.md")

    opik_prompts = [
        get_or_register_prompt(system_spec),
        get_or_register_prompt(schema_spec)
    ]

    # We combine them into the text_qa_template
    # This ensures the LLM sees the grounding rules AND the JSON schema rules.
    combined_prompt = f"{system_spec.text}\n\n{schema_spec.text}"
    text_qa_template = PromptTemplate(combined_prompt)

    rerank_top_n = 24 if is_list_query else 6
    reranker = LLMRerank(llm=llm, top_n=rerank_top_n)

    query_engine = RetrieverQueryEngine.from_args(
        retriever=hybrid_retriever,
        llm=llm,
        callback_manager=callback_manager,
        text_qa_template=text_qa_template,
        node_postprocessors=[reranker],
    )

    return query_engine, opik_prompts
