# inject_critical_event.ps1 — sends one deliberately extreme reading directly to the edge gateway
# Usage: .\chaos-scripts\inject_critical_event.ps1
#
# What to watch:
#   - Edge log: "CRITICAL reading at edge (score=9 or 10)"
#   - Grafana "Critical readings/sec" counter ticks up
#   - If run during an outage: reading buffers in Redis with high criticality,
#     meaning it will survive eviction even if the buffer fills.
#   - If run while cloud is up: flows through immediately to DB.

$body = @{
    sensorId   = "sensor-chaos"
    timestamp  = [long]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
    value      = 155.0      # well above normal range (60-90), will score as anomaly
    metricType = "temperature"
    criticality = 0         # edge gateway will override this with ONNX score
} | ConvertTo-Json

Write-Host "=== [INJECT] Sending critical event (value=155.0) to edge gateway ==="
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080/telemetry" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -UseBasicParsing
    Write-Host "=== [INJECT] Response: $($response.Content) ==="
    Write-Host "    Check edge log for 'CRITICAL reading' and Grafana critical counter. ==="
} catch {
    Write-Host "=== [INJECT] Failed (is edge gateway running?): $($_.Exception.Message) ==="
}
