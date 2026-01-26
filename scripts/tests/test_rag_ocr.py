#!/usr/bin/env python3
"""
RAG OCR Functionality Tests.

This script verifies the hybrid OCR/Digital-Text extraction logic for PDFs
and images. It creates synthetic documents (purely scanned, purely digital,
and hybrid) and ensures the OCR system correctly identifies the extraction
method for each page while preserving metadata.

Usage:
    python3 scripts/tests/test_rag_ocr.py
"""
from backend.services.rag.ocr_utils import get_ocr_config
from backend.services.rag import ocr_readers
from PIL import Image, ImageDraw, ImageFont
import fitz
import os
import sys
import tempfile

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def create_text_image(path, text, size=(1200, 400)):
    image = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((40, 40), text, fill="black", font=font)
    image.save(path)


def create_scanned_pdf(path, text):
    with tempfile.TemporaryDirectory() as tmpdir:
        image_path = os.path.join(tmpdir, "scan.png")
        create_text_image(image_path, text)
        img = Image.open(image_path)
        doc = fitz.open()
        page = doc.new_page(width=img.width, height=img.height)
        page.insert_image(
            fitz.Rect(0, 0, img.width, img.height), filename=image_path)
        doc.save(path)
        doc.close()


def create_hybrid_pdf(path, digital_text, image_text):
    with tempfile.TemporaryDirectory() as tmpdir:
        image_path = os.path.join(tmpdir, "page2.png")
        create_text_image(image_path, image_text)
        img = Image.open(image_path)
        doc = fitz.open()
        page1 = doc.new_page(width=612, height=792)
        page1.insert_text((72, 72), digital_text)
        page2 = doc.new_page(width=img.width, height=img.height)
        page2.insert_image(
            fitz.Rect(0, 0, img.width, img.height), filename=image_path)
        doc.save(path)
        doc.close()


def assert_has_metadata(doc, expected_source, expected_page):
    metadata = doc.metadata or {}
    assert metadata.get("source") == expected_source
    assert metadata.get("page_number") == expected_page
    assert metadata.get("file_name")
    assert metadata.get("mime_type")


def test_scanned_pdf(config):
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "scanned.pdf")
        create_scanned_pdf(pdf_path, "SCANNED PDF OCR SAMPLE")
        metadata = {
            "file id": "scanned_pdf",
            "file name": "scanned.pdf",
            "mime type": "application/pdf",
            "modified at": "2024-01-01T00:00:00Z",
        }
        docs = ocr_readers.load_pdf_documents(
            pdf_path, metadata, config=config)
        assert docs, "Expected OCR documents for scanned PDF"
        assert any(doc.metadata.get("source") == "ocr" for doc in docs)
        assert_has_metadata(
            docs[0],
            docs[0].metadata.get("source"),
            docs[0].metadata.get("page_number"),
        )


def test_hybrid_pdf(config):
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "hybrid.pdf")
        digital_text = (
            "This page contains digital text that should exceed the OCR threshold."
        )
        create_hybrid_pdf(pdf_path, digital_text, "IMAGE OCR PAGE TWO")
        metadata = {
            "file id": "hybrid_pdf",
            "file name": "hybrid.pdf",
            "mime type": "application/pdf",
            "modified at": "2024-01-02T00:00:00Z",
        }
        docs = ocr_readers.load_pdf_documents(
            pdf_path, metadata, config=config)
        sources = {
            (doc.metadata.get("page_number"), doc.metadata.get("source"))
            for doc in docs
        }
        assert (1, "digital_text") in sources, "Expected digital text on page 1"
        assert (2, "ocr") in sources, "Expected OCR on page 2"
        assert any(
            digital_text.strip() in doc.text
            for doc in docs
            if doc.metadata.get("source") == "digital_text"
        )


def test_image_ocr(config):
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "sample.png")
        create_text_image(img_path, "IMAGE OCR SAMPLE")
        metadata = {
            "file id": "image_file",
            "file name": "sample.png",
            "mime type": "image/png",
            "modified at": "2024-01-03T00:00:00Z",
        }
        docs = ocr_readers.load_documents_for_file(
            img_path, metadata, config=config)
        assert docs, "Expected OCR document for image"
        doc = docs[0]
        assert_has_metadata(doc, "ocr", 1)
        assert doc.text.strip()


def main():
    os.environ.setdefault("OCR_LANGS", "eng")
    os.environ.setdefault("OCR_PSM", "6")
    os.environ.setdefault("OCR_OEM", "3")
    os.environ.setdefault("OCR_MAX_WORKERS", "2")
    os.environ.setdefault("OCR_PAGE_TIMEOUT_SECONDS", "30")
    os.environ.setdefault("OCR_PDF_TEXT_MIN_CHARS", "20")
    os.environ.setdefault("OCR_CACHE_ENABLED", "0")

    with tempfile.TemporaryDirectory() as cache_dir:
        os.environ["OCR_CACHE_DIR"] = cache_dir
        config = get_ocr_config()
        test_scanned_pdf(config)
        test_hybrid_pdf(config)
        test_image_ocr(config)

    print("OCR tests passed.")


if __name__ == "__main__":
    main()
