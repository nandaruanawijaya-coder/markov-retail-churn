# QRIS Soundbox Merchant Churn Scoring Pipeline

Markov Chain churn scoring pipeline for QRIS Soundbox merchants. Runs as a monthly scheduled job on Cloud Run.

## Pipeline Steps
1. **Build transition matrices** — Queries BigQuery for merchant state transitions
2. **Monte Carlo simulation** — Computes churn probabilities from transition matrices
3. **Upload analysis** — Writes simulation results to BigQuery
4. **Run scoring query** — Executes weekly scoring and updates merchant_churn_scores table

## Segments and Tenure Buckets
A separate transition matrix is built per segment. A merchant is `promo_2m_free` if its earliest-paid order has a free 2-month subscription SKU (`product_sku` contains `2months-free`), otherwise `standard`. Tenure = weeks since first settlement (Monday weeks, current week excluded).

| Segment | Bucket | Weeks |
|---|---|---|
| standard | `standard_early` | 2–4 |
| standard | `standard_growing` | 5–9 |
| standard | `standard_mature` | 10–19 |
| standard | `standard_veteran` | 20+ |
| promo_2m_free | `promo_free_period` | 2–7 |
| promo_2m_free | `promo_post_free_early` | 8–12 |
| promo_2m_free | `promo_post_free` | 13+ |

Cut points were chosen from observed weekly churn/reactivation behavior (the promo break at week 8 matches the end of the free period). Definitions live in `segments.py`, `transition_query.sql` and `scoring_query.sql` — keep them in sync.

## Files
- `pipeline.py` — Main orchestrator (runs all steps)
- `markov_transition.py` — Normalizes transitions into probability matrices
- `markov_analysis.py` — Runs Monte Carlo simulation (multi-process) to compute churn probabilities per segment/bucket
- `segments.py` — Segment and tenure bucket definitions shared by the scripts
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
export REGION="asia-southeast1"  # default if unset

./deploy-cloud-run.sh
```
Uses the existing `data-team-ml-model` service account by default; override with `SERVICE_ACCOUNT_EMAIL`.

### Manual Setup
See [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) for detailed steps.

## Schedule
**Monthly** — 1st of each month at 2:00 AM UTC via Cloud Scheduler
- Results written to `temp_amal.merchant_churn_scores`
- Logs available via: `gcloud run jobs log markov-churn-pipeline`

## Trigger Manually (Testing)
```bash
gcloud scheduler jobs run markov-pipeline-monthly --location=asia-southeast1
```
