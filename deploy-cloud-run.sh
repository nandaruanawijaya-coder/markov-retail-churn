#!/bin/bash
set -e

# Configuration
PROJECT_ID="${PROJECT_ID:-ledger-fcc1e}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-markov-pipeline-sa}"
SERVICE_NAME="${SERVICE_NAME:-markov-churn-pipeline}"
REGION="${REGION:-us-central1}"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "=========================================="
echo "Cloud Run Deployment Script"
echo "=========================================="
echo "Project ID: $PROJECT_ID"
echo "Service Account: $SERVICE_ACCOUNT"
echo "Service Name: $SERVICE_NAME"
echo "Region: $REGION"
echo ""

# Step 1: Check if service account exists
echo "1️⃣  Checking service account..."
if gcloud iam service-accounts describe "${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" --project=$PROJECT_ID &>/dev/null; then
  echo "   ✅ Service account exists"
else
  echo "   📝 Creating service account..."
  gcloud iam service-accounts create $SERVICE_ACCOUNT \
    --display-name="Markov Churn Pipeline Service Account" \
    --project=$PROJECT_ID

  echo "   📝 Granting BigQuery admin role..."
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/bigquery.admin" \
    --quiet
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
  --service-account="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
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
    --oidc-service-account-email="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
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
