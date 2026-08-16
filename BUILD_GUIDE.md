# Aegis — Full Build Guide

This is the complete, phased build plan. Each phase ends with something that actually runs.
Do not start a phase until the previous one works end-to-end. Skipping ahead is how these projects die half-finished.

---

## Phase 0 — Environment Setup (Day 1)

**Install on your machine:**
- Java 17 (JDK) — `java -version` to confirm
- Maven — `mvn -version`
- Python 3.10+ with pip
- Docker + Docker Compose
- An IDE (IntelliJ Community is free and fine)

**Verify Docker works:**
```bash
docker run hello-world
```

If that fails, fix Docker before doing anything else — everything downstream depends on it.

**Checkpoint:** Java, Maven, Python, and Docker all confirmed working.

---

## Phase 1 — The Pipe (MVP core, Week 1)

**Goal:** One Python simulator sends fake sensor readings to a Spring Boot "edge gateway," which forwards them to a Spring Boot "cloud aggregator," which logs/stores them. No AI, no resilience yet — just prove the plumbing works.

**Steps:**
1. Build `edge-gateway`: a Spring Boot app with one REST endpoint `POST /telemetry` that receives a JSON reading and immediately forwards it via REST to the cloud aggregator's endpoint.
2. Build `cloud-aggregator`: a Spring Boot app with one REST endpoint `POST /ingest` that receives the forwarded reading and logs it (println/logger is fine for now).
3. Build `simulator/simulate.py`: a Python script that generates fake readings (e.g., `temperature`, `vibration`, `sensor_id`, `timestamp`) and POSTs them to the edge gateway every second.
4. Run all three locally (edge gateway on port 8080, cloud aggregator on port 8081, simulator hitting 8080) and confirm data flows end-to-end — you should see logs appear in the cloud aggregator's console as the simulator runs.

**Checkpoint:** Data visibly flows from simulator → edge → cloud, confirmed in logs. **Starter code for this phase is included below in this package — see `edge-gateway/` and `cloud-aggregator/`.**

---

## Phase 2 — The AI Filter (Week 2)

**Goal:** The edge gateway scores each reading for "criticality" using a trained model, instead of forwarding everything blindly.

**Steps:**
1. In Python, generate a synthetic dataset of "normal" and "anomalous" readings (you control the generator, so you know the ground truth).
2. Train an Isolation Forest (`sklearn.ensemble.IsolationForest`) on the normal data.
3. Export the trained model to ONNX using `skl2onnx`.
4. In the edge gateway (Java), add the ONNX Runtime dependency (`com.microsoft.onnxruntime:onnxruntime`).
5. Load the `.onnx` file at startup, and for every incoming reading, run inference to get a criticality score before deciding whether to batch it or send it immediately.
6. Log the score alongside each reading so you can see it working.

**Common failure point:** tensor shape mismatches between what Python exported and what Java sends in. Test with a single hardcoded input first before wiring it into the live stream.

**Checkpoint:** Every reading gets a criticality score in the logs, and readings above a threshold are visibly treated differently (e.g., tagged "CRITICAL" in logs).

---

## Phase 3 — The Resilience Layer (Week 3)

**Goal:** If the cloud aggregator becomes unreachable, the edge gateway buffers data locally instead of losing it.

**Steps:**
1. Add Redis to your `docker-compose.yml` and connect to it from the edge gateway (Spring Data Redis).
2. Add Resilience4j to the edge gateway. Wrap the "send to cloud" call in a `@CircuitBreaker`.
3. Configure the circuit breaker: after N consecutive failures, it opens.
4. When the breaker is open, instead of attempting the cloud call, write the reading to a Redis list/stream.
5. Add a simple eviction rule: if the Redis buffer exceeds a size threshold, delete the oldest *low-criticality* entries first (use the score from Phase 2), keeping high-criticality entries.
6. Test manually: stop the cloud-aggregator process while the simulator is running, confirm data starts appearing in Redis instead of erroring out, then restart the cloud aggregator.

**Checkpoint:** Killing the cloud aggregator process causes the edge gateway to buffer to Redis without crashing or losing data, visible via `redis-cli LLEN` or similar.

---

## Phase 4 — Safe Recovery (Week 4)

**Goal:** When the connection comes back, buffered data drains back smoothly, without flooding the cloud, and without duplicates.

**Steps:**
1. Implement a token-bucket rate limiter (Resilience4j has a `RateLimiter` module — use it) around the drain process.
2. On reconnect (circuit breaker moves to half-open / closed), start a background process that reads from Redis and sends to the cloud at the limited rate, while still handling new live data.
3. Add a deterministic hash (e.g., SHA-256 of `sensor_id + timestamp + value`) to every reading before it's sent.
4. On the cloud side, use this hash as a unique constraint in your database table so duplicate sends are silently rejected.
5. Swap your cloud-side storage from console logging to a real database — Postgres with the TimescaleDB extension (via Docker image `timescale/timescaledb`).

**Checkpoint:** Manually stop the cloud aggregator, let data buffer for a minute, restart it, and confirm: (a) buffered data arrives gradually, not all at once, and (b) no duplicate rows appear in the database even if you simulate a retry.

---

## Phase 5 — Observability & Demo Polish (Week 5)

**Goal:** A dashboard you can actually show in your demo video.

**Steps:**
1. Add Micrometer + Prometheus dependencies to both Spring Boot apps; expose `/actuator/prometheus`.
2. Add Prometheus and Grafana containers to `docker-compose.yml`, point Prometheus at both apps.
3. Build a Grafana dashboard showing: live throughput, current Redis buffer size, count of critical vs. normal readings, and circuit breaker state.
4. Add Toxiproxy to `docker-compose.yml`, and route the edge→cloud traffic through it, so you can inject latency/failures via its API instead of manually killing processes.
5. Write your chaos scripts (`chaos-scripts/`): `kill_connection.sh`, `restore_connection.sh`, `inject_critical_event.sh` — simple curl/toxiproxy-cli commands.

**Checkpoint:** You can run one script to break the connection and watch the dashboard react live, then run another to restore it and watch recovery — this is your demo.

---

## Phase 6 — Stretch: Peer Failover (Optional, only if Phases 1–5 are solid)

**Goal:** Run 2–3 edge gateways; if one goes silent, a neighbor takes over its sensors.

**Steps:**
1. Run multiple instances of the edge gateway (different ports/container names), each assigned a subset of simulated sensors.
2. Each instance periodically sends a lightweight heartbeat (simple HTTP ping) to its peers.
3. If a peer misses N heartbeats, the next healthy node (by a simple deterministic rule, e.g., lowest node ID among survivors) takes over its sensor assignments.
4. Update the simulator to redirect traffic to whichever node currently owns a given sensor.

**Do not attempt this until Phases 1–5 work reliably.** This is the highest-risk, highest-complexity part and is explicitly a bonus, not a requirement.

---

## Recording the Demo

Once Phase 5 is done (Phase 6 optional), follow the demo script:
1. Show normal flow on the dashboard
2. Run `kill_connection.sh` — narrate what's happening as logs show the circuit breaker tripping
3. Run `inject_critical_event.sh` — show it protected from eviction
4. Run `restore_connection.sh` — show the controlled catch-up on the dashboard
5. (If Phase 6 built) kill one gateway container, show failover

Keep it unpolished and real — a slightly rough screen recording where everything visibly works is more convincing than an over-edited video.
