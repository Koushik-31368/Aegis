"""
Aegis Simulator — Unit Tests
Run: python -m pytest simulator/ -v
"""
import pytest
import sys
import os

# Allow importing simulate.py directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulate import generate_reading, SENSORS, NORMAL_MEAN, NORMAL_STD, ANOMALY_PROB


class TestGenerateReading:
    def test_returns_all_required_fields(self):
        reading = generate_reading()
        assert "sensorId" in reading
        assert "timestamp" in reading
        assert "value" in reading
        assert "metricType" in reading
        assert "criticality" in reading

    def test_sensor_id_is_valid(self):
        for _ in range(20):
            reading = generate_reading()
            assert reading["sensorId"] in SENSORS

    def test_criticality_defaults_to_zero(self):
        """Edge gateway overrides this — simulator always sends 0."""
        reading = generate_reading()
        assert reading["criticality"] == 0

    def test_metric_type_is_temperature(self):
        reading = generate_reading()
        assert reading["metricType"] == "temperature"

    def test_timestamp_is_positive_integer(self):
        reading = generate_reading()
        assert isinstance(reading["timestamp"], int)
        assert reading["timestamp"] > 0

    def test_normal_value_within_expected_range(self):
        """5-sigma check: normal values should almost never exceed 60±30."""
        values = [generate_reading()["value"] for _ in range(200)]
        normal_values = [v for v in values if abs(v - NORMAL_MEAN) < 5 * NORMAL_STD]
        # At least 80% should be 'normal' (some may be injected anomalies)
        assert len(normal_values) / len(values) > 0.6

    def test_anomaly_values_exist_over_many_readings(self):
        """With ANOMALY_PROB=0.1, expect anomalies in 200 readings."""
        values = [generate_reading()["value"] for _ in range(200)]
        anomaly_values = [v for v in values if v > NORMAL_MEAN + 3 * NORMAL_STD]
        assert len(anomaly_values) > 0, "Expected at least one anomaly in 200 readings"
