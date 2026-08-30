#!/usr/bin/env python3
"""
Aegis Phase 1 Simulator.

Sends fake sensor readings to the edge gateway once per second.
Occasionally sends an obvious "anomalous" spike so that in later phases
(once the AI scorer is wired in) you have something to actually detect.

Usage:
    pip install requests
    python simulate.py
"""

import random
import time
import requests

EDGE_GATEWAY_URL = "http://localhost:8080/telemetry"
SENSORS = ["sensor-01", "sensor-02", "sensor-03", "sensor-04", "sensor-05"]
NORMAL_MEAN = 67.5          # midpoint of normal temp range
NORMAL_STD = 4.0            # approximate std for normal readings
NORMAL_TEMP_RANGE = (60.0, 75.0)   # degrees, "normal" operating range
ANOMALY_TEMP_RANGE = (95.0, 120.0)  # degrees, clearly abnormal
ANOMALY_PROB = 0.05         # 5% of readings are anomalies
ANOMALY_PROBABILITY = ANOMALY_PROB  # legacy alias
SENSOR_IDS = SENSORS        # legacy alias


def generate_reading():
    """Generate one sensor reading dict. Always returns a plain dict.
    criticality is always 0 here â€” the edge gateway ONNX model overrides it."""
    sensor_id = random.choice(SENSORS)
    is_anomaly = random.random() < ANOMALY_PROB

    if is_anomaly:
        value = round(random.uniform(*ANOMALY_TEMP_RANGE), 2)
    else:
        value = round(random.uniform(*NORMAL_TEMP_RANGE), 2)

    return {
        "sensorId": sensor_id,
        "timestamp": int(time.time() * 1000),
        "value": value,
        "metricType": "temperature",
        "criticality": 0,   # overridden by edge ONNX scorer
    }


def _is_anomaly_value(value):
    """Helper: true if a value falls in the anomaly range."""
    lo, hi = ANOMALY_TEMP_RANGE
    return lo <= value <= hi


def main():
    print(f"Sending simulated telemetry to {EDGE_GATEWAY_URL}")
    print("Press Ctrl+C to stop.\n")

    while True:
        reading = generate_reading()
        tag = "  <-- ANOMALY" if _is_anomaly_value(reading["value"]) else ""
        try:
            resp = requests.post(EDGE_GATEWAY_URL, json=reading, timeout=5)
            print(f"Sent {reading} -> status {resp.status_code}{tag}")
        except requests.exceptions.RequestException as e:
            print(f"Failed to send reading (is the edge gateway running?): {e}")

        time.sleep(1)



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSimulator stopped.")

