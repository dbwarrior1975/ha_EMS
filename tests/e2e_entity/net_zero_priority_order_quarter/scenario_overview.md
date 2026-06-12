# Story: NET_ZERO priority order (quarter)

## What this folder contains
- tests/e2e_entity/net_zero_priority_order_quarter/test_01_activation_chain.py
- tests/e2e_entity/net_zero_priority_order_quarter/test_02_release_relay2_then_adjustable.py
- tests/e2e_entity/net_zero_priority_order_quarter/test_03_release_relay1_then_restart.py
- tests/e2e_entity/net_zero_priority_order_quarter/scenario_steps.py

## Phase split
1. Phase 1 (t0, t30, t60, t61): activation order RELAY1 -> ADJUSTABLE(EV) -> RELAY2.
2. Phase 2 (t76, t90, t91): all-active stability, then release RELAY2 -> ADJUSTABLE.
3. Phase 3 (t120, t121, t150): release RELAY1 and restart the cycle.

## Implementation notes
1. Each phase seeds its own initial state and does not rely on warmup chains.
2. Steps stay local in phase files.
3. Shared helper keeps only build_harness and run_steps.
