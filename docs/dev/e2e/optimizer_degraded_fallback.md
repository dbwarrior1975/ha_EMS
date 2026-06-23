# Story: Optimizer degraded fallback

## What this folder contains
- tests/e2e_entity/optimizer_degraded_fallback/test_01_stale_reactive_fallback.py
- tests/e2e_entity/optimizer_degraded_fallback/test_02_forecast_missing_runtime_alive.py
- tests/e2e_entity/optimizer_degraded_fallback/scenario_steps.py

## Scenario split
1. Scenario 1: stale HAEO freshness forces local forecast fallback in NET_ZERO.
2. Scenario 2: missing HAEO payload falls back to local policy while runtime remains active.

## Implementation notes
1. Both scenarios use independent harness seeds.
2. Shared helper centralizes policy and dispatch assertions.
