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

## GCP Initial Project Setup (One-Time)

If you are setting up this project in a new Google Cloud Project, follow these steps to initialize the environment:

### 1. Enable Required APIs
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com
```

### 2. Create Artifact Registry
```bash
gcloud artifacts repositories create knowledge-assistant \
  --repository-format=docker \
  --location=us-west1 \
  --description="Docker repository for Internal Knowledge Assistant"
```

### 3. Configure Secret Manager
Create and upload your credentials safely:
```bash
# Create the secrets
gcloud secrets create firebase-admin-creds --replication-policy="automatic"
gcloud secrets create google-oauth-creds --replication-policy="automatic"

# Add the data versions
gcloud secrets versions add firebase-admin-creds --data-file=backend/credentials/firebase-admin.json
gcloud secrets versions add google-oauth-creds --data-file=backend/credentials/google-credentials.json
```

### 4. Setup IAM Permissions
Create a dedicated service account and grant it the minimum required permissions:
```bash
# Create service account
gcloud iam service-accounts create knowledge-assistant-runner

# Grant access to Secret Manager
gcloud secrets add-iam-policy-binding firebase-admin-creds \
  --member="serviceAccount:knowledge-assistant-runner@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding google-oauth-creds \
  --member="serviceAccount:knowledge-assistant-runner@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Grant access to Firestore
gcloud projects add-iam-policy-binding [PROJECT_ID] \
  --member="serviceAccount:knowledge-assistant-runner@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

---

## Production Deployment (GCP Cloud Run)

This project is configured for automated deployment using **Google Cloud Build** and **Cloud Run**.

### 1. Automated CI/CD
The repository includes a `cloudbuild.yaml` file that:
- Builds the Docker image on every push to the `master` branch.
- Pushes the image to **Artifact Registry**.
- Deploys the container to **Cloud Run** in the `us-west1` region.

### 2. Secret Management
Sensitive credentials are not stored in the container. Instead, they are managed via **GCP Secret Manager** and mounted as volumes at runtime:
- `firebase-admin-creds`: Mounted at `/secrets/firebase/creds.json`
- `google-oauth-creds`: Mounted at `/secrets/google/creds.json`

### 3. Deployment Command (Manual)
To trigger a manual build and deployment:
```bash
gcloud builds submit --config cloudbuild.yaml . --substitutions SHORT_SHA=$(git rev-parse --short HEAD)
```

### 4. Custom Domain & Firebase
The application is live at: [https://internal-knowledge-assistant-cp35zlfwgq-uw.a.run.app/](https://internal-knowledge-assistant-cp35zlfwgq-uw.a.run.app/)

**Troubleshooting (403 Forbidden)**:
If you receive a 403 error when accessing the URL, ensure the service is public by running:
```bash
gcloud run services add-iam-policy-binding internal-knowledge-assistant \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --region=us-west1
```

**Custom Domain**:
Update your DNS records to point `knowledge-assistant.arjuntheprogrammer.com` to the Cloud Run service.

**Important**: Ensure the production URL is added to:
1. **Firebase Console**: Auth > Settings > Authorized Domains.
2. **Google Cloud Console**: APIs & Services > Credentials > OAuth 2.0 Client IDs (Update Redirect URIs to include `/api/config/drive-oauth-callback`).

## Analytics and Monitoring (LangSmith & PostHog)

### LangSmith
Tracing is enabled by default in production. Monitor your AI pipeline at [smith.langchain.com](https://smith.langchain.com).

### PostHog (Coming Soon)
Token usage (Input, Thinking, Output) and user behavior analytics are integrated via PostHog.
To enable, add your API key to the Cloud Run environment variables:
`POSTHOG_API_KEY=your_key_here`
