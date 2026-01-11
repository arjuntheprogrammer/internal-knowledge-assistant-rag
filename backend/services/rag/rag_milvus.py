import os
from llama_index.vector_stores.milvus import MilvusVectorStore

def get_milvus_vector_store(user_id=None):
    # Zilliz/Milvus configuration
    # For Zilliz, URI is the Public Endpoint and Token is the API Key
    uri = os.getenv("MILVUS_URI")
    token = os.getenv("MILVUS_TOKEN")
    collection_name = os.getenv("MILVUS_COLLECTION", "internal_knowledge_assistant")

    # Multi-tenant shared collection: stop appending user_id to name
    # overwrite=False because multiple users share this collection
    return MilvusVectorStore(
        uri=uri,
        token=token,
        collection_name=collection_name,
        dim=1536,  # Default for OpenAI text-embedding-3-small / ada-002
        overwrite=False
    )
