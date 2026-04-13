#!/bin/bash
# ── Deploy QRIS Soundbox Churn Scoring Job ────────────────────────────────────
# Packages the scoring script as a Cloud Run Job and schedules it weekly
# via Cloud Scheduler every Monday at 10:00 WIB (UTC+7 = 03:00 UTC).
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Prerequisites:
#   gcloud auth login
#   gcloud auth configure-docker asia-southeast2-docker.pkg.dev
# ─────────────────────────────────────────────────────────────────────────────

set -e  # exit on any error

# ── Config — update these ─────────────────────────────────────────────────────
PROJECT_ID="ledger-fcc1e"          # 👈 change this
REGION="asia-southeast2"                  # Jakarta region
REPO_NAME="qris-soundbox"                 # Artifact Registry repo name
IMAGE_NAME="merchant-churn-scoring"
JOB_NAME="merchant-churn-scoring"
SCHEDULER_NAME="merchant-churn-scoring-weekly"
SERVICE_ACCOUNT="data-team-ml-model@${PROJECT_ID}.iam.gserviceaccount.com"  # 👈 change this

# Full image path
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

echo "================================================"
echo "  Deploying QRIS Soundbox Churn Scoring Job"
echo "================================================"
echo "  Project  : ${PROJECT_ID}"
echo "  Region   : ${REGION}"
echo "  Image    : ${IMAGE}"
echo ""

# ── Step 1: Enable required APIs ─────────────────────────────────────────────
# echo "[1/6] Enabling required GCP APIs..."
# gcloud services enable \
#   run.googleapis.com \
#   cloudscheduler.googleapis.com \
#   artifactregistry.googleapis.com \
#   bigquery.googleapis.com \
#   --project="${PROJECT_ID}"

# ── Step 2: Create Artifact Registry repo (if not exists) ────────────────────
echo "[2/6] Creating Artifact Registry repository..."
gcloud artifacts repositories create "${REPO_NAME}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --quiet 2>/dev/null || echo "  (repo already exists, skipping)"

# ── Step 3: Build and push Docker image ──────────────────────────────────────
echo "[3/6] Building and pushing Docker image..."
gcloud builds submit \
  --tag="${IMAGE}" \
  --project="${PROJECT_ID}" \
  .

# ── Step 4: Create or update Cloud Run Job ───────────────────────────────────
echo "[4/6] Deploying Cloud Run Job..."
gcloud run jobs create "${JOB_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SERVICE_ACCOUNT}" \
  --memory=2Gi \
  --cpu=2 \
  --task-timeout=30m \
  --max-retries=2 \
  --project="${PROJECT_ID}" \
  --quiet 2>/dev/null || \
gcloud run jobs update "${JOB_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SERVICE_ACCOUNT}" \
  --memory=2Gi \
  --cpu=2 \
  --task-timeout=30m \
  --max-retries=2 \
  --project="${PROJECT_ID}" \
  --quiet

# ── Step 5: Create or update Cloud Scheduler ─────────────────────────────────
# Monday 10:00 WIB = Monday 03:00 UTC
echo "[5/6] Setting up Cloud Scheduler (Monday 10:00 WIB)..."
gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
  --location="${REGION}" \
  --schedule="0 3 * * 1" \
  --time-zone="UTC" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
  --http-method=POST \
  --oauth-service-account-email="${SERVICE_ACCOUNT}" \
  --project="${PROJECT_ID}" \
  --quiet 2>/dev/null || \
gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
  --location="${REGION}" \
  --schedule="0 3 * * 1" \
  --time-zone="UTC" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
  --http-method=POST \
  --oauth-service-account-email="${SERVICE_ACCOUNT}" \
  --project="${PROJECT_ID}" \
  --quiet

# ── Step 6: Test run ──────────────────────────────────────────────────────────
echo "[6/6] Triggering a test run..."
gcloud run jobs execute "${JOB_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --wait

echo ""
echo "================================================"
echo "  Deployment complete!"
echo "================================================"
echo ""
echo "  Schedule  : Every Monday 10:00 WIB (03:00 UTC)"
echo "  Job       : ${JOB_NAME}"
echo "  Scheduler : ${SCHEDULER_NAME}"
echo ""
echo "  Monitor job executions:"
echo "  https://console.cloud.google.com/run/jobs?project=${PROJECT_ID}"
echo ""
echo "  Monitor scheduler:"
echo "  https://console.cloud.google.com/cloudscheduler?project=${PROJECT_ID}"