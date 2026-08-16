package com.aegis.edge;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Receives raw telemetry from the simulator, scores it with the ONNX model,
 * then delegates to CloudForwarderService for the circuit-breaker-protected
 * forward to the cloud aggregator.
 *
 * Scoring happens HERE, unconditionally, BEFORE the circuit-breaker call.
 * This fixes the criticality=0 bug from Phase 3: previously @CircuitBreaker
 * wrapped the whole receiveTelemetry() body, so when the circuit was OPEN
 * Resilience4j short-circuited before scoring ran, and readings landed in
 * Redis with criticality=0.
 *
 * Now the flow is:
 *   1. Score the reading (always runs, no circuit breaker involved)
 *   2. Log at INFO or WARN depending on criticality (always runs)
 *   3. Call cloudForwarderService.forwardToCloud(reading) — this is the ONLY
 *      circuit-breaker-protected step. If the circuit is OPEN or the call
 *      fails, the fallback in CloudForwarderService buffers the already-scored
 *      reading into Redis.
 */
@RestController
public class TelemetryController {

    private static final Logger log = LoggerFactory.getLogger(TelemetryController.class);

    private final CriticalityScorer criticalityScorer;
    private final CloudForwarderService cloudForwarderService;

    // Readings scoring at or above this are treated as critical.
    private static final int CRITICAL_THRESHOLD = 7;

    public TelemetryController(CriticalityScorer criticalityScorer,
                               CloudForwarderService cloudForwarderService) {
        this.criticalityScorer = criticalityScorer;
        this.cloudForwarderService = cloudForwarderService;
    }

    @PostMapping("/telemetry")
    public ResponseEntity<String> receiveTelemetry(@RequestBody TelemetryReading reading) {
        // STEP 1: Score unconditionally — this runs regardless of circuit state.
        // By the time we hand off to CloudForwarderService, reading.getCriticality()
        // is always a real ONNX score, never the default 0.
        int criticality = criticalityScorer.scoreCriticality(reading.getValue());
        reading.setCriticality(criticality);

        // STEP 1b: Compute deterministic hash for deduplication at the cloud.
        // Must happen BEFORE buffering — buffered readings carry their hash so
        // when they're drained and replayed, the cloud's unique constraint rejects
        // any accidental duplicate rather than storing it twice.
        reading.computeAndSetHash();

        // STEP 2: Log at appropriate level.
        if (criticality >= CRITICAL_THRESHOLD) {
            log.warn("CRITICAL reading at edge (score={}): {}", criticality, reading);
        } else {
            log.info("Received reading at edge (score={}): {}", criticality, reading);
        }

        // STEP 3: Forward (circuit-breaker-protected). If circuit is OPEN or the
        // call fails, CloudForwarderService.bufferOnFailure() handles buffering.
        // The reading already carries its criticality score at this point.
        return cloudForwarderService.forwardToCloud(reading);
    }

    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("Edge gateway is up");
    }
}
