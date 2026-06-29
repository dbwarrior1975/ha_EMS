# Obsolete EV refactor test cleanup - follow-up plan

## Purpose

This document is a staged cleanup plan for a later session. It is based on `codex_task_cleanup_obsolete_tests_after_ev_refactor.md` and the current repository state after the EV watt-based refactor and legacy EV selector conversion removal.

## Execution status (2026-06-29)

Overall status: completed for phases 1-8.

Completed work:

1. Removed the obsolete name-based surplus allocator test file and production helpers.
2. Removed legacy surplus target/export mapper helpers and their tests.
3. Consolidated duplicate writer legacy-fallback coverage to a smaller canonical set.
4. Removed the weaker duplicate dispatch-state legacy-sensor test.
5. Removed dead EV garage min/max current seed values from grouped-config parity coverage.
6. Renamed the valid engine test to watt-target semantics.
7. Shortened `tests/e2e_entity/e2e_conventions.md` into current e2e conventions.
8. Kept required protections for deprecated config rejection, runtime registry absence, EV W/A helpers, and writer actuator conversion.

Verification status:

1. `pytest -q tests/unit/test_surplus_device_targets.py tests/unit/test_writer_semantics.py tests/unit/test_dispatch_state_applier.py tests/unit/test_engine.py tests/contract/test_grouped_config_runtime_parity.py tests/unit/test_config_loader.py tests/contract/test_runtime_entity_registry_contract.py tests/unit/test_ev_power.py` -> `133 passed`
2. Removed-symbol search is clean in active `modules/`, `tests/`, `docs/`, and `README.md`; remaining hits are archive docs only.
3. Deprecated EV amp field hits remain only in expected rejection/runtime-absence coverage, active EV current helper code, and archive docs.

Do not execute these steps blindly. Each phase includes a search or test gate because some legacy-looking names still protect the current architecture.

Current architecture boundary:

1. EV policy and core engine targets are watt-based.
2. EV writer still converts `target_w` to Home Assistant selector `current_a`.
3. `current_a` remains valid in writer, actuator, measured-state, runtime debug, and EV power helper contexts.
4. Deprecated EV amp policy config fields must stay rejected and absent from runtime registry.

## Current observations

High-confidence cleanup candidates found from the current tree:

1. `tests/unit/test_surplus_allocator.py` still exercises old `SurplusTargetConfig` / decision-name allocator API.
2. `modules/ems_core/net_zero/surplus_allocator.py` still contains old helpers:
   - `active_stack`
   - `next_target`
   - `release_target`
   - `compute_surplus_dispatch`
3. `tests/unit/test_surplus_device_targets.py` still tests legacy mapper helpers:
   - `device_target_to_legacy_target`
   - `device_dispatch_to_legacy_dispatch`
4. `modules/ems_core/net_zero/surplus_device_targets.py` still exposes legacy mapping helpers and imports `SurplusTargetConfig`.
5. `tests/unit/test_writer_semantics.py` has multiple overlapping tests for "do not fall back to legacy policy/current sensors".
6. `tests/unit/test_dispatch_state_applier.py` has two legacy sensor conflict/absence tests that may be reducible to one canonical device-trace contract.
7. `tests/contract/test_grouped_config_runtime_parity.py` still seeds stale EV garage min/max current entities:
   - `input_number.ems_ev_garage_min_current_a`
   - `input_number.ems_ev_garage_max_current_a`
8. `tests/unit/test_engine.py` has a valid test with misleading old naming:
   - `test_engine_primary_ev_current_uses_configurable_step_size`

## Phase 0: Baseline and classification

Before editing, capture the current search results and test baseline.

