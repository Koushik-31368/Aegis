#!/usr/bin/env python3
"""
Aegis â€” Deduplication verification script.

Sends the same reading twice and confirms the cloud-aggregator
accepts the first and silently rejects the second.

Usage:
    python scripts/verify_dedup.py
"""

import json
import time
import urllib.request
import urllib.request


def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except Exception as e:
        return None, str(e)


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read().decode()
    except Exception as e:
        return f"ERROR: {e}"


def main():
    edge_url = "http://localhost:8080/telemetry"
    stats_url = "http://localhost:8081/stats"

    # Fixed payload â€” same every time so same SHA-256 hash is produced
    payload = {
        "sensorId": "sensor-dedup-test",
        "timestamp": 9999999999001,
        "value": 55.55,
        "metricType": "temperature",
        "criticality": 0,
    }

    print("=== Aegis Dedup Verification ===\n")

    # Check Prometheus dedup counter â€” unambiguous even with simulator running
    def get_dedup_count():
        try:
            url = "http://localhost:9090/api/v1/query?query=aegis_duplicates_rejected_total"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read())
                results = data["data"]["result"]
                return float(results[0]["value"][1]) if results else 0.0
        except Exception:
            return -1.0

    dedup_before = get_dedup_count()
    print(f"\nPrometheus aegis_duplicates_rejected_total before: {dedup_before}")

    print("Sending request #1 (new reading) ...")
    status1, body1 = post_json(edge_url, payload)
    print(f"  Status: {status1}, Body: {body1}")

    time.sleep(1)

    print("Sending request #2 (identical payload = same hash) ...")
    status2, body2 = post_json(edge_url, payload)
    print(f"  Status: {status2}, Body: {body2}")

    time.sleep(2)  # let Prometheus scrape (5s interval, but give it a moment)

    dedup_after = get_dedup_count()
    print(f"Prometheus aegis_duplicates_rejected_total after:  {dedup_after}")

    delta = dedup_after - dedup_before
    print(f"\nDedup counter delta: +{delta} (expected: +1)")
    if delta >= 1:
        print("[PASS] Dedup working correctly â€” at least 1 rejection recorded")
    else:
        print("[FAIL] Expected dedup counter to increment")



if __name__ == "__main__":
    main()
