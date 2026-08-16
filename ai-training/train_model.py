#!/usr/bin/env python3
"""
Aegis Phase 2 - Train the criticality scorer and export to ONNX.

Trains an Isolation Forest on synthetic normal readings (same distribution
the simulator generates), then exports it to ONNX so it can run inside
the Java edge gateway via ONNX Runtime.

Usage:
    pip install scikit-learn skl2onnx onnx onnxruntime numpy
    python train_model.py

Output:
    model.onnx  (copy this into edge-gateway/src/main/resources/)
"""

import numpy as np
from sklearn.ensemble import IsolationForest
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
import onnxruntime as ort

# --- Step 1: Generate synthetic training data ---
np.random.seed(42)
normal_readings = np.random.uniform(60.0, 75.0, size=(2000, 1)).astype(np.float32)

print("Training Isolation Forest on normal readings...")
model = IsolationForest(
    n_estimators=100,
    contamination=0.05,
    random_state=42,
)
model.fit(normal_readings)

# --- Step 2: Sanity check before exporting ---
test_values = np.array([[65.0], [70.0], [72.0], [95.0], [110.0], [50.0]], dtype=np.float32)
scores = model.decision_function(test_values)
predictions = model.predict(test_values)  # 1 = normal, -1 = anomaly

print("\nSanity check (before ONNX export):")
for val, score, pred in zip(test_values.flatten(), scores, predictions):
    label = "ANOMALY" if pred == -1 else "normal"
    print(f"  value={val:6.1f}  score={score:+.4f}  -> {label}")

# --- Step 3: Export to ONNX ---
print("\nExporting to ONNX...")
initial_type = [("input", FloatTensorType([None, 1]))]
onnx_model = convert_sklearn(
    model,
    initial_types=initial_type,
    target_opset={"": 15, "ai.onnx.ml": 3},
)

with open("model.onnx", "wb") as f:
    f.write(onnx_model.SerializeToString())
print("Saved model.onnx")

# --- Step 4: Verify the ONNX file works independently of sklearn ---
print("\nVerifying ONNX model produces the same results...")
session = ort.InferenceSession("model.onnx")
input_name = session.get_inputs()[0].name
output_names = [o.name for o in session.get_outputs()]
print(f"  Input name: {input_name}")
print(f"  Output names: {output_names}")

onnx_results = session.run(None, {input_name: test_values})
print("\nONNX inference results:")
for i, val in enumerate(test_values.flatten()):
    print(f"  value={val:6.1f}  outputs={[r[i] for r in onnx_results]}")

print("\nDone. Copy model.onnx into edge-gateway/src/main/resources/")
