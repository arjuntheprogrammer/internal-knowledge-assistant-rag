# Internal Knowledge Assistant

## About

This is a simple AI-powered internal knowledge assistant that can be used to answer questions about internal knowledge using Retrieval Augmented Generation (RAG).

## Architecture Components

1. UI: Chat interface
2. Backend: Flask
3. Frontend: HTML, CSS, JS
4. RAG: LlamaIndex
5. Database: Firestore
6. Vector Store: Chroma
7. Chat Model: OpenAI
8. Knowledge Base: Google Drive folder
9. Google Drive Connector: Google Drive API
10. Analytics and Monitoring: LangSmith

## Workflow

1. User signs in with Google via Firebase Auth.
2. User is redirected to Configure to set their OpenAI API key, authorize Drive access, and add a single Drive folder ID.
3. Frontend chat interface: user enters a question.
4. Backend verifies the Firebase ID token and loads user config from Firestore.
5. Router selects between casual chat or knowledge-base retrieval.
6. For retrieval, the backend loads local files and the user's Google Drive folder (with retries/backoff) and annotates metadata.
7. Documents are chunked (SentenceSplitter) and indexed into Chroma; BM25 nodes are prepared for hybrid retrieval.
8. Hybrid retrieval (BM25 + vector) runs with higher recall for list queries.
9. LLM reranking refines the top retrieved nodes.
10. LLM synthesizes an answer using list-aware prompts and a refine step.
11. Responses are formatted as Markdown with sources, and list queries fall back to a document catalog if needed.
12. Backend returns the response to the frontend, and the UI renders Markdown with safe links.
13. Feedback endpoint accepts thumbs up/down and logs to the backend.
14. Background scheduler re-indexes configured Drive folders every 60 seconds.
15. LangSmith tracing captures query/retrieve/synthesize/LLM events when enabled.
16. Optional: run end-to-end API tests via `scripts/tests/rag_api_tests.py`.

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

### Configure Google Drive Connector (UI)

1. Authorize Google Drive access for the signed-in user.
2. Add a single Google Drive folder ID.
3. Test the Drive connection from the Configure page.
4. The backend polls the Drive folder for updates every 60 seconds.

### Configure LLM (OpenAI) in UI

1. Add your OpenAI API key in the Configure page.
2. Use the "Test OpenAI Key" button to validate the key.
3. Model is fixed to `gpt-4o-mini`.

## Notes

- User authentication: Firebase ID tokens verified server-side.
- User configuration: stored per-user in Firestore.
- OpenAI API keys are stored per user (not in `.env`).
- User document access: retrieval from the user's Google Drive folder is implemented.
- Feedback and rating capture: API endpoint logs to backend stdout.
- Analytics and monitoring: LangSmith tracing is supported.
- Background: the background process updates the vector store every 60 seconds.

## Installation and Usage

### Prerequisites

- Docker and Docker Compose
- Python 3.9+ (for local development)

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
FIREBASE_ADMIN_CREDENTIALS_PATH=backend/credentials/internal-knowledge-assistant-firebase-adminsdk-fbsvc-61b18bef66.json
FIRESTORE_DB=internal-knowledge-assistant
GOOGLE_OAUTH_CLIENT_PATH=backend/credentials/credentials.json
ALLOW_ENV_OPENAI_KEY_FOR_TESTS=false
CHROMA_HOST=chroma # use localhost when running without Docker
CHROMA_PORT=8000
CHROMA_COLLECTION=internal-knowledge-assistant
```

Frontend Firebase config lives in `frontend/static/js/firebase.js`.

### 3. Firebase + GCP Setup (Required)

#### 3.1 Firebase Auth + Firestore

1. Create or select your Firebase project.
2. Enable Google sign-in under Firebase Auth.
3. Create a Firestore database (Native mode). Use the database ID shown in the console.
4. Download the Firebase Admin SDK JSON for your Firebase project.
5. Place it in `backend/credentials/` (gitignored).
6. Point `FIREBASE_ADMIN_CREDENTIALS_PATH` to that file.
7. If you use a non-default Firestore database, set `FIRESTORE_DB` to its ID.
8. Copy your Firebase Web config into `frontend/static/js/firebase.js`.

#### 3.2 Google OAuth (Drive access)

1. In Google Cloud Console, enable the Google Drive API for your OAuth project.
2. Configure the OAuth consent screen:
   - Publishing status: Testing (add your Gmail to Test users).
   - Scopes: `openid`, `userinfo.email`, `userinfo.profile`, `drive.readonly`.
3. Create an OAuth Client ID (Web application):
   - Authorized redirect URI: `http://localhost:5001/api/config/drive-oauth-callback`
   - Add your production redirect URI if deployed.
4. Download the OAuth client JSON and save it as `backend/credentials/credentials.json`.
5. Set `GOOGLE_OAUTH_CLIENT_PATH=backend/credentials/credentials.json`.

Note: if you just enabled the Drive API, wait a few minutes for propagation before testing.

### 4. Run with Docker (Recommended)

```bash
docker compose up --build
```

The backend API will be available at `http://localhost:${PORT}`.

### 5. Run Locally (with Conda) - Recommended for Local Dev

1. Create and activate the Conda environment:

   ```bash
   conda env create -f environment.yml
   conda activate internal-knowledge-assistant
   ```

2. Run the application:

   ```bash
   python app.py
   ```

### 6. Chroma Vector Store (Docker)

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
