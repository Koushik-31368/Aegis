package com.aegis.edge;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RateLimiterRegistry;
import io.github.resilience4j.ratelimiter.RequestNotPermitted;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Phase 4: drains Redis-buffered readings back to the cloud when the circuit
 * breaker transitions from OPEN → HALF_OPEN → CLOSED.
 *
 * Key design decisions:
 *
 * 1. TRIGGER: Resilience4j's EventPublisher fires onStateTransition events.
 *    We listen for any transition to CLOSED state. This is cleaner than
 *    polling, and fires exactly once per recovery event.
 *
 * 2. RATE LIMITING: Drain uses the "cloudDrain" RateLimiter (5 req/sec).
 *    Live readings from the simulator continue arriving on their own thread
 *    and are NOT affected by this — they use CloudForwarderService directly
 *    (circuit-breaker protected, not rate-limited). The drain is a background
 *    thread that trickles readings out independently.
 *
 * 3. BATCH PULL: We drain in batches of 10 to avoid holding a huge list in
 *    memory. Each batch is popped from Redis (LPOP x10), forwarded one by
 *    one respecting the rate limiter, then the next batch starts.
 *
 * 4. DEDUPLICATION: The cloud's UNIQUE constraint on reading_hash handles
 *    dedup transparently. If a reading was forwarded live AND buffered (edge
 *    case during the HALF_OPEN probe), the cloud logs "Duplicate ignored" and
 *    returns 200 — the drain proceeds normally.
 *
 * 5. IDEMPOTENCY: AtomicBoolean drainInProgress prevents concurrent drains
 *    if somehow two CLOSED events fire close together.
 */
@Service
public class DrainService {

    private static final Logger log = LoggerFactory.getLogger(DrainService.class);

    private static final int BATCH_SIZE = 10;

    private final RedisBufferService redisBufferService;
    private final CloudForwarderService cloudForwarderService;
    private final CircuitBreakerRegistry circuitBreakerRegistry;
    private final RateLimiterRegistry rateLimiterRegistry;

    private final AtomicBoolean drainInProgress = new AtomicBoolean(false);

    public DrainService(RedisBufferService redisBufferService,
                        CloudForwarderService cloudForwarderService,
                        CircuitBreakerRegistry circuitBreakerRegistry,
                        RateLimiterRegistry rateLimiterRegistry) {
        this.redisBufferService = redisBufferService;
        this.cloudForwarderService = cloudForwarderService;
        this.circuitBreakerRegistry = circuitBreakerRegistry;
        this.rateLimiterRegistry = rateLimiterRegistry;
    }

    /**
     * Registers a state-transition listener on the "cloudForward" circuit breaker.
     * Called automatically by Spring after construction (@PostConstruct).
     *
     * Resilience4j API: CircuitBreaker.EventPublisher.onStateTransition(consumer)
     * fires every time the CB moves between states (CLOSED→OPEN, OPEN→HALF_OPEN,
     * HALF_OPEN→CLOSED, etc.). We only act on transitions TO CLOSED.
     */
    @PostConstruct
    public void registerCircuitBreakerListener() {
        CircuitBreaker cb = circuitBreakerRegistry.circuitBreaker("cloudForward");
        cb.getEventPublisher().onStateTransition(event -> {
            CircuitBreaker.State toState = event.getStateTransition().getToState();
            log.info("Circuit breaker transition: {} → {}",
                    event.getStateTransition().getFromState(), toState);

            if (toState == CircuitBreaker.State.CLOSED) {
                log.info("Circuit CLOSED — scheduling background drain of Redis buffer");
                triggerDrain();
            }
        });
        log.info("DrainService: registered state-transition listener on 'cloudForward' circuit breaker");
    }

    /**
     * Starts the drain on a background CompletableFuture thread.
     * The request thread (live telemetry) is NOT blocked.
     */
    public void triggerDrain() {
        if (!drainInProgress.compareAndSet(false, true)) {
            log.info("Drain already in progress — skipping duplicate trigger");
            return;
        }

        CompletableFuture.runAsync(this::drainAll)
                .whenComplete((v, ex) -> {
                    drainInProgress.set(false);
                    if (ex != null) {
                        log.error("Drain encountered an error — buffer may have remaining items", ex);
                    }
                });
    }

    /**
     * Drains the entire Redis buffer in batches, respecting the "cloudDrain"
     * rate limiter (5 readings/sec). Runs entirely on the CompletableFuture thread.
     */
    private void drainAll() {
        RateLimiter rateLimiter = rateLimiterRegistry.rateLimiter("cloudDrain");
        long totalDrained = 0;

        log.info("Drain started. Buffer size before drain: {}", redisBufferService.getBufferSize());

        while (true) {
            // Pull a batch of up to BATCH_SIZE readings atomically from the front of the list.
            List<TelemetryReading> batch = redisBufferService.drainBatch(BATCH_SIZE);
            if (batch == null || batch.isEmpty()) {
                break; // Buffer exhausted
            }

            for (TelemetryReading reading : batch) {
                try {
                    // Acquire a rate-limiter permit (blocks up to timeoutDuration=2s).
                    // This enforces max 5 drain-forwards/sec, preventing cloud flood.
                    RateLimiter.waitForPermission(rateLimiter);

                    // Forward through the same CloudForwarderService used for live traffic.
                    // If the circuit trips again mid-drain, this will re-buffer the reading.
                    cloudForwarderService.forwardToCloud(reading);
                    totalDrained++;
                    log.debug("Drained reading: sensorId={}, criticality={}, hash={}...",
                            reading.getSensorId(), reading.getCriticality(),
                            reading.getReadingHash() != null ?
                                    reading.getReadingHash().substring(0, 8) : "null");

                } catch (RequestNotPermitted e) {
                    // Rate limiter timed out (2s with no permit available).
                    // Re-buffer this reading and stop — something's wrong.
                    log.warn("Rate limiter timed out during drain — re-buffering reading and stopping");
                    redisBufferService.bufferReading(reading);
                    drainInProgress.set(false);
                    return;
                } catch (Exception e) {
                    log.error("Error forwarding buffered reading during drain — re-buffering: {}", e.getMessage());
                    redisBufferService.bufferReading(reading);
                }
            }
        }

        log.info("Drain complete. {} readings forwarded to cloud. Buffer size after drain: {}",
                totalDrained, redisBufferService.getBufferSize());
    }
}
