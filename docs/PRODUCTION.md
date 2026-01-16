# Production Setup & Deployment

This guide covers the initial GCP environment setup and the production deployment workflow for the **Internal Knowledge Assistant**.

## GCP Initial Project Setup (One-Time)

If you are setting up this project in a new Google Cloud Project, follow these steps:

### 1. Enable Required APIs
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com \
  drive.googleapis.com
```

### 2. Create Artifact Registry
```bash
gcloud artifacts repositories create knowledge-assistant \
  --repository-format=docker \
  --location=us-west1 \
  --description="Docker repository for Internal Knowledge Assistant"
```

### 3. Configure Secret Manager (Consolidated Secrets)

All configuration and secrets are stored in a **single consolidated JSON secret** called `app-secrets`.

**Structure of `app-secrets`:**
```json
{
  "FIREBASE_ADMIN_CREDENTIALS": { ...your firebase service account JSON... },
  "GOOGLE_OAUTH_CLIENT": { ...your Google OAuth client JSON... },
  "MILVUS_URI": "...",
  "MILVUS_TOKEN": "...",
  "OPIK_API_KEY": "...",
  ... (all other environment variables)
}
```

**Using the Helper Script:**
We recommend using `scripts/create-consolidated-secret.sh` to package your local `.env` and credential files into this single GCP secret.

### 4. Setup IAM Permissions
Create a dedicated service account:
```bash
gcloud iam service-accounts create knowledge-assistant-runner

# Grant access to the secret
gcloud secrets add-iam-policy-binding app-secrets \
  --member="serviceAccount:knowledge-assistant-runner@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Grant access to Firestore
gcloud projects add-iam-policy-binding [PROJECT_ID] \
  --member="serviceAccount:knowledge-assistant-runner@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

---

## Production Deployment (GCP Cloud Run)

### 1. Automated CI/CD
A push to the `master` branch triggers **Google Cloud Build**, which:
1. Builds the Docker image.
2. Pushes it to Artifact Registry.
3. Deploys it to Cloud Run.

### 2. Deployment Command (Manual)
To trigger a manual deploy:
```bash
gcloud builds submit --config cloudbuild.yaml . --substitutions SHORT_SHA=$(git rev-parse --short HEAD)
```

### 3. Resource Requirements
OCR and RAG operations can be memory-intensive. We recommend at least **1Gi of memory** for the Cloud Run service:
```bash
gcloud run services update internal-knowledge-assistant \
  --region us-west1 \
  --memory 1Gi
```

### 4. Custom Domain & Firebase
1. Map your custom domain (e.g., `knowledge-assistant.example.com`) to the Cloud Run service.
2. Update **Firebase Console** > Auth > Settings > Authorized Domains to include your production domain.
3. Update **Google Cloud Console** > APIs & Services > Credentials > OAuth 2.0 Client IDs to include the production redirect URI: `https://your-domain.com/api/config/drive-oauth-callback`.

## Monitoring (Opik)

To enable production tracing, ensure `OPIK_API_KEY` is present in your consolidated secrets. This allows you to monitor RAG performance and debug production queries in the Opik dashboard.
