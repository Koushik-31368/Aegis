## Aegis — Local Dev Runbook

Quick reference for starting / stopping everything without reading the full README.

---

### Start everything (fresh session)

Open **4 terminals**:

**Terminal 1 — Redis**
```powershell
redis-server --port 6379
```

**Terminal 2 — Edge Gateway**
```powershell
cd g:\aegis-project\edge-gateway
mvn spring-boot:run
# Wait for: "Started EdgeGatewayApplication"
```

**Terminal 3 — Cloud Aggregator**
```powershell
cd g:\aegis-project\cloud-aggregator
mvn spring-boot:run
# Wait for: "Started CloudAggregatorApplication"
```

**Terminal 4 — Simulator**
```powershell
cd g:\aegis-project\simulator
python simulate.py
```

**Terminal 5 — Prometheus**
```powershell
cd g:\aegis-project
$p = "$env:USERPROFILE\scoop\apps\prometheus\current\prometheus.exe"
& $p "--config.file=g:/aegis-project/prometheus/prometheus.yml" `
      "--storage.tsdb.path=g:/aegis-project/prometheus/data" `
      "--web.listen-address=0.0.0.0:9090" `
      "--web.enable-lifecycle"
```

**Terminal 6 — Grafana** *(once installed)*
```powershell
cd C:\grafana\bin
.\grafana-server.exe --config=g:\aegis-project\grafana-custom.ini
# Open: http://localhost:3000 (admin / admin)
```

---

### Quick health check
```powershell
python -X utf8 g:\aegis-project\scripts\check_health.py
```

---

### Demo chaos sequence

```powershell
# 1. Verify everything healthy
python -X utf8 scripts\check_health.py

# 2. Kill cloud — circuit trips, buffer fills
.\chaos-scripts\kill_cloud.ps1

# 3. Inject a critical anomaly while cloud is down
.\chaos-scripts\inject_critical_event.ps1

# 4. Watch buffer fill in Grafana (redis_buffer_size panel)
#    Watch circuit state flip to OPEN (1.0)

# 5. Restore cloud — drain starts, buffer empties gradually
.\chaos-scripts\restore_cloud.ps1

# 6. Watch buffer drain slope in Grafana
#    Watch circuit state return to CLOSED (0.0)
```

---

### Useful one-liners

```powershell
# DB row count
Invoke-WebRequest http://localhost:8081/stats -UseBasicParsing | Select -Exp Content

# Redis buffer depth
redis-cli llen telemetry:buffer

# Circuit breaker state live
Invoke-WebRequest "http://localhost:9090/api/v1/query?query=aegis_circuit_breaker_state" -UseBasicParsing | Select -Exp Content

# Prometheus scrape target health
Invoke-WebRequest http://localhost:9090/api/v1/targets -UseBasicParsing | Select -Exp Content
```
