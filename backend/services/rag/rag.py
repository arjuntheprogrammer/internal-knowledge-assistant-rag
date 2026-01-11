import logging
import os
import re

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.base.response.schema import Response
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.tools import QueryEngineTool

from . import rag_google_drive
from .catalog import (
    annotate_documents,
    build_document_catalog,
    extract_bullet_count,
    format_document_catalog_response,
    log_vector_store_count,
    parse_list_limit,
)
from .engines import CasualQueryEngine, LazyRAGQueryEngine
from .rag_chroma import get_chroma_vector_store
from .rag_context import get_service_context
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
        annotate_documents(documents)
        cls.document_catalog = build_document_catalog(documents)

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
                log_vector_store_count(vector_store)
        except Exception as e:
            print(f"Index initialization error: {e}")

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
            llm=settings.llm,
            callback_manager=settings.callback_manager,
            service=cls,
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
                    r"\b(document|documents|doc|docs|file|files|knowledge base|drive|"
                    r"folder|stock|stocks|company|companies|ticker|tickers)\b",
                    query_text or "",
                    re.I,
                )
            )
            bullet_count = extract_bullet_count(formatted)
            if is_list_query and (
                is_catalog_query or (cls.document_catalog and bullet_count == 0)
            ):
                if not cls.document_catalog:
                    return formatted
                requested = parse_list_limit(query_text or "")
                list_all = bool(re.search(r"\ball\b", query_text or "", re.I))
                catalog_count = len(cls.document_catalog)
                needs_fallback = bullet_count == 0
                if requested:
                    needs_fallback = needs_fallback or bullet_count != requested
                elif list_all and bullet_count < catalog_count:
                    needs_fallback = True
                if needs_fallback:
                    return format_document_catalog_response(
                        cls.document_catalog, limit=requested
                    )
            return formatted
        if isinstance(response, Response):
            return response.response or ""
        return str(response)
