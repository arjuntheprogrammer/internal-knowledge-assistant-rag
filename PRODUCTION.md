# Production Setup & Deployment

This guide covers the initial GCP environment setup and the production deployment workflow for the **Internal Knowledge Assistant**.

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

All secrets are stored in a **single consolidated JSON secret** called `app-secrets`. This simplifies management and deployment.

**Option A: Use the helper script (recommended):**
```bash
# First, create individual secrets temporarily (if migrating from old setup)
# Then run the consolidation script:
chmod +x scripts/create-consolidated-secret.sh
./scripts/create-consolidated-secret.sh
```

**Option B: Create manually:**
Create a JSON file with all your secrets and upload it to GCP Secret Manager as `app-secrets`.

### 4. Setup IAM Permissions
Create a dedicated service account and grant it the minimum required permissions:
```bash
# Create service account
gcloud iam service-accounts create knowledge-assistant-runner

# Grant access to the consolidated secret
gcloud secrets add-iam-policy-binding app-secrets \
  --member="serviceAccount:knowledge-assistant-runner@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Grant access to Firestore
gcloud projects add-iam-policy-binding [PROJECT_ID] \
  --member="serviceAccount:knowledge-assistant-runner@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/datastore.user" \
  --condition=None
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
Sensitive credentials are not stored in the container. Instead, they are managed via **GCP Secret Manager** using a **single consolidated secret** (`app-secrets`), which is mounted at `/secrets/app/secrets.json`.

### 3. Deployment Command (Manual)
To trigger a manual build and deployment:
```bash
gcloud builds submit --config cloudbuild.yaml . --substitutions SHORT_SHA=$(git rev-parse --short HEAD)
```

### 4. Custom Domain & Firebase
Update your DNS records to point your custom domain to the Cloud Run service.

**Important**: Ensure the production URL is added to:
1. **Firebase Console**: Auth > Settings > Authorized Domains.
2. **Google Cloud Console**: APIs & Services > Credentials > OAuth 2.0 Client IDs.
