package com.aegis.edge;

import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

/**
 * Owns the circuit-breaker-protected cloud forward call.
 *
 * Extracted from TelemetryController specifically to solve the Spring AOP
 * self-invocation problem: @CircuitBreaker works via a CGLIB proxy, but if
 * the annotated method is called from within the same class (i.e. "this.method()"),
 * the call bypasses the proxy entirely and the circuit breaker never fires.
 * Putting the annotated method on a separate bean guarantees every call goes
 * through the proxy.
 *
 * Contract: by the time forwardToCloud() is called, reading.getCriticality()
 * MUST already be set (scored by CriticalityScorer in TelemetryController).
 * The fallback buffers the already-scored reading — criticality is never 0
 * regardless of whether the circuit is CLOSED, OPEN, or HALF_OPEN.
 */
@Service
public class CloudForwarderService {

    private static final Logger log = LoggerFactory.getLogger(CloudForwarderService.class);

    private final WebClient cloudWebClient;
    private final RedisBufferService redisBufferService;

    private static final int BUFFER_MAX_SIZE = 1000;

    public CloudForwarderService(WebClient cloudWebClient,
                                 RedisBufferService redisBufferService) {
        this.cloudWebClient = cloudWebClient;
        this.redisBufferService = redisBufferService;
    }

    /**
     * Forwards a pre-scored reading to the cloud aggregator.
     * Protected by the "cloudForward" circuit breaker defined in application.yml.
     * On failure (or when OPEN), routes to bufferOnFailure.
     */
    @CircuitBreaker(name = "cloudForward", fallbackMethod = "bufferOnFailure")
    public ResponseEntity<String> forwardToCloud(TelemetryReading reading) {
        cloudWebClient.post()
                .uri("/ingest")
                .bodyValue(reading)
                .retrieve()
                .toBodilessEntity()
                .block();
        log.info("Forwarded reading to cloud: sensorId={}, criticality={}",
                reading.getSensorId(), reading.getCriticality());
        return ResponseEntity.ok("Received and forwarded");
    }

    /**
     * Resilience4j fallback — invoked when:
     *   (a) forwardToCloud() throws (circuit CLOSED, failure recorded), or
     *   (b) the circuit is OPEN and the call is short-circuited before the
     *       method body runs.
     *
     * Because scoring happens in TelemetryController BEFORE this bean is
     * called, reading.getCriticality() is always the real ONNX score here —
     * never 0, regardless of circuit state.
     *
     * Signature rule: must exactly match forwardToCloud()'s parameters,
     * plus a trailing Throwable as the last parameter.
     */
    public ResponseEntity<String> bufferOnFailure(TelemetryReading reading, Throwable t) {
        log.warn("Circuit open or forward failed [{}]. Buffering reading: sensorId={}, criticality={}",
                t.getMessage(), reading.getSensorId(), reading.getCriticality());

        redisBufferService.bufferReading(reading);
        redisBufferService.evictIfOverCapacity(BUFFER_MAX_SIZE);

        long bufferSize = redisBufferService.getBufferSize();
        log.info("Redis buffer size after push: {}", bufferSize);

        return ResponseEntity.accepted()
                .body("Reading buffered in Redis (cloud unreachable). Buffer size: " + bufferSize);
    }
}
