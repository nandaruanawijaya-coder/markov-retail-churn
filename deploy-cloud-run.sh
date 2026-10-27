#!/bin/bash
set -e

# Configuration
PROJECT_ID="${PROJECT_ID:-ledger-fcc1e}"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_EMAIL:-data-team-ml-model@ledger-fcc1e.iam.gserviceaccount.com}"
SERVICE_NAME="${SERVICE_NAME:-markov-churn-pipeline}"
REGION="${REGION:-asia-southeast1}"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "=========================================="
echo "Cloud Run Deployment Script"
echo "=========================================="
echo "Project ID: $PROJECT_ID"
echo "Service Account: $SERVICE_ACCOUNT_EMAIL"
echo "Service Name: $SERVICE_NAME"
echo "Region: $REGION"
echo ""

# Step 1: Verify service account exists
echo "1️⃣  Verifying service account..."
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project=$PROJECT_ID &>/dev/null; then
  echo "   ✅ Service account exists: $SERVICE_ACCOUNT_EMAIL"
else
  echo "   ❌ Service account not found: $SERVICE_ACCOUNT_EMAIL"
  exit 1
fi

# Step 2: Build and push image
echo ""
echo "2️⃣  Building Docker image..."
gcloud builds submit --tag=$IMAGE --project=$PROJECT_ID

# Step 3: Deploy to Cloud Run
echo ""
echo "3️⃣  Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image=$IMAGE \
  --platform=managed \
  --region=$REGION \
  --timeout=3600 \
  --memory=2Gi \
  --cpu=2 \
  --service-account="$SERVICE_ACCOUNT_EMAIL" \
  --project=$PROJECT_ID

# Step 4: Check if scheduler job exists and create/update
echo ""
echo "4️⃣  Setting up Cloud Scheduler..."
JOB_EXISTS=$(gcloud scheduler jobs describe markov-pipeline-monthly --location=$REGION --project=$PROJECT_ID 2>/dev/null || echo "")

if [ -z "$JOB_EXISTS" ]; then
  echo "   📝 Creating Cloud Scheduler job (monthly, 1st at 2 AM UTC)..."
  gcloud scheduler jobs create http markov-pipeline-monthly \
    --location=$REGION \
    --schedule="0 2 1 * *" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${SERVICE_NAME}:run" \
    --oidc-service-account-email="$SERVICE_ACCOUNT_EMAIL" \
    --oidc-token-audience="https://${REGION}-run.googleapis.com/${SERVICE_NAME}" \
    --http-method=POST \
    --project=$PROJECT_ID
else
  echo "   ✅ Scheduler job already exists"
fi

echo ""
echo "=========================================="
echo "✅ Deployment complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. View logs: gcloud run jobs log $SERVICE_NAME --limit=100 --project=$PROJECT_ID"
echo "2. Trigger manually: gcloud scheduler jobs run markov-pipeline-monthly --location=$REGION"
echo "3. View schedule: gcloud scheduler jobs describe markov-pipeline-monthly --location=$REGION"
