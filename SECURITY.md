# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Aegis, please report it responsibly:

1. **Do NOT open a public GitHub issue** for security vulnerabilities
2. Contact the maintainer via GitHub profile
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment

## Security Architecture

Aegis processes IoT telemetry through multiple safety and resilience layers:

- **ONNX Isolation Forest** - ML-based anomaly scoring at the edge before forwarding
- **Circuit Breaker** - Resilience4j circuit breaker isolates edge from cloud failures
- **SHA-256 Deduplication** - Deterministic hashing prevents duplicate ingestion
- **Rate-Limited Drain** - Buffered readings are replayed at controlled rate during recovery

## Data Handling

- Sensor readings are processed at the edge and forwarded to the cloud aggregator
- Redis buffering is temporary and drains automatically on cloud recovery
- API keys and database credentials are stored in application.yml / environment variables
- No authentication is currently implemented (local development scope)

## Dependencies

Both Spring Boot services use managed dependencies via Maven. To check for vulnerabilities:

```bash
cd edge-gateway && mvn dependency:tree
cd cloud-aggregator && mvn dependency:tree
```
