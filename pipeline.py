"""
QRIS Soundbox - Full Churn Scoring Pipeline (Local)
Runs all steps in order:
  1. Build transition matrices from BigQuery
  2. Normalize into probability matrices
  3. Run Monte Carlo simulations
  4. Upload markov_analysis.csv to BigQuery
  5. Run weekly scoring query and write to BigQuery

Usage:
    python pipeline.py                  # run all steps
    python pipeline.py --steps 1 2 3   # run specific steps only
    python pipeline.py --skip-upload    # skip BQ upload (step 4)

Requirements:
    pip install google-cloud-bigquery pandas db-dtypes pyarrow numpy

Auth:
    gcloud auth application-default login
"""

import argparse
import time
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID       = "ledger-fcc1e"
WORKING_DIR      = Path(__file__).parent

# ── Helpers ───────────────────────────────────────────────────────────────────
def header(step: int, title: str):
    print(f"\n{'='*60}")
    print(f"  STEP {step}: {title.upper()}")
    print(f"{'='*60}\n")


def success(msg: str):
    print(f"\n  ✅ {msg}")


def failed(msg: str):
    print(f"\n  ❌ {msg}")


def elapsed(start: float) -> str:
    s = time.time() - start
    return f"{int(s//60)}m {int(s%60)}s" if s >= 60 else f"{s:.1f}s"


# ── Step 1: Build transition matrices ────────────────────────────────────────
def step1_build_transitions():
    header(1, "Build transition matrices from BigQuery")
    start = time.time()

    import subprocess
    result = subprocess.run(
        ["python", str(WORKING_DIR / "markov_transition.py")],
        capture_output=False
    )
    if result.returncode != 0:
        raise RuntimeError("markov_transition.py failed")

    success(f"Transition matrices built — {elapsed(start)}")


# ── Step 2 & 3: Monte Carlo simulations ──────────────────────────────────────
def step2_run_simulations():
    header(2, "Run Monte Carlo simulations")
    start = time.time()

    import subprocess
    result = subprocess.run(
        ["python", str(WORKING_DIR / "markov_analysis.py")],
        capture_output=False
    )
    if result.returncode != 0:
        raise RuntimeError("markov_analysis.py failed")

    success(f"Simulations complete — {elapsed(start)}")


# ── Step 3: Upload markov_analysis.csv to BigQuery ───────────────────────────
def step3_upload_analysis():
    header(3, "Upload markov_analysis.csv to BigQuery")
    start = time.time()

    import subprocess
    result = subprocess.run(
        ["python", str(WORKING_DIR / "upload_markov_analysis.py")],
        capture_output=False
    )
    if result.returncode != 0:
        raise RuntimeError("upload_markov_analysis.py failed")

    success(f"Uploaded to temp_amal.markov_analysis — {elapsed(start)}")


# ── Step 4: Run scoring query and write to BigQuery ──────────────────────────
def step4_run_scoring():
    header(4, "Run weekly scoring query")
    start = time.time()

    from google.cloud import bigquery

    sql_path = WORKING_DIR / "scoring_bq.sql"
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")

    query = sql_path.read_text()

    client = bigquery.Client(project=PROJECT_ID)
    print(f"  Running scoring query against BigQuery...")

    job = client.query(query)
    job.result()  # wait for completion

    # Count rows written
    table = client.get_table("temp_amal.merchant_churn_scores")
    success(f"Scoring complete — {elapsed(start)}")
    print(f"  Total rows in merchant_churn_scores: {table.num_rows:,}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="QRIS Soundbox full churn scoring pipeline"
    )
    parser.add_argument(
        "--steps", nargs="+", type=int,
        help="Run specific steps only (e.g. --steps 1 2 3 4)"
    )
    parser.add_argument(
        "--skip-upload", action="store_true",
        help="Skip step 3 (uploading markov_analysis.csv to BigQuery)"
    )
    args = parser.parse_args()

    all_steps = {
        1: ("Build transition matrices",     step1_build_transitions),
        2: ("Run Monte Carlo simulations",   step2_run_simulations),
        3: ("Upload analysis to BigQuery",   step3_upload_analysis),
        4: ("Run scoring query",             step4_run_scoring),
    }

    # Determine which steps to run
    steps_to_run = args.steps if args.steps else list(all_steps.keys())
    if args.skip_upload and 3 in steps_to_run:
        steps_to_run.remove(3)

    print(f"\n{'='*60}")
    print(f"  QRIS Soundbox Churn Scoring Pipeline")
    print(f"  Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Steps    : {steps_to_run}")
    print(f"{'='*60}")

    pipeline_start = time.time()
    failed_steps   = []

    for step_num in steps_to_run:
        if step_num not in all_steps:
            print(f"\n  ⚠️  Step {step_num} not found, skipping.")
            continue

        title, fn = all_steps[step_num]
        try:
            fn()
        except Exception as e:
            failed(f"Step {step_num} failed: {e}")
            failed_steps.append(step_num)
            print("\n  Pipeline stopped due to error.")
            break

    # Summary
    print(f"\n{'='*60}")
    print(f"  Pipeline finished in {elapsed(pipeline_start)}")
    if failed_steps:
        print(f"  Failed steps: {failed_steps}")
    else:
        print(f"  All steps completed successfully!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()