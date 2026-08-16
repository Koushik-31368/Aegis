# Contributing to Aegis

## Dev Setup

1. Java 17+, Maven, Python 3.10+, Redis
2. `pip install requests onnxruntime scikit-learn numpy`
3. Start services in order: Redis → edge-gateway → cloud-aggregator → simulator

## Commit Style

We use conventional commits:
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `chore:` — tooling, config, deps
- `test:` — tests
- `refactor:` — no behaviour change

## Branch Strategy

Work directly on `master` for now (single-developer MVP).

## Adding a New Metric

1. Inject `MeterRegistry` into the Spring bean
2. Register your `Counter` or `Gauge` in the constructor
3. Verify it appears at `/actuator/prometheus`
4. Add a panel to `grafana/provisioning/dashboards/aegis-dashboard.json`
