#!/usr/bin/env python3
"""
Aegis ONNX Anomaly Scorer — Standalone Benchmark
=================================================

Measures two things:

  1. INFERENCE LATENCY — pure session.run() wall-clock time (no HTTP, no Redis,
     no Spring overhead) using time.perf_counter_ns() per call. Reports p50/p95/p99.

  2. CLASSIFICATION QUALITY — precision, recall, false-positive rate against a
     labelled synthetic dataset whose distributions exactly match simulate.py.
     Ground truth is value >= 95 (ANOMALY_TEMP_RANGE lo), which is
     non-overlapping with the normal range (60-75), so labels are unambiguous.

The Java scoring logic is replicated exactly:
  - ONNX output[1][0][0] is the raw Isolation Forest score (float)
  - mapToCriticality() clamps to [SCORE_MOST_CRITICAL, SCORE_MOST_NORMAL] then
    linearly maps to int [1, 10]  (10 = most anomalous)
  - CRITICAL_THRESHOLD = 7 (same as TelemetryController.java) separates normal
    from anomalous predictions

Usage:
    pip install onnxruntime numpy
    python ai-training/benchmark.py

Output:
    - Console summary table
    - ai-training/benchmark_results.csv  (one row per reading, for spot-checking)

No server, no database, no Spring context required.
"""

import csv
import os
import time
import numpy as np
import onnxruntime as ort

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Primary: the model baked into the edge gateway jar (source of truth)
MODEL_PATH = os.path.join(
    SCRIPT_DIR, "..", "edge-gateway", "src", "main", "resources", "model.onnx"
)
# Fallback: local copy produced when someone ran ai-training/train_model.py
FALLBACK_MODEL_PATH = os.path.join(SCRIPT_DIR, "model.onnx")

CSV_PATH = os.path.join(SCRIPT_DIR, "benchmark_results.csv")

# ---------------------------------------------------------------------------
# Constants — mirrored from Java source (do NOT change independently)
# ---------------------------------------------------------------------------
# From CriticalityScorer.java
SCORE_MOST_NORMAL   =  0.12   # rawScore for a clearly-normal reading
SCORE_MOST_CRITICAL = -0.15   # rawScore for a clearly-anomalous reading
# From TelemetryController.java
CRITICAL_THRESHOLD  =  7      # criticality >= 7  ->  "critical" / anomaly prediction

# ---------------------------------------------------------------------------
# Data generation — mirrors simulate.py exactly
# ---------------------------------------------------------------------------
NORMAL_TEMP_RANGE  = (60.0,  75.0)   # NORMAL_TEMP_RANGE  in simulate.py
ANOMALY_TEMP_RANGE = (95.0, 120.0)   # ANOMALY_TEMP_RANGE in simulate.py
N_NORMAL           = 1000
N_ANOMALY          =   50            # ~5% rate, matching ANOMALY_PROB = 0.05
RANDOM_SEED        = 42


def generate_dataset(n_normal: int, n_anomaly: int, seed: int) -> list:
    """
    Build an interleaved labelled dataset using the same distributions as
    simulate.py.  Each entry is a dict: {value, ground_truth_anomaly}.

    Anomalies are shuffled into the stream at random positions (not batched at
    the end) — this mirrors realistic edge-gateway traffic patterns.
    """
    rng = np.random.default_rng(seed)

    normal_values  = rng.uniform(*NORMAL_TEMP_RANGE,  n_normal ).tolist()
    anomaly_values = rng.uniform(*ANOMALY_TEMP_RANGE, n_anomaly).tolist()

    dataset = (
        [{"value": round(v, 2), "ground_truth_anomaly": False} for v in normal_values]
        + [{"value": round(v, 2), "ground_truth_anomaly": True}  for v in anomaly_values]
    )

    # Shuffle to interleave, not batch
    indices = rng.permutation(len(dataset)).tolist()
    return [dataset[i] for i in indices]


# ---------------------------------------------------------------------------
# Java scoring logic — exact Python port
# ---------------------------------------------------------------------------

