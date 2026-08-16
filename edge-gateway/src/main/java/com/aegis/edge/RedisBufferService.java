package com.aegis.edge;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

/**
 * Buffers TelemetryReadings into a Redis list when the cloud aggregator is
 * unreachable. The buffer is criticality-aware: when over capacity it evicts
 * the LOWEST-criticality reading, not the oldest — so high-priority anomaly
 * readings survive cloud outages even under sustained load.
 *
 * Key: "telemetry:buffer"  (Redis list, RPUSH / LRANGE / LREM)
 *
 * Phase 4 will call drainBuffer() to replay buffered readings once the cloud
 * comes back up. This class only handles storage — no drain logic here.
 */
@Service
public class RedisBufferService {

    private static final Logger log = LoggerFactory.getLogger(RedisBufferService.class);
    private static final String BUFFER_KEY = "telemetry:buffer";

    private final RedisTemplate<String, String> redisTemplate;
    private final ObjectMapper objectMapper;

    public RedisBufferService(RedisTemplate<String, String> redisTemplate,
                              ObjectMapper objectMapper,
                              MeterRegistry meterRegistry) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        // Gauge: tracks live buffer depth — Prometheus scrapes this directly.
        // Uses a supplier so the value is read at scrape time, not at registration.
        Gauge.builder("redis.buffer.size", this, RedisBufferService::getBufferSize)
             .description("Current number of readings buffered in Redis")
             .register(meterRegistry);
    }

    /**
     * Serialise reading to JSON and push it to the right end of the buffer list.
     */
    public void bufferReading(TelemetryReading reading) {
        try {
            String json = objectMapper.writeValueAsString(reading);
            redisTemplate.opsForList().rightPush(BUFFER_KEY, json);
            log.info("Buffered reading in Redis: sensorId={}, criticality={}",
                    reading.getSensorId(), reading.getCriticality());
        } catch (JsonProcessingException e) {
            log.error("Failed to serialise reading for Redis buffer: {}", reading, e);
        }
    }

    /**
     * Returns the current number of entries in the buffer list.
     */
    public long getBufferSize() {
        Long size = redisTemplate.opsForList().size(BUFFER_KEY);
        return size != null ? size : 0L;
    }

    /**
     * If the buffer exceeds maxSize, removes the single entry with the LOWEST
     * criticality score (not just the tail / oldest). This keeps high-priority
     * anomaly readings alive during sustained cloud outages.
     *
     * The removal is O(n) — we read all entries, find the minimum, then use
     * LREM to delete the first occurrence of that exact JSON string. Acceptable
     * at buffer sizes up to a few thousand; revisit for Phase 4 if needed.
     */
    public void evictIfOverCapacity(int maxSize) {
        long size = getBufferSize();
        if (size <= maxSize) {
            return;
        }

        // Read every entry to find the one with the lowest criticality.
        List<String> allEntries = redisTemplate.opsForList().range(BUFFER_KEY, 0, -1);
        if (allEntries == null || allEntries.isEmpty()) {
            return;
        }

        // Deserialise each entry and track which JSON string has the lowest criticality.
        String lowestJson = null;
        TelemetryReading lowestReading = null;

        for (String json : allEntries) {
            try {
                TelemetryReading candidate = objectMapper.readValue(json, TelemetryReading.class);
                if (lowestReading == null
                        || candidate.getCriticality() < lowestReading.getCriticality()) {
                    lowestReading = candidate;
                    lowestJson = json;
                }
            } catch (JsonProcessingException e) {
                log.warn("Could not deserialise buffered entry during eviction scan, skipping: {}", json);
            }
        }

        if (lowestJson != null) {
            // LREM key 1 value  → remove the first occurrence of that exact string.
            redisTemplate.opsForList().remove(BUFFER_KEY, 1, lowestJson);
            log.warn("EVICTED lowest-criticality reading from buffer (score={}, buffer was {}): {}",
                    lowestReading != null ? lowestReading.getCriticality() : "?",
                    size,
                    lowestReading);
        }
    }

    /**
     * Atomically drains the entire buffer: returns all readings as a list and
     * deletes the Redis key. Kept for backward compatibility and testing.
     * For Phase 4 recovery, prefer drainBatch() which pulls in small increments.
     */
    public List<TelemetryReading> drainBuffer() {
        List<String> allEntries = redisTemplate.opsForList().range(BUFFER_KEY, 0, -1);
        redisTemplate.delete(BUFFER_KEY);

        List<TelemetryReading> readings = new ArrayList<>();
        if (allEntries == null) {
            return readings;
        }

        for (String json : allEntries) {
            try {
                readings.add(objectMapper.readValue(json, TelemetryReading.class));
            } catch (JsonProcessingException e) {
                log.error("Could not deserialise buffered entry during drain, skipping: {}", json);
            }
        }

        log.info("Drained {} readings from Redis buffer", readings.size());
        return readings;
    }

    /**
     * Phase 4: Pops up to {@code batchSize} readings from the LEFT (oldest) end
     * of the buffer list atomically, using LPOP with a count argument.
     * Returns an empty list when the buffer is exhausted.
     *
     * Using LPOP (pop-and-delete) rather than LRANGE+DEL means:
     *  - readings are removed as they are pulled, so a crash mid-drain won't
     *    re-drain readings that were already forwarded.
     *  - concurrent calls from multiple threads won't pull the same reading twice.
     */
    public List<TelemetryReading> drainBatch(int batchSize) {
        List<String> popped = redisTemplate.opsForList().leftPop(BUFFER_KEY, batchSize);
        List<TelemetryReading> readings = new ArrayList<>();
        if (popped == null || popped.isEmpty()) {
            return readings;
        }
        for (String json : popped) {
            try {
                readings.add(objectMapper.readValue(json, TelemetryReading.class));
            } catch (JsonProcessingException e) {
                log.error("Could not deserialise buffered entry in drainBatch, skipping: {}", json);
            }
        }
        return readings;
    }
}

