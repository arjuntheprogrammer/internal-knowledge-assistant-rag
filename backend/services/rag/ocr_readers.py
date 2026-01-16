import logging
import mimetypes
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Dict, List, Optional, Tuple

import fitz
from llama_index.core import Document
from pypdf import PdfReader
from PIL import Image

from .ocr_utils import (
    build_cache_key,
    build_fallback_config,
    get_ocr_config,
    is_ocr_quality_low,
    load_cached_ocr,
    ocr_quality_score,
    ocr_image,
    preprocess_image,
    store_cached_ocr,
    text_density,
)
from backend.utils.metadata import (
    resolve_file_id,
    resolve_file_name,
    resolve_mime_type,
    resolve_revision_id,
    normalize_metadata,
)


logger = logging.getLogger(__name__)

IMAGE_MIME_TYPES = {"image/png", "image/jpeg"}
PDF_MIME_TYPE = "application/pdf"


def is_image_mime_type(mime_type: Optional[str]) -> bool:
    return (mime_type or "").lower() in IMAGE_MIME_TYPES


def is_pdf_mime_type(mime_type: Optional[str]) -> bool:
    return (mime_type or "").lower() == PDF_MIME_TYPE


def load_documents_for_file(
    file_path: str, metadata: Dict[str, Any], config=None
) -> List[Document]:
    config = config or get_ocr_config()
    mime_type = _resolve_mime_type(file_path, metadata)
    if is_pdf_mime_type(mime_type):
        return load_pdf_documents(file_path, metadata, config)
    if is_image_mime_type(mime_type):
        doc = load_image_document(file_path, metadata, config)
        return [doc] if doc else []
    return []


def load_pdf_documents(
    file_path: str, metadata: Dict[str, Any], config=None
) -> List[Document]:
    config = config or get_ocr_config()
    documents: List[Document] = []
    try:
        reader = PdfReader(file_path)
    except Exception as exc:
        logger.warning("Failed reading PDF %s: %s", file_path, exc)
        return documents

    file_id = resolve_file_id(metadata) or os.path.basename(file_path)
    revision_id = resolve_revision_id(metadata)
    config_hash = config.config_hash()
    pages_to_ocr: List[int] = []

    for index, page in enumerate(reader.pages):
        page_number = index + 1
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.warning(
                "Failed extracting PDF text page %s (%s): %s",
                page_number,
                file_path,
                exc,
            )
            text = ""
        if text_density(text) >= config.pdf_text_min_chars:
            doc = _build_document(
                text,
                metadata,
                page_number,
                source="digital_text",
            )
            if doc:
                _set_document_id(doc, file_id, page_number, "digital_text")
                documents.append(doc)
        else:
            pages_to_ocr.append(page_number)

    if pages_to_ocr:
        documents.extend(
            _ocr_pdf_pages(
                file_path,
                metadata,
                pages_to_ocr,
                file_id,
                revision_id,
                config,
                config_hash,
            )
        )

    return documents


def load_image_document(
    file_path: str, metadata: Dict[str, Any], config=None
) -> Optional[Document]:
    config = config or get_ocr_config()
    file_id = resolve_file_id(metadata) or os.path.basename(file_path)
    revision_id = resolve_revision_id(metadata)
    config_hash = config.config_hash()
    page_number = 1
    cache_key = build_cache_key(file_id, revision_id, page_number, config_hash)
    cached = None
    cached_low_quality = False
    if config.cache_enabled:
        cached = load_cached_ocr(config.cache_dir, cache_key)
        if cached is not None:
            text, confidence = cached
            if not is_ocr_quality_low(text, confidence, config):
                return _document_from_ocr(
                    text,
                    confidence,
                    metadata,
                    page_number,
                    file_id,
                )
            cached_low_quality = True

    try:
        with Image.open(file_path) as image:
            image = image.copy()
    except Exception as exc:
        logger.warning("Failed opening image %s: %s", file_path, exc)
        return None

    text = ""
    confidence = None
    if cached is not None and cached_low_quality:
        text, confidence = cached
    else:
        try:
            processed = preprocess_image(image, config)
            text, confidence = ocr_image(processed, config)
        except Exception as exc:
            logger.warning("OCR failed for image %s: %s", file_path, exc)
            return None

    if config.cache_enabled:
        store_cached_ocr(config.cache_dir, cache_key, text, confidence)

    if is_ocr_quality_low(text, confidence, config):
        fallback_config = build_fallback_config(config)
        if fallback_config:
            fallback_hash = fallback_config.config_hash()
            fallback_key = build_cache_key(
                file_id, revision_id, page_number, fallback_hash
            )
            fallback_cached = None
            if config.cache_enabled:
                fallback_cached = load_cached_ocr(
                    fallback_config.cache_dir, fallback_key
                )
            if fallback_cached is None:
                try:
                    fallback_processed = preprocess_image(
                        image, fallback_config)
                    fallback_text, fallback_confidence = ocr_image(
                        fallback_processed, fallback_config
                    )
                except Exception as exc:
                    logger.warning(
                        "Fallback OCR failed for image %s: %s", file_path, exc
                    )
                    fallback_text, fallback_confidence = "", None
                if config.cache_enabled:
                    store_cached_ocr(
                        fallback_config.cache_dir,
                        fallback_key,
                        fallback_text,
                        fallback_confidence,
                    )
            else:
                fallback_text, fallback_confidence = fallback_cached

            if ocr_quality_score(
                fallback_text, fallback_confidence, fallback_config
            ) > ocr_quality_score(text, confidence, config):
                text, confidence = fallback_text, fallback_confidence

    return _document_from_ocr(
        text,
        confidence,
        metadata,
        page_number,
        file_id,
    )


