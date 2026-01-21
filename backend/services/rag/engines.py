import re

from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.base.response.schema import Response
from llama_index.core.postprocessor import LLMRerank
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.retrievers.bm25 import BM25Retriever

from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter

from .retrievers import HybridRetriever


class CasualQueryEngine(BaseQueryEngine):
    def __init__(self, llm, callback_manager):
        super().__init__(callback_manager)
        self._llm = llm
        self._prompt = PromptTemplate(
            "You are a friendly assistant. Respond briefly and naturally to casual "
            "conversation. If the user asks about internal documents or data, say "
            "you can look it up and ask for a specific question.\n"
            "User: {query_str}\nAssistant:"
        )

    def _get_prompt_modules(self):
        return {"casual_prompt": self._prompt}

    def _query(self, query_bundle: QueryBundle):
        query_str = query_bundle.query_str or ""
        response_text = self._llm.predict(self._prompt, query_str=query_str)
        return Response(response_text)

    async def _aquery(self, query_bundle: QueryBundle):
        return self._query(query_bundle)


class LazyRAGQueryEngine(BaseQueryEngine):
    def __init__(self, llm, callback_manager, service, user_context):
        super().__init__(callback_manager)
        self._llm = llm
        self._callback_manager = callback_manager
        self._service = service
        self._user_context = user_context

    def _get_prompt_modules(self):
        return {}

    def _query(self, query_bundle: QueryBundle):
        user_id = self._user_context.get("uid")

        # Get the index - it should have been built by IndexingService
        # If not available, try to rebuild from vector store
        index = self._service.get_index(user_id)
        if not index:
            # Check if user has completed indexing before (status is COMPLETED)
            from backend.services.indexing_service import (
                IndexingService,
                IndexingStatus,
            )

            status_info = IndexingService.get_status(user_id)

            if status_info.get("status") == IndexingStatus.COMPLETED:
                # Index was built but in-memory cache is empty (e.g., server restart)
                # Rebuild from persisted vector store
                index = self._rebuild_index_from_vector_store(user_id)

            if not index:
                return Response(
                    "I'm sorry, I'm still connecting to your documents. "
                    "Please go to Settings and click 'Connect Google Drive' to finish the setup."
                )

        query_engine = build_rag_query_engine(
            query_bundle=query_bundle,
            llm=self._llm,
            callback_manager=self._callback_manager,
            index=index,
            bm25_nodes=self._service.get_bm25_nodes(user_id),
            user_id=user_id,
        )
        return query_engine.query(query_bundle)

    def _rebuild_index_from_vector_store(self, user_id: str):
        """Rebuild the index from persisted vector store after server restart."""
        from llama_index.core import VectorStoreIndex
        from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
        import logging

        logger = logging.getLogger(__name__)

        try:
            logger.info("Rebuilding index from vector store for user %s", user_id)

            vector_store = self._service.get_vector_store(user_id)
            if not vector_store:
                logger.warning("No vector store available for user %s", user_id)
                return None

            # Create index from existing vector store
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                callback_manager=self._callback_manager,
            )

            # Cache it for future requests
            self._service._index_by_user[user_id] = index
            logger.info(
                "Successfully rebuilt index from vector store for user %s", user_id
            )

            return index
        except Exception as e:
            logger.error(
                "Failed to rebuild index from vector store for user %s: %s", user_id, e
            )
            return None

    async def _aquery(self, query_bundle: QueryBundle):
        return self._query(query_bundle)


def build_rag_query_engine(
    query_bundle, llm, callback_manager, index, bm25_nodes, user_id=None
):
    query_text = query_bundle.query_str or str(query_bundle)
    is_list_query = bool(
        re.search(r"\b(list|all|show|enumerate|provide|give me)\b", query_text, re.I)
    )
    vector_top_k = 24 if is_list_query else 6
    bm25_top_k = 24 if is_list_query else 6
    max_results = 30 if is_list_query else 10

    default_text_qa_template = PromptTemplate(
        "Context: {context_str}\n"
        "Answer the question based ONLY on the context. "
        "If unsure, say 'I'm sorry, I couldn't find that information in your documents. I'm only able to answer questions based on the knowledge base you've provided.' "
        "Format as Markdown with:\n"
        "**Answer:** [response]\n"
        "**Sources:** bullet list of citations\n"
        "If the question asks for a list, use bullet points.\n"
        "Question: {query_str}\n**Answer:** "
    )
    list_text_qa_template = PromptTemplate(
        "Context: {context_str}\n"
        "Answer the question based ONLY on the context. "
        "If unsure, say 'I'm sorry, I couldn't find any relevant lists or documents in your knowledge base regarding this.' "
        "The user asked for a list. Enumerate every unique item mentioned "
        "in the context; do not stop early. "
        "If the context seems incomplete, add: '(List may be incomplete)'. "
        "Format as Markdown with:\n"
        "**Answer:** [bullet list]\n"
        "**Sources:** bullet list of citations\n"
        "Question: {query_str}\n**Answer:** "
    )
    default_refine_template = PromptTemplate(
        "Original: {query_str}\nPrevious answer: {existing_answer}\n"
        "Refine using new context: {context_str}\n"
        "If the question asks for a list, keep bullet points. "
        "Keep the Markdown formatting. **Answer:** "
    )
    list_refine_template = PromptTemplate(
        "Original: {query_str}\nPrevious answer: {existing_answer}\n"
        "Refine using new context: {context_str}\n"
        "Update the list with any new unique items from the context. "
        "Keep bullet points and Markdown formatting. **Answer:** "
    )
    text_qa_template = (
        list_text_qa_template if is_list_query else default_text_qa_template
    )
    refine_template = list_refine_template if is_list_query else default_refine_template
    rerank_top_n = 24 if is_list_query else 6
    reranker = LLMRerank(llm=llm, top_n=rerank_top_n)

    retriever_opts = {"similarity_top_k": vector_top_k}
    if user_id:
        retriever_opts["filters"] = MetadataFilters(
            filters=[ExactMatchFilter(key="user_id", value=user_id)]
        )

    vector_retriever = index.as_retriever(**retriever_opts)
    bm25_retriever = None
    if bm25_nodes:
        actual_bm25_top_k = min(bm25_top_k, len(bm25_nodes))
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=bm25_nodes, similarity_top_k=actual_bm25_top_k
        )
    hybrid_retriever = HybridRetriever(
        vector_retriever=vector_retriever,
        bm25_retriever=bm25_retriever,
        max_results=max_results,
        callback_manager=callback_manager,
        bm25_weight=1.2 if is_list_query else 1.0,
    )
    return RetrieverQueryEngine.from_args(
        retriever=hybrid_retriever,
        llm=llm,
        callback_manager=callback_manager,
        text_qa_template=text_qa_template,
        refine_template=refine_template,
        node_postprocessors=[reranker],
    )
