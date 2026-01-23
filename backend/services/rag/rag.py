import logging
import os
import re

from llama_index.core import VectorStoreIndex, StorageContext
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
from .structured_output import parse_rag_json, parse_casual_json, StructuredResponse

# Register prompts in Opik at module load
try:
    from backend.utils.opik_prompts import sync_all_prompts_to_opik
    sync_all_prompts_to_opik()
except Exception as e:
    logging.getLogger(__name__).warning(
        "Failed to sync prompts to Opik: %s", e)


class RAGService:
    _index_by_user = {}
    _bm25_nodes_by_user = {}
    _document_catalog_by_user = {}
    logger = logging.getLogger(__name__)

    @classmethod
    def get_service_context(cls, openai_api_key, user_id=None):
        return get_service_context(openai_api_key, user_id=user_id)

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
    def initialize_index(cls, user_context, on_progress=None):
        """
        Initialize the RAG index for a user by loading documents from Drive,
        parsing them into nodes, and storing embeddings in Milvus.
        """

        def notify(msg, progress):
            if on_progress:
                on_progress(msg, progress)
            else:
                cls.logger.info(f"Indexing progress: {msg} ({progress}%)")

        user_id = user_context.get("uid")
        if not user_id:
            cls.logger.error("No user ID provided for index initialization")
            return

        notify("Connecting to Google Drive...", 10)

        # Load Google Drive documents by file IDs (drive.file scope)
        try:
            file_ids = user_context.get("drive_file_ids") or []

            if file_ids:
                documents = rag_google_drive.load_google_drive_documents_by_file_ids(
                    user_id=user_id,
                    file_ids=file_ids,
                    token_json=user_context.get("google_token"),
                )
            else:
                documents = []
        except Exception as e:
            cls.logger.error(f"Failed to load documents from Drive: {e}")
            raise

        if not documents:
            cls.logger.warning(
                f"No documents found for user {user_id}. Index will be empty."
            )
            notify("No documents found.", 100)
            return

        notify(f"Processing {len(documents)} documents...", 40)
        annotate_documents(documents, user_id=user_id)
        cls._document_catalog_by_user[user_id] = build_document_catalog(
            documents)

        try:
            notify("Analyzing document structure...", 50)
            settings = cls.get_service_context(
                user_context.get("openai_api_key"), user_id=user_id
            )
            vector_store = cls.get_vector_store(user_id)

            # Since we are using a shared collection, we must manually delete
            # old records for THIS user before indexing new ones to avoid duplicates.
            if vector_store:
                try:
                    notify("Clearing old index data...", 55)
                    client = getattr(vector_store, "client", None)
                    collection_name = getattr(
                        vector_store, "collection_name", None)
                    if client and collection_name:
                        # Delete by metadata filter
                        client.delete(
                            collection_name=collection_name,
                            filter=f"user_id == '{user_id}'",
                        )
                        cls.logger.info(
                            f"Successfully cleared existing records for user {user_id}"
                        )
                except Exception as del_err:
                    cls.logger.warning(
                        f"Could not clear existing records: {del_err}")

            storage_context = None
            if vector_store:
                storage_context = StorageContext.from_defaults(
                    vector_store=vector_store
                )

            notify("Preparing nodes for embedding...", 60)
            splitter = SentenceSplitter(chunk_size=512, chunk_overlap=60)

            # Ensure all documents have file_id as their identity
            for doc in documents:
                f_id = doc.metadata.get("file_id")
                if f_id:
                    doc.id_ = f_id

            # Generate nodes and assign deterministic IDs
            nodes = splitter.get_nodes_from_documents(documents)
            node_counts = {}
            for node in nodes:
                m = node.metadata
                f_id = m.get("file_id")
                rev_id = m.get("revision_id") or "unknown"
                p_num = m.get("page_number") or 1
                e_method = m.get("extraction_method") or m.get(
                    "source") or "digital_text"

                key = (f_id, rev_id, p_num, e_method)
                idx = node_counts.get(key, 0)
                node_counts[key] = idx + 1

                node.id_ = f"{f_id}#rev:{rev_id}#p:{p_num}#m:{e_method}#c:{idx}"

            cls._bm25_nodes_by_user[user_id] = nodes

            notify("Generating embeddings and uploading...", 75)
            cls._index_by_user[user_id] = VectorStoreIndex(
                nodes,
                callback_manager=settings.callback_manager,
                storage_context=storage_context,
            )

            notify("Finalizing...", 95)
            if vector_store:
                log_vector_store_count(vector_store)

            cls.logger.info(
                f"Index initialized successfully for user {user_id}.")
            return documents
        except Exception as e:
            cls.logger.error(
                f"Index initialization error for user {user_id}: {e}")
            raise

    @classmethod
    def query(cls, question, user_context):
        """
        Standard query method returning markdown string.
        Maintains backward compatibility.
        """
        response_obj = cls.query_structured(question, user_context)

        # If it was a knowledge base selection, it might have been formatted
        # already by RAGFormatter if it wasn't valid JSON.
        # But we want to prefer the structured response to_markdown.

        # Extract selected tool info from response_obj's raw metadata
        selected_tool = "unknown"
        if hasattr(response_obj, "_llama_response") and isinstance(response_obj._llama_response, Response):
            metadata = response_obj._llama_response.metadata or {}
            selector_result = metadata.get("selector_result")
            if selector_result:
                selections = getattr(selector_result, "selections", None)
                if selections:
                    indices = [s.index for s in selections]
                    if 1 in indices:
                        selected_tool = "knowledge_base_retrieval"
                    elif 0 in indices:
                        selected_tool = "casual_chat"

        if selected_tool == "knowledge_base_retrieval":
            # Check for document catalog fallback
            query_text = question.query_str if isinstance(
                question, QueryBundle) else str(question)
            user_catalog = cls.get_document_catalog(user_context.get("uid"))

            is_list_query = bool(re.search(
                r"\b(list|all|show|enumerate|provide|give me|top)\b", query_text or "", re.I))
            is_catalog_query = bool(re.search(
                r"\b(document|documents|doc|docs|file|files|knowledge base|drive|folder|stock|stocks|company|companies|ticker|tickers)\b", query_text or "", re.I))

            # Use structured response for bullet count
            bullet_count = len(response_obj.answer.split(
                '\n')) if response_obj.answer_style == 'bullets' else response_obj.answer.count('\n- ')

            if is_list_query and (is_catalog_query or (user_catalog and bullet_count == 0)):
                if user_catalog:
                    requested = parse_list_limit(query_text or "")
                    list_all = bool(
                        re.search(r"\ball\b", query_text or "", re.I))
                    catalog_count = len(user_catalog)
                    needs_fallback = bullet_count == 0
                    if requested:
                        needs_fallback = needs_fallback or bullet_count != requested
                    elif list_all and bullet_count < catalog_count:
                        needs_fallback = True

                    if needs_fallback:
                        return format_document_catalog_response(user_catalog, limit=requested)

        return response_obj.to_markdown()

    @classmethod
    def query_structured(cls, question, user_context) -> StructuredResponse:
        """
        Query the RAG system and return a StructuredResponse object.
        """
        user_id = user_context.get("uid")
        settings = cls.get_service_context(
            user_context.get("openai_api_key"), user_id=user_id
        )
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

        # Extract selection info for logging and prompt linking
        selector_result = (response.metadata or {}).get("selector_result")
        selected_inds = []
        if selector_result is not None:
            selections = getattr(selector_result, "selections", None)
            if selections:
                selected_inds = [selection.index for selection in selections]
            else:
                selected_inds = list(
                    getattr(selector_result, "inds", None) or [])

        # Link prompts to Opik trace if available
        try:
            from opik.opik_context import update_current_trace
            prompts_to_link = []

            if 0 in selected_inds:
                if hasattr(casual_engine, "opik_prompt") and casual_engine.opik_prompt:
                    prompts_to_link.append(casual_engine.opik_prompt)
            if 1 in selected_inds:
                if hasattr(rag_engine, "opik_prompts") and rag_engine.opik_prompts:
                    prompts_to_link.extend(rag_engine.opik_prompts)

            if prompts_to_link:
                update_current_trace(prompts=prompts_to_link)
        except Exception as e:
            cls.logger.debug("Failed to link prompts to Opik trace: %s", e)

        # Parse structured output based on selection
        raw_text = response.response or ""
        if 1 in selected_inds:
            structured = parse_rag_json(raw_text)
        else:
            structured = parse_casual_json(raw_text)

        # Attach original LlamaIndex response for metadata extraction in query()
        structured._llama_response = response

        # Attach source file names to citations if missing/generic
        if 1 in selected_inds and hasattr(response, 'source_nodes'):
            node_map = {
                node.node.id_: node.node for node in response.source_nodes}
            for citation in structured.citations:
                if not citation.file_name or citation.file_name.lower() in ["unknown", ""]:
                    # Try to find file_name in source nodes
                    for node in response.source_nodes:
                        if node.node.metadata.get("file_id") == citation.file_id:
                            citation.file_name = node.node.metadata.get(
                                "file_name", "document")
                            break

        return structured
