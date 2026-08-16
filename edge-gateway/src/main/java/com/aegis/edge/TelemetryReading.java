package com.aegis.edge;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * Data model for one sensor reading, shared across all phases.
 *
 * Phase 4 additions:
 *   - readingHash: SHA-256 of (sensorId:timestamp:value), hex-encoded.
 *     Computed once at the edge (in TelemetryController, right after scoring)
 *     and carried through to the cloud. The cloud uses it as a UNIQUE constraint
 *     to enforce exactly-once storage — duplicate hashes are silently rejected.
 */
public class TelemetryReading {

    private String sensorId;
    private long timestamp;
    private double value;
    private String metricType;
    private int criticality;   // 1 (normal) to 10 (highly critical) — set by CriticalityScorer
    private String readingHash; // SHA-256(sensorId:timestamp:value), set at edge before forwarding

    public TelemetryReading() {
    }

    public TelemetryReading(String sensorId, long timestamp, double value, String metricType) {
        this.sensorId = sensorId;
        this.timestamp = timestamp;
        this.value = value;
        this.metricType = metricType;
    }

    /**
     * Computes and stores a deterministic SHA-256 hash for this reading.
     * Input: "sensorId:timestamp:value" — stable regardless of field ordering.
     * Must be called ONCE at the edge before forwarding or buffering.
     */
    public void computeAndSetHash() {
        String input = sensorId + ":" + timestamp + ":" + value;
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hashBytes = md.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(64);
            for (byte b : hashBytes) {
                sb.append(String.format("%02x", b));
            }
            this.readingHash = sb.toString();
        } catch (NoSuchAlgorithmException e) {
            // SHA-256 is mandated by the JVM spec — this cannot happen.
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }

    public String getSensorId() { return sensorId; }
    public void setSensorId(String sensorId) { this.sensorId = sensorId; }

    public long getTimestamp() { return timestamp; }
    public void setTimestamp(long timestamp) { this.timestamp = timestamp; }

    public double getValue() { return value; }
    public void setValue(double value) { this.value = value; }

    public String getMetricType() { return metricType; }
    public void setMetricType(String metricType) { this.metricType = metricType; }

    public int getCriticality() { return criticality; }
    public void setCriticality(int criticality) { this.criticality = criticality; }

    public String getReadingHash() { return readingHash; }
    public void setReadingHash(String readingHash) { this.readingHash = readingHash; }

    @Override
    public String toString() {
        return "TelemetryReading{" +
                "sensorId='" + sensorId + '\'' +
                ", timestamp=" + timestamp +
                ", value=" + value +
                ", metricType='" + metricType + '\'' +
                ", criticality=" + criticality +
                ", hash=" + (readingHash != null ? readingHash.substring(0, 8) + "..." : "null") +
                '}';
    }
}
