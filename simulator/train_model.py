#!/usr/bin/env python3
"""
Aegis Model Training Pipeline.

Trains an IsolationForest anomaly detector on synthetic sensor data,
exports it to ONNX format for use in the edge gateway's CriticalityScorer.

Usage:
    pip install scikit-learn onnxruntime skl2onnx numpy
    python train_model.py

Output:
    model.onnx  — loaded at runtime by edge-gateway/CriticalityScorer.java
"""

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler
import skl2onnx
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
import os

# ─── Configuration ────────────────────────────────────────────────────────────
NORMAL_MEAN = 67.5
NORMAL_STD = 4.0
ANOMALY_MEAN = 107.5
ANOMALY_STD = 6.0
N_NORMAL_SAMPLES = 1000
N_ANOMALY_SAMPLES = 50          # kept small so model learns normal well
RANDOM_STATE = 42
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "model.onnx")

# ─── Generate training data ────────────────────────────────────────────────────
rng = np.random.RandomState(RANDOM_STATE)
normal_samples = rng.normal(NORMAL_MEAN, NORMAL_STD, (N_NORMAL_SAMPLES, 1)).astype(np.float32)
anomaly_samples = rng.normal(ANOMALY_MEAN, ANOMALY_STD, (N_ANOMALY_SAMPLES, 1)).astype(np.float32)
X_train = np.vstack([normal_samples, anomaly_samples])

# ─── Train ─────────────────────────────────────────────────────────────────────
print(f"Training IsolationForest on {len(X_train)} samples ...")
clf = IsolationForest(
    n_estimators=100,
    contamination=N_ANOMALY_SAMPLES / len(X_train),
    random_state=RANDOM_STATE,
)
clf.fit(X_train)

# Quick sanity check
test_normal = np.array([[67.0]], dtype=np.float32)
test_anomaly = np.array([[113.0]], dtype=np.float32)
assert clf.predict(test_normal)[0] == 1,  "Expected normal reading to be classified as inlier"
assert clf.predict(test_anomaly)[0] == -1, "Expected anomaly reading to be classified as outlier"
print("  Sanity check passed: normal=1 (inlier), anomaly=-1 (outlier)")

# ─── Export to ONNX ────────────────────────────────────────────────────────────
initial_type = [("input", FloatTensorType([None, 1]))]
onnx_model = convert_sklearn(clf, initial_types=initial_type)

with open(OUTPUT_PATH, "wb") as f:
    f.write(onnx_model.SerializeToString())

print(f"  Exported to: {OUTPUT_PATH}")
print(f"  File size:   {os.path.getsize(OUTPUT_PATH):,} bytes")
print("Done.")
