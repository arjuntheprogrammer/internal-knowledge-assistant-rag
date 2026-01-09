from llama_index import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.prompts import PromptTemplate
from llama_index.response.schema import Response
from typing import Any
import os
import re

from backend.services.rag_context import get_service_context
from backend.services.rag_chroma import get_chroma_vector_store
from backend.services import rag_google_drive


class RAGService:
    index = None

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
            service_context = cls.get_service_context()
            vector_store = cls.get_vector_store()
            storage_context = None
            if vector_store:
                storage_context = StorageContext.from_defaults(
                    vector_store=vector_store
                )

            cls.index = VectorStoreIndex.from_documents(
                documents,
                service_context=service_context,
                storage_context=storage_context,
            )
            print("Index initialized successfully.")
            if vector_store:
                cls._log_vector_store_count(vector_store)
        except Exception as e:
            print(f"Index initialization error: {e}")

    @classmethod
    def get_drive_file_list(cls):
        return rag_google_drive.get_drive_file_list()

    @classmethod
    def query(cls, question):
        if not cls.index:
            cls.initialize_index()

        if not cls.index:
            return "Knowledge base is empty. Please add documents."

        query_text = str(question)
        is_list_query = bool(
            re.search(r"\b(list|all|show|enumerate|provide|give me)\b", query_text, re.I)
        )
        similarity_top_k = 10 if is_list_query else 3

        text_qa_template = PromptTemplate(
            "Context: {context_str}\n"
            "Answer the question based ONLY on the context. "
            "If unsure, say 'Insufficient information'. "
            "Format as Markdown with:\n"
            "Answer: [response]\n"
            "**Sources:** bullet list of citations\n"
            "If the question asks for a list, use bullet points.\n"
            "Question: {query_str}\nAnswer: "
        )
        refine_template = PromptTemplate(
            "Original: {query_str}\nPrevious answer: {existing_answer}\n"
            "Refine using new context: {context_str}\n"
            "If the question asks for a list, keep bullet points. "
            "Keep the Markdown formatting. Answer: "
        )
        query_engine = cls.index.as_query_engine(
            similarity_top_k=similarity_top_k,
            text_qa_template=text_qa_template,
            refine_template=refine_template,
        )
        response = query_engine.query(question)
        return cls._format_markdown_response(response)

    @staticmethod
    def _log_vector_store_count(vector_store):
        try:
            collection = getattr(vector_store, "_collection", None)
            if collection is not None and hasattr(collection, "count"):
                print(f"Chroma collection count: {collection.count()}")
        except Exception as exc:
            print(f"Chroma collection count check failed: {exc}")

    @classmethod
    def _format_markdown_response(cls, response: Any) -> str:
        response_text = cls._extract_response_text(response) or ""
        response_text = response_text.strip()

        answer_text, sources_text = cls._split_sources(response_text)
        if not answer_text:
            answer_text = "Insufficient information"

        sources_block = cls._format_sources(response, sources_text)
        return f"{answer_text}\n\n{sources_block}"

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        if isinstance(response, Response):
            return response.response or ""
        return str(response)

    @staticmethod
    def _split_sources(text: str) -> tuple[str, str]:
        if not text:
            return "", ""
        match = re.search(
            r"(?im)^[\s>*-]*\**sources\**\s*[:\-]\s*",
            text,
        )
        if not match:
            return text, ""
        return text[: match.start()].strip(), text[match.end() :].strip()

    @staticmethod
    def _format_sources(response: Any, sources_text: str) -> str:
        sources = []
        source_nodes = getattr(response, "source_nodes", None)
        if source_nodes:
            for node_with_score in source_nodes:
                node = getattr(node_with_score, "node", None)
                if not node:
                    continue
                metadata = getattr(node, "metadata", {}) or {}
                label = (
                    metadata.get("file name")
                    or metadata.get("file_name")
                    or metadata.get("filename")
                    or metadata.get("file id")
                    or node.node_id
                )
                if label and label not in sources:
                    if label != node.node_id:
                        sources.append(f"{label} (id: {node.node_id})")
                    else:
                        sources.append(label)

        if sources:
            bullets = "\n".join(f"- {source}" for source in sources)
            return f"\n**Sources:**\n{bullets}"

        cleaned_sources = sources_text.strip()
        if cleaned_sources:
            cleaned_sources = re.sub(
                r"(?i)^\s*\**sources\**\s*[:\-]\s*",
                "",
                cleaned_sources,
            ).strip()
            if re.search(r"(?m)^\s*[-*]\s+", cleaned_sources):
                return f"**Sources:**\n{cleaned_sources}"
            if "," in cleaned_sources:
                items = [item.strip() for item in cleaned_sources.split(",") if item.strip()]
                bullets = "\n".join(f"- {item}" for item in items)
                return f"**Sources:**\n{bullets}" if bullets else "**Sources:** None"
            return f"**Sources:** {cleaned_sources}"

        return "**Sources:** None"
