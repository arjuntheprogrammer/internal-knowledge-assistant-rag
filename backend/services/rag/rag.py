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
from .rag_milvus import get_milvus_vector_store
from .rag_context import get_service_context
from .rag_formatter import RAGFormatter


class RAGService:
    _index_by_user = {}
    _bm25_nodes_by_user = {}
    _document_catalog_by_user = {}
    logger = logging.getLogger(__name__)

    @classmethod
    def get_service_context(cls, openai_api_key):
        return get_service_context(openai_api_key)

    @classmethod
    def get_vector_store(cls, user_id):
        return get_milvus_vector_store(user_id=user_id)

    @classmethod
    def get_index(cls, user_id):
        return cls._index_by_user.get(user_id)

    @classmethod
    def get_bm25_nodes(cls, user_id):
        return cls._bm25_nodes_by_user.get(user_id)

    @classmethod
    def get_document_catalog(cls, user_id):
        return cls._document_catalog_by_user.get(user_id, [])

    @classmethod
    def reset_user_cache(cls, user_id):
        if not user_id:
            return
        cls._index_by_user.pop(user_id, None)
        cls._bm25_nodes_by_user.pop(user_id, None)
        cls._document_catalog_by_user.pop(user_id, None)

    @classmethod
    def initialize_index(cls, user_context):
        user_id = user_context.get("uid")
        if not user_id:
            return
        documents = []

        data_dir = os.path.join(os.getcwd(), "backend", "data")
        os.makedirs(data_dir, exist_ok=True)
        try:
            local_docs = SimpleDirectoryReader(data_dir).load_data()
            documents.extend(local_docs)
            print(f"Loaded {len(local_docs)} local documents.")
        except Exception:
            pass

        drive_docs = rag_google_drive.load_google_drive_documents(
            user_id=user_id,
            drive_folder_id=user_context.get("drive_folder_id"),
            token_json=user_context.get("google_token"),
        )
        documents.extend(drive_docs)

        if not documents:
            print("No documents found. Index will be empty.")
            return
        annotate_documents(documents, user_id=user_id)
        cls._document_catalog_by_user[user_id] = build_document_catalog(documents)

        try:
            settings = cls.get_service_context(user_context.get("openai_api_key"))
            vector_store = cls.get_vector_store(user_id)

            # Since we are using a shared collection, we must manually delete
            # old records for THIS user before indexing new ones to avoid duplicates.
            if vector_store:
                try:
                    client = getattr(vector_store, "client", None)
                    collection_name = getattr(vector_store, "collection_name", None)
                    if client and collection_name:
                        # Delete by metadata filter
                        client.delete(
                            collection_name=collection_name,
                            filter=f"user_id == '{user_id}'"
                        )
                        print(f"Successfully cleared existing records for user {user_id} in shared collection.")
                except Exception as del_err:
                    print(f"Warning: Could not clear existing records: {del_err}")

            storage_context = None
            if vector_store:
                storage_context = StorageContext.from_defaults(
                    vector_store=vector_store
                )

            splitter = SentenceSplitter(chunk_size=512, chunk_overlap=60)
            cls._bm25_nodes_by_user[user_id] = splitter.get_nodes_from_documents(
                documents
            )
            cls._index_by_user[user_id] = VectorStoreIndex.from_documents(
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
    def get_drive_file_list(cls, user_id, drive_folder_id):
        return rag_google_drive.get_drive_file_list(
            user_id=user_id,
            drive_folder_id=drive_folder_id,
        )

    @classmethod
    def query(cls, question, user_context):
        settings = cls.get_service_context(user_context.get("openai_api_key"))
        selector = LLMSingleSelector.from_defaults(llm=settings.llm)

        casual_engine = CasualQueryEngine(
            llm=settings.llm, callback_manager=settings.callback_manager
        )
        rag_engine = LazyRAGQueryEngine(
            llm=settings.llm,
            callback_manager=settings.callback_manager,
            service=cls,
            user_context=user_context,
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
            user_catalog = cls.get_document_catalog(user_context.get("uid"))
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
                is_catalog_query or (user_catalog and bullet_count == 0)
            ):
                if not user_catalog:
                    return formatted
                requested = parse_list_limit(query_text or "")
                list_all = bool(re.search(r"\ball\b", query_text or "", re.I))
                catalog_count = len(user_catalog)
                needs_fallback = bullet_count == 0
                if requested:
                    needs_fallback = needs_fallback or bullet_count != requested
                elif list_all and bullet_count < catalog_count:
                    needs_fallback = True
                if needs_fallback:
                    return format_document_catalog_response(
                        user_catalog, limit=requested
                    )
            return formatted
        if isinstance(response, Response):
            return response.response or ""
        return str(response)
