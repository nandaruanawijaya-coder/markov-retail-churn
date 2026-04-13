"""
QRIS Soundbox - Markov Transition Matrix Builder (2-step)
Reads SQL from transition_query.sql and executes against BigQuery.

Matrix structure: (prev_tier, current_tier) -> next_tier
This captures momentum — a merchant declining vs recovering in the same
current tier will have different forward-looking churn probabilities.

Churn definition: 3 consecutive weeks with 0 settlement days.
  - Each zero-streak is independently capped at 3 weeks
  - Merchants are re-eligible after reactivation (gaps-and-islands)
  - Merchants with tenure < 2 weeks are excluded

Output:
  - Terminal: transition counts & probability summary per tenure bucket
  - markov_transitions.csv: long-format with (prev_tier, current_tier,
    next_tier, probability, raw_count) per tenure bucket

Requirements:
    pip install google-cloud-bigquery pandas db-dtypes

Auth:
    gcloud auth application-default login
"""

from pathlib import Path
import pandas as pd
from google.cloud import bigquery

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID  = "ledger-fcc1e"   # 👈 change this
SQL_FILE    = Path(__file__).parent / "transition_query.sql"
OUTPUT_CSV  = "markov_transitions.csv"

TIER_LABELS  = ["0", "1-2", "3-4", "5-6", "7"]
N            = 5
TENURE_ORDER = ["early", "growing", "mature", "veteran"]


# ── Load SQL ──────────────────────────────────────────────────────────────────
def load_query(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    print(f"Loading SQL from: {path}")
    return path.read_text()


# ── Build 2-step transition matrix ────────────────────────────────────────────
def build_transition_matrix(df_bucket: pd.DataFrame) -> pd.DataFrame:
    """
    For each (prev_tier, current_tier) pair, compute probability distribution
    over next_tier. Returns a DataFrame with columns:
      prev_tier, current_tier, next_tier, raw_count, probability
    """
    results = []

    for prev in range(N):
        for curr in range(N):
            subset = df_bucket[
                (df_bucket["prev_tier"] == prev) &
                (df_bucket["current_tier"] == curr)
            ]
            total = subset["transition_count"].sum()

            for nxt in range(N):
                raw = subset[subset["next_tier"] == nxt]["transition_count"].sum()
                prob = raw / total if total > 0 else 0.0
                results.append({
                    "prev_tier":    TIER_LABELS[prev],
                    "current_tier": TIER_LABELS[curr],
                    "next_tier":    TIER_LABELS[nxt],
                    "raw_count":    int(raw),
                    "total_count":  int(total),
                    "probability":  round(prob, 6),
                })

    return pd.DataFrame(results)


# ── Print summary ─────────────────────────────────────────────────────────────
def print_summary(name: str, df_matrix: pd.DataFrame):
    """Print a readable summary of transition probabilities for each
    (prev_tier, current_tier) → P(next_tier = 0) to show churn risk."""
    print(f"\n{'─'*65}")
    print(f"  {name.upper()} — P(next = Tier 0) by (prev → current)")
    print(f"{'─'*65}")
    print(f"  {'prev → curr':<20} {'P(→ Tier 0)':>12}  {'n':>8}")
    print(f"  {'─'*44}")

    p0 = df_matrix[df_matrix["next_tier"] == "0"].copy()
    p0["label"] = (
        "Tier " + p0["prev_tier"].astype(str) +
        " → Tier " + p0["current_tier"].astype(str)
    )
    p0 = p0.sort_values("probability", ascending=False)

    for _, row in p0.iterrows():
        bar = "█" * int(row["probability"] * 20)
        print(
            f"  {row['label']:<20} {row['probability']:>11.1%}  "
            f"{row['total_count']:>8,}  {bar}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    query = load_query(SQL_FILE)

    client = bigquery.Client(project=PROJECT_ID)
    print("Running BigQuery query...")
    df = client.query(query).to_dataframe()
    print(f"  → {len(df):,} rows fetched\n")

    all_results = []

    for bucket in TENURE_ORDER:
        df_bucket = df[df["tenure_bucket"] == bucket]

        if df_bucket.empty:
            print(f"[{bucket}] No data found, skipping.")
            continue

        total = df_bucket["transition_count"].sum()
        print(f"{'═'*65}")
        print(f"  Tenure bucket: {bucket.upper()} — {total:,} total transitions")
        print(f"{'═'*65}")

        df_matrix = build_transition_matrix(df_bucket)
        df_matrix.insert(0, "tenure_bucket", bucket)

        print_summary(bucket, df_matrix)
        all_results.append(df_matrix)

    df_out = pd.concat(all_results, ignore_index=True)
    df_out.to_csv(OUTPUT_CSV, index=False)

    print(f"\n{'─'*65}")
    print(f"✅ Results saved to: {OUTPUT_CSV}")
    print(f"   Shape: {df_out.shape[0]:,} rows "
          f"({N}×{N}×{N} states × {len(TENURE_ORDER)} buckets = "
          f"{N*N*N*len(TENURE_ORDER)} rows)")


if __name__ == "__main__":
    main()