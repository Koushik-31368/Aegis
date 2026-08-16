package com.aegis.cloud;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Phase 4: receives telemetry readings from the edge gateway and persists them
 * to TimescaleDB via JPA. Duplicate readings (same readingHash) are silently
 * ignored — the DB's UNIQUE constraint on reading_hash fires a
 * DataIntegrityViolationException which we catch and log, never returning 5xx.
 *
 * The /stats endpoint now queries a live COUNT(*) from the DB instead of the
 * old in-memory AtomicLong (which reset on every restart).
 */
@RestController
public class IngestController {

    private static final Logger log = LoggerFactory.getLogger(IngestController.class);

    private final TelemetryReadingRepository repository;
    private final Counter duplicatesRejectedCounter;

    public IngestController(TelemetryReadingRepository repository,
                            MeterRegistry meterRegistry) {
        this.repository = repository;
        this.duplicatesRejectedCounter = Counter.builder("aegis.duplicates.rejected")
                .description("Readings rejected because reading_hash already exists in DB")
                .register(meterRegistry);
    }

    @PostMapping("/ingest")
    public ResponseEntity<String> ingest(@RequestBody TelemetryReading reading) {
        // Guard: if edge didn't supply a hash (shouldn't happen, but be safe),
        // reject rather than inserting a row with a null unique column.
        if (reading.getReadingHash() == null || reading.getReadingHash().isBlank()) {
            log.warn("Received reading without hash — rejecting: {}", reading);
            return ResponseEntity.badRequest().body("Missing readingHash");
        }

        try {
            TelemetryReading saved = repository.save(reading);
            long total = repository.countAll();
            log.info("[{}] Ingested: sensorId={}, criticality={}, hash={}",
                    total, reading.getSensorId(), reading.getCriticality(),
                    reading.getReadingHash().substring(0, 8) + "...");
            return ResponseEntity.ok("Ingested");

        } catch (DataIntegrityViolationException e) {
            // Unique constraint on reading_hash fired — this is a duplicate.
            // Log and return 200 so the caller doesn't retry unnecessarily.
            log.info("Duplicate reading ignored: {}", reading.getReadingHash());
            duplicatesRejectedCounter.increment();
            return ResponseEntity.ok("Duplicate ignored");
        }
    }

    @GetMapping("/stats")
    public ResponseEntity<String> stats() {
        long count = repository.countAll();
        return ResponseEntity.ok("Total readings stored: " + count);
    }

    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("Cloud aggregator is up");
    }
}
