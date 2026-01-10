from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.response.schema import Response
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.postprocessor import LLMRerank
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine import RetrieverQueryEngine, RouterQueryEngine
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.tools import QueryEngineTool
from llama_index.retrievers.bm25 import BM25Retriever
import logging
import os
import re

from .rag_context import get_service_context
from .rag_chroma import get_chroma_vector_store
from . import rag_google_drive
from .rag_formatter import RAGFormatter


class RAGService:
    index = None
    bm25_nodes = None
    document_catalog = []
    logger = logging.getLogger(__name__)

    @classmethod
    def get_service_context(cls):
        return get_service_context()

    @classmethod
    def get_vector_store(cls):
        return get_chroma_vector_store()

    @classmethod
    def initialize_index(cls):
        documents = []

        data_dir = os.path.join(os.getcwd(), "backend", "data")
        os.makedirs(data_dir, exist_ok=True)
        try:
            local_docs = SimpleDirectoryReader(data_dir).load_data()
            documents.extend(local_docs)
            print(f"Loaded {len(local_docs)} local documents.")
        except Exception:
            pass

        drive_docs = rag_google_drive.load_google_drive_documents()
        documents.extend(drive_docs)

        if not documents:
            print("No documents found. Index will be empty.")
            return
        cls._annotate_documents(documents)
        cls.document_catalog = cls._build_document_catalog(documents)

        try:
            settings = cls.get_service_context()
            vector_store = cls.get_vector_store()
            storage_context = None
            if vector_store:
                storage_context = StorageContext.from_defaults(
                    vector_store=vector_store
                )

            splitter = SentenceSplitter(chunk_size=512, chunk_overlap=60)
            cls.bm25_nodes = splitter.get_nodes_from_documents(documents)
            cls.index = VectorStoreIndex.from_documents(
                documents,
                callback_manager=settings.callback_manager,
                storage_context=storage_context,
                transformations=[splitter],
            )
            print("Index initialized successfully.")
            if vector_store:
                cls._log_vector_store_count(vector_store)
        except Exception as e:
            print(f"Index initialization error: {e}")

    @classmethod
    def _build_rag_query_engine(cls, query_bundle: QueryBundle, llm, callback_manager):
        query_text = query_bundle.query_str or str(query_bundle)
        is_list_query = bool(
            re.search(
                r"\b(list|all|show|enumerate|provide|give me)\b", query_text, re.I
            )
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
        text_qa_template = (
            list_text_qa_template if is_list_query else default_text_qa_template
        )
        refine_template = (
            list_refine_template if is_list_query else default_refine_template
        )
        rerank_top_n = 24 if is_list_query else 6
        reranker = LLMRerank(llm=llm, top_n=rerank_top_n)

        vector_retriever = cls.index.as_retriever(similarity_top_k=vector_top_k)
        bm25_retriever = None
        if cls.bm25_nodes:
            bm25_retriever = BM25Retriever.from_defaults(
                nodes=cls.bm25_nodes, similarity_top_k=bm25_top_k
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

    @classmethod
    def get_drive_file_list(cls):
        return rag_google_drive.get_drive_file_list()

    @classmethod
    def query(cls, question):
        settings = cls.get_service_context()
        selector = LLMSingleSelector.from_defaults(llm=settings.llm)

        casual_engine = CasualQueryEngine(
            llm=settings.llm, callback_manager=settings.callback_manager
        )
        rag_engine = LazyRAGQueryEngine(
            llm=settings.llm, callback_manager=settings.callback_manager
        )

        tools = [
            QueryEngineTool.from_defaults(
                query_engine=casual_engine,
                name="casual_chat",
                description=(
                    "Handle greetings, small talk, confirmations, thanks, or casual "
                    "conversation that does not require company documents or data. "
                    "Use this for short social replies like 'hi', 'hello', 'thanks', "
                    "'how are you', or general chit-chat."
                ),
            ),
            QueryEngineTool.from_defaults(
                query_engine=rag_engine,
                name="knowledge_base_retrieval",
                description=(
                    "Use for questions that need internal knowledge, policies, files, "
                    "procedures, or any answer that must be grounded in the document "
                    "corpus. Run retrieval when the user asks about specific facts, "
                    "summaries, or details from company docs or Google Drive."
                ),
            ),
        ]

        router_engine = RouterQueryEngine.from_defaults(
            query_engine_tools=tools,
            llm=settings.llm,
            selector=selector,
            select_multi=False,
        )
        response = router_engine.query(question)

        query_text = None
        if isinstance(question, QueryBundle):
            query_text = question.query_str
        else:
            query_text = str(question)

        selector_result = None
        if isinstance(response, Response):
            selector_result = (response.metadata or {}).get("selector_result")
        selected_inds = []
        selected_reasons = []
        if selector_result is not None:
            selections = getattr(selector_result, "selections", None)
            if selections:
                selected_inds = [selection.index for selection in selections]
                selected_reasons = [selection.reason for selection in selections]
            else:
                inds = getattr(selector_result, "inds", None) or []
                selected_inds = list(inds)
                reasons = getattr(selector_result, "reasons", None) or []
                selected_reasons = list(reasons)

        selected_tools = [
            tools[index].metadata.name
            for index in selected_inds
            if 0 <= index < len(tools)
        ]
        selected_tool = selected_tools[0] if selected_tools else "unknown"
        selected_reason = selected_reasons[0] if selected_reasons else None

        cls.logger.info(
            "rag_router selection=%s reason=%s query_len=%s",
            ",".join(selected_tools) if selected_tools else selected_tool,
            selected_reason,
            len(query_text) if query_text else 0,
        )

        if 1 in selected_inds:
            formatted = RAGFormatter.format_markdown_response(response)
            is_list_query = bool(
                re.search(
                    r"\b(list|all|show|enumerate|provide|give me|top)\b",
                    query_text or "",
                    re.I,
                )
            )
            is_catalog_query = bool(
                re.search(
                    r"\b(document|documents|doc|docs|file|files|knowledge base|drive|folder|stock|stocks|company|companies|ticker|tickers)\b",
                    query_text or "",
                    re.I,
                )
            )
            bullet_count = cls._extract_bullet_count(formatted)
            if is_list_query and (
                is_catalog_query or (cls.document_catalog and bullet_count == 0)
            ):
                if not cls.document_catalog:
                    return formatted
                requested = cls._parse_list_limit(query_text or "")
                list_all = bool(re.search(r"\ball\b", query_text or "", re.I))
                catalog_count = len(cls.document_catalog)
                needs_fallback = bullet_count == 0
                if requested:
                    needs_fallback = needs_fallback or bullet_count != requested
                elif list_all and bullet_count < catalog_count:
                    needs_fallback = True
                if needs_fallback:
                    return cls._format_document_catalog_response(limit=requested)
            return formatted
        if isinstance(response, Response):
            return response.response or ""
        return str(response)

    @staticmethod
    def _log_vector_store_count(vector_store):
        try:
            collection = getattr(vector_store, "_collection", None)
            if collection is not None and hasattr(collection, "count"):
                print(f"Chroma collection count: {collection.count()}")
        except Exception as exc:
            print(f"Chroma collection count check failed: {exc}")

    @staticmethod
    def _annotate_documents(documents):
        for doc in documents:
            metadata = getattr(doc, "metadata", None)
            if not isinstance(metadata, dict):
                continue
            file_name = (
                metadata.get("file name")
                or metadata.get("file_name")
                or metadata.get("filename")
                or metadata.get("file_path")
            )
            if file_name:
                base_name = os.path.basename(str(file_name))
                stock_name = os.path.splitext(base_name)[0].strip()
                if stock_name:
                    metadata.setdefault("stock_name", stock_name)

    @staticmethod
    def _build_document_catalog(documents):
        catalog = {}
        for doc in documents:
            metadata = getattr(doc, "metadata", None)
            if not isinstance(metadata, dict):
                continue
            doc_name = metadata.get("stock_name")
            if not doc_name:
                file_name = (
                    metadata.get("file name")
                    or metadata.get("file_name")
                    or metadata.get("filename")
                )
                if file_name:
                    doc_name = os.path.splitext(os.path.basename(str(file_name)))[0].strip()
            if not doc_name:
                continue
            drive_id = metadata.get("file id") or metadata.get("file_id")
            url = None
            if drive_id:
                url = f"https://drive.google.com/file/d/{drive_id}/view"
            catalog.setdefault(doc_name, url)
        return sorted(
            [{"name": name, "url": url} for name, url in catalog.items()],
            key=lambda item: item["name"].lower(),
        )

    @staticmethod
    def _parse_list_limit(query_text):
        if not query_text:
            return None
        match = re.search(
            r"\b(?:top|list|show|give me|provide)\s+(\d+)\b", query_text, re.I
        )
        if match:
            return int(match.group(1))
        match = re.search(
            r"\b(\d+)\s+(?:stocks|stock|companies|company|tickers|ticker)\b",
            query_text,
            re.I,
        )
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_bullet_count(response_text):
        if not response_text:
            return 0
        answer_match = re.search(
            r"(?is)\*\*answer\*\*\s*:?(.*?)(\*\*sources\*\*|$)",
            response_text,
        )
        answer_text = answer_match.group(1) if answer_match else response_text
        return len(re.findall(r"(?m)^\s*[-*]\s+", answer_text))

    @classmethod
    def _format_document_catalog_response(cls, limit=None):
        catalog = cls.document_catalog or []
        if limit:
            catalog = catalog[:limit]
        if not catalog:
            return "**Answer:** Insufficient information\n\n**Sources:** None"
        answer_lines = [f"- {item['name']}" for item in catalog]
        sources = []
        for item in catalog:
            if item.get("url"):
                sources.append(f"- [{item['name']}]({item['url']})")
        answer_block = "**Answer:**\n" + "\n".join(answer_lines)
        if sources:
            sources_block = "**Sources:**\n" + "\n".join(sources)
        else:
            sources_block = "**Sources:** None"
        return f"{answer_block}\n\n{sources_block}"


class HybridRetriever(BaseRetriever):
    def __init__(
        self,
        vector_retriever,
        bm25_retriever,
        max_results,
        callback_manager,
        vector_weight=1.0,
        bm25_weight=1.0,
    ):
        super().__init__(callback_manager=callback_manager)
        self._vector_retriever = vector_retriever
        self._bm25_retriever = bm25_retriever
        self._max_results = max_results
        self._vector_weight = vector_weight
        self._bm25_weight = bm25_weight

    def _get_prompt_modules(self):
        return {}

    def _retrieve(self, query_bundle: QueryBundle):
        vector_nodes = self._vector_retriever.retrieve(query_bundle)
        bm25_nodes = []
        if self._bm25_retriever is not None:
            bm25_nodes = self._bm25_retriever.retrieve(query_bundle)
        merged = {}

        def add_nodes(nodes, weight):
            for node in nodes:
                score = (node.score or 0.0) * weight
                key = getattr(node.node, "node_id", None) or getattr(
                    node.node, "hash", None
                )
                if key is None:
                    key = id(node.node)
                existing = merged.get(key)
                if existing is None or score > (existing.score or 0.0):
                    merged[key] = NodeWithScore(node=node.node, score=score)

        add_nodes(vector_nodes, self._vector_weight)
        if bm25_nodes:
            add_nodes(bm25_nodes, self._bm25_weight)

        results = sorted(
            merged.values(), key=lambda item: item.score or 0.0, reverse=True
        )
        if self._max_results:
            return results[: self._max_results]
        return results


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
    def __init__(self, llm, callback_manager):
        super().__init__(callback_manager)
        self._llm = llm
        self._callback_manager = callback_manager

    def _get_prompt_modules(self):
        return {}

    def _query(self, query_bundle: QueryBundle):
        if not RAGService.index:
            RAGService.initialize_index()

        if not RAGService.index:
            return Response("Knowledge base is empty. Please add documents.")

        query_engine = RAGService._build_rag_query_engine(
            query_bundle, self._llm, self._callback_manager
        )
        return query_engine.query(query_bundle)

    async def _aquery(self, query_bundle: QueryBundle):
        return self._query(query_bundle)
