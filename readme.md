# QRIS Soundbox Merchant Churn Scoring Pipeline

Markov Chain churn scoring pipeline for QRIS Soundbox merchants. Runs as a monthly scheduled job on Cloud Run.

## Pipeline Steps
1. **Build transition matrices** — Queries BigQuery for merchant state transitions
2. **Monte Carlo simulation** — Computes churn probabilities from transition matrices
3. **Upload analysis** — Writes simulation results to BigQuery
4. **Run scoring query** — Executes weekly scoring and updates merchant_churn_scores table

## Files
- `pipeline.py` — Main orchestrator (runs all steps)
- `markov_transition.py` — Normalizes transitions into probability matrices
- `markov_analysis.py` — Runs Monte Carlo simulation to compute churn probabilities
- `merchant_scoring.py` — Merchant-specific scoring logic
- `upload_markov_analysis.py` — Uploads markov_analysis.csv to BigQuery
- `transition_query.sql` — Builds raw transition counts from BigQuery
- `scoring_query.sql` — Weekly scoring query
- `Dockerfile` + `requirements.txt` — Containerization for Cloud Run
- `deploy-cloud-run.sh` — Deployment automation script

## Deployment to Cloud Run

### Quick Start
```bash
export PROJECT_ID="ledger-fcc1e"
export REGION="us-central1"

./deploy-cloud-run.sh
```

### Manual Setup
See [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) for detailed steps.

## Schedule
**Monthly** — 1st of each month at 2:00 AM UTC via Cloud Scheduler
- Results written to `temp_amal.merchant_churn_scores`
- Logs available via: `gcloud run jobs log markov-churn-pipeline`

## Trigger Manually (Testing)
```bash
gcloud scheduler jobs run markov-pipeline-monthly --location=us-central1
```
