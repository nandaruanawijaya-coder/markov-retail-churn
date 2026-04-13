# QRIS Soundbox — Merchant Churn Scoring

A weekly churn scoring pipeline for QRIS Soundbox merchants using a 2-step Markov chain model. Scores each merchant based on their recent settlement day activity and predicts the probability of churning within the next 4 weeks.

---

## Background

QRIS Soundbox uses a subscription pricing model — merchants are charged **1,500 IDR on any day they transact**, regardless of transaction volume. This makes frequency the key behavioral signal, not amount.

**Churn is defined as 3 consecutive weeks with 0 settlement days.**

---

## How it works

### 1. State space
Each merchant's state is represented as a **(prev_tier, current_tier)** pair based on their settlement days in the last 2 weeks:

| Tier | Settlement days |
|------|----------------|
| 0    | 0 days         |
| 1-2  | 1–2 days       |
| 3-4  | 3–4 days       |
| 5-6  | 5–6 days       |
| 7    | 7 days         |

The 2-step state captures **momentum** — a merchant declining from Tier 7 to Tier 0 is scored differently from one recovering from Tier 0 to Tier 5-6, even though both share the same current tier.

### 2. Transition matrices
Separate 5×5×5 transition matrices are estimated per tenure bucket:

| Bucket  | Tenure         |
|---------|----------------|
| Early   | Weeks 2–4      |
| Growing | Weeks 5–12     |
| Mature  | Weeks 13–26    |
| Veteran | Weeks 27+      |

Merchants with tenure < 2 weeks are excluded (insufficient history) and tagged as `new_user`.

### 3. Monte Carlo simulation
10,000 simulations per starting state estimate churn probability at **4, 8, 13, 26, and 52 week** horizons. The **4-week probability** is the primary churn score used for intervention.

### 4. Weekly scoring
Every Monday at 10:00 WIB, each merchant is scored using their latest `(prev_tier, current_tier)` state and joined against pre-computed Markov analysis results.

---

## Risk segments & interventions

| Segment   | Churn score | Intervention                          |
|-----------|-------------|---------------------------------------|
| Critical  | ≥ 75%       | Field visit or direct call, same week |
| Very high | 60–74%      | WhatsApp + call within 3–5 days       |
| High      | 40–59%      | Automated WhatsApp nudge, weekly      |
| Medium    | 20–39%      | Monthly touchpoint                    |
| Low       | 5–19%       | Reward & retain, quarterly            |
| Very low  | < 5%        | Power user nurture                    |

---

## Project structure

```
├── transition_query.sql       # Extracts (prev, curr, next) tier triplets from BQ
├── markov_transition.py       # Normalizes raw counts into probability matrices
├── markov_analysis.py         # Runs Monte Carlo simulations per (tenure, state)
├── upload_markov_analysis.py  # Uploads markov_analysis.csv to BigQuery
├── scoring_query.sql          # Pulls latest 2 weeks per merchant for scoring
├── merchant_scoring.py        # Python scoring script (local / Cloud Run)
├── scoring_bq.sql             # BigQuery scheduled query (weekly scoring)
├── Dockerfile                 # Container definition for Cloud Run Job
├── requirements.txt           # Python dependencies
└── deploy.sh                  # Cloud Run + Cloud Scheduler deploy script
```

---

## BigQuery tables

| Table                            | Description                              |
|----------------------------------|------------------------------------------|
| `temp_amal.retail_weekly_rfm`    | Source: weekly merchant activity data    |
| `temp_amal.markov_analysis`      | Markov churn probabilities per state     |
| `temp_amal.merchant_churn_scores`| Weekly scored merchant output            |

### Output columns (`merchant_churn_scores`)

| Column                  | Description                                      |
|-------------------------|--------------------------------------------------|
| `snapshot_date`         | Date the score was generated (WIB)               |
| `nmid`                  | Merchant ID                                      |
| `latest_week_start`     | Start of merchant's latest observed week         |
| `weeks_since_first_tx`  | Merchant tenure in weeks                         |
| `current_transaction_days` | Settlement days this week                     |
| `prev_transaction_days` | Settlement days last week                        |
| `current_tier`          | Current week tier (0, 1-2, 3-4, 5-6, 7)        |
| `prev_tier`             | Previous week tier                               |
| `tenure_bucket`         | early / growing / mature / veteran / new_user    |
| `last_active_week`      | Last week with at least 1 settlement day         |
| `days_since_last_active`| Days since last active week                      |
| `consecutive_zero_weeks`| Trailing consecutive zero-settlement weeks       |
| `churn_flag`            | TRUE if 3+ consecutive zero weeks                |
| `expected_weeks_churn`  | Expected weeks until churn from current state    |
| `churn_prob_4w`         | Churn probability within 4 weeks                 |
| `churn_prob_8w`         | Churn probability within 8 weeks                 |
| `churn_prob_13w`        | Churn probability within 13 weeks                |
| `churn_prob_26w`        | Churn probability within 26 weeks                |
| `churn_prob_52w`        | Churn probability within 52 weeks                |
| `churn_score`           | Primary score = churn_prob_4w                    |
| `confident`             | TRUE if state has ≥ 50 training observations     |
| `risk_segment`          | very low / low / medium / high / very high / critical |
| `intervention_action`   | Recommended action for this merchant             |

---

## Setup

### Requirements
```bash
pip install google-cloud-bigquery pandas db-dtypes pyarrow
```

### Authentication
```bash
gcloud auth application-default login
```

### Run pipeline (quarterly retraining)
```bash
# 1. Build transition matrices from BigQuery
python markov_transition.py

# 2. Run Monte Carlo simulations
python markov_analysis.py

# 3. Upload updated analysis to BigQuery
python upload_markov_analysis.py
```

### Schedule weekly scoring
Set up `scoring_bq.sql` as a BigQuery Scheduled Query:
- Schedule: every Monday 10:00 WIB (`0 3 * * 1` UTC)
- Destination: `temp_amal.merchant_churn_scores`
- Write mode: Append

---

## Retraining schedule

The transition matrices should be retrained **every quarter** as merchant behavior evolves. Run steps 1–3 above and re-upload `markov_analysis.csv` to BigQuery. The weekly scoring query will automatically pick up the updated probabilities.