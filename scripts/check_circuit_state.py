#!/usr/bin/env python3
"""
Aegis — Circuit breaker smoke test.

Verifies the circuit breaker trips OPEN when the cloud is unreachable,
then checks the Redis buffer fills. Non-destructive: does not kill any
service — just checks current circuit state via Prometheus.

Usage:
    python scripts/check_circuit_state.py
"""

import json
import urllib.request


def query_prometheus(promql):
    url = f"http://localhost:9090/api/v1/query?query={urllib.request.quote(promql)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            results = data["data"]["result"]
            if not results:
                return None, "no data"
            return float(results[0]["value"][1]), None
    except Exception as e:
        return None, str(e)


STATE_LABELS = {0.0: "CLOSED (healthy)", 1.0: "OPEN (tripped)", 2.0: "HALF_OPEN (probing)"}


def main():
    print("=== Aegis Circuit Breaker State Check ===\n")

    # Circuit breaker state
    state, err = query_prometheus("aegis_circuit_breaker_state")
    if err:
        print(f"[FAIL] Could not read circuit state: {err}")
        return
    label = STATE_LABELS.get(state, f"UNKNOWN ({state})")
    print(f"  Circuit breaker state : {label}")

    # Buffer depth
    buf, err = query_prometheus("redis_buffer_size")
    print(f"  Redis buffer size     : {int(buf) if buf is not None else 'N/A'} readings")

    # Total scored readings
    normal, _ = query_prometheus("aegis_readings_scored_total{criticality_tier='normal'}")
    critical, _ = query_prometheus("aegis_readings_scored_total{criticality_tier='critical'}")
    total = (normal or 0) + (critical or 0)
    pct_critical = (critical / total * 100) if total > 0 else 0
    print(f"  Readings scored       : {int(total)} total "
          f"({int(normal or 0)} normal, {int(critical or 0)} critical = {pct_critical:.1f}%)")

    # Duplicates rejected
    dedup, _ = query_prometheus("aegis_duplicates_rejected_total")
    print(f"  Duplicates rejected   : {int(dedup or 0)}")

    print()
    if state == 0.0 and (buf or 0) == 0:
        print("[OK] System healthy — circuit CLOSED, buffer empty")
    elif state == 1.0:
        print("[WARN] Circuit is OPEN — cloud unreachable, readings buffering in Redis")
    elif state == 2.0:
        print("[INFO] Circuit is HALF_OPEN — probing cloud, drain may be in progress")
    else:
        print(f"[INFO] State = {state}")


if __name__ == "__main__":
    main()