Run:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a|compute_surplus_dispatch|SurplusTargetConfig|device_target_to_legacy_target|device_dispatch_to_legacy_dispatch|legacy_policy|legacy sensor|ev_strategy_current_a|actuator_ev_current_a|target_current_a" tests modules docs README.md
pytest -q tests/unit/test_surplus_allocator.py tests/unit/test_surplus_device_targets.py tests/unit/test_writer_semantics.py tests/unit/test_dispatch_state_applier.py tests/unit/test_engine.py tests/contract/test_grouped_config_runtime_parity.py
```

Classify each hit:

1. `keep`: protects current watt-based architecture or actuator conversion.
2. `remove`: only tests obsolete legacy API.
3. `consolidate`: duplicate transitional coverage.
4. `rename`: valid behavior, misleading old test name.

## Phase 1: Remove old surplus allocator API if still unused

Status: completed.

Notes:

1. Removed `tests/unit/test_surplus_allocator.py`.
2. Removed `active_stack`, `next_target`, `release_target`, and `compute_surplus_dispatch` from `modules/ems_core/net_zero/surplus_allocator.py`.
3. Removed `SurplusTargetConfig` from `modules/ems_core/domain/models.py`.
4. Kept `SurplusDispatchInput` because the active device-id dispatch path still uses it.

Search:

```bash
rg -n "SurplusTargetConfig|SurplusDispatchInput|active_stack\(|next_target\(|release_target\(|compute_surplus_dispatch" modules tests
```

Expected current state: the old API is used by `tests/unit/test_surplus_allocator.py` and its own production helper functions, while the active path uses device-id based surplus dispatch.

If no production caller remains:

1. Delete `tests/unit/test_surplus_allocator.py`.
2. Remove old functions from `modules/ems_core/net_zero/surplus_allocator.py`:
   - `active_stack`
   - `next_target`
   - `release_target`
   - `compute_surplus_dispatch`
3. Remove obsolete dataclasses from `modules/ems_core/domain/models.py` if they become unused:
   - `SurplusTargetConfig`
   - `SurplusDispatchInput`
4. Keep device-id based functions:
   - `active_device_stack`
   - `next_device_target`
   - `release_device_target`
   - `compute_surplus_device_dispatch`

Verification:

```bash
pytest -q tests/unit/test_engine.py tests/unit/test_surplus_device_targets.py
rg -n "SurplusTargetConfig|SurplusDispatchInput|compute_surplus_dispatch|active_stack\(|next_target\(|release_target\(" modules tests
```

## Phase 2: Remove legacy surplus device mappers if unused

Status: completed.

Notes:

1. Removed mapper tests from `tests/unit/test_surplus_device_targets.py`.
2. Removed `device_target_to_legacy_target`, `device_targets_to_legacy_targets`, and `device_dispatch_to_legacy_dispatch` from `modules/ems_core/net_zero/surplus_device_targets.py`.
3. Kept `decision_name_for_device_id` because `modules/ems_core/net_zero/engine.py` still uses it for active decision trace naming.

Search:

```bash
rg -n "device_target_to_legacy_target|device_targets_to_legacy_targets|device_dispatch_to_legacy_dispatch|decision_name_for_device_id" modules tests
```

Expected current state: mapper helpers are only imported by `tests/unit/test_surplus_device_targets.py` and implemented in `surplus_device_targets.py`.

If unused by production code:

1. Remove mapper tests from `tests/unit/test_surplus_device_targets.py`:
   - `test_device_target_export_mapping_preserves_threshold_and_state`
   - `test_device_dispatch_export_mapping_maps_device_id_to_decision_name`
2. Remove mapper helpers from `modules/ems_core/net_zero/surplus_device_targets.py`:
   - `device_target_to_legacy_target`
   - `device_targets_to_legacy_targets`
   - `device_dispatch_to_legacy_dispatch`
   - `decision_name_for_device_id`, if only needed by the legacy mapper
3. Remove now-unused imports:
   - `SurplusTargetConfig`
   - `SurplusDispatchDecision`, if no longer used in that module

Keep all tests that validate `build_surplus_device_targets`.

Verification:

```bash
pytest -q tests/unit/test_surplus_device_targets.py tests/unit/test_engine.py
rg -n "device_target_to_legacy_target|device_targets_to_legacy_targets|device_dispatch_to_legacy_dispatch" modules tests
```

## Phase 3: Consolidate writer legacy fallback coverage

Status: completed.

Notes:

1. Removed duplicate missing-device-policy tests for relay and battery branches.
2. Kept canonical no-fallback coverage for EV writer and the integration-style writer loop conflict test.
3. Kept active `target_w -> current_a` conversion coverage unchanged.

Inspect:

```bash
rg -n "without_device_policy|fallback_to_legacy|legacy_command|legacy_current|legacy_policy_sensors_conflict|device_policy_overrides" tests/unit/test_writer_semantics.py
```

Candidate tests to review:

1. `test_writer_relay_without_device_policy_does_not_use_legacy_command`
2. `test_writer_ev_without_device_policy_does_not_use_legacy_current_even_without_device_id`
3. `test_writer_battery_does_not_fallback_to_legacy_policy_target_without_device_policy`
4. `test_writer_ev_does_not_fallback_to_legacy_current_without_device_policy`
5. `test_writer_relay_device_policy_overrides_legacy_command`
6. `test_writer_relay_does_not_fallback_to_legacy_command_with_device_id`
7. `test_writer_loop_uses_device_policies_when_legacy_policy_sensors_conflict`

Target state:

1. Keep one focused test proving missing `device_policy` causes a skip and no legacy fallback.
2. Keep one integration-style writer loop test proving canonical `device_policy` wins when legacy sensor values conflict.
3. Remove smaller duplicates if they assert the same branch and outcome.

Do not remove tests that validate active writer behavior:

1. `target_w` converts to supported EV selector `current_a`.
2. zero target disables charger and restores derived minimum current.
3. hard-off disables charger and restores derived minimum current.
4. force-on / max-absorb maps to supported selector current.
5. multi-EV writer routing uses each device's own actuator entities.

Verification:

```bash
pytest -q tests/unit/test_writer_semantics.py
```

## Phase 4: Consolidate dispatch state legacy sensor tests

Status: completed.

Notes:

1. Kept `test_dispatch_state_applier_uses_device_trace_when_legacy_sensor_conflicts`.
2. Removed the weaker duplicate `test_dispatch_state_applier_ignores_legacy_sensor_without_device_trace`.
3. Kept normal device-trace activation/release/no-op coverage.

Inspect:

```bash
rg -n "legacy_sensor|device_trace|without_device_trace|conflicts" tests/unit/test_dispatch_state_applier.py
```

Candidate tests:

1. `test_dispatch_state_applier_uses_device_trace_when_legacy_sensor_conflicts`
2. `test_dispatch_state_applier_ignores_legacy_sensor_without_device_trace`

Target state:

1. Keep the strongest contract proving canonical device trace drives dispatch state.
2. Remove or merge the weaker duplicate if it only verifies transitional legacy sensor behavior.
3. Keep tests for normal device-trace activation and no-op behavior.

Verification:

```bash
pytest -q tests/unit/test_dispatch_state_applier.py
```

## Phase 5: Remove dead EV current seed values

Status: completed.

Notes:

1. Removed `input_number.ems_ev_garage_min_current_a`.
2. Removed `input_number.ems_ev_garage_max_current_a`.
3. Kept valid watt/current-step/phase/voltage/current-selector seed values.

Inspect:

```bash
sed -n '560,595p' tests/contract/test_grouped_config_runtime_parity.py
rg -n "ems_ev_garage_min_current_a|ems_ev_garage_max_current_a" .
```

Expected current state: `test_grouped_config_runtime_parity.py` seeds `input_number.ems_ev_garage_min_current_a` and `input_number.ems_ev_garage_max_current_a`, but the grouped config uses watt capability fields and current step/phase/voltage.

If these entities are not referenced by config or runtime logic:

1. Remove the dead seed values from `tests/contract/test_grouped_config_runtime_parity.py`.
2. Keep these valid EV garage values:
   - `input_number.ems_ev_garage_min_power_w`
   - `input_number.ems_ev_garage_max_power_w`
   - `input_number.ems_ev_garage_power_step_w`
   - `input_number.ems_ev_garage_current_step_a`
   - `input_number.ems_ev_garage_phases`
   - `input_number.ems_ev_garage_voltage_v`
   - `number.ev_garage_current_a`

Verification:

```bash
pytest -q tests/contract/test_grouped_config_runtime_parity.py
```

## Phase 6: Rename misleading valid engine test

Status: completed.

Notes:

1. Renamed `test_engine_primary_ev_current_uses_configurable_step_size`.
2. New name: `test_engine_primary_ev_target_w_uses_derived_power_step`.

Rename this test:

```text
test_engine_primary_ev_current_uses_configurable_step_size
```

Suggested new name:

```text
test_engine_primary_ev_target_w_uses_derived_power_step
```

Do not remove the test. It validates useful current architecture behavior: different EV current steps derive different watt targets in the engine output.

Verification:

```bash
pytest -q tests/unit/test_engine.py -k "primary_ev_target_w_uses_derived_power_step or primary_ev_current_uses_configurable_step_size"
pytest -q tests/unit/test_engine.py
```

## Phase 7: Archive or shorten stale migration docs

Status: completed.

Notes:

1. Replaced `tests/e2e_entity/e2e_conventions.md` with a shorter current-conventions document.
2. Removed stale migration-plan sections while keeping current canonical e2e rules and fail-fast guard intent.
3. Active docs no longer reference the removed surplus name-based API.

Inspect:

```bash
sed -n '1,430p' tests/e2e_entity/e2e_conventions.md
```

If it is now only historical planning material:

1. Move it to `docs/archive/`, or replace it with a short note pointing to current e2e conventions.
2. Ensure current docs do not imply deprecated EV amp policy config is supported.
3. Keep useful current e2e rules, especially fail-fast guards for legacy policy mirror assertions.

Verification:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a" docs README.md tests/e2e_entity
```

