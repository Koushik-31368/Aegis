# Aegis — Edge Resilience System

A distributed IoT telemetry pipeline built to demonstrate production-grade resilience patterns: AI-based anomaly scoring at the edge, circuit-breaker-triggered buffering, rate-limited recovery drain, and idempotent deduplication at the cloud.

> **Portfolio note:** Database persistence is currently verified against H2 (PostgreSQL-compatible schema via JPA). TimescaleDB-specific features (hypertables, `time_bucket` queries) are scoped for Option A but not yet verified — see [Known Gaps](#known-gaps).

---

## Architecture

```
Simulator ──► Edge Gateway (8080) ──► Cloud Aggregator (8081)
                    │                        │
                    │ [circuit OPEN]          │ H2 / PostgreSQL
                    ▼                        │ (JPA + UNIQUE constraint)
               Redis Buffer                  │
                    │                        │
                    └──── DrainService ──────┘
                          (rate-limited,
                           dedup-safe)
```

### Components

| Service | Port | Role |
|---|---|---|
| `simulator/` | — | Python script generating realistic sensor readings with injected anomalies |
| `edge-gateway/` | 8080 | Scores readings with ONNX model, circuit-breaker-protected forward, Redis buffer on outage |
| `cloud-aggregator/` | 8081 | Ingests readings into DB with SHA-256 dedup, exposes `/stats` and `/actuator/prometheus` |
| Redis | 6379 | Criticality-aware buffer (evicts lowest-criticality on overflow) |
| Prometheus | 9090 | Scrapes both services every 5s |
| Grafana | 3000 | Live dashboard: buffer depth, CB state, readings/sec, dedup count |

---

## Phases Built

### Phase 1 — End-to-End Pipeline
- Python simulator → Edge Gateway (`POST /telemetry`) → Cloud Aggregator (`POST /ingest`)
- Verified: data visible in all three stages simultaneously
- Demonstrated data loss when cloud goes down (motivation for Phase 3)

### Phase 2 — AI Scoring at the Edge
- Trained `IsolationForest` on synthetic sensor data, exported to ONNX
- `CriticalityScorer` loads `model.onnx` at startup, scores every reading **before** the circuit-breaker call
- Criticality score (0–10) attached to every reading, visible in cloud logs
- Key fix: scoring moved out of `@CircuitBreaker` scope so OPEN-state readings still get real scores (not `criticality=0`) before buffering

### Phase 3 — Circuit Breaker + Redis Buffer
- `CloudForwarderService` wraps the HTTP forward with Resilience4j `@CircuitBreaker`
- On failure/OPEN: `bufferOnFailure()` pushes reading to Redis list `telemetry:buffer`
- Buffer is **criticality-aware**: when over 1000 entries, evicts the lowest-criticality reading (not the oldest)
- Key fix: `@CircuitBreaker` requires Spring AOP proxy — moved to a separate `@Service` bean so the annotation is actually honoured

### Phase 4 — Drain + Deduplication
- `DrainService` listens to Resilience4j `EventPublisher.onStateTransition` — fires drain exactly once on CLOSED
- Drain is **rate-limited** at 5 readings/sec via Resilience4j `RateLimiter` so recovery never floods the cloud
- SHA-256 hash of `(sensorId, timestamp, value, metricType)` computed at edge before buffering
- Cloud's `UNIQUE(reading_hash)` constraint catches duplicates — `DataIntegrityViolationException` caught, logged, returns `200 OK`
- Verified: Redis buffer drains from 60 → 0 over ~40s (gradual slope, not a vertical drop)

### Option B — Observability Layer
- `micrometer-registry-prometheus` on both services → `/actuator/prometheus`
- Custom metrics:
  - `redis.buffer.size` — live Gauge, reads Redis `LLEN` at scrape time
  - `aegis.readings.scored{criticality_tier=normal|critical}` — Counter per reading
  - `aegis.circuit.breaker.state` — Gauge: 0=CLOSED, 1=OPEN, 2=HALF_OPEN
  - `aegis.circuit.transitions{to_state}` — Counter per CB transition
  - `aegis.duplicates.rejected` — Counter on cloud dedup catch
- Grafana dashboard with 5 panels, auto-provisioned from `grafana/provisioning/`
- Chaos scripts in `chaos-scripts/` for demo recording

---

## Running Locally

### Prerequisites
- Java 17+, Maven
- Python 3.x + `pip install requests onnxruntime scikit-learn numpy`
- Redis (via `redis-server` or `scoop install redis`)
- Prometheus (via `scoop install prometheus`)
- Grafana (via `scoop install extras/grafana` or manual install)

### Start order

```powershell
# 1. Redis
redis-server --port 6379

# 2. Edge Gateway
cd edge-gateway; mvn spring-boot:run

# 3. Cloud Aggregator
cd cloud-aggregator; mvn spring-boot:run

# 4. Simulator
cd simulator; python simulate.py

# 5. Prometheus
prometheus --config.file=prometheus/prometheus.yml `
           --storage.tsdb.path=prometheus/data `
           --web.listen-address=0.0.0.0:9090 `
           --web.enable-lifecycle

# 6. Grafana (start from grafana/bin/, using custom.ini)
grafana-server --config=grafana-custom.ini
```

### Verify it's working
```
GET http://localhost:8080/actuator/health    → {"status":"UP"}
GET http://localhost:8081/actuator/health    → {"status":"UP"}
GET http://localhost:8081/stats             → Total readings stored: N
GET http://localhost:9090/-/ready           → 200 OK
GET http://localhost:3000                   → Grafana login (admin/admin)
```

---

## Demo Chaos Scripts

```powershell
# Kill the cloud (circuit trips, buffer fills — watch Grafana)
.\chaos-scripts\kill_cloud.ps1

# Inject a critical event while cloud is down
.\chaos-scripts\inject_critical_event.ps1

# Restore cloud (drain starts, buffer slopes to 0 — watch Grafana)
.\chaos-scripts\restore_cloud.ps1
```

---

## Key Technical Decisions

| Decision | Why |
|---|---|
| Score **before** circuit breaker | OPEN-state readings would get `criticality=0` if scoring were inside the CB-protected method, breaking eviction logic |
| `@CircuitBreaker` on a **separate bean** | Spring AOP only intercepts calls through the proxy — self-invocation bypasses it silently |
| SHA-256 hash at **edge**, not cloud | Hash must be computed before buffering; buffered readings carry their hash so drain replays are dedup-safe |
| `LPOP` for drain batch | Atomic — no risk of double-processing if drain thread is interrupted |
| `RateLimiter` on drain only | Live traffic bypasses the rate limiter; only the drain thread is throttled, so active sensors are never blocked during recovery |

---

## Known Gaps

| Gap | Status |
|---|---|
| TimescaleDB hypertables + `time_bucket` queries | Not yet verified — H2 with `MODE=PostgreSQL` used for dedup/JPA testing |
| Docker Desktop (Windows) daemon instability | Prometheus + Grafana run natively via Scoop as workaround |
| Grafana screenshots / demo video | Option B Step 6 — in progress |

---

## Metrics Reference

All metrics are labelled with `application=edge-gateway` or `application=cloud-aggregator`.

| Metric | Type | Description |
|---|---|---|
| `redis_buffer_size` | Gauge | Live reading count in Redis list |
| `aegis_readings_scored_total` | Counter | Tagged `criticality_tier=normal\|critical` |
| `aegis_circuit_breaker_state` | Gauge | 0=CLOSED, 1=OPEN, 2=HALF_OPEN |
| `aegis_circuit_transitions_total` | Counter | Tagged `to_state=CLOSED\|OPEN\|HALF_OPEN` |
| `aegis_duplicates_rejected_total` | Counter | Cloud-side dedup rejections |

---

## Project Structure

```
aegis-project/
├── simulator/               # Python sensor simulator
├── edge-gateway/            # Spring Boot 3, port 8080
│   ├── src/main/java/com/aegis/edge/
│   │   ├── TelemetryController.java    # Scores + routes readings
│   │   ├── CriticalityScorer.java      # ONNX runtime inference
│   │   ├── CloudForwarderService.java  # @CircuitBreaker protected forward
│   │   ├── RedisBufferService.java     # Criticality-aware Redis buffer
│   │   └── DrainService.java           # Rate-limited drain on CB recovery
│   └── src/main/resources/
│       ├── application.yml
│       └── model.onnx                  # Exported IsolationForest model
├── cloud-aggregator/        # Spring Boot 3, port 8081
│   └── src/main/java/com/aegis/cloud/
│       ├── IngestController.java       # /ingest + /stats + /health
│       └── TelemetryReadingRepository.java
├── prometheus/
│   └── prometheus.yml       # Scrape config (localhost for native, host.docker.internal for Docker)
├── grafana/
│   └── provisioning/        # Auto-provisioned datasource + dashboard
│       ├── datasources/prometheus.yml
│       └── dashboards/aegis-dashboard.json
├── chaos-scripts/           # PowerShell demo scripts
│   ├── kill_cloud.ps1
│   ├── restore_cloud.ps1
│   └── inject_critical_event.ps1
└── docker-compose.yml       # Redis + TimescaleDB + Prometheus + Grafana
```
