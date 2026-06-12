# Story: Goal transition NET_ZERO to MAX_EXPORT

## What this folder contains
- tests/e2e_entity/goal_transition_net_zero_to_max_export/test_01_activation_and_ev_burn.py
- tests/e2e_entity/goal_transition_net_zero_to_max_export/test_02_goal_switch_clears_surplus.py
- tests/e2e_entity/goal_transition_net_zero_to_max_export/test_03_max_export_hard_off_stability.py
- tests/e2e_entity/goal_transition_net_zero_to_max_export/scenario_steps.py

## Phase split
1. Phase 1 (t0, t30, t44, t60): NET_ZERO surplus activation and EV burn stabilization.
2. Phase 2 (t90): goal switch to MAX_EXPORT and CLEAR_ALL latch reset.
3. Phase 3 (t120, t150): MAX_EXPORT hard-off behavior remains stable over time.

## Implementation notes
1. Each phase is independently seeded and does not depend on warmup execution from another file.
2. Shared helper holds harness setup and assertion plumbing.
