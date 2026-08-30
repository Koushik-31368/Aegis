# Aegis Development Makefile
# Common commands for local development workflow

.PHONY: test benchmark train simulate health

## Run simulator unit tests
test:
	python -m pytest simulator/ -v

## Run ONNX model benchmark (no server needed)
benchmark:
	python ai-training/benchmark.py

## Train the anomaly detection model and export to ONNX
train:
	python ai-training/train_model.py

## Start the sensor simulator (requires edge-gateway running)
simulate:
	python simulator/simulate.py

## Check health of all services + Prometheus + Redis
health:
	python scripts/check_health.py

## Check circuit breaker state via Prometheus
circuit:
	python scripts/check_circuit_state.py

## Run deduplication verification
dedup:
	python scripts/verify_dedup.py

## Stress test the Redis buffer
stress:
	python scripts/stress_buffer.py --count 50