def map_to_criticality(raw_score: float) -> int:
    """
    Exact Python port of CriticalityScorer.mapToCriticality().

    Step 1: clamp raw_score to [SCORE_MOST_CRITICAL, SCORE_MOST_NORMAL]
    Step 2: linearly normalise that range to [0.0, 1.0]
    Step 3: invert so that 0.0 (most normal) -> 10 and 1.0 (most critical) -> 1
    Step 4: round to nearest int, clamp to [1, 10]
    """
    clamped    = max(SCORE_MOST_CRITICAL, min(SCORE_MOST_NORMAL, raw_score))
    normalized = (clamped - SCORE_MOST_CRITICAL) / (SCORE_MOST_NORMAL - SCORE_MOST_CRITICAL)
    criticality = round(10 - (normalized * 9))   # 1 = most normal, 10 = most critical
    return max(1, min(10, criticality))


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(session: ort.InferenceSession, dataset: list) -> list:
    """
    For each reading: time session.run(), derive criticality, record everything.
    Returns list of result dicts, one per reading.
    """
    input_name = session.get_inputs()[0].name
    results = []

    for entry in dataset:
        value = entry["value"]
        inp   = np.array([[value]], dtype=np.float32)   # shape [1, 1] — same as Java

        t0 = time.perf_counter_ns()
        outputs = session.run(None, {input_name: inp})
        t1 = time.perf_counter_ns()

        latency_ns = t1 - t0

        # outputs[0]: label array (int64)  — 1 = inlier/normal, -1 = outlier/anomaly
        # outputs[1]: scores array (float32) — continuous Isolation Forest score
        #   Matches Java: float[][] scoresOutput = (float[][]) result.get(1).getValue()
        #                 float rawScore = scoresOutput[0][0]
        raw_score   = float(outputs[1][0][0])
        criticality = map_to_criticality(raw_score)

        results.append({
            "value":                value,
            "ground_truth_anomaly": entry["ground_truth_anomaly"],
            "raw_score":            raw_score,
            "criticality_1_to_10":  criticality,
            "predicted_anomaly":    criticality >= CRITICAL_THRESHOLD,
            "latency_ns":           latency_ns,
            "latency_ms":           latency_ns / 1_000_000,
        })

    return results


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_latency_percentiles(results: list) -> dict:
    latencies_ms = sorted(r["latency_ms"] for r in results)
    n = len(latencies_ms)

    def percentile(p):
        # Nearest-rank method
        idx = int(np.ceil(p / 100.0 * n)) - 1
        return latencies_ms[max(0, min(idx, n - 1))]

    return {
        "n":    n,
        "min":  latencies_ms[0],
        "mean": sum(latencies_ms) / n,
        "p50":  percentile(50),
        "p95":  percentile(95),
        "p99":  percentile(99),
        "max":  latencies_ms[-1],
    }


