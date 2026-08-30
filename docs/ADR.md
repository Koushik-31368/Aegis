# Aegis — Architecture Decision Records

## ADR-001: Score readings at edge, before circuit breaker

**Status:** Accepted

**Context:** Phase 2 added ONNX-based criticality scoring. The initial implementation wrapped the entire `receiveTelemetry()` body with `@CircuitBreaker`. When the circuit was OPEN, Resilience4j short-circuited before the scoring ran — readings buffered into Redis with `criticality=0`.

**Decision:** Scoring (`CriticalityScorer.scoreCriticality()`) and hash computation (`reading.computeAndSetHash()`) run unconditionally in `TelemetryController`, before any call to `CloudForwarderService`. Only the HTTP forward is circuit-breaker protected.

**Consequences:** Every reading in Redis always carries its real criticality score. The eviction policy (drop lowest-criticality on overflow) works correctly regardless of circuit state.

---

## ADR-002: @CircuitBreaker requires a separate Spring bean

**Status:** Accepted

**Context:** Spring AOP creates a proxy around the target bean. Calls from within the same class bypass the proxy entirely — `@CircuitBreaker` is silently ignored.

**Decision:** Extracted the circuit-breaker-protected cloud forward call into `CloudForwarderService`, a separate `@Service` bean. `TelemetryController` calls it externally, so the AOP proxy intercepts correctly.

**Consequences:** Circuit breaker actually fires on HTTP failures. `bufferOnFailure()` (the fallback) is invoked correctly when the cloud is unreachable.

---

## ADR-003: SHA-256 hash computed at edge, not cloud

**Status:** Accepted

**Context:** Deduplication requires a stable identifier per reading. The hash could be computed at the cloud on arrival, but buffered readings that are replayed after an outage may arrive out of order or twice.

**Decision:** Hash is computed in `TelemetryReading.computeAndSetHash()` at the edge immediately after scoring, before either forwarding or buffering. Buffered readings carry their hash so drain replays use the same hash as any live forward attempt.

**Consequences:** The cloud's `UNIQUE(reading_hash)` constraint correctly deduplicates live + drained readings even when the same reading was forwarded live and buffered (HALF_OPEN probe edge case).

---

## ADR-004: H2 in-memory DB as PostgreSQL stand-in

**Status:** Accepted (temporary)

**Context:** Docker Desktop daemon was unstable on the Windows dev machine. Native PostgreSQL install had TCP binding conflicts on port 5432/5433.

**Decision:** Use H2 with `MODE=PostgreSQL` and `DB_CLOSE_DELAY=-1`. JPA entities, UNIQUE constraints, and the drain/dedup flow are fully verified on H2.

**Consequences (known gap):** TimescaleDB-specific features (hypertables, `time_bucket`, compression policies) are not verified. Resume bullets should say "PostgreSQL" not "TimescaleDB" until Option A is complete.

---

## ADR-005: Rate limiter applied to drain thread only

**Status:** Accepted

**Context:** When the circuit breaker transitions to CLOSED after an outage, potentially hundreds of buffered readings need to be replayed to the cloud. Forwarding them all at once would spike cloud load and potentially re-trip the circuit breaker.

**Decision:** The Resilience4j RateLimiter (`cloudDrain`, 5 req/sec) is applied only to the drain thread in DrainService. Live readings from the simulator continue flowing through CloudForwarderService.forwardToCloud() without rate limiting.

**Consequences:** Live sensor traffic is never delayed by the drain backlog. The cloud receives a steady, manageable trickle of buffered readings alongside normal live traffic. Recovery time is proportional to buffer depth (buffer_size / 5 seconds).

---

## ADR-006: LPOP for drain batches instead of LRANGE+DEL

**Status:** Accepted

**Context:** Phase 4 drain needs to pull readings from Redis in small batches. Two approaches: (a) LRANGE to read + DEL to remove, or (b) LPOP with count to atomically pop entries.

**Decision:** Use LPOP(key, count) in RedisBufferService.drainBatch(). Each call atomically removes and returns up to N entries from the left (oldest) end of the list.

**Consequences:** No risk of double-processing if the drain thread crashes mid-batch — readings are removed as they are popped. Concurrent calls from multiple threads cannot pull the same reading twice. Simpler code than LRANGE+LTRIM.
