"""
QRIS Soundbox - Merchant Churn Scoring (2-step)
Scores each merchant using (prev_tier, current_tier) Markov state.

Inputs:
  - scoring_query.sql   : pulls latest 2 weeks per merchant from BigQuery
  - markov_analysis.csv : churn probabilities per (tenure_bucket, prev_tier, current_tier)

Output:
  - BigQuery table : BQ_OUTPUT_TABLE (appended with snapshot_date = today)
  - merchant_scores.csv : local backup

Risk segments (based on 4-week churn score):
  critical  >= 75%
  very high >= 60%
  high      >= 40%
  medium    >= 20%
  low       >= 05%
  very low   < 05%

Requirements:
    pip install google-cloud-bigquery pandas db-dtypes pyarrow

Auth:
    gcloud auth application-default login
"""

from pathlib import Path
from datetime import date
import pandas as pd
from google.cloud import bigquery

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID     = "ledger-fcc1e"          # 👈 change this
BQ_OUTPUT_TABLE = "retail_payment_base.merchant_churn_scores"  # 👈 change this
SQL_FILE       = Path(__file__).parent / "scoring_query.sql"
ANALYSIS_CSV   = Path(__file__).parent / "markov_analysis.csv"
OUTPUT_CSV     = "merchant_scores.csv"

TIER_LABEL_MAP = {0: "0", 1: "1-2", 2: "3-4", 3: "5-6", 4: "7"}
TENURE_ORDER   = ["early", "growing", "mature", "veteran"]

# BigQuery schema — ensures correct types on write
BQ_SCHEMA = [
    bigquery.SchemaField("snapshot_date",            "DATE"),
    bigquery.SchemaField("nmid",                     "STRING"),
    bigquery.SchemaField("latest_week_start",        "DATE"),
    bigquery.SchemaField("weeks_since_first_tx",     "INTEGER"),
    bigquery.SchemaField("current_transaction_days", "INTEGER"),
    bigquery.SchemaField("prev_transaction_days",    "INTEGER"),
    bigquery.SchemaField("current_tier",             "STRING"),
    bigquery.SchemaField("prev_tier",                "STRING"),
    bigquery.SchemaField("tenure_bucket",            "STRING"),
    bigquery.SchemaField("expected_weeks_churn",     "FLOAT"),
    bigquery.SchemaField("churn_prob_4w",            "FLOAT"),
    bigquery.SchemaField("churn_prob_8w",            "FLOAT"),
    bigquery.SchemaField("churn_prob_13w",           "FLOAT"),
    bigquery.SchemaField("churn_prob_26w",           "FLOAT"),
    bigquery.SchemaField("churn_prob_52w",           "FLOAT"),
    bigquery.SchemaField("churn_score",              "FLOAT"),
    bigquery.SchemaField("confident",                "BOOLEAN"),
    bigquery.SchemaField("risk_segment",             "STRING"),
]


