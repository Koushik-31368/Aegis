# Aegis Demo Video — Narration Script

**Target length:** ~4-5 minutes  
**Tone:** Technical but direct — no filler, no hype, just what it does and why it matters

---

## [0:00 — 0:30] Opening: What is this?

> "This is Aegis — a distributed IoT telemetry pipeline built around one real problem:
> what happens to sensor data when the cloud goes down?
>
> The short answer most systems give you is: you lose it.
> Aegis's answer is: you don't.
>
> There are three services running here — a Python sensor simulator,
> a Spring Boot edge gateway that scores every reading with an ONNX anomaly model,
> and a cloud aggregator that persists readings to a database.
> Redis sits between them as a criticality-aware buffer,
> and Prometheus plus Grafana give us live visibility into everything."

*[On screen: architecture diagram or just the Grafana dashboard loading]*

---

## [0:30 — 1:00] Normal operation — before anything breaks

> "Here's the system under normal load.
>
> Top left — readings per second, split by normal and critical.
> The edge gateway is scoring every reading with an IsolationForest model exported to ONNX.
> Normal readings come in around 67 degrees. Anything above 95 gets flagged as critical.
>
> Bottom left — Redis buffer size. Right now it's zero, because the circuit breaker is closed
> and every reading is being forwarded directly to the cloud aggregator.
>
> Bottom right — circuit breaker state. Zero means closed, healthy.
>
> This is the baseline."

*[On screen: Grafana dashboard, 01-normal-operation.png stage]*

---

## [1:00 — 2:00] Killing the cloud — outage begins

> "Now I'll kill the cloud aggregator — simulating an unreachable downstream service."

*[Run kill_cloud.ps1]*

> "Watch the circuit breaker. Resilience4j is configured to trip open after
> a failure threshold — you'll see the state panel flip from zero to one.
>
> And the buffer. Every reading that can't reach the cloud now lands in Redis instead.
> The edge gateway is still running, still scoring, still accepting sensor data —
> nothing at the edge has changed from the sensor's perspective.
>
> The buffer is climbing. That's the point — no data loss."

*[On screen: 02-outage-buffering.png — buffer rising, circuit state = 1.0 (OPEN)]*

---

## [2:00 — 2:30] Injecting a critical event during the outage

> "While the cloud is down, I'll inject a deliberately anomalous reading —
> value of 155 degrees, well outside normal operating range."

*[Run inject_critical_event.ps1]*

> "The ONNX scorer at the edge flags this as critical immediately.
> The criticality score gets attached to the reading before it hits the buffer.
>
> This matters because the buffer has an eviction policy:
> if it fills past a thousand entries, it drops the lowest-criticality readings first —
> not the oldest ones. High-criticality readings survive outages.
> The critical counter just ticked up."

*[On screen: 03-critical-event.png — critical counter increment visible]*

---

## [2:30 — 3:30] Restoring the cloud — drain begins

> "Bringing the cloud aggregator back."

*[Run restore_cloud.ps1]*

> "Resilience4j detects the cloud is reachable again and transitions the circuit
> to half-open to probe, then closes it.
>
> The drain service fires exactly once on that closed transition —
> it pulls buffered readings from Redis and forwards them at five readings per second.
> That rate limit is deliberate — a full buffer flooding the cloud at once would just
> cause a different outage. Gradual drain.
>
> Watch the buffer slope down. Not a vertical drop — a ramp.
> That's the rate limiter working."

*[On screen: 04-draining.png — buffer declining steadily, circuit CLOSED again]*

---

## [3:30 — 4:00] Recovery complete

> "Buffer's back to zero. Circuit closed. Normal throughput resumed.
>
> Every reading that came in during the outage is now in the database.
> If anything was forwarded live AND ended up in the buffer due to a half-open probe,
> the deduplication layer handles it — SHA-256 hash on every reading,
> unique constraint in the database, duplicate silently rejected."

*[On screen: 05-recovered.png — buffer=0, circuit=0, readings flowing normally]*

---

## [4:00 — 4:30] Closing

> "So: AI-scored readings at the edge, circuit-breaker-protected forwarding,
> criticality-aware buffering in Redis, rate-limited drain on recovery,
> and idempotent deduplication at the cloud.
>
> The whole stack is instrumented — five custom Micrometer metrics,
> scraped by Prometheus, visualized here in Grafana.
>
> Everything you just saw is live data, not a mock."

*[End on full Grafana dashboard showing recovered state]*

---

## Recording notes

- **Grafana URL:** http://localhost:3001 (NOT 3000 — TradeLearn is on 3000, don't say 3000)
- **Login:** admin / admin
- **Dashboard:** Aegis → Resilience Dashboard
- **Set time window to "Last 10 minutes"** before starting — keeps the chart tight
- **Run check_health.py first** to confirm all services alive before hitting record
- **Reset cloud-aggregator** (restart it) before recording so DB row count is clean
- **Chaos scripts are in:** `g:\aegis-project\chaos-scripts\`
- **Recommend OBS or Windows Game Bar (Win+G)** for screen recording
