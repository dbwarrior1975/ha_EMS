# Story: NET_ZERO EV primary with HOME_BATTERY as adjustable surplus load

## What this folder contains
- tests/e2e_entity/net_zero_ev_adjustable_load/test_01_ev_primary_ramp_and_adjustable_activation.py
- tests/e2e_entity/net_zero_ev_adjustable_load/test_02_release_and_hard_off_hold.py
- tests/e2e_entity/net_zero_ev_adjustable_load/test_03_post_hard_off_recovery.py
- tests/e2e_entity/net_zero_ev_adjustable_load/scenario_steps.py

## Phase split
1. Phase 1 (t0..t90): EV-primary burn ramp, ADJUSTABLE activation, and RELAY1 activation edge.
2. Phase 2 (t120..t226): release sequence and hard-off hold with gated battery setpoint.
3. Phase 3 (t240..t295): post-hard-off NOOP behavior and release-ready EV recovery.

## Implementation notes
1. Each phase seeds its own initial state and does not depend on warmup chains.
2. Phase 2 and phase 3 seed `policy_ev_current_a` attrs to preserve hard-off continuity.
3. Shared helper keeps only build_harness and run_steps.
