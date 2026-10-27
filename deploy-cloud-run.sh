#!/bin/bash
set -e

# Deploys one image as two Cloud Run Jobs, each triggered by Cloud Scheduler:
#   markov-matrices-monthly : rebuild + upload Markov matrices (1st of month, 02:00 UTC)
#   merchant-scoring-weekly : score merchants, append a snapshot (Monday 03:00 UTC = 10:00 WIB)

# Configuration
PROJECT_ID="${PROJECT_ID:-ledger-fcc1e}"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_EMAIL:-data-team-ml-model@${PROJECT_ID}.iam.gserviceaccount.com}"
REGION="${REGION:-asia-southeast1}"
REPO_NAME="${REPO_NAME:-qris-soundbox}"
IMAGE_NAME="${IMAGE_NAME:-markov-churn-pipeline}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

MONTHLY_JOB="markov-matrices-monthly"
WEEKLY_JOB="merchant-scoring-weekly"
MONTHLY_SCHEDULE="0 2 1 * *"
WEEKLY_SCHEDULE="0 3 * * 1"

echo "=========================================="
echo "Cloud Run Jobs Deployment Script"
echo "=========================================="
echo "Project ID: $PROJECT_ID"
echo "Service Account: $SERVICE_ACCOUNT_EMAIL"
echo "Region: $REGION"
echo "Image: $IMAGE"
echo ""

# Step 1: Verify service account exists
echo "1️⃣  Verifying service account..."
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project=$PROJECT_ID &>/dev/null; then
  echo "   ✅ Service account exists: $SERVICE_ACCOUNT_EMAIL"
else
  echo "   ❌ Service account not found: $SERVICE_ACCOUNT_EMAIL"
  exit 1
fi

# Step 2: Ensure Artifact Registry repo, then build and push image
echo ""
echo "2️⃣  Building Docker image..."
if ! gcloud artifacts repositories describe "$REPO_NAME" --location=$REGION --project=$PROJECT_ID &>/dev/null; then
  echo "   📝 Creating Artifact Registry repo: $REPO_NAME"
  gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location=$REGION \
    --project=$PROJECT_ID
fi
gcloud builds submit --tag=$IMAGE --project=$PROJECT_ID

# deploy_job NAME MODE CPU MEMORY TIMEOUT
deploy_job() {
  local name=$1 mode=$2 cpu=$3 memory=$4 timeout=$5
  local action=create
  if gcloud run jobs describe "$name" --region=$REGION --project=$PROJECT_ID &>/dev/null; then
    action=update
  fi
  echo "   📝 ${action}: $name (--mode $mode, ${cpu} CPU, ${memory}, timeout ${timeout})"
  gcloud run jobs $action "$name" \
    --image=$IMAGE \
    --args="--mode,${mode}" \
    --region=$REGION \
    --cpu=$cpu \
    --memory=$memory \
    --task-timeout=$timeout \
    --max-retries=1 \
    --service-account="$SERVICE_ACCOUNT_EMAIL" \
    --project=$PROJECT_ID
}

# Step 3: Create or update the Cloud Run Jobs
echo ""
echo "3️⃣  Deploying Cloud Run Jobs..."
deploy_job $MONTHLY_JOB monthly 4 4Gi 3600s
deploy_job $WEEKLY_JOB  weekly  2 2Gi 1800s

# schedule_job NAME CRON
schedule_job() {
  local name=$1 cron=$2
  local action=create
  if gcloud scheduler jobs describe "${name}-scheduler" --location=$REGION --project=$PROJECT_ID &>/dev/null; then
    action=update
  fi
  echo "   📝 ${action}: ${name}-scheduler ($cron UTC)"
  gcloud scheduler jobs $action http "${name}-scheduler" \
    --location=$REGION \
    --schedule="$cron" \
    --time-zone="UTC" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${name}:run" \
    --http-method=POST \
    --oauth-service-account-email="$SERVICE_ACCOUNT_EMAIL" \
    --project=$PROJECT_ID
}

# Step 4: Create or update the Cloud Scheduler triggers
echo ""
echo "4️⃣  Setting up Cloud Scheduler..."
schedule_job $MONTHLY_JOB "$MONTHLY_SCHEDULE"
schedule_job $WEEKLY_JOB  "$WEEKLY_SCHEDULE"

echo ""
echo "=========================================="
echo "✅ Deployment complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. First run the monthly job once so the matrices exist before the weekly job scores:"
echo "   gcloud run jobs execute $MONTHLY_JOB --region=$REGION --project=$PROJECT_ID --wait"
echo "2. Then test the weekly job:"
echo "   gcloud run jobs execute $WEEKLY_JOB --region=$REGION --project=$PROJECT_ID --wait"
echo "3. View executions: gcloud run jobs executions list --job=$WEEKLY_JOB --region=$REGION --project=$PROJECT_ID"
echo "4. View schedules: gcloud scheduler jobs list --location=$REGION --project=$PROJECT_ID"
