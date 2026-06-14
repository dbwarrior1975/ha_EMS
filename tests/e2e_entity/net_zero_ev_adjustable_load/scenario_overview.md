# Story: NET_ZERO with EV as primary and HOME_BATTERY as adjustable surplus

## Scope
This scenario validates the full V2 behavior when EV is the primary control channel and battery is the adjustable surplus target.

Files in this story:
- tests/e2e_entity/net_zero_ev_adjustable_load/test_01_ev_primary_ramp_and_adjustable_activation.py
- tests/e2e_entity/net_zero_ev_adjustable_load/test_02_release_and_hard_off_hold.py
- tests/e2e_entity/net_zero_ev_adjustable_load/test_03_post_hard_off_recovery.py
- tests/e2e_entity/net_zero_ev_adjustable_load/scenario_steps.py

## Narrative timeline
1. Phase 1, ramp and activation (t0..t90)
- Starts from low PV where EV remains at minimum while battery target can be briefly negative before stabilizing near zero.
- PV rises, EV ramps first (primary path), while ADJUSTABLE waits until RPC threshold is crossed.
- At the threshold edge, ADJUSTABLE activates and relay behavior follows dispatch priority.

2. Phase 2, release and hard-off hold (t135..t240)
- Surplus weakens and release sequence is triggered in deterministic order.
- Low-PV persistence drives EV into hard_off.
- While hard_off is active, EV stays disabled and battery setpoint is held by gate/floor rules.

3. Phase 3, post hard-off recovery (t240..t295)
- System remains stable with NOOP dispatch while hard_off continuity is preserved.
- Release-ready progression is validated explicitly: only cycles that satisfy both PV and RPC release conditions count.
- When release-ready conditions are met for configured consecutive cycles, EV exits hard_off and returns to active minimum-current control.

## Why this split exists
1. Each phase is independently seedable, so debugging does not require replaying the whole quarter.
2. Hard-off continuity is explicit via seeded policy attributes in later phases.
3. Shared helper keeps execution contract identical across all phase files.

## Key acceptance intent
1. EV-primary dynamics stay continuous across dispatch edges.
2. Hard_off anti-flap semantics remain intact.
3. Post-hard_off recovery validates release-ready gating (PV + RPC + consecutive cycles) before hard_off is released.
