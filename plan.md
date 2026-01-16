# Improved Plan: OCR & Image Support for RAG

This document outlines an improved, production-ready plan for adding robust image and scanned-PDF support to the Internal Knowledge Assistant’s RAG pipeline. It builds on the original proposal by optimizing for **accuracy, performance, debuggability, and future extensibility**.

---

## 1. Goals

* Reliably extract knowledge from:

  * Scanned PDFs
  * Image files (PNG, JPG, screenshots)
  * Hybrid PDFs (digital text + images)
* Minimize unnecessary OCR to control cost and latency
* Preserve strong citations (file + page)
* Enable future image-aware retrieval (diagrams, screenshots)

---

## 2. High-Level Architecture

**Ingestion Pipeline (per file):**

1. MIME-type detection
2. Page-level analysis (for PDFs)
3. Conditional OCR (only when needed)
4. Text + metadata normalization
5. Chunking + embedding
6. Indexing into Milvus

OCR is treated as a **bounded, optional sub-pipeline**, not a default step.

---

## 3. System Dependencies & Docker Updates

### Dockerfile

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*
```

### Language Packs (Optional but Recommended)

Install additional traineddata files if multilingual documents are expected (e.g. `eng+hin`). Expose via env var:

```bash
OCR_LANGS=eng
```

---

## 4. Python Dependencies

```text
pytesseract==0.3.10
Pillow==10.3.0
PyMuPDF==1.24.9
```

> **Note**: Prefer PyMuPDF for PDF page rendering. Keep `pdf2image` as a fallback if needed.

---

## 5. PDF Processing Strategy (Critical Upgrade)

### 5.1 Page-Level Scan Detection

For each PDF page:

1. Extract digital text using `pypdf`
2. Measure text density (char or word count)
3. Decide per page:

| Condition               | Action                     |
| ----------------------- | -------------------------- |
| Sufficient digital text | Index text, skip OCR       |
| Low / no text           | Render page → OCR          |
| Hybrid (optional)       | Render page → OCR + dedupe |

This avoids OCR on text-native PDFs and reduces CPU cost significantly.

---

### 5.2 Page Rasterization (Preferred OCR Path)

Instead of extracting embedded images, **render the entire page as an image**:

```python
image = render_page(pdf, page_num)  # PyMuPDF
text = ocr(image)
```

Benefits:

* Handles rotation, overlays, screenshots
* Avoids missing text in complex PDFs
* Matches how humans see the page

---

### 5.3 OCR Preprocessing (High-Impact)

Before OCR, apply:

* Grayscale conversion
* Contrast normalization
* Adaptive thresholding
* DPI normalization (200–300)

These steps dramatically improve Tesseract accuracy.

---

## 6. Image File Processing

Supported MIME types:

* `image/png`
* `image/jpeg`

Pipeline:

1. Load image via Pillow
2. Preprocess
3. OCR via `pytesseract.image_to_string`
4. Normalize text + metadata

---

## 7. OCR Configuration

Explicitly configure Tesseract:

* Page Segmentation Mode (PSM)
* OCR Engine Mode (OEM)
* Language packs

Example:

```python
pytesseract.image_to_string(
    image,
    lang=OCR_LANGS,
    config="--psm 6 --oem 3"
)
```

Allow overrides via config/env for future tuning.

---

## 8. Data Model for Retrieval (Important)

Store OCR and digital text **as structured chunks**, not concatenated blobs.

Recommended metadata per chunk:

```json
{
  "doc_id": "...",
  "file_name": "...",
  "mime_type": "application/pdf",
  "page_number": 12,
  "source": "ocr" | "digital_text",
  "confidence": 0.92
}
```

Benefits:

* Precise citations (file + page)
* Easier debugging
* Enables future UI highlights

---

## 9. Performance & Reliability Controls

### 9.1 OCR as a Bounded Workload

* Limit OCR concurrency per worker
* Per-page timeout (fail fast on pathological PDFs)
* Log failures per page, not per file

### 9.2 Caching

Cache OCR results by:

```
(file_id, revision_id, page_number, ocr_config_hash)
```

Avoids re-OCR during re-indexing or partial updates.

---

## 10. Google Drive Ingestion Updates

Modify `rag_google_drive.py` to:

* Include image MIME types
* Route files to specialized readers
* Detect file revisions and invalidate OCR cache only when needed

---

## 11. Verification & Evaluation

### Automated Tests

* Scanned PDF (image-only)
* Hybrid PDF
* Screenshot image with text

Assertions:

* OCR text is indexed
* Page numbers preserved
* Citations resolve correctly

### Retrieval Evaluation

Maintain a small eval set:

* Queries whose answers exist *only* in scanned documents
* Track recall@k and faithfulness

---

## 12. Optional: True Image-Aware Retrieval (Future Upgrade)

Beyond OCR:

* Generate image embeddings (e.g. CLIP/SigLIP)
* Caption images/diagrams
* Hybrid retrieve text chunks + image embeddings

This enables Q&A over diagrams and screenshots, not just text.

---

## 13. Summary of Key Improvements Over Original Plan

* Page-level scan detection (skip unnecessary OCR)
* Page rasterization OCR (more robust than embedded images)
* OCR preprocessing + explicit config
* Structured, page-level chunk storage
* Caching + bounded OCR execution
* Clear path to future image-aware RAG

---

**Result:** Faster indexing, better OCR quality, stronger citations, and a scalable foundation for multimodal RAG.