def compute_confusion_matrix(results: list) -> dict:
    tp = sum(1 for r in results if     r["ground_truth_anomaly"] and     r["predicted_anomaly"])
    fp = sum(1 for r in results if not r["ground_truth_anomaly"] and     r["predicted_anomaly"])
    tn = sum(1 for r in results if not r["ground_truth_anomaly"] and not r["predicted_anomaly"])
    fn = sum(1 for r in results if     r["ground_truth_anomaly"] and not r["predicted_anomaly"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    recall    = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    fpr       = fp / (fp + tn) if (fp + tn) > 0 else float("nan")
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else float("nan"))

    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision,
        "recall":    recall,
        "fpr":       fpr,
        "f1":        f1,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_summary(latency: dict, cm: dict, model_path: str) -> None:
    SEP = "=" * 55
    print()
    print(SEP)
    print("  AEGIS ONNX ANOMALY SCORER — BENCHMARK RESULTS")
    print(SEP)
    print(f"  Model    : {os.path.relpath(model_path)}")
    print(f"  Readings : {latency['n']}  "
          f"({N_NORMAL} normal + {N_ANOMALY} anomaly, interleaved)")
    print(f"  Threshold: criticality >= {CRITICAL_THRESHOLD}  ->  'anomaly'")
    print()
    print("  -- Inference Latency (session.run only) ---------")
    print(f"     Min    {latency['min']:>8.4f} ms")
    print(f"     Mean   {latency['mean']:>8.4f} ms")
    print(f"     p50    {latency['p50']:>8.4f} ms")
    print(f"     p95    {latency['p95']:>8.4f} ms")
    print(f"     p99    {latency['p99']:>8.4f} ms")
    print(f"     Max    {latency['max']:>8.4f} ms")
    print()
    print("  -- Classification Quality -----------------------")
    print(f"     TP={cm['tp']}  FP={cm['fp']}  TN={cm['tn']}  FN={cm['fn']}")
    print(f"     Precision      {cm['precision']:>7.1%}")
    print(f"     Recall         {cm['recall']:>7.1%}")
    print(f"     False-Pos Rate {cm['fpr']:>7.1%}")
    print(f"     F1             {cm['f1']:>7.3f}")
    print(SEP)
    print()


def print_spot_checks(results: list) -> None:
    """
    Print rows for manual gut-check:
      - 3 lowest values  (should all be normal)
      - 3 highest values (should all be anomaly)
      - 2 values closest to the decision boundary (most interesting edge cases)

    Decision boundary in raw_score space: the normalized value that maps to
    criticality == 6.5 is normalized = (10 - 6.5) / 9 = 0.389, which gives
    raw_score = SCORE_MOST_CRITICAL + 0.389 * (SCORE_MOST_NORMAL - SCORE_MOST_CRITICAL).
    """
    sorted_asc  = sorted(results, key=lambda r: r["value"])
    low3  = sorted_asc[:3]
    high3 = sorted_asc[-3:]

    boundary_raw = SCORE_MOST_CRITICAL + 0.389 * (SCORE_MOST_NORMAL - SCORE_MOST_CRITICAL)
    borderline   = sorted(results, key=lambda r: abs(r["raw_score"] - boundary_raw))[:2]

    rows = low3 + high3 + borderline

    print("  -- Spot Checks (gut-check individual predictions) ---")
    print(f"  {'value':>7}  {'raw_score':>10}  {'crit':>4}  {'predicted':>9}  "
          f"{'truth':>9}  {'ok?':>6}")
    print("  " + "-" * 60)
    for r in rows:
        pred  = "ANOMALY" if r["predicted_anomaly"]    else "normal"
        truth = "ANOMALY" if r["ground_truth_anomaly"] else "normal"
        ok    = "OK" if pred == truth else "WRONG"
        print(f"  {r['value']:>7.2f}  {r['raw_score']:>+10.5f}  "
              f"{r['criticality_1_to_10']:>4}  {pred:>9}  {truth:>9}  {ok:>6}")
    print()


def save_csv(results: list, path: str) -> None:
    fields = [
        "value", "ground_truth_anomaly", "raw_score",
        "criticality_1_to_10", "predicted_anomaly",
        "latency_ns", "latency_ms",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    print(f"  CSV saved -> {os.path.relpath(path)}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Resolve model path — prefer edge-gateway copy (source of truth for production)
    if os.path.exists(MODEL_PATH):
        model_path = os.path.abspath(MODEL_PATH)
    elif os.path.exists(FALLBACK_MODEL_PATH):
        model_path = os.path.abspath(FALLBACK_MODEL_PATH)
        print(f"[info] Edge-gateway model not found; using fallback: {FALLBACK_MODEL_PATH}")
    else:
        raise FileNotFoundError(
            "model.onnx not found at either expected location:\n"
            f"  {MODEL_PATH}\n"
            f"  {FALLBACK_MODEL_PATH}\n"
            "Run ai-training/train_model.py first, or check your paths."
        )

    print(f"\nLoading ONNX model: {os.path.relpath(model_path)}")
    session = ort.InferenceSession(model_path)
    print(f"  Inputs : {[i.name for i in session.get_inputs()]}")
    print(f"  Outputs: {[o.name for o in session.get_outputs()]}")

    print(f"\nGenerating {N_NORMAL + N_ANOMALY} interleaved test readings "
          f"(seed={RANDOM_SEED})...")
    dataset = generate_dataset(N_NORMAL, N_ANOMALY, RANDOM_SEED)

    # Warm up: 10 unclocked runs so ORT's JIT / thread-pool is stable before timing
    print("Warming up ORT session (10 unclocked runs)...")
    warmup_inp = np.array([[67.5]], dtype=np.float32)
    inp_name   = session.get_inputs()[0].name
    for _ in range(10):
        session.run(None, {inp_name: warmup_inp})

    print(f"Running {N_NORMAL + N_ANOMALY} timed inferences...")
    results = run_benchmark(session, dataset)

    latency = compute_latency_percentiles(results)
    cm      = compute_confusion_matrix(results)

    print_summary(latency, cm, model_path)
    print_spot_checks(results)
    save_csv(results, CSV_PATH)


if __name__ == "__main__":
    main()
