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
7. **Chat Model**: OpenAI (GPT-4o-mini).
8. **Knowledge Base**: Google Drive folder integration.
9. **Analytics**: LangSmith tracing for observability.

## Workflow

1. User signs in with Google via Firebase Auth.
2. User configures OpenAI API key and Google Drive folder ID.
3. User asks a question in the chat interface.
4. Backend retrieves relevant documents from **Zilliz Cloud** using hybrid search.
5. Large Language Model (OpenAI) synthesizes the answer from the retrieved context.
6. Responsive answers are returned with clickable citations and sources.

## Key Features

- **Google Drive Integration**: Seamlessly connect your Drive folders and index documents (Docs, PDFs, etc.) for instant retrieval.
- **Scalable Multi-Tenancy**: Built using a shared Zilliz Cloud (Milvus) collection with metadata isolation, ensuring high performance regardless of the number of users.
- **Hybrid Retrieval Engine**: Combines **Vector Search** (for semantic meaning) and **BM25 Search** (for keyword exact matches) to provide the most accurate context.
- **Advanced Observability**: Full integration with **LangSmith** enables detailed tracing of the AI pipeline, including cost tracking, latency monitoring, and per-user analytics.
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

## Installation & Local Development

### Prerequisites

- Python 3.9+
- A Zilliz Cloud account (for Vector Storage)
- A Firebase project (for Auth & Database)
- An OpenAI API key

### 1. Configuration

Create a `.env` file in the root directory:

```bash
# Flask
SECRET_KEY=your_secret_key
PORT=5001
FLASK_APP=app.py

# Vector Store (Zilliz Cloud / Milvus)
MILVUS_URI=https://your-endpoint.zillizcloud.com
MILVUS_TOKEN=your_zilliz_token
MILVUS_COLLECTION=internal_knowledge_assistant

# Firebase Admin
FIREBASE_ADMIN_CREDENTIALS_PATH=backend/credentials/firebase-admin.json
FIRESTORE_DB=(default)

# Google Drive OAuth
GOOGLE_OAUTH_CLIENT_PATH=backend/credentials/google-credentials.json
```

### 2. Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python app.py
```

The app will be available at `http://localhost:5001`.

---

## Production Deployment (GCP Cloud Run)

### 1. Build & Push Container

Build the container using the root `Dockerfile`:

```bash
gcloud builds submit --tag gcr.io/[PROJECT_ID]/knowledge-assistant
```

### 2. Deploy to Cloud Run

Deploy the service to Cloud Run:

```bash
gcloud run deploy knowledge-assistant \
  --image gcr.io/[PROJECT_ID]/knowledge-assistant \
  --platform managed \
  --region [REGION] \
  --allow-unauthenticated
```

### 3. Custom Domain Mapping

To use your domain `knowledge-assistant.arjuntheprogrammer.com`:

1. In the Google Cloud Console, navigate to **Cloud Run** > **Manage Custom Domains**.
2. Click **Add Mapping** and select the service.
3. Enter your domain and follow the instructions to update your DNS records (CNAME).
4. SSL certificates will be automatically provisioned by GCP.

### 4. Firebase Configuration for Production

1. Update the **Authorized Domains** in Firebase Auth to include `knowledge-assistant.arjuntheprogrammer.com`.
2. Update the **Redirect URI** in Google Cloud Console (OAuth Client) to:
   `https://knowledge-assistant.arjuntheprogrammer.com/api/config/drive-oauth-callback`

---

## Analytics and Monitoring (LangSmith)

To enable tracing, add these to your `.env`:

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=your_langchain_api_key
LANGCHAIN_PROJECT=internal-knowledge-assistant
```

The application will automatically log traces to your LangSmith project.
