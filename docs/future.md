# Future Roadmap and Improvements

This document outlines potential improvements and optimizations for the Internal Knowledge Assistant, ranging from core RAG pipeline enhancements to architectural and UX upgrades.

## 1. RAG Pipeline & Retrieval Optimizations

- **Persistent Hybrid Search**: Currently, BM25 indices are stored in-memory. Persisting these indices (e.g., using a local file-based index or an integrated vector+text store) ensures consistent retrieval performance after server restarts without requiring a full re-index.
- **Reciprocal Rank Fusion (RRF)**: Replace simple linear weighting with RRF to more robustly combine results from vector and keyword searches without manual weight tuning.
- **Recursive Folder Indexing**: Support recursive scanning of Google Drive subfolders to allow users more flexibility in organizing their knowledge base.
- **Local Reranker**: Integrate a dedicated cross-encoder (like `BGE-Reranker`) running locally to improve precision and reduce the latency/cost associated with LLM-based reranking.
- **Dynamic Chunking Strategy**: Move beyond fixed chunk sizes to semantic or structure-aware chunking (e.g., markdown-aware) for better contextual retrieval.

## 2. Backend Architecture

- **Asynchronous Task Queue**: Transition indexing jobs to a dedicated task queue (e.g., Celery or Google Cloud Tasks) to improve reliability and horizontal scalability.
- **Streaming Responses**: Implement Server-Sent Events (SSE) to stream bot responses to the UI in real-time, enhancing the user experience.
- **Enhanced Observability**: Add granular instrumentation for OCR latency per page and individual retrieval steps within the RAG pipeline.
- **Structured Logging**: Move to JSON-formatted logging for easier production debugging and log aggregation.

## 3. Frontend & User Experience

- **Chat History Persistence**: Store chat history in `localStorage` or a backend database to ensure context is maintained across page refreshes.
- **Document Preview**: Add a "Quick Preview" modal in the chat UI to display retrieved text snippets or document previews directly.
- **Granular Indexing Feedback**: Update the indexing loader to show the specific file currently being processed (e.g., "Step: Performing OCR on Policy_2024.pdf...").

## 4. Code Quality & Maintainability

- **Unified Document Processor**: Centralize PDF rendering and text extraction logic into a single service to reduce duplication and simplify adding new file type support.
- **Expanded Test Suite**: Create comprehensive integration tests using mocked Drive and Milvus services to allow for safer logic refactoring.
- **Stricter Type Hinting**: Increase the use of Python type hints across all backend services to improve code clarity and catch potential bugs early.
