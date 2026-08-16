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
SENSOR_IDS = ["sensor-01", "sensor-02", "sensor-03"]
NORMAL_TEMP_RANGE = (60.0, 75.0)   # degrees, "normal" operating range
ANOMALY_TEMP_RANGE = (95.0, 120.0)  # degrees, clearly abnormal
ANOMALY_PROBABILITY = 0.05  # 5% of readings are anomalies


def generate_reading():
    sensor_id = random.choice(SENSOR_IDS)
    is_anomaly = random.random() < ANOMALY_PROBABILITY

    if is_anomaly:
        value = round(random.uniform(*ANOMALY_TEMP_RANGE), 2)
    else:
        value = round(random.uniform(*NORMAL_TEMP_RANGE), 2)

    return {
        "sensorId": sensor_id,
        "timestamp": int(time.time() * 1000),
        "value": value,
        "metricType": "temperature",
    }, is_anomaly


def main():
    print(f"Sending simulated telemetry to {EDGE_GATEWAY_URL}")
    print("Press Ctrl+C to stop.\n")

    while True:
        reading, is_anomaly = generate_reading()
        tag = "  <-- ANOMALY" if is_anomaly else ""
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
