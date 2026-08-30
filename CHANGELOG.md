# Changelog

All notable changes to Aegis are documented in this file.

## [1.0.0] - 2026-08-31

### Phase 1 - The Pipe
- Spring Boot edge-gateway receives telemetry on port 8080
- Spring Boot cloud-aggregator ingests on port 8081
- Python simulator sends 1 reading/sec with 5% anomaly injection

### Phase 2 - AI Filter
- Isolation Forest trained on Uniform(60,75) normal readings
- ONNX export for cross-language inference (Python to Java)
- CriticalityScorer maps raw anomaly scores to 1-10 scale

### Phase 3 - Resilience Layer
- Resilience4j circuit breaker on cloud forward calls
- Redis buffer with criticality-aware eviction (lowest-score first)
- Separate Spring bean for @CircuitBreaker AOP proxy compatibility

### Phase 4 - Safe Recovery
- DrainService: rate-limited (5/sec) background drain on circuit CLOSED
- SHA-256 deduplication hash computed at edge, enforced at cloud
- LPOP-based atomic batch drain prevents double-processing
- PostgreSQL/H2 persistence with UNIQUE constraint on reading_hash

### Phase 5 - Observability
- Micrometer + Prometheus metrics on both services
- Grafana dashboard with auto-provisioned datasource
- Custom metrics: buffer size, circuit state, scored readings, dedup rejections
- Chaos scripts: kill_cloud, restore_cloud, inject_critical_event

### AI Benchmark
- Offline ONNX benchmark: p50=2.54ms, p95=4.42ms latency
- Classification: 100% recall, 66.7% precision, 2.5% FPR
