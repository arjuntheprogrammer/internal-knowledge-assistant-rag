# Internal Knowledge Assistant

## About

This is a simple AI-powered internal knowledge assistant that can be used to answer questions about internal knowledge using Retrieval Augmented Generation (RAG).

## Architecture Components

1. UI: Chat interface
2. Backend: Flask
3. Frontend: HTML, CSS, JS
4. RAG: LlamaIndex
5. Database: MongoDB
6. Vector Store: Chroma
7. Chat Model: OpenAI
8. Knowledge Base: Google Drive folder
9. Google Drive Connector: Google Drive API
10. Analytics and Monitoring: LangSmith

## Workflow

1. User authentication and authorization: user signup (full name, email, password) and login (email, password).
2. Admin configures Google Drive folders and the OpenAI model in the Admin UI.
3. Frontend chat interface: user enters a question.
4. Backend receives the question, applies a basic safety term check, and builds a `QueryBundle`.
5. Router selects between casual chat or knowledge-base retrieval.
6. For retrieval, the backend loads local files and Google Drive docs (with download retries/backoff) and annotates metadata.
7. Documents are chunked (SentenceSplitter) and indexed into Chroma; BM25 nodes are prepared for hybrid retrieval.
8. Hybrid retrieval (BM25 + vector) runs with higher recall for list queries.
9. LLM reranking refines the top retrieved nodes.
10. LLM synthesizes an answer using list-aware prompts and a refine step.
11. Responses are formatted as Markdown with sources, and list queries fall back to a document catalog if needed.
12. Backend returns the response to the frontend, and the UI renders Markdown with safe links.
13. Feedback endpoint accepts thumbs up/down and logs to the backend.
14. Background scheduler re-indexes Google Drive content every 60 seconds.
15. LangSmith tracing captures query/retrieve/synthesize/LLM events when enabled.
16. Optional: run end-to-end API tests via `scripts/rag_api_tests.py`.

For a deeper RAG implementation overview, see [RAG.md](RAG.md).

## Not Implemented Yet

1. Platform & Ops
   1. API gateway rate limiting.
   2. Feedback storage/analytics (feedback is logged only).
   3. Advanced evaluation/metrics (accuracy, drift, hallucination scoring).
2. Retrieval & Access
   1. Per-user ACL filtering in retrieval/indexing.
   2. Change detection for Drive updates (currently re-indexes on schedule).
3. LLM & Safety
   1. Context history, compression, and caching.
   2. Additional LLM optimizations (context window management, caching, usage dashboards/alerting).
   3. Full safety pipeline (policy checks, PII detection, prompt injection prevention, moderation, redaction).

## Knowledge Base Connector

> Note: Admin only (username: admin@gmail.com, password: admin@gmail.com).

### Configure Google Drive Connector (UI)

1. Add a new Google Drive folder.
2. Provide access to the Google Drive folder.
3. Automatic: poll the Google Drive folder for new documents and update the vector store.
4. Preview the discovered documents in the Admin UI.

### Configure LLM (OpenAI) in UI

1. Provide the OpenAI API key in `.env`.
2. Choose the OpenAI model name in the Admin UI (default: `gpt-4o-mini`).

## Notes

- User authentication: JWT token.
- User document access: retrieval from Google Drive is implemented.
- Feedback and rating capture: API endpoint logs to backend stdout.
- Analytics and monitoring: LangSmith tracing is supported.
- Background: the background process updates the vector store every 60 seconds.

## Installation and Usage

### Prerequisites

- Docker and Docker Compose
- Python 3.9+ (for local development)
- MongoDB (if running locally without Docker)

### 1. Clone the repository

```bash
git clone <repository_url>
cd internal-knowledge-assistant
```

### 2. Configuration

Create a `.env` file in the root directory and add the following variables:

```bash
SECRET_KEY=your_secret_key
PORT=5001
FLASK_APP=app.py
FLASK_ENV=development
FLASK_DEBUG=1
MONGO_URI=mongodb://mongo:27017/internal_knowledge_db # use localhost when running without Docker
OPENAI_API_KEY=your_openai_api_key
CHROMA_HOST=chroma # use localhost when running without Docker
CHROMA_PORT=8000
CHROMA_COLLECTION=internal-knowledge-assistant
```

### 3. Run with Docker (Recommended)

```bash
docker compose up --build
```

The backend API will be available at `http://localhost:${PORT}`.

### 4. Run Locally (with Conda) - Recommended for Local Dev

1. Create and activate the Conda environment:

   ```bash
   conda env create -f environment.yml
   conda activate internal-knowledge-assistant
   ```

2. Start MongoDB (ensure it's running on port 27017).
3. Run the application:

   ```bash
   python app.py
   ```

### 5. Chroma Vector Store (Docker)

Chroma runs as a local service. The `docker-compose.yml` includes a `chroma` container that the backend connects to.

To use Chroma with Docker:

1. Ensure the `chroma` service is running via `docker compose up --build`.
2. Set the following in your `.env` file:

   ```bash
   CHROMA_HOST=chroma
   CHROMA_PORT=8000
   CHROMA_COLLECTION=internal-knowledge-assistant
   ```

To use Chroma locally (outside Docker), run a server and point the backend at it:

```bash
docker run -p 8000:8000 chromadb/chroma:latest
```

```bash
CHROMA_HOST=localhost
CHROMA_PORT=8000
CHROMA_COLLECTION=internal-knowledge-assistant
```

### 6. Google Drive Configuration

To enable the Google Drive connector:

1. Enable the Google Drive API in your Google Cloud Console.
2. Create a Service Account or OAuth credentials.
3. Download the JSON key file.
4. Rename `backend/credentials/credentials.template.json` to `backend/credentials/credentials.json` and paste your content there (or just save your downloaded file as `credentials.json` in that folder).
   Note: `credentials.json` is gitignored to secure your secrets.
5. Run the application; it will automatically detect the credentials and attempt to load documents from folders configured in the Admin Dashboard.

### 7. Analytics and Monitoring (LangSmith)

To enable tracing with LangSmith:

1. Sign up at [smith.langchain.com](https://smith.langchain.com).
2. Get your API key.
3. Add the following to your `.env` file:

   ```bash
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
   LANGCHAIN_API_KEY=your_langchain_api_key
   LANGCHAIN_PROJECT=internal-knowledge-assistant
   ```

   The application will automatically log traces to your project.
