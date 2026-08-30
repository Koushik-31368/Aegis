#!/usr/bin/env python3
"""
Aegis â€” Buffer stress test.

Sends N readings rapidly to edge-gateway while cloud-aggregator is running.
Then checks how many landed in Redis vs were forwarded directly.

Useful for verifying buffer behaviour without killing any process.
Run AFTER manually tripping the circuit (kill_cloud.ps1).

Usage:
    python scripts/stress_buffer.py [--count 50]
"""
import json
import time
import argparse
import urllib.request


def post(url, payload):
    """POST a JSON payload and return the HTTP status code, or None on error."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status
    except Exception:
        return None


def get_buffer_size():
    try:
        url = "http://localhost:9090/api/v1/query?query=redis_buffer_size"
        with urllib.request.urlopen(url, timeout=3) as r:
            data = json.loads(r.read())
            results = data["data"]["result"]
            return int(float(results[0]["value"][1])) if results else 0
    except Exception:
        return -1


def main():
    parser = argparse.ArgumentParser(description="Aegis buffer stress test")
    parser.add_argument("--count", type=int, default=20, help="Number of readings to send")
    args = parser.parse_args()

    url = "http://localhost:8080/telemetry"
    buf_before = get_buffer_size()
    print(f"Buffer size before: {buf_before}")
    print(f"Sending {args.count} readings rapidly ...\n")

    ok = fail = 0
    for i in range(args.count):
        payload = {
            "sensorId": f"stress-{i % 3:02d}",
            "timestamp": int(time.time() * 1000) + i,
            "value": round(65.0 + i * 0.1, 2),
            "metricType": "temperature",
            "criticality": 0,
        }
        status = post(url, payload)
        if status == 200:
            ok += 1
        else:
            fail += 1

    time.sleep(2)
    buf_after = get_buffer_size()
    print(f"Sent: {ok} OK, {fail} failed")
    print(f"Buffer size after:  {buf_after}")
    print(f"Buffer delta:       +{buf_after - buf_before}")
    print("\n(If cloud is UP: buffer delta ~ 0, readings forwarded directly)")
    print("(If cloud is DOWN: buffer delta ~ count, readings queued in Redis)")


if __name__ == "__main__":
    import sys
    main()
    sys.exit(0)


