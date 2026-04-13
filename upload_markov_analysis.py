"""
QRIS Soundbox - Upload Markov Analysis to BigQuery
Reads markov_analysis.csv and writes it to a BigQuery table.

This only needs to be run once (or whenever markov_analysis.csv is updated).

Requirements:
    pip install google-cloud-bigquery pandas db-dtypes pyarrow

Auth:
    gcloud auth application-default login
"""

from pathlib import Path
import pandas as pd
from google.cloud import bigquery

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID      = "ledger-fcc1e"
BQ_OUTPUT_TABLE = "temp_amal.markov_analysis"   # 👈 change dataset name
INPUT_CSV       = Path(__file__).parent / "markov_analysis.csv"

BQ_SCHEMA = [
    bigquery.SchemaField("tenure_bucket",          "STRING"),
    bigquery.SchemaField("prev_tier",              "STRING"),
    bigquery.SchemaField("current_tier",           "STRING"),
    bigquery.SchemaField("sample_n",               "INTEGER"),
    bigquery.SchemaField("confident",              "BOOLEAN"),
    bigquery.SchemaField("expected_weeks_churn",   "FLOAT"),
    bigquery.SchemaField("churn_prob_4w",          "FLOAT"),
    bigquery.SchemaField("churn_prob_8w",          "FLOAT"),
    bigquery.SchemaField("churn_prob_13w",         "FLOAT"),
    bigquery.SchemaField("churn_prob_26w",         "FLOAT"),
    bigquery.SchemaField("churn_prob_52w",         "FLOAT"),
    bigquery.SchemaField("churn_score",            "FLOAT"),
]


def main():
    # Load CSV
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"CSV not found: {INPUT_CSV}")
    print(f"Loading: {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV)

    # Ensure correct types
    df["sample_n"]   = df["sample_n"].astype("int64")
    df["confident"]  = df["confident"].astype("bool")
    df["prev_tier"]    = df["prev_tier"].astype("str")
    df["current_tier"] = df["current_tier"].astype("str")
    print(f"  -> {len(df):,} rows loaded")

    # Write to BigQuery (overwrite each time)
    client = bigquery.Client(project=PROJECT_ID)
    job_config = bigquery.LoadJobConfig(
        schema=BQ_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,  # overwrite
    )

    print(f"Writing to BigQuery: {BQ_OUTPUT_TABLE}")
    job = client.load_table_from_dataframe(df, BQ_OUTPUT_TABLE, job_config=job_config)
    job.result()

    print(f"  -> Done. {job.output_rows:,} rows written.")
    print(f"\n✅ Table ready: {BQ_OUTPUT_TABLE}")


if __name__ == "__main__":
    main()