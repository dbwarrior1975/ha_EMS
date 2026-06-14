# Story: NET_ZERO home-battery primary with EV adjustable surplus load

## What this folder contains
- tests/e2e_entity/net_zero_homebattery_adjustable_load/test_01_baseline_to_adjustable_activation.py
- tests/e2e_entity/net_zero_homebattery_adjustable_load/test_02_release_and_low_pv_hard_off_path.py
- tests/e2e_entity/net_zero_homebattery_adjustable_load/test_03_recovery_and_reactivation.py
- tests/e2e_entity/net_zero_homebattery_adjustable_load/scenario_steps.py

## Phase split
1. Phase 1 (t0..t89): pre-threshold battery path, ADJUSTABLE activation, and freeze-era EV burn visibility.
2. Phase 2 (t90..t180): low-PV stress, RELEASE_ADJUSTABLE, and EV hard-off progression.
3. Phase 3 (t210..t280): post-hard-off negative-battery trough, recovery, ADJUSTABLE reactivation, and EV burn restore.

## Implementation notes
1. Each phase seeds its own initial state and does not depend on warmup chains.
2. Shared helper includes EV non-negative invariant and optional negative battery-target checks.
3. Phase 3 seeds EV policy attrs to preserve hard-off continuity at phase start.
