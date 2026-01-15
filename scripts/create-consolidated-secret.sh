#!/bin/bash
# Script to create the consolidated app-secrets in Secret Manager
# Run this once to set up the secret

set -e

PROJECT_ID="internal-knowledge-assistant"
SECRET_NAME="app-secrets"

# Check for required environment variable
if [ -z "$GOOGLE_PICKER_API_KEY" ]; then
  echo "❌ Error: GOOGLE_PICKER_API_KEY environment variable is not set."
  echo "   Please set it before running this script:"
  echo "   export GOOGLE_PICKER_API_KEY=your_api_key_here"
  exit 1
fi

echo "Fetching existing secrets..."

# Fetch existing secrets
FIREBASE_CREDS=$(gcloud secrets versions access latest --secret=firebase-admin-creds --project=$PROJECT_ID)
GOOGLE_OAUTH=$(gcloud secrets versions access latest --secret=google-oauth-creds --project=$PROJECT_ID)
MILVUS_TOKEN=$(gcloud secrets versions access latest --secret=milvus-token --project=$PROJECT_ID)
OPIK_KEY=$(gcloud secrets versions access latest --secret=opik-api-key --project=$PROJECT_ID)

echo "Building consolidated secret..."

# Create the consolidated JSON
# We use jq to properly escape and embed JSON
CONSOLIDATED=$(cat <<EOF
{
  "FIREBASE_ADMIN_CREDENTIALS": $FIREBASE_CREDS,
  "GOOGLE_OAUTH_CLIENT": $GOOGLE_OAUTH,
  "MILVUS_URI": "https://in03-955a82bbe424026.api.gcp-us-west1.zillizcloud.com",
  "MILVUS_TOKEN": "$MILVUS_TOKEN",
  "MILVUS_COLLECTION": "internal_knowledge_assistant",
  "OPIK_API_KEY": "$OPIK_KEY",
  "OPIK_PROJECT_NAME": "internal-knowledge-assistant",
  "OPIK_ENABLED": "true",
  "GOOGLE_PICKER_API_KEY": "$GOOGLE_PICKER_API_KEY",
  "SECRET_KEY": "$(openssl rand -hex 32)",
  "FIRESTORE_DB": "internal-knowledge-assistant"
}
EOF
)

echo "Creating/updating secret '$SECRET_NAME'..."

# Check if secret exists
if gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID &>/dev/null; then
  # Add new version
  echo "$CONSOLIDATED" | gcloud secrets versions add $SECRET_NAME --data-file=- --project=$PROJECT_ID
  echo "Added new version to existing secret."
else
  # Create new secret
  echo "$CONSOLIDATED" | gcloud secrets create $SECRET_NAME --data-file=- --project=$PROJECT_ID
  echo "Created new secret."
fi

echo ""
echo "✅ Consolidated secret '$SECRET_NAME' created successfully!"
echo ""
echo "To verify, run:"
echo "  gcloud secrets versions access latest --secret=$SECRET_NAME --project=$PROJECT_ID | jq ."

