#!/usr/bin/env python3
"""
Aegis — Manual verification script.

Queries both services and Prometheus to confirm the full pipeline
is healthy without needing to read logs manually.

Usage:
    python check_health.py
"""

import sys
import json
import urllib.request
import urllib.error


def get(url, label):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            body = r.read().decode()
            return r.status, body
    except urllib.error.URLError as e:
        return None, str(e)


def check_json(url, key, label):
    status, body = get(url, label)
    if status is None:
        print(f"  [FAIL] {label}: UNREACHABLE — {body}")
        return False
    try:
        data = json.loads(body)
        val = data.get(key, "KEY_NOT_FOUND")
        ok = val == "UP"
        icon = "[OK]" if ok else "[FAIL]"
        print(f"  {icon} {label}: {key}={val}")
        return ok
    except json.JSONDecodeError:
        print(f"  [FAIL] {label}: bad JSON — {body[:60]}")
        return False


def check_plain(url, label, expect_contains):
    status, body = get(url, label)
    if status is None:
        print(f"  [FAIL] {label}: UNREACHABLE — {body}")
        return False
    ok = expect_contains in body
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {label}: {body.strip()[:80]}")
    return ok


def check_prometheus(metric_name, label):
    url = f"http://localhost:9090/api/v1/query?query={metric_name}"
    status, body = get(url, label)
    if status is None:
        print(f"  [FAIL] {label}: Prometheus UNREACHABLE")
        return False
    data = json.loads(body)
    results = data.get("data", {}).get("result", [])
    if not results:
        print(f"  [FAIL] {label}: metric not found in Prometheus")
        return False
    val = results[0]["value"][1]
    print(f"  [OK] {label}: {metric_name} = {val}")
    return True


def main():
    print("\n=== Aegis Health Check ===\n")
    all_ok = True

    print("[ Spring Boot Services ]")
    all_ok &= check_json("http://localhost:8080/actuator/health", "status", "edge-gateway (8080)")
    all_ok &= check_json("http://localhost:8081/actuator/health", "status", "cloud-aggregator (8081)")
    all_ok &= check_plain("http://localhost:8081/stats", "cloud stats", "Total readings stored")

    print("\n[ Prometheus ]")
    all_ok &= check_plain("http://localhost:9090/-/ready", "prometheus ready", "")
    all_ok &= check_prometheus("redis_buffer_size", "redis buffer metric")
    all_ok &= check_prometheus("aegis_readings_scored_total", "readings scored metric")
    all_ok &= check_prometheus("aegis_circuit_breaker_state", "circuit breaker metric")
    all_ok &= check_prometheus("aegis_duplicates_rejected_total", "dedup metric")

    print("\n[ Redis ]")
    import subprocess
    r = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True, timeout=3)
    ok = r.stdout.strip() == "PONG"
    print(f"  {'[OK]' if ok else '[FAIL]'} redis-cli ping: {r.stdout.strip() or r.stderr.strip()}")
    all_ok &= ok

    print(f"\n{'[ALL PASS] All checks passed' if all_ok else '[FAIL] Some checks failed'}\n")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
