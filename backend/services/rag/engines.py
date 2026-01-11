import re

from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.base.response.schema import Response
from llama_index.core.postprocessor import LLMRerank
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.retrievers.bm25 import BM25Retriever

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
    def __init__(self, llm, callback_manager, service):
        super().__init__(callback_manager)
        self._llm = llm
        self._callback_manager = callback_manager
        self._service = service

    def _get_prompt_modules(self):
        return {}

    def _query(self, query_bundle: QueryBundle):
        if not self._service.index:
            self._service.initialize_index()

        if not self._service.index:
            return Response("Knowledge base is empty. Please add documents.")

        query_engine = build_rag_query_engine(
            query_bundle=query_bundle,
            llm=self._llm,
            callback_manager=self._callback_manager,
            index=self._service.index,
            bm25_nodes=self._service.bm25_nodes,
        )
        return query_engine.query(query_bundle)

    async def _aquery(self, query_bundle: QueryBundle):
        return self._query(query_bundle)


def build_rag_query_engine(query_bundle, llm, callback_manager, index, bm25_nodes):
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
        "If unsure, say 'Insufficient information'. "
        "Format as Markdown with:\n"
        "**Answer:** [response]\n"
        "**Sources:** bullet list of citations\n"
        "If the question asks for a list, use bullet points.\n"
        "Question: {query_str}\n**Answer:** "
    )
    list_text_qa_template = PromptTemplate(
        "Context: {context_str}\n"
        "Answer the question based ONLY on the context. "
        "If unsure, say 'Insufficient information'. "
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
    text_qa_template = list_text_qa_template if is_list_query else default_text_qa_template
    refine_template = list_refine_template if is_list_query else default_refine_template
    rerank_top_n = 24 if is_list_query else 6
    reranker = LLMRerank(llm=llm, top_n=rerank_top_n)

    vector_retriever = index.as_retriever(similarity_top_k=vector_top_k)
    bm25_retriever = None
    if bm25_nodes:
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=bm25_nodes, similarity_top_k=bm25_top_k
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
