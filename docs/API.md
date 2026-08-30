# Aegis API Reference

## Edge Gateway (port 8080)

### POST /telemetry
Receives a single sensor reading, scores it with the ONNX model, and forwards to cloud.

**Request Body:**
```json
{
  "sensorId": "sensor-01",
  "timestamp": 1693000000000,
  "value": 72.5,
  "metricType": "temperature",
  "criticality": 0
}
```

**Response (circuit CLOSED):** `200 Received and forwarded`
**Response (circuit OPEN):** `202 Reading buffered in Redis (cloud unreachable). Buffer size: N`

### GET /health
Returns edge gateway status.

### GET /actuator/prometheus
Prometheus scrape endpoint (Micrometer metrics).

---

## Cloud Aggregator (port 8081)

### POST /ingest
Persists a telemetry reading to the database. Rejects duplicates via SHA-256 hash.

**Response:** `200 Ingested` or `200 Duplicate ignored`

### GET /stats
Returns total readings stored in the database.

### GET /health
Returns cloud aggregator status.

### GET /actuator/prometheus
Prometheus scrape endpoint (Micrometer metrics).

---

## Prometheus (port 9090)

### GET /api/v1/query?query={promql}
Standard Prometheus instant query API.

**Key metrics:**
- `redis_buffer_size` - current buffer depth
- `aegis_readings_scored_total` - tagged by criticality_tier
- `aegis_circuit_breaker_state` - 0=CLOSED, 1=OPEN, 2=HALF_OPEN
- `aegis_duplicates_rejected_total` - dedup rejection count
