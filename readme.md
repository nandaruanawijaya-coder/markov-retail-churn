# QRIS Soundbox Merchant Churn Scoring Pipeline

Markov Chain churn scoring pipeline for QRIS Soundbox merchants. Runs as two scheduled Cloud Run Jobs: matrices refreshed monthly, merchants scored weekly.

## How It Works (the simple version)

Think of it like a **weather forecast for merchants**.

**The matrix = the weather record book.**
Each week we label a merchant by how many days they had transactions: 0 days, 1–2, 3–4, 5–6, or all 7 (these are the "tiers"). We then look at what merchants did in the past:
*"Last week they were a 3–4 day merchant, this week they dropped to 0 days. What happened the week after?"*
Across hundreds of thousands of real merchant-weeks, we count how often the next week was 0 days, 1–2 days, and so on. That table of odds is the **transition matrix**. It's just like a weather book that says *"yesterday rainy + today cloudy → 60% sunny tomorrow."*

We keep a separate book for each group of merchants (the segment and tenure bucket), because new merchants, veterans and the free-subscription merchants don't behave the same way, just like different cities have different weather.

**The catch: the book only looks one week ahead.**
But what we actually want to know is bigger: *"how likely is this merchant to **churn** (4 weeks in a row with 0 days) sometime in the next 4 weeks?"* You can't read that straight off a one-week table.

**Monte Carlo simulation = playing out the future 10,000 times.**
It's like asking *"will it rain 4 days in a row at some point in the next few weeks?"* when you only have a one-day forecast. So you:
1. Start from the merchant's current state (last week + this week).
2. Roll a weighted dice using the matrix to pick next week.
3. Repeat from the new state, week after week.
4. Check if 4 zero-day weeks happened in a row.

Do that 10,000 times, and count how many of the pretend futures ended in churn. If 2,000 of them did, the churn probability is 20%. The same simulation gives the other horizons (8, 13, 26 and 52 weeks) and the expected number of weeks until churn.

**Scoring = looking up the merchant in the results.**
Every week we check each merchant's latest state, find the matching row in the simulation results, and attach its churn probability. The 4-week probability becomes the `churn_score`, which is then bucketed into risk segments (critical, very high, high, medium, low, very low).

Why monthly and weekly? The matrices and simulation are the heavy part, and the odds barely move from month to month, so we redo them **monthly**. Looking up each merchant's current state is cheap, and their state changes every week, so we score **weekly**.

## Pipeline Steps
**Monthly** (`python pipeline.py --mode monthly`)
1. **Build transition matrices** — Queries BigQuery for merchant state transitions
2. **Monte Carlo simulation** — Computes churn probabilities from transition matrices
3. **Upload analysis** — Writes matrices to `temp_amal.markov_analysis_v2`

**Weekly** (`python pipeline.py --mode weekly`)
4. **Score merchants** — Runs `scoring_query.sql`, looks up each merchant's state in the matrices and appends a snapshot to `temp_amal.merchant_churn_scores_v2`

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
- `merchant_scoring.py` — Scores merchants against the matrices and writes the weekly snapshot
- `upload_markov_analysis.py` — Uploads markov_analysis.csv to `temp_amal.markov_analysis_v2`
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
Creates/updates two Cloud Run Jobs and their Cloud Scheduler triggers. Uses the existing `data-team-ml-model` service account by default; override with `SERVICE_ACCOUNT_EMAIL`. Run the monthly job once before the first weekly run (see [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md)).

## Schedule
| Job | Schedule (UTC) |
|---|---|
| `markov-matrices-monthly` | 1st of each month, 02:00 |
| `merchant-scoring-weekly` | Every Monday, 03:00 (10:00 WIB) |

## Trigger Manually (Testing)
```bash
gcloud run jobs execute merchant-scoring-weekly --region=asia-southeast1 --wait
```

## Local Testing
```bash
python merchant_scoring.py --dry-run --analysis-csv markov_analysis.csv   # score, write nothing
```
