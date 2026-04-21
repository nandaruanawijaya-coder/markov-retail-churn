"""
QRIS Soundbox - Markov Chain Analysis (2-step)
Reads transition matrices from markov_transitions.csv and computes for
each (tenure_bucket, prev_tier, current_tier) starting state:

  1. Churn probability at 4, 8, 13, 26, 52 weeks (Monte Carlo)
  2. Expected weeks until churn (3 consecutive Tier 0 weeks)
  3. Confidence flag based on sample size

Churn definition: 3 consecutive weeks with 0 settlement days.
The consecutive counter resets on any active week (re-eligible).

State space: (prev_tier, current_tier) → next_tier
The simulation carries a 2-element state window forward at each step.

Requirements:
    pip install numpy pandas
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
INPUT_CSV        = Path(__file__).parent / "markov_transitions.csv"
OUTPUT_CSV       = "markov_analysis.csv"
TIER_LABELS      = ["0", "1-2", "3-4", "5-6", "7"]
N                = 5
SIM_HORIZONS     = [4, 8, 13, 26, 52]
SIM_N            = 10000
SIM_SEED         = 42
MIN_SAMPLES      = 50   # flag (prev, current) pairs with fewer observations
CONSEC_THRESHOLD = 3    # consecutive Tier 0 weeks to confirm churn

TENURE_ORDER = ["early", "growing", "mature", "veteran"]


# ── Load transition data ──────────────────────────────────────────────────────
def load_transitions(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    print(f"Loading transitions from: {path}")
    df = pd.read_csv(path)
    print(f"  -> {len(df):,} rows loaded\n")
    return df


def build_conditional_matrix(df_bucket: pd.DataFrame) -> dict:
    """
    Build a dict: (prev_tier_idx, current_tier_idx) -> (probs array, total_n)
    representing P(next_tier | prev_tier, current_tier).
    Returns None for pairs with no observations.
    """
    matrix = {}
    for prev in range(N):
        for curr in range(N):
            probs = np.zeros(N)
            total = 0
            for nxt in range(N):
                subset = df_bucket[
                    (df_bucket["prev_tier"]    == TIER_LABELS[prev]) &
                    (df_bucket["current_tier"] == TIER_LABELS[curr]) &
                    (df_bucket["next_tier"]    == TIER_LABELS[nxt])
                ]
                count = subset["raw_count"].sum() if not subset.empty else 0
                probs[nxt] = count
                total += count

            if total > 0:
                matrix[(prev, curr)] = (probs / total, total)
            else:
                matrix[(prev, curr)] = None
    return matrix


# ── Starting consecutive zero count ──────────────────────────────────────────
def start_consec(start_prev: int, start_curr: int, target: int = 0) -> int:
    """
    Count how many consecutive zeros already exist at the starting state.
    Max 2 since we only have a 2-step window (prev, curr).
    """
    if start_curr != target:
        return 0
    if start_prev == target:
        return 2  # both prev and curr are Tier 0
    return 1      # only curr is Tier 0


# ── Monte Carlo: churn probability ───────────────────────────────────────────
def simulate_churn(
    matrix: dict,
    start_prev: int,
    start_curr: int,
    target_tier: int = 0,
    n_steps: int = 4,
    n_simulations: int = SIM_N,
    seed: int = SIM_SEED,
) -> float:
    """
    Simulate forward from (start_prev, start_curr).
    Churn = CONSEC_THRESHOLD consecutive weeks in Tier 0.
    Consecutive counter resets on any active week (re-eligible).
    Returns P(churning within n_steps).
    """
    rng    = np.random.default_rng(seed)
    consec_init = start_consec(start_prev, start_curr, target_tier)
    visits = 0

    for _ in range(n_simulations):
        prev   = start_prev
        curr   = start_curr
        consec = consec_init
        hit    = False

        # already churned at start
        if consec >= CONSEC_THRESHOLD:
            visits += 1
            continue

        for _ in range(n_steps):
            entry = matrix.get((prev, curr))
            if entry is None:
                break
            probs, _ = entry
            if probs.sum() == 0:
                break
            nxt  = rng.choice(N, p=probs)
            prev = curr
            curr = nxt

            if curr == target_tier:
                consec += 1
            else:
                consec = 0  # reset on any active week

            if consec >= CONSEC_THRESHOLD:
                hit = True
                break

        if hit:
            visits += 1

    return visits / n_simulations


# ── Monte Carlo: expected weeks to churn ─────────────────────────────────────
def simulate_expected_weeks(
    matrix: dict,
    start_prev: int,
    start_curr: int,
    target_tier: int = 0,
    n_steps: int = 104,
    n_simulations: int = SIM_N,
    seed: int = SIM_SEED,
) -> float:
    """
    Expected number of weeks until CONSEC_THRESHOLD consecutive Tier 0 weeks.
    Week count ends at the Nth consecutive zero (when churn is confirmed).
    Returns None if churn never triggered within n_steps.
    """
    rng         = np.random.default_rng(seed)
    consec_init = start_consec(start_prev, start_curr, target_tier)
    times       = []

    for _ in range(n_simulations):
        prev   = start_prev
        curr   = start_curr
        consec = consec_init

        if consec >= CONSEC_THRESHOLD:
            times.append(0)
            continue

        for step in range(1, n_steps + 1):
            entry = matrix.get((prev, curr))
            if entry is None:
                break
            probs, _ = entry
            if probs.sum() == 0:
                break
            nxt  = rng.choice(N, p=probs)
            prev = curr
            curr = nxt

            if curr == target_tier:
                consec += 1
            else:
                consec = 0

            if consec >= CONSEC_THRESHOLD:
                times.append(step)
                break

    return round(float(np.mean(times)), 2) if times else None


# ── Analyze one bucket ────────────────────────────────────────────────────────
def analyze_bucket(name: str, df_bucket: pd.DataFrame) -> pd.DataFrame:
    print(f"\n{'='*65}")
    print(f"  TENURE BUCKET: {name.upper()}")
    print(f"{'='*65}")

    matrix = build_conditional_matrix(df_bucket)

    horizon_header = "  ".join([f"P@{h}w" for h in SIM_HORIZONS])
    print(f"\n  {'prev -> curr':<20} {'E[wks churn]':>13}  {horizon_header}  {'n':>7}  conf")
    print(f"  {'-'*75}")

    results = []

    for prev in range(N):
        for curr in range(N):
            entry = matrix.get((prev, curr))

            if entry is None:
                sample_n    = 0
                confident   = False
                churn_probs = {h: None for h in SIM_HORIZONS}
                exp_weeks   = None
            else:
                _, sample_n = entry
                confident   = sample_n >= MIN_SAMPLES
                churn_probs = {
                    h: simulate_churn(matrix, prev, curr, n_steps=h)
                    for h in SIM_HORIZONS
                }
                exp_weeks = simulate_expected_weeks(matrix, prev, curr)

            label    = f"Tier {TIER_LABELS[prev]} -> Tier {TIER_LABELS[curr]}"
            p_vals   = "  ".join(
                f"{churn_probs[h]:>5.1%}" if churn_probs[h] is not None else f"{'N/A':>5}"
                for h in SIM_HORIZONS
            )
            ew_str   = f"{exp_weeks:>12.1f}" if exp_weeks is not None else f"{'N/A':>12}"
            conf_str = "ok" if confident else "low n"

            print(f"  {label:<20} {ew_str}  {p_vals}  {int(sample_n):>7,}  {conf_str}")

            results.append({
                "tenure_bucket":        name,
                "prev_tier":            TIER_LABELS[prev],
                "current_tier":         TIER_LABELS[curr],
                "sample_n":             int(sample_n),
                "confident":            confident,
                "expected_weeks_churn": exp_weeks,
                **{
                    f"churn_prob_{h}w": round(churn_probs[h], 4)
                    if churn_probs[h] is not None else None
                    for h in SIM_HORIZONS
                },
                # primary score = 4-week churn probability
                "churn_score": round(churn_probs[4], 4)
                    if churn_probs[4] is not None else None,
            })

    return pd.DataFrame(results)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    df_raw = load_transitions(INPUT_CSV)

    all_results = []
    for bucket in TENURE_ORDER:
        df_bucket = df_raw[df_raw["tenure_bucket"] == bucket]
        if df_bucket.empty:
            print(f"[{bucket}] No data, skipping.")
            continue
        df = analyze_bucket(bucket, df_bucket)
        all_results.append(df)

    df_all = pd.concat(all_results, ignore_index=True)

    # Summary pivot: churn_score @ 4w (confident pairs only)
    print(f"\n\n{'='*65}")
    print("  SUMMARY -- Churn score @ 4w (confident pairs only)")
    print(f"{'='*65}")
    confident = df_all[df_all["confident"]].copy()
    confident["state"] = (
        "Tier " + confident["prev_tier"] +
        " -> Tier " + confident["current_tier"]
    )
    pivot = confident.pivot(
        index="state", columns="tenure_bucket", values="churn_score"
    ).reindex(columns=TENURE_ORDER)
    print(pivot.to_string(float_format="{:.1%}".format, na_rep="--"))

    df_all.to_csv(OUTPUT_CSV, index=False)
    print(f"\nResults saved to: {OUTPUT_CSV}")
    print(f"  {len(df_all):,} rows ({N}x{N} states x {len(TENURE_ORDER)} buckets)")


if __name__ == "__main__":
    main()