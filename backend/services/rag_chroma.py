import os

from llama_index.vector_stores import ChromaVectorStore


def _get_chroma_port(value):
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("CHROMA_PORT must be an integer.") from exc


def get_chroma_vector_store():
    collection_name = os.getenv("CHROMA_COLLECTION", "internal-knowledge-assistant")
    host = os.getenv("CHROMA_HOST", "localhost")
    port = _get_chroma_port(os.getenv("CHROMA_PORT", "8000"))
    persist_dir = os.getenv("CHROMA_PERSIST_DIR")
    ssl = os.getenv("CHROMA_SSL", "false").lower() in {"1", "true", "yes"}

    if persist_dir:
        return ChromaVectorStore.from_params(
            collection_name=collection_name,
            persist_dir=persist_dir,
        )

    return ChromaVectorStore.from_params(
        collection_name=collection_name,
        host=host,
        port=port,
        ssl=ssl,
    )