## Phase 8: Keep these protections

Status: completed.

Notes:

1. Deprecated config rejection tests were kept.
2. Runtime registry absence assertions were kept.
3. `tests/unit/test_ev_power.py` was kept.
4. Writer/current-selector actuator assertions were kept.
5. Runtime debug current-derived fields were kept.

Do not remove these categories during cleanup:

1. Deprecated config rejection tests for `adapter.current_min_a`, `adapter.current_max_a`, and `adapter.force_current_a`.
2. Runtime registry absence assertions for `ev_min_current_a`, `ev_max_current_a`, `ev_force_current_a`, `deprecated_current_min_a`, `deprecated_current_max_a`, and `deprecated_force_current_a`.
3. `tests/unit/test_ev_power.py`, because it protects W/A conversion and derived current bounds.
4. E2E actuator assertions using `actuator_ev_current_a` and device `target_current_a`.
5. Writer tests that prove `target_w` maps to a supported Home Assistant selector current.
6. Runtime debug fields named `ev_derived_min_current_a`, `ev_derived_max_current_a`, and `ev_current_power_w`.

## Final verification

After all phases:

```bash
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_dispatch_state_applier.py
pytest -q tests/unit/test_engine.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/unit/test_config_loader.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/unit/test_ev_power.py
pytest -q
```

Final audit:

```bash
rg -n "SurplusTargetConfig|SurplusDispatchInput|compute_surplus_dispatch|device_target_to_legacy_target|device_targets_to_legacy_targets|device_dispatch_to_legacy_dispatch" modules tests
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" EMS_config.yaml example_EMS_config.yaml modules tests docs README.md
```

Allowed remaining hits should be explicitly documented in the implementation notes, especially rejection tests, runtime absence tests, actuator current fields, and archive documents.

## Acceptance criteria

The later cleanup session is complete when:

1. Old surplus allocator API tests/helpers are removed or explicitly justified.
2. Legacy surplus device mapper tests/helpers are removed or explicitly justified.
3. Writer legacy fallback tests are consolidated to a small high-value set.
4. Dispatch state legacy sensor tests are consolidated if safe.
5. Dead EV current seed values are removed.
6. Misleading current-policy test names are renamed to watt-target semantics.
7. Stale migration docs are archived or shortened.
8. Valid watt-based policy and amp-based actuator protections remain.
9. Full `pytest -q` passes.
10. The final implementation notes list removed tests, removed helpers, renamed tests, and allowed remaining legacy/current references.
