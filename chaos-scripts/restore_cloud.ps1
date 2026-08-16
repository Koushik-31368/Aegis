# restore_cloud.ps1 — restarts the cloud-aggregator in the background
# Usage: .\chaos-scripts\restore_cloud.ps1
#
# What happens: the cloud comes back up, Resilience4j probes it in HALF_OPEN,
# calls succeed, circuit transitions to CLOSED, DrainService fires and starts
# draining Redis buffer at rate-limited 5 readings/sec.
# Watch Grafana: buffer size should slope down gradually (not a vertical drop).

Write-Host "=== [RESTORE] Starting cloud-aggregator ==="
$projectRoot = Split-Path -Parent $PSScriptRoot
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "cd '$projectRoot\cloud-aggregator'; mvn spring-boot:run" `
    -WindowStyle Normal

Write-Host "=== [RESTORE] Cloud-aggregator starting in new window. ==="
Write-Host "    Watch Grafana: CB state -> HALF_OPEN (2) -> CLOSED (0), then buffer drains. ==="