# ── Loaders ───────────────────────────────────────────────────────────────────
def load_query(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    print(f"Loading SQL from: {path}")
    return path.read_text()


def fetch_merchant_states(client: bigquery.Client, query: str) -> pd.DataFrame:
    print("Fetching merchant states from BigQuery...")
    df = client.query(query).to_dataframe()
    print(f"  -> {len(df):,} merchants fetched")
    return df


def load_analysis(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Analysis CSV not found: {path}")
    print(f"Loading Markov analysis from: {path}")
    df = pd.read_csv(path)
    df["prev_tier"]    = df["prev_tier"].astype(str)
    df["current_tier"] = df["current_tier"].astype(str)
    print(f"  -> {len(df):,} rows loaded")
    return df


# ── Scoring ───────────────────────────────────────────────────────────────────
def risk_segment(churn_score: float) -> str:
    if churn_score >= 0.75:
        return "critical"
    elif churn_score >= 0.60:
        return "very high"
    elif churn_score >= 0.40:
        return "high"
    elif churn_score >= 0.20:
        return "medium"
    elif churn_score >= 0.05:
        return "low"
    else:
        return "very low"


def score_merchants(
    df_merchants: pd.DataFrame,
    df_analysis: pd.DataFrame,
    snapshot_date: date,
) -> pd.DataFrame:

    lookup = df_analysis.set_index(["tenure_bucket", "prev_tier", "current_tier"])
    scores = []

    for _, row in df_merchants.iterrows():
        bucket     = row["tenure_bucket"]
        prev_label = TIER_LABEL_MAP.get(int(row["prev_tier"]), None)
        curr_label = TIER_LABEL_MAP.get(int(row["current_tier"]), None)
        key        = (bucket, prev_label, curr_label)

        base = {
            "snapshot_date":            snapshot_date,
            "nmid":                     row["nmid"],
            "latest_week_start":        row["latest_week_start"],
            "weeks_since_first_tx":     row["weeks_since_first_tx"],
            "current_transaction_days": row["current_transaction_days"],
            "prev_transaction_days":    row["prev_transaction_days"],
            "current_tier":             curr_label,
            "prev_tier":                prev_label,
            "tenure_bucket":            bucket,
        }

        null_scores = {
            "expected_weeks_churn": None,
            "churn_prob_4w":        None,
            "churn_prob_8w":        None,
            "churn_prob_13w":       None,
            "churn_prob_26w":       None,
            "churn_prob_52w":       None,
            "churn_score":          None,
            "confident":            False,
        }

        if bucket == "new_user" or prev_label is None or curr_label is None:
            scores.append({
                **base, **null_scores,
                "risk_segment": "new_user" if bucket == "new_user" else "unscored",
            })
            continue

        if key not in lookup.index:
            scores.append({**base, **null_scores, "risk_segment": "unscored"})
            continue

        m        = lookup.loc[key]
        churn_4w = m["churn_prob_4w"]

        scores.append({
            **base,
            "expected_weeks_churn": m["expected_weeks_churn"],
            "churn_prob_4w":        m["churn_prob_4w"],
            "churn_prob_8w":        m["churn_prob_8w"],
            "churn_prob_13w":       m["churn_prob_13w"],
            "churn_prob_26w":       m["churn_prob_26w"],
            "churn_prob_52w":       m["churn_prob_52w"],
            "churn_score":          round(float(churn_4w), 4),
            "confident":            bool(m["confident"]),
            "risk_segment":         risk_segment(churn_4w),
        })

    return pd.DataFrame(scores)


# ── BigQuery writer ───────────────────────────────────────────────────────────
def write_to_bigquery(client: bigquery.Client, df: pd.DataFrame):
    print(f"\nWriting {len(df):,} rows to BigQuery: {BQ_OUTPUT_TABLE}")

    job_config = bigquery.LoadJobConfig(
        schema=BQ_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,  # append each snapshot
    )

    job = client.load_table_from_dataframe(df, BQ_OUTPUT_TABLE, job_config=job_config)
    job.result()  # wait for job to complete

    print(f"  -> Done. Rows written: {job.output_rows:,}")


# ── Summary ───────────────────────────────────────────────────────────────────
def print_summary(df: pd.DataFrame):
    print(f"\n{'='*55}")
    print("  SCORING SUMMARY")
    print(f"{'='*55}")

    total  = len(df)
    scored = df[df["churn_score"].notna()]
    print(f"\n  Snapshot date     : {df['snapshot_date'].iloc[0]}")
    print(f"  Total merchants   : {total:,}")
    print(f"  Scored            : {len(scored):,}")
    print(f"  Unscored/new user : {total - len(scored):,}")

    print("\nRisk segment distribution:")
    seg_order  = ["critical", "very high", "high", "medium", "low", "very low", "new_user", "unscored"]
    seg_counts = df["risk_segment"].value_counts()
    for seg in seg_order:
        if seg in seg_counts:
            count = seg_counts[seg]
            pct   = count / total * 100
            bar   = "█" * int(pct / 2)
            print(f"  {seg:<12} {count:>7,}  ({pct:>5.1f}%)  {bar}")

    print("\nMean churn score (4w) by tenure bucket:")
    summary = scored.groupby("tenure_bucket")["churn_score"].agg(
        mean="mean", median="median", count="count"
    ).reindex(TENURE_ORDER)
    print(summary.to_string(float_format="{:.3f}".format))

    print("\nCurrent tier distribution (scored merchants):")
    tier_order = ["0", "1-2", "3-4", "5-6", "7"]
    tier_dist  = scored.groupby("current_tier")["nmid"].count()
    for t in tier_order:
        if t in tier_dist.index:
            count = tier_dist[t]
            pct   = count / len(scored) * 100
            bar   = "█" * int(pct / 2)
            print(f"  Tier {t:<6} {count:>7,}  ({pct:>5.1f}%)  {bar}")

    print("\nMomentum breakdown (prev -> curr) for critical merchants:")
    critical = scored[scored["risk_segment"] == "critical"].copy()
    if not critical.empty:
        critical["state"] = "Tier " + critical["prev_tier"] + " -> Tier " + critical["current_tier"]
        print(critical.groupby("state")["nmid"].count().sort_values(ascending=False).head(10).to_string())


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    snapshot_date = date.today()
    client        = bigquery.Client(project=PROJECT_ID)

    query        = load_query(SQL_FILE)
    df_merchants = fetch_merchant_states(client, query)
    df_analysis  = load_analysis(ANALYSIS_CSV)
    df_scores    = score_merchants(df_merchants, df_analysis, snapshot_date)

    print_summary(df_scores)

    # Save to BigQuery
    write_to_bigquery(client, df_scores)

    # Save local CSV backup
    df_scores.to_csv(OUTPUT_CSV, index=False)
    print(f"\n✅ Local backup saved to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()