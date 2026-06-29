# Story: NET_ZERO force-on relay2 with freeze hygiene

## What this folder contains
- tests/e2e_entity/net_zero_force_on_battery_support/test_01_force_rising_edge_freeze_hygiene.py
- tests/e2e_entity/net_zero_force_on_battery_support/test_02_relay1_on_then_release_under_force.py
- tests/e2e_entity/net_zero_force_on_battery_support/test_03_unforce_then_reactivate_relay2.py
- tests/e2e_entity/net_zero_force_on_battery_support/test_04_relay1_reactivation_after_relay2_freeze.py
- tests/e2e_entity/net_zero_force_on_battery_support/scenario_steps.py

## Phase split
1. Phase 1 (t0, t30, t60, t74, t90): baseline, force RELAY2 rising-edge freeze, and RELAY1 activation decision after freeze expiry.
2. Phase 2 (t120, t150, t180, t210): RELAY1 visible on under forced RELAY2, then RELAY1 release path.
3. Phase 3 (t240, t270, t284): remove force, ordinary RELAY2 reactivation, and freeze blocking RELAY1.
4. Phase 4 (t300, t301, t330): RELAY1 reactivation after freeze and stable dual-relay state.

## Implementation notes
1. Each phase seeds its own initial state and does not rely on warmup chains.
2. Phase 2 seeds policy attrs (`prev_force_on_device_ids=('RELAY2',)`) to avoid synthetic force rising-edge freeze.
3. Shared helper keeps only build_harness and run_steps.
