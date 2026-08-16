# kill_cloud.ps1 — stops the cloud-aggregator Maven process
# Usage: .\chaos-scripts\kill_cloud.ps1
#
# What happens: the edge gateway loses its forward target, failures accumulate,
# the Resilience4j circuit breaker trips OPEN, and readings start buffering in Redis.
# Watch the Grafana dashboard: buffer size will climb, CB state will flip to OPEN (1).

Write-Host "=== [CHAOS] Killing cloud-aggregator ==="

$victims = Get-Process -Name "java" -ErrorAction SilentlyContinue |
    Where-Object {
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
            $cmd -like "*cloud-aggregator*"
        } catch { $false }
    }

if ($victims) {
    $victims | ForEach-Object {
        Write-Host "  Stopping PID $($_.Id) — $($_.ProcessName)"
        Stop-Process -Id $_.Id -Force
    }
    Write-Host "=== [CHAOS] Cloud-aggregator killed. Watch the dashboard: buffer size should climb. ==="
} else {
    Write-Host "=== [CHAOS] No cloud-aggregator process found. Is it running? ==="
}
