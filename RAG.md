# RAG in internal-knowledge-assistant

This document explains how Retrieval-Augmented Generation (RAG) is implemented in
this repo and the optimizations added to improve answer quality, coverage, and
reliability.

## High-level flow

1. The API receives a chat message at `POST /api/chat/message`.
2. The message is wrapped in a `QueryBundle` (see `backend/routes/chat.py`).
3. `RAGService.query(...)` routes the request:
   - Casual chit-chat goes to a lightweight LLM-only engine.
   - Knowledge queries go to the retrieval engine.
4. The retrieval engine pulls documents from Google Drive + local files, chunks
   them, runs hybrid retrieval (vector + BM25), then reranks and synthesizes a
   grounded answer.

## Core components

- `backend/services/rag/rag.py`
  - `RAGService` orchestrates indexing, retrieval, routing, and fallback logic.
- `backend/services/rag/engines.py`
  - `CasualQueryEngine`: small-talk responses without retrieval.
  - `LazyRAGQueryEngine`: builds the retrieval query engine on demand.
- `backend/services/rag/retrievers.py`
  - `HybridRetriever`: merges vector and BM25 results.
- `backend/services/rag/catalog.py`
  - Document catalog and list fallback helpers.
- `backend/services/rag/rag_context.py`
  - LLM + embedding configuration.
- `backend/services/rag/rag_google_drive.py`
  - Google Drive loader + auth helpers.

## Data sources

- Local files in `backend/data` (loaded via `SimpleDirectoryReader`).
- Google Drive files (loaded via `rag_google_drive.load_google_drive_documents()`).

Each document is annotated with metadata (e.g., file name) and indexed.

## Retrieval pipeline

1. **Chunking**
   - `SentenceSplitter(chunk_size=512, chunk_overlap=60)` splits documents into
     manageable chunks.
2. **Vector store**
   - Zilliz Cloud (Milvus) is used as the vector backend (`backend/services/rag/rag_milvus.py`).
3. **Hybrid retrieval**
   - Vector retriever + BM25 retriever are merged in `HybridRetriever`.
4. **Reranking**
   - `LLMRerank` refines top results before answer synthesis.
5. **Answer synthesis**
   - Uses task-specific prompts for list vs non-list queries and a refine step.

## Query routing (casual vs retrieval)

`RouterQueryEngine` + `LLMSingleSelector` choose between:

- `casual_chat`: greeting, thanks, small talk (no retrieval).
- `knowledge_base_retrieval`: anything that needs documents or facts.

This keeps small talk fast and cheap while reserving retrieval for grounded
questions.

## Optimizations added to improve output

1. **Hybrid retrieval (BM25 + vector)**
   - Captures both exact keyword matches and semantic similarity.
   - Particularly useful for list queries and domain-specific names.
2. **Reranking with LLM**
   - Improves relevance of retrieved chunks before synthesis.
3. **List-specific prompts**
   - Dedicated prompt template for list queries with explicit instructions to
     enumerate all unique items and avoid early truncation.
4. **Adaptive retrieval depth**
   - `top_k` and `max_results` are higher for list queries (more recall).
5. **Document catalog fallback**
   - When the RAG answer is empty or incomplete for list requests, a catalog
     built from document metadata is returned.
6. **Router multi-selection safety**
   - Router selection metadata is handled safely even if multiple tools are
     returned by the selector.

## LLM and embeddings

- OpenAI:
  - LLM default: `gpt-4o-mini`
  - Embeddings: `text-embedding-3-small`

Configuration is in `backend/services/rag/rag_context.py` and is supplied per
user from Firestore (OpenAI API key + Drive folder ID).

## Telemetry (LangSmith)

Tracing is enabled when `LANGCHAIN_TRACING_V2=true` and a LangSmith API key is
present. The callback handler lives in `backend/services/langsmith_tracing.py`
and is attached in `rag_context.py`.

## Notes for Docker builds

BM25 uses `pystemmer`, which requires build tools inside the container. The
backend Docker image installs `build-essential` before installing Python deps
(`backend/Dockerfile`).

## Quick sanity checks

- Start services: `docker compose up --build -d`
- Run API tests: `conda run -n internal-knowledge-assistant python scripts/tests/rag_api_tests.py`

## File map (entry points)

- `backend/routes/chat.py`: main chat API.
- `backend/services/rag/rag.py`: RAG orchestration and routing.
- `backend/services/rag/rag_google_drive.py`: Google Drive ingestion.
- `backend/services/rag/rag_context.py`: LLM + embed config.
