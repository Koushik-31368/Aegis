package com.aegis.cloud;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

/**
 * Spring Data JPA repository for telemetry readings.
 * Provides save(), findById(), count(), etc. out of the box.
 */
@Repository
public interface TelemetryReadingRepository extends JpaRepository<TelemetryReading, Long> {

    /** Checks whether a reading with this exact hash was already stored. */
    boolean existsByReadingHash(String readingHash);

    /** COUNT(*) from the DB — used by the /stats endpoint instead of the old AtomicLong. */
    @Query("SELECT COUNT(r) FROM TelemetryReading r")
    long countAll();
}
