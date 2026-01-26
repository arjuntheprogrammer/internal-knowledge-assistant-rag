"""Metadata extraction and normalization utilities."""

import os
from typing import Any, Dict, Optional


def resolve_file_name(metadata: Dict[str, Any]) -> Optional[str]:
    """Extract file name from various metadata keys."""
    return (
        metadata.get("file_name")
        or metadata.get("file name")
        or metadata.get("filename")
        or metadata.get("file_path")
    )


def resolve_file_id(metadata: Dict[str, Any]) -> Optional[str]:
    """Extract file ID from various metadata keys."""
    return metadata.get("file_id") or metadata.get("file id")


def resolve_mime_type(metadata: Dict[str, Any]) -> Optional[str]:
    """Extract mime type from various metadata keys."""
    return metadata.get("mime_type") or metadata.get("mime type")


def resolve_revision_id(metadata: Dict[str, Any]) -> str:
    """Extract revision or modification timestamp."""
    revision = (
        metadata.get("modified_time")
        or metadata.get("modifiedTime")
        or metadata.get("modified_at")
        or metadata.get("modified at")
    )
    return str(revision) if revision else "unknown"


def normalize_metadata(
    metadata: Dict[str, Any],
    page_number: Optional[int] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Standardize metadata keys for consistency."""
    meta = dict(metadata or {})

    file_name = resolve_file_name(meta)
    if file_name:
        meta["file_name"] = file_name

    file_id = resolve_file_id(meta)
    if file_id:
        meta["file_id"] = file_id

    mime_type = resolve_mime_type(meta)
    if mime_type:
        meta["mime_type"] = mime_type

    if page_number is not None:
        meta["page_number"] = page_number

    # extraction_method is the new canonical field for 'source'
    extraction_method = source or meta.get(
        "extraction_method") or meta.get("source")
    if extraction_method:
        meta["extraction_method"] = extraction_method
        meta["source"] = extraction_method  # Keep for backward compatibility

    meta["revision_id"] = resolve_revision_id(meta)

    return meta


def get_stock_name(metadata: Dict[str, Any]) -> Optional[str]:
    """Extract stock name from file name metadata."""
    stock_name = metadata.get("stock_name")
    if not stock_name:
        file_name = resolve_file_name(metadata)
        if file_name:
            base_name = os.path.basename(str(file_name))
            stock_name = os.path.splitext(base_name)[0].strip()
    return stock_name
