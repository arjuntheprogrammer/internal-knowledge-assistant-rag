import logging
import os
import re
from typing import Any, Dict, List, Optional, Union

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
    format_document_catalog_response,
    log_vector_store_count,
    parse_list_limit,
)
from .engines import CasualQueryEngine, LazyRAGQueryEngine
from .rag_milvus import get_milvus_vector_store
from .rag_context import get_service_context
from .schemas.llm_output import LLMOutput
from .schemas.system_output import SystemOutput, RetrievalHit
from .opik_prompts import link_prompts_to_current_trace


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
        def notify(msg, progress):
            if on_progress:
                on_progress(msg, progress)
            else:
                cls.logger.info(f"Indexing progress: {msg} ({progress}%)")

        user_id = user_context.get("uid")
        if not user_id:
            return

        notify("Connecting to Google Drive...", 10)
        try:
            file_ids = user_context.get("drive_file_ids") or []
            documents = rag_google_drive.load_google_drive_documents_by_file_ids(
                user_id=user_id, file_ids=file_ids, token_json=user_context.get(
                    "google_token")
            ) if file_ids else []
        except Exception as e:
            cls.logger.error(f"Failed to load documents: {e}")
            raise

        if not documents:
            notify("No documents found.", 100)
            return

        notify(f"Processing {len(documents)} documents...", 40)
        annotate_documents(documents, user_id=user_id)
        cls._document_catalog_by_user[user_id] = build_document_catalog(
            documents)

        try:
            notify("Analyzing document structure...", 50)
            settings = cls.get_service_context(
                user_context.get("openai_api_key"), user_id=user_id)
            vector_store = cls.get_vector_store(user_id)

            if vector_store:
                try:
                    notify("Clearing old index data...", 55)
                    client = getattr(vector_store, "client", None)
                    col = getattr(vector_store, "collection_name", None)
                    if client and col:
                        client.delete(collection_name=col,
                                      filter=f"user_id == '{user_id}'")
                except Exception:
                    pass

            storage_context = StorageContext.from_defaults(
                vector_store=vector_store) if vector_store else None

            notify("Preparing nodes for embedding...", 60)
            splitter = SentenceSplitter(chunk_size=512, chunk_overlap=60)
            for doc in documents:
                if doc.metadata.get("file_id"):
                    doc.id_ = doc.metadata.get("file_id")

            nodes = splitter.get_nodes_from_documents(documents)
            node_counts = {}
            for node in nodes:
                m = node.metadata
                f_id, rev = m.get("file_id"), m.get("revision_id") or "unknown"
                p, meth = m.get("page_number") or 1, m.get(
                    "extraction_method") or m.get("source") or "text"
                key = (f_id, rev, p, meth)
                idx = node_counts.get(key, 0)
                node_counts[key] = idx + 1
                node.id_ = f"{f_id}#rev:{rev}#p:{p}#m:{meth}#c:{idx}"

            cls._bm25_nodes_by_user[user_id] = nodes
            notify("Generating embeddings and uploading...", 75)
            cls._index_by_user[user_id] = VectorStoreIndex(
                nodes, callback_manager=settings.callback_manager, storage_context=storage_context
            )
            notify("Finalizing...", 95)
            if vector_store:
                log_vector_store_count(vector_store)
            return documents
        except Exception as e:
            cls.logger.error(f"Indexing error: {e}")
            raise

    @classmethod
    def query(cls, question, user_context, return_structured: bool = False) -> Union[str, Dict[str, Any]]:
        """
        Unified query entrypoint.
        Returns markdown string by default, or SystemOutput dict if return_structured=True.
        """
        user_id = user_context.get("uid")
        settings = cls.get_service_context(
            user_context.get("openai_api_key"), user_id=user_id)

        casual_engine = CasualQueryEngine(
            llm=settings.llm, callback_manager=settings.callback_manager)
        rag_engine = LazyRAGQueryEngine(
            llm=settings.llm, callback_manager=settings.callback_manager, service=cls, user_context=user_context)

        tools = [
            QueryEngineTool.from_defaults(query_engine=casual_engine, name="casual_chat",
                                          description="Small talk, greetings, or general questions."),
            QueryEngineTool.from_defaults(query_engine=rag_engine, name="knowledge_base_retrieval",
                                          description="Questions requiring internal documents or company info.")
        ]

        router_engine = RouterQueryEngine.from_defaults(
            query_engine_tools=tools, llm=settings.llm, selector=LLMSingleSelector.from_defaults(llm=settings.llm), select_multi=False
        )

        response = router_engine.query(question)

        # Link prompts to Opik
        selected_tool = "unknown"
        sel_res = (response.metadata or {}).get("selector_result")
        if sel_res:
            inds = [s.index for s in getattr(sel_res, "selections", [])] if hasattr(
                sel_res, "selections") else list(getattr(sel_res, "inds", []))
            if 0 in inds:
                selected_tool = "casual_chat"
                link_prompts_to_current_trace(casual_engine.opik_prompts)
            if 1 in inds:
                selected_tool = "knowledge_base_retrieval"
                link_prompts_to_current_trace(rag_engine.opik_prompts)

        # Build SystemOutput
        llm_output = response.metadata.get("llm_output")
        if not isinstance(llm_output, LLMOutput):
            # Fallback if metadata is missing (shouldn't happen with our engines)
            from .structured_output import parse_structured_output, get_safe_llm_output
            try:
                llm_output = parse_structured_output(
                    response.response, LLMOutput)
            except Exception:
                llm_output = get_safe_llm_output(
                    intent="rag" if selected_tool == "knowledge_base_retrieval" else "casual")

        hits = []
        if hasattr(response, "source_nodes"):
            for sn in response.source_nodes:
                hits.append(RetrievalHit(
                    file_id=sn.node.metadata.get("file_id", "unknown"),
                    file_name=sn.node.metadata.get("file_name"),
                    node_id=sn.node.id_,
                    score=getattr(sn, "score", None),
                    text=sn.node.get_content()[:200]
                ))

        system_output = SystemOutput(
            llm=llm_output,
            retrieval={
                "engine": selected_tool,
                "top_k": len(hits),
                "hits": [h.model_dump() for h in hits],
                "citation_validation": {"invalid_count": 0, "reason": None}
            }
        )

        # Catalog Fallback (Deterministic)
        if selected_tool == "knowledge_base_retrieval":
            query_text = question.query_str if isinstance(
                question, QueryBundle) else str(question)
            user_catalog = cls.get_document_catalog(user_id)

            is_list_query = llm_output.answer_type == "list_documents" or bool(
                re.search(r"\b(list|all|show|enumerate)\b", query_text, re.I))

            # Simple check if catalog fallback is needed
            if is_list_query and user_catalog:
                bullet_count = llm_output.answer_md.count(
                    '\n- ') + llm_output.answer_md.count('\n* ')
                if bullet_count == 0 or len(llm_output.listed_file_ids) == 0:
                    requested = parse_list_limit(query_text)
                    fallback_text = format_document_catalog_response(
                        user_catalog, limit=requested)
                    system_output.llm.answer_md = fallback_text
                    system_output.llm.listed_file_ids = [doc.get("file_id") for doc in user_catalog[:requested] if requested] or [
                        doc.get("file_id") for doc in user_catalog]

        if return_structured:
            return system_output.model_dump()

        return system_output.to_markdown()
