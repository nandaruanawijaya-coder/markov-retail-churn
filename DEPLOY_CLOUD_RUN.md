# Deploy to Cloud Run (Monthly Scheduled Job)

## Prerequisites
- `gcloud` CLI installed and configured
- Active GCP project with Cloud Run and Cloud Scheduler enabled
- BigQuery access in your project

## Step 1: Create Service Account

```bash
# Set your GCP project
export PROJECT_ID="ledger-fcc1e"
export SERVICE_ACCOUNT="markov-pipeline-sa"

# Create service account
gcloud iam service-accounts create $SERVICE_ACCOUNT \
  --display-name="Markov Churn Pipeline Service Account" \
  --project=$PROJECT_ID

# Grant BigQuery roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.admin"
```

## Step 2: Build and Deploy to Cloud Run

```bash
# Set variables
export SERVICE_NAME="markov-churn-pipeline"
export REGION="us-central1"  # Change if needed
export IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Build and push image
gcloud builds submit --tag=$IMAGE --project=$PROJECT_ID

# Deploy to Cloud Run (as a job, not a service)
gcloud run deploy $SERVICE_NAME \
  --image=$IMAGE \
  --platform=managed \
  --region=$REGION \
  --timeout=3600 \
  --memory=2Gi \
  --cpu=2 \
  --service-account="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project=$PROJECT_ID
```

## Step 3: Create Cloud Scheduler Job (Monthly)

```bash
# Create Cloud Scheduler job that runs on the 1st of each month at 2 AM UTC
gcloud scheduler jobs create http markov-pipeline-monthly \
  --location=$REGION \
  --schedule="0 2 1 * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${SERVICE_NAME}:run" \
  --oidc-service-account-email="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --oidc-token-audience="https://${REGION}-run.googleapis.com/${SERVICE_NAME}" \
  --http-method=POST \
  --project=$PROJECT_ID
```

## Step 4: Verify Setup

```bash
# List Cloud Run jobs
gcloud run jobs list --project=$PROJECT_ID

# List Cloud Scheduler jobs
gcloud scheduler jobs list --location=$REGION --project=$PROJECT_ID

# View job details
gcloud scheduler jobs describe markov-pipeline-monthly --location=$REGION
```

## Manual Trigger (for testing)

```bash
gcloud scheduler jobs run markov-pipeline-monthly --location=$REGION --project=$PROJECT_ID
```

## View Logs

```bash
gcloud run jobs log markov-churn-pipeline --limit=100 --project=$PROJECT_ID
```

## Cron Schedule Reference
- `0 2 1 * *` = 1st of each month at 2 AM UTC
- Change the schedule by updating the `--schedule` parameter in the Cloud Scheduler creation command

## Cleanup

```bash
# Delete Cloud Scheduler job
gcloud scheduler jobs delete markov-pipeline-monthly --location=$REGION

# Delete Cloud Run job
gcloud run jobs delete markov-churn-pipeline --region=$REGION
```
