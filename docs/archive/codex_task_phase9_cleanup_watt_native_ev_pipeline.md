# Codex Task: Phase 9 Cleanup - Watt-Native EV Pipeline

Source review: [review_comments.md](/home/virtamik/code/ha_EMS/review_comments.md)

## Goal

Finish the Phase 9 EV refactor so EMS core policy and HAEO planning are watt-native.

The desired boundary is:

- Core policy and planning choose EV power targets in watts.
- Measured charger current may be used only for telemetry, load estimation, and safety observation.
- Writer / adapter boundary converts `target_w` to charger selector current when the physical actuator requires amps.

## Current Gaps

The main EV target pipeline is already watt-based, but one remaining cleanup still needs explicit regression coverage:

- `_ev_policy_mode_and_target_w(...)` now uses policy/state-only max-burn selection, and that contract still needs a dedicated regression.

## Progress

| Step | Status | Notes |
| --- | --- | --- |
| 1. Remove Measured-Current Target Selection | Done | Removed the `measured_ev_current_a -> ev_current_a_to_power_w(...) -> target_w` branch from `_ev_policy_mode_and_target_w(...)`. Measured current remains available for runtime load estimation and telemetry paths, but no longer chooses EV policy target watts. |
| 2. Keep EV Burn Active from Policy/State Only | Done | Kept the surplus max-burn path canonical on `burn_active`, `adjustable_surplus_active`, `ev_release_pending`, `rpnz_w`, and `use_ev_adjustable_mode` only. Removed now-unused measured-current/grid-power arguments from `_ev_policy_mode_and_target_w(...)` so the helper interface matches the state-only decision contract. |
| 3. Make HAEO Net-Zero Plan Watt-Native | Done | Removed `ev_limit_a` from `HaeoNetZeroPlan`, removed HAEO plan-time current quantization and adapter current min/max dependence from `compute_haeo_net_zero_plan(...)`, and kept `ev_limit_w` plus `device_limits_w` as the canonical EV HAEO contract. Updated engine debug attrs and HAEO tests to stop expecting amp-based internal plan fields. |
| 4. Add Regression Coverage | Done | Added a unit regression proving EV surplus max-burn keeps `ev_target_w` at max even when measured charger current is `0 A`. Verified focused unit suites, HAEO unit coverage, EV power/writer coverage, and compile checks after the cleanup. |

## Step 1: Remove Measured-Current Target Selection

Remove the branch in `modules/ems_core/net_zero/engine.py` that:

- reads `measured_ev_current_a`
- converts it to watts with `ev_current_a_to_power_w(...)`
- sets `target_w = ev_max_power_w(cfg)`

Measured charger current remains allowed for:

- telemetry/debug attrs
- load estimate inputs
- safety observation

Measured charger current must not choose EV policy `target_w`.

### Acceptance

- `_ev_policy_mode_and_target_w(...)` no longer derives target selection from `measured_ev_current_a`.
- `measured_ev_current_a` may still be passed through the engine when needed by telemetry/safety paths.
- Search in `modules/ems_core/net_zero/engine.py` should show no current-measurement branch that sets EV `target_w`.

## Step 2: Keep EV Burn Active from Policy/State Only

If EV burn should remain at max while surplus remains valid, express that with policy/state inputs only:

- `burn_active`
- `adjustable_surplus_active`
- `ev_release_pending`
- `rpnz_w`
- previous EV mode / hard-off state only if the existing state machine requires it

The existing watt-native max-burn branch should be the canonical path.

### Acceptance

- EV max target in surplus burn mode is selected without measured charger current.
- Existing behavior for `force_charge_blocked`, `ev_release_pending`, and `hard_off` remains unchanged.
- No `current_a` value is required to keep `target_w` at max when policy state says EV burn is active and surplus remains valid.

## Step 3: Make HAEO Net-Zero Plan Watt-Native

Treat `ev_limit_w` as the canonical HAEO EV limit.

Refactor `modules/ems_core/integrations/haeo_net_zero_plan.py` so grouped EV plan params do not depend on adapter `current_min_a` / `current_max_a` for plan decisions.

Preferred direction:

- derive EV plan caps from watt capabilities such as `max_absorb_w`
- keep `device_limits_w` and `ev_limit_w` as the plan contract
- remove `ev_limit_a` from the plan model if nothing outside debug requires it

If `ev_limit_a` must remain temporarily for compatibility, isolate it clearly as debug-only and do not use it for planning or target decisions.

### Acceptance

- `HaeoNetZeroPlan.ev_limit_w` is the canonical EV HAEO limit.
- `compute_haeo_net_zero_plan(...)` does not need `adapter.current_min_a` or `adapter.current_max_a` to decide grouped EV limits.
- `ev_limit_a` is removed from the core plan model or documented as debug-only with no decision usage.
- Existing HAEO tests are updated to assert watt limits instead of amp limits where possible.

## Step 4: Add Regression Coverage

Add a regression test proving measured charger current is not required to maintain EV max target.

Test scenario:

- policy state says `burn_active=True`
- surplus conditions remain valid
- `ev_release_pending=False`
- `rpnz_w > 0`
- measured charger current is below max, zero, stale, or otherwise not at max

Expected result:

- EV policy still returns max `target_w` when policy/state conditions require max burn.
- No assertion depends on measured current being at max.

### Suggested Test Targets

- `tests/unit/test_engine.py` for `_ev_policy_mode_and_target_w(...)` behavior through the public engine path or the smallest existing helper-level pattern.
- Existing HAEO tests in `tests/unit/test_haeo_net_zero_plan.py` for plan watt-native assertions.
- Existing e2e HAEO expectation files only if debug attrs are intentionally changed or removed.

## Verification

Run focused tests first:

```bash
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_haeo_net_zero_plan.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_ev_power.py
pytest -q tests/unit/test_writer_semantics.py
```

Run contract/e2e coverage impacted by HAEO debug attrs:

```bash
pytest -q tests/contract/test_grouped_config_runtime_parity.py tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable
```

Compile changed modules:

```bash
python3 -m py_compile modules/ems_core/net_zero/engine.py modules/ems_core/integrations/haeo_net_zero_plan.py modules/ems_core/domain/models.py
```

## Final Acceptance Checklist

- [x] EV core target selection no longer uses measured charger current.
- [x] EV burn hold at max is based on policy/state variables only.
- [x] HAEO net-zero plan is watt-native, with `ev_limit_w` canonical.
- [x] `ev_limit_a` is removed or explicitly debug-only.
- [ ] Writer remains the only production boundary that converts EV watt target to amp selector value.
- [x] Regression test proves measured charger current at max is not required to keep EV target at max.
- [x] Focused unit, contract, and impacted e2e tests pass.