def _ocr_pdf_pages(
    file_path: str,
    metadata: Dict[str, Any],
    pages: List[int],
    file_id: str,
    revision_id: str,
    config,
    config_hash: str,
) -> List[Document]:
    documents: List[Document] = []

    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        futures = {
            executor.submit(
                _ocr_pdf_page,
                file_path,
                page_number,
                file_id,
                revision_id,
                config,
                config_hash,
            ): page_number
            for page_number in pages
        }

        for future, page_number in futures.items():
            try:
                text, confidence = future.result(
                    timeout=config.page_timeout_seconds)
            except TimeoutError:
                future.cancel()
                logger.warning(
                    "OCR timeout for PDF page %s (%s)",
                    page_number,
                    file_path,
                )
                continue
            except Exception as exc:
                logger.warning(
                    "OCR failed for PDF page %s (%s): %s",
                    page_number,
                    file_path,
                    exc,
                )
                continue

            doc = _document_from_ocr(
                text,
                confidence,
                metadata,
                page_number,
                file_id,
            )
            if doc:
                documents.append(doc)

    return documents


def _ocr_pdf_page(
    file_path: str,
    page_number: int,
    file_id: str,
    revision_id: str,
    config,
    config_hash: str,
) -> Tuple[str, Optional[float]]:
    cache_key = build_cache_key(file_id, revision_id, page_number, config_hash)
    cached = None
    cached_low_quality = False
    if config.cache_enabled:
        cached = load_cached_ocr(config.cache_dir, cache_key)
        if cached is not None:
            text, confidence = cached
            if not is_ocr_quality_low(text, confidence, config):
                return cached
            cached_low_quality = True

    image = _render_pdf_page(file_path, page_number, config.dpi)
    if image is None:
        return "", None

    if cached is not None and cached_low_quality:
        text, confidence = cached
    else:
        processed = preprocess_image(image, config)
        text, confidence = ocr_image(processed, config)

    if config.cache_enabled:
        store_cached_ocr(config.cache_dir, cache_key, text, confidence)

    if is_ocr_quality_low(text, confidence, config):
        fallback_config = build_fallback_config(config)
        if fallback_config:
            fallback_hash = fallback_config.config_hash()
            fallback_key = build_cache_key(
                file_id, revision_id, page_number, fallback_hash
            )
            fallback_cached = None
            if config.cache_enabled:
                fallback_cached = load_cached_ocr(
                    fallback_config.cache_dir, fallback_key
                )
            if fallback_cached is None:
                fallback_processed = preprocess_image(image, fallback_config)
                fallback_text, fallback_confidence = ocr_image(
                    fallback_processed, fallback_config
                )
                if config.cache_enabled:
                    store_cached_ocr(
                        fallback_config.cache_dir,
                        fallback_key,
                        fallback_text,
                        fallback_confidence,
                    )
            else:
                fallback_text, fallback_confidence = fallback_cached

            if ocr_quality_score(
                fallback_text, fallback_confidence, fallback_config
            ) > ocr_quality_score(text, confidence, config):
                return fallback_text, fallback_confidence

    return text, confidence


def _render_pdf_page(file_path: str, page_number: int, dpi: int) -> Optional[Image.Image]:
    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        logger.warning(
            "Failed opening PDF for rendering %s: %s", file_path, exc)
        return None
    try:
        page_index = page_number - 1
        if page_index < 0 or page_index >= doc.page_count:
            return None
        page = doc.load_page(page_index)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return image
    except Exception as exc:
        logger.warning(
            "Failed rendering PDF page %s (%s): %s", page_number, file_path, exc
        )
        return None
    finally:
        doc.close()


def _document_from_ocr(
    text: str,
    confidence: Optional[float],
    metadata: Dict[str, Any],
    page_number: int,
    file_id: str,
) -> Optional[Document]:
    if not text or not text.strip():
        return None
    doc = _build_document(text, metadata, page_number, source="ocr")
    if doc is None:
        return None
    if confidence is not None:
        doc.metadata["confidence"] = confidence
    _set_document_id(doc, file_id, page_number, "ocr")
    return doc


def _build_document(
    text: str,
    metadata: Dict[str, Any],
    page_number: int,
    source: str,
) -> Optional[Document]:
    if not text or not text.strip():
        return None
    normalized = normalize_metadata(
        metadata, page_number=page_number, source=source)
    try:
        return Document(text=text, metadata=normalized)
    except Exception as exc:
        logger.warning(
            "Failed creating document for page %s: %s", page_number, exc)
        return None


def _resolve_mime_type(file_path: str, metadata: Dict[str, Any]) -> str:
    mime_type = resolve_mime_type(metadata)
    if mime_type:
        return str(mime_type)
    guessed, _ = mimetypes.guess_type(file_path)
    if guessed:
        metadata["mime_type"] = guessed
        return guessed
    return ""


def _set_document_id(doc: Document, file_id: str, page_number: int, source: str) -> None:
    try:
        doc.id_ = f"{file_id}_page_{page_number}_{source}"
    except Exception:
        return
