import logging
import os
import re
from backend.utils.metadata import normalize_metadata, get_stock_name

logger = logging.getLogger(__name__)


def log_vector_store_count(vector_store):
    try:
        # Check for MilvusVectorStore
        client = getattr(vector_store, "client", None)
        collection_name = getattr(vector_store, "collection_name", None)
        if client is not None and collection_name:
            stats = client.get_collection_stats(collection_name)
            count = stats.get("row_count", 0)
            logger.info(
                f"Milvus collection '{collection_name}' count: {count}")
            return
    except Exception as exc:
        logger.warning(f"Vector store count check failed: {exc}")


def annotate_documents(documents, user_id=None):
    for doc in documents:
        metadata = getattr(doc, "metadata", None)
        if not isinstance(metadata, dict):
            continue
        if user_id:
            metadata["user_id"] = user_id

        stock_name = get_stock_name(metadata)
        if stock_name:
            metadata["stock_name"] = stock_name

        # Ensure normalized keys exist
        normalized = normalize_metadata(metadata)
        metadata.update(normalized)


def build_document_catalog(documents):
    catalog = {}
    for doc in documents:
        metadata = getattr(doc, "metadata", None)
        if not isinstance(metadata, dict):
            continue

        doc_name = get_stock_name(metadata)
        if not doc_name:
            continue

        drive_id = metadata.get("file_id") or metadata.get("file id")
        url = None
        if drive_id:
            url = f"https://drive.google.com/file/d/{drive_id}/view"
        catalog.setdefault(doc_name, url)
    return sorted(
        [{"name": name, "url": url} for name, url in catalog.items()],
        key=lambda item: item["name"].lower(),
    )


def parse_list_limit(query_text):
    if not query_text:
        return None
    match = re.search(
        r"\b(?:top|list|show|give me|provide)\s+(\d+)\b", query_text, re.I
    )
    if match:
        return int(match.group(1))
    match = re.search(
        r"\b(\d+)\s+(?:stocks|stock|companies|company|tickers|ticker)\b",
        query_text,
        re.I,
    )
    if match:
        return int(match.group(1))
    return None


def extract_bullet_count(response_text):
    if not response_text:
        return 0
    answer_match = re.search(
        r"(?is)\*\*answer\*\*\s*:?(.*?)(\*\*sources\*\*|$)",
        response_text,
    )
    answer_text = answer_match.group(1) if answer_match else response_text
    return len(re.findall(r"(?m)^\s*[-*]\s+", answer_text))


def format_document_catalog_response(catalog, limit=None):
    catalog = catalog or []
    if limit:
        catalog = catalog[:limit]
    if not catalog:
        return "**Answer:** Insufficient information\n\n**Sources:** None"
    answer_lines = [f"- {item['name']}" for item in catalog]
    sources = []
    for item in catalog:
        if item.get("url"):
            sources.append(f"- [{item['name']}]({item['url']})")
    answer_block = "**Answer:**\n" + "\n".join(answer_lines)
    if sources:
        sources_block = "**Sources:**\n" + "\n".join(sources)
    else:
        sources_block = "**Sources:** None"
    return f"{answer_block}\n\n{sources_block}"
