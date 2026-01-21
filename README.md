# Internal Knowledge Assistant

## About

This is a premium AI-powered internal knowledge assistant designed to help you answer questions based on your Google Drive files using Retrieval Augmented Generation (RAG).

## Architecture Components

1. **UI**: Modern chat interface with glassmorphism and real-time feedback.
2. **Backend**: Flask (Python) with Gunicorn (Production).
3. **Frontend**: HTML5, Vanilla CSS, and JavaScript.
4. **RAG**: LlamaIndex (Hybrid search: Vector + BM25).
5. **Database**: Google Cloud Firestore (Managed).
6. **Vector Store**: Zilliz Cloud (Managed Milvus).
7. **Chat Model**: OpenAI (GPT-4.1 mini).
8. **Knowledge Base**: Google Drive file selection.
9. **Analytics**: Opik tracing for observability.
10. **OCR Engine**: Tesseract OCR for high-fidelity scanning of images and non-searchable PDFs.

## Workflow

```mermaid
flowchart TD
    subgraph Auth["🔐 Authentication"]
        A[User] --> B[Google Sign-In]
        B --> C[Firebase Auth]
    end

    subgraph Setup["⚙️ Configuration"]
        C --> D[Enter OpenAI API Key]
        D --> E[Select Google Drive Files]
        E --> F[Build Database]
    end

    subgraph Chat["💬 Chat"]
        F --> G[Ask Question]
        G --> H{Router}
        H -->|Casual| I[Direct LLM Response]
        H -->|Knowledge| J[Hybrid Retrieval]
        J --> K[Rerank & Synthesize]
        K --> L[Answer + Citations]
    end

    L --> G
```

1. User signs in with Google via Firebase Auth.
2. User completes setup: validate OpenAI API key, authorize Drive, and select files.
3. User builds the database (documents are indexed with progress feedback).
4. Chat is enabled only after configuration is complete.
5. User asks a question in the chat interface.
6. Backend retrieves relevant documents from **Zilliz Cloud** using hybrid search.
7. Large Language Model (OpenAI) synthesizes the answer from the retrieved context.
8. Responsive answers are returned with clickable citations and sources.

## Key Features

- **Google Drive Integration**: Seamlessly connect your Drive files and build the searchable database for instant retrieval.
- **Scalable Multi-Tenancy**: Built using a shared Zilliz Cloud (Milvus) collection with metadata isolation, ensuring high performance regardless of the number of users.
- **Hybrid Retrieval Engine**: Combines **Vector Search** (for semantic meaning) and **BM25 Search** (for keyword exact matches) to provide the most accurate context.
- **Intelligent OCR & Document Parsing**: Advanced multi-stage processing for PDFs and images. The system extracts digital text where available and automatically falls back to **Tesseract OCR** for scanned documents, ensuring comprehensive knowledge coverage with built-in caching and multi-threaded performance.
- **Advanced Observability with Opik**: Deeply integrated **Opik** tracing for debugging, evaluating, and monitoring LLM applications. Track every step of the RAG pipeline with production-ready dashboards and evaluation metrics.
- **Automated Synchronization**: Background scheduler periodically polls your Google Drive to keep the knowledge base up-to-date.

## Not Implemented Yet

1. **Platform & Ops**
   - API gateway rate limiting.
   - Feedback storage/analytics (feedback is logged only).
   - Advanced evaluation/metrics (accuracy, drift, hallucination scoring).
2. **Retrieval & Access**
   - Per-user ACL filtering in retrieval/indexing.
   - Change detection for Drive updates (currently re-indexes on schedule).
3. **LLM & Safety**
   - Context history, compression, and caching.
   - Additional LLM optimizations (context window management, caching, usage dashboards/alerting).
   - Full safety pipeline (policy checks, PII detection, prompt injection prevention, moderation, redaction).

---

---

## 🚀 Getting Started

### Local Development
Follow the **[Local Setup Guide](docs/LOCAL.md)** to get the application running on your machine.

### Production Deployment
For information on setting up the GCP environment and deploying to Cloud Run, see the **[Production & Deployment Guide](docs/PRODUCTION.md)**.

### Technical Documentation
Learn more about the retrieval pipeline and optimizations in the **[RAG Documentation](docs/RAG.md)**.

---

## Analytics and Monitoring (Opik & PostHog)

### Opik

Debug, evaluate, and monitor your LLM applications, RAG systems, and agentic workflows with tracing, eval metrics, and production-ready dashboards. Tracing is enabled by default in production.

> **Migration Note**: LangSmith was replaced with Opik for observability.

### PostHog (Coming Soon)
Token usage (Input, Thinking, Output) and user behavior analytics are integrated via PostHog.
To enable, add your API key to the Cloud Run environment variables:
`POSTHOG_API_KEY=your_key_here`

---

🎥 **YouTube Walkthrough**: https://youtu.be/mf2SiJLMSDY

[![Internal Knowledge Assistant Walkthrough](assets/img.jpeg)](https://youtu.be/mf2SiJLMSDY)

🔗 **Live Demo Link**: https://knowledge-assistant.arjuntheprogrammer.com
