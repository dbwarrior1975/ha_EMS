# Story: BATTERY_PROTECT min-cell recovery (quarter)

## What this folder contains
- tests/e2e_entity/battery_protect_min_cell_recovery/test_01_baseline_and_trigger.py
- tests/e2e_entity/battery_protect_min_cell_recovery/test_02_recovery_gate_then_restore.py
- tests/e2e_entity/battery_protect_min_cell_recovery/test_03_min_cell_retrigger_and_recovery.py
- tests/e2e_entity/battery_protect_min_cell_recovery/scenario_steps.py

## Phase split
1. Phase 1 (t0, t30): baseline then SOC+min-cell trigger to BATTERY_PROTECT.
2. Phase 2 (t60, t90): explicit BATTERY_PROTECT recovery gating, then NORMAL_LIMITS recovery.
3. Phase 3 (t120, t150): min-cell-only trigger and explicit recovery back to NORMAL_LIMITS.

## Implementation notes
1. Each phase seeds its own initial state and does not depend on warmup chains.
2. Steps are local in each phase file.
3. Shared helper keeps only build_harness and run_steps.
