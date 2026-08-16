package com.aegis.cloud;

import jakarta.persistence.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * JPA entity mapped to the "telemetry_readings" table in TimescaleDB.
 *
 * The readingHash column has a UNIQUE constraint enforced at the DB level.
 * Any attempt to insert a duplicate hash is caught in IngestController and
 * logged as "Duplicate reading ignored" rather than propagated as a 500.
 *
 * TimescaleDB is Postgres-compatible, so standard JPA + Hibernate works
 * without any special driver. In production you'd call
 * CREATE EXTENSION timescaledb and convert this to a hypertable partitioned
 * on the timestamp column — that's a one-line SQL command, left for later.
 */
@Entity
@Table(name = "telemetry_readings",
       uniqueConstraints = @UniqueConstraint(name = "uq_reading_hash",
                                             columnNames = "reading_hash"))
public class TelemetryReading {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sensor_id", nullable = false)
    private String sensorId;

    @Column(nullable = false)
    private long timestamp;

    @Column(nullable = false)
    private double value;

    @Column(name = "metric_type")
    private String metricType;

    @Column(nullable = false)
    private int criticality;

    /** SHA-256(sensorId:timestamp:value), hex-encoded. Unique per reading. */
    @Column(name = "reading_hash", nullable = false, length = 64)
    private String readingHash;

    public TelemetryReading() {
    }

    // ─── Getters / Setters ───────────────────────────────────────────────────

    public Long getId() { return id; }

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
