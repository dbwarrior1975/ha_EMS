# Story: System degraded safe mode

## What this folder contains
- tests/e2e_entity/system_degraded_safe_mode/test_01_soc_stale_enters_safe_mode.py
- tests/e2e_entity/system_degraded_safe_mode/test_02_writer_freeze_in_degraded.py
- tests/e2e_entity/system_degraded_safe_mode/scenario_steps.py

## Scenario split
1. Scenario 1: stale inverter heartbeat forces DEGRADED and clamps policy outputs.
2. Scenario 2: existing latch state is cleared while relay writes are skipped in DEGRADED.

## Implementation notes
1. Each scenario seeds initial conditions independently.
2. Shared helper centralizes policy, dispatch, value, and writer-trace assertions.
