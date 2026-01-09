from llama_index import VectorStoreIndex, SimpleDirectoryReader, StorageContext
import os

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

        query_engine = cls.index.as_query_engine()
        response = query_engine.query(question)
        return str(response)

    @staticmethod
    def _log_vector_store_count(vector_store):
        try:
            collection = getattr(vector_store, "_collection", None)
            if collection is not None and hasattr(collection, "count"):
                print(f"Chroma collection count: {collection.count()}")
        except Exception as exc:
            print(f"Chroma collection count check failed: {exc}")
