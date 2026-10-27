"""
QRIS Soundbox - Churn Scoring Pipeline
Two modes, run on different schedules:

  monthly  (refresh the Markov matrices)
    1. Build transition matrices from BigQuery
    2. Run Monte Carlo simulations
    3. Upload markov_analysis.csv to BigQuery (temp_amal.markov_analysis_v2)

  weekly   (score merchants)
    4. Score merchants against the uploaded matrices and append a snapshot to
       temp_amal.merchant_churn_scores_v2

Usage:
    python pipeline.py --mode monthly        # steps 1 2 3
    python pipeline.py --mode weekly         # step 4
    python pipeline.py --steps 1 2           # run specific steps only
    python pipeline.py --mode monthly --skip-upload

Requirements:
    pip install google-cloud-bigquery pandas db-dtypes pyarrow numpy

Auth:
    gcloud auth application-default login
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID       = "ledger-fcc1e"
MATRIX_TABLE     = "temp_amal.markov_analysis_v2"
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


# ── Steps ─────────────────────────────────────────────────────────────────────
def run_script(name: str):
    result = subprocess.run(
        [sys.executable, str(WORKING_DIR / name)],
        capture_output=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed")


def step1_build_transitions():
    header(1, "Build transition matrices from BigQuery")
    start = time.time()
    run_script("markov_transition.py")
    success(f"Transition matrices built — {elapsed(start)}")


def step2_run_simulations():
    header(2, "Run Monte Carlo simulations")
    start = time.time()
    run_script("markov_analysis.py")
    success(f"Simulations complete — {elapsed(start)}")


def step3_upload_analysis():
    header(3, "Upload markov_analysis.csv to BigQuery")
    start = time.time()
    run_script("upload_markov_analysis.py")
    success(f"Uploaded to {MATRIX_TABLE} — {elapsed(start)}")


def step4_run_scoring():
    header(4, "Score merchants")
    start = time.time()
    run_script("merchant_scoring.py")
    success(f"Scoring complete — {elapsed(start)}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="QRIS Soundbox churn scoring pipeline"
    )
    parser.add_argument(
        "--mode", choices=["monthly", "weekly"], default="monthly",
        help="monthly = refresh matrices (steps 1-3), weekly = score merchants (step 4)"
    )
    parser.add_argument(
        "--steps", nargs="+", type=int,
        help="Run specific steps only (e.g. --steps 1 2); overrides --mode"
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
        4: ("Score merchants",               step4_run_scoring),
    }
    mode_steps = {"monthly": [1, 2, 3], "weekly": [4]}

    # Determine which steps to run
    steps_to_run = args.steps if args.steps else list(mode_steps[args.mode])
    if args.skip_upload and 3 in steps_to_run:
        steps_to_run.remove(3)

    print(f"\n{'='*60}")
    print(f"  QRIS Soundbox Churn Scoring Pipeline ({'custom steps' if args.steps else args.mode})")
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

    if failed_steps:
        sys.exit(1)  # non-zero so Cloud Run marks the execution as failed


if __name__ == "__main__":
    main()