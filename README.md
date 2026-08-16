# Aegis — Phase 1 MVP

Read `BUILD_GUIDE.md` first for the full phased plan. This README covers only how to run
what's built so far: Phase 1, the basic pipe.

## What's included right now

- `edge-gateway/` — Spring Boot app (port 8080), receives telemetry, forwards to cloud
- `cloud-aggregator/` — Spring Boot app (port 8081), receives forwarded telemetry, logs it
- `simulator/simulate.py` — Python script generating fake sensor readings

No AI, no Redis, no resilience yet — that's Phases 2-4. This is purely "prove the plumbing works."

## How to run it (3 terminals)

**Terminal 1 — start the cloud aggregator first (it needs to be up before edge forwards to it):**
```bash
cd cloud-aggregator
mvn spring-boot:run
```
Wait until you see `Started CloudAggregatorApplication`.

**Terminal 2 — start the edge gateway:**
```bash
cd edge-gateway
mvn spring-boot:run
```
Wait until you see `Started EdgeGatewayApplication`.

**Terminal 3 — start the simulator:**
```bash
cd simulator
pip install requests
python simulate.py
```

## What you should see

- Terminal 3 (simulator): a new reading printed once per second, with `<-- ANOMALY` occasionally
- Terminal 2 (edge gateway): `Received reading at edge: ...` and `Forwarded reading to cloud: ...` for each one
- Terminal 1 (cloud aggregator): `[N] Ingested at cloud: ...` counting up

You can also check:
- `http://localhost:8080/health` — edge gateway health
- `http://localhost:8081/health` — cloud aggregator health
- `http://localhost:8081/stats` — running count of ingested readings

## Try this to understand the current (Phase 1) limitation

Stop the cloud-aggregator (Ctrl+C in Terminal 1) while the simulator keeps running.
Watch Terminal 2 — you'll see forward failures logged. Right now, that data is just lost.
**This is exactly the problem Phase 3 (circuit breaker + Redis buffer) fixes.** Seeing the
failure happen for real here is worth doing before you build the fix — you'll understand
why the resilience layer matters instead of just taking it on faith.

## Next step

Once this runs cleanly end-to-end, move to Phase 2 in `BUILD_GUIDE.md`.
