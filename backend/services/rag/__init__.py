from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.base.response.schema import Response
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.tools import QueryEngineTool
import logging
import os
import re

from .rag_context import get_service_context
from .rag_chroma import get_chroma_vector_store
from . import rag_google_drive
from .rag_formatter import RAGFormatter


class RAGService:
    index = None
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

        try:
            settings = cls.get_service_context()
            vector_store = cls.get_vector_store()
            storage_context = None
            if vector_store:
                storage_context = StorageContext.from_defaults(
                    vector_store=vector_store
                )

            cls.index = VectorStoreIndex.from_documents(
                documents,
                callback_manager=settings.callback_manager,
                storage_context=storage_context,
            )
            print("Index initialized successfully.")
            if vector_store:
                cls._log_vector_store_count(vector_store)
        except Exception as e:
            print(f"Index initialization error: {e}")

    @classmethod
    def _build_rag_query_engine(cls, query_bundle: QueryBundle, llm):
        query_text = query_bundle.query_str or str(query_bundle)
        is_list_query = bool(
            re.search(
                r"\b(list|all|show|enumerate|provide|give me)\b", query_text, re.I
            )
        )
        similarity_top_k = 10 if is_list_query else 3

        text_qa_template = PromptTemplate(
            "Context: {context_str}\n"
            "Answer the question based ONLY on the context. "
            "If unsure, say 'Insufficient information'. "
            "Format as Markdown with:\n"
            "**Answer:** [response]\n"
            "**Sources:** bullet list of citations\n"
            "If the question asks for a list, use bullet points.\n"
            "Question: {query_str}\n**Answer:** "
        )
        refine_template = PromptTemplate(
            "Original: {query_str}\nPrevious answer: {existing_answer}\n"
            "Refine using new context: {context_str}\n"
            "If the question asks for a list, keep bullet points. "
            "Keep the Markdown formatting. **Answer:** "
        )
        return cls.index.as_query_engine(
            llm=llm,
            similarity_top_k=similarity_top_k,
            text_qa_template=text_qa_template,
            refine_template=refine_template,
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
        selected_index = None
        selected_reason = None
        if selector_result is not None:
            selected_index = getattr(selector_result, "ind", None)
            selected_reason = getattr(selector_result, "reason", None)
            if selected_index is None:
                inds = getattr(selector_result, "inds", [])
                selected_index = inds[0] if inds else None
                reasons = getattr(selector_result, "reasons", None)
                if reasons:
                    selected_reason = reasons[0]

        if selected_index is not None:
            selected_tool = tools[selected_index].metadata.name
        else:
            selected_tool = "unknown"

        cls.logger.info(
            "rag_router selection=%s reason=%s query_len=%s",
            selected_tool,
            selected_reason,
            len(query_text) if query_text else 0,
        )

        if selected_index == 1:
            return RAGFormatter.format_markdown_response(response)
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

    def _get_prompt_modules(self):
        return {}

    def _query(self, query_bundle: QueryBundle):
        if not RAGService.index:
            RAGService.initialize_index()

        if not RAGService.index:
            return Response("Knowledge base is empty. Please add documents.")

        query_engine = RAGService._build_rag_query_engine(query_bundle, self._llm)
        return query_engine.query(query_bundle)

    async def _aquery(self, query_bundle: QueryBundle):
        return self._query(query_bundle)
