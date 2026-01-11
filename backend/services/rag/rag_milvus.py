import os
from llama_index.vector_stores.milvus import MilvusVectorStore

def get_milvus_vector_store(user_id=None):
    # Zilliz/Milvus configuration
    # For Zilliz, URI is the Public Endpoint and Token is the API Key
    uri = os.getenv("MILVUS_URI")
    token = os.getenv("MILVUS_TOKEN")
    collection_name = os.getenv("MILVUS_COLLECTION", "internal_knowledge_assistant")

    # If user_id is provided, we can either use a separate collection
    # or use metadata filtering. LlamaIndex MilvusVectorStore supports collections.
    # To match previous Chroma behavior, we'll append user_id to collection name.
    # Note: Milvus collection names shouldn't have hyphens, using underscores.
    if user_id:
        # Sanitize user_id for collection name (remove non-alphanumeric/underscore)
        safe_user_id = "".join(c if c.isalnum() else "_" for c in user_id)
        collection_name = f"{collection_name}_{safe_user_id}"

    return MilvusVectorStore(
        uri=uri,
        token=token,
        collection_name=collection_name,
        dim=1536,  # Default for OpenAI text-embedding-3-small / ada-002
        overwrite=True
    )
