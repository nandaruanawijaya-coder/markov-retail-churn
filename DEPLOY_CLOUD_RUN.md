# Deploy to Cloud Run (Scheduled Jobs)

One image, two Cloud Run **Jobs**, each triggered by Cloud Scheduler:

| Job | Mode | Schedule (UTC) | What it does |
|---|---|---|---|
| `markov-matrices-monthly` | `--mode monthly` | 1st of month, 02:00 | Rebuild transitions, run Monte Carlo, upload matrices to `temp_amal.markov_analysis_v2` |
| `merchant-scoring-weekly` | `--mode weekly` | Monday, 03:00 (10:00 WIB) | Score merchants against the matrices, append a snapshot to `temp_amal.merchant_churn_scores_v2` |

Scoring is weekly because tiers come from the last complete Monday–Sunday week and churn is a 4-week-zero event; the matrices change slowly, so they are refreshed monthly.

## Prerequisites
- `gcloud` CLI installed and authenticated
- Cloud Run, Cloud Scheduler, Cloud Build and Artifact Registry APIs enabled
- Service account `data-team-ml-model@${PROJECT_ID}.iam.gserviceaccount.com` (the script verifies it exists; it does not create it or change IAM) with:
  - BigQuery read on `retail_payment_base`, and data editor + job user for `temp_amal`
  - permission to run the two jobs (e.g. `roles/run.invoker` on them) so Cloud Scheduler can trigger them

## Deploy

```bash
export PROJECT_ID="ledger-fcc1e"
export REGION="asia-southeast1"      # default
./deploy-cloud-run.sh
```

The script builds the image, then creates or updates both jobs and both scheduler triggers. Override defaults with `SERVICE_ACCOUNT_EMAIL`, `REPO_NAME` and `IMAGE_NAME`.

## First run
The weekly job reads the matrices from BigQuery, so run the monthly job once first:

```bash
gcloud run jobs execute markov-matrices-monthly --region=$REGION --project=$PROJECT_ID --wait
gcloud run jobs execute merchant-scoring-weekly --region=$REGION --project=$PROJECT_ID --wait
```

Re-running the weekly job on the same day replaces that day's snapshot instead of duplicating it.

## Operate

```bash
# Executions and status
gcloud run jobs executions list --job=merchant-scoring-weekly --region=$REGION --project=$PROJECT_ID

# Logs for a job
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="merchant-scoring-weekly"' \
  --limit=100 --project=$PROJECT_ID

# Scheduler triggers
gcloud scheduler jobs list --location=$REGION --project=$PROJECT_ID

# Trigger through the scheduler
gcloud scheduler jobs run merchant-scoring-weekly-scheduler --location=$REGION --project=$PROJECT_ID
```

## Change a schedule
Edit `MONTHLY_SCHEDULE` / `WEEKLY_SCHEDULE` in `deploy-cloud-run.sh` and re-run it.

## Cleanup

```bash
for j in markov-matrices-monthly merchant-scoring-weekly; do
  gcloud scheduler jobs delete ${j}-scheduler --location=$REGION --project=$PROJECT_ID
  gcloud run jobs delete $j --region=$REGION --project=$PROJECT_ID
done
```
