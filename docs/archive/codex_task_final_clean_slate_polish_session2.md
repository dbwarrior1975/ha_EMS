# Codex Task: Final Clean-Slate Polish Cleanup Session

## Context

This task continues from `codex_task_final_clean_slate_polish.md`.

The codebase is already expected to be functionally correct. Do not redesign business logic. This session is for the remaining cleanup so the repository reads as if the current device-native, watt-based architecture was always the intended architecture.

Current expected baseline from the source task:

```text
pytest -q
243 passed, 1 xfailed
```

The selected-EV scalar mirror was removed earlier. The old helper must stay absent:

```text
_cfg_with_selected_ev_scalars
```

The current selected EV helper is:

```text
_selected_ev_context
```

## Target Architecture

Keep the architecture device-native:

```text
Grouped EMS_config.yaml
  -> CoreConfig
  -> runtime device registry
  -> device-native measurements
  -> device-based net-zero engine
  -> device_policies[device_id].target_w
  -> actuator writers
```

EV policy remains watt-native:

```text
min_absorb_w
max_absorb_w
force_on
target_w
```

EV current is valid only at conversion and IO boundaries:

```text
writer target_w -> current_a
EV power helper conversion
runtime/debug derived values
measured actuator state -> measured power estimate
e2e actuator output assertions
```

## Non-Goals

Do not change EV target semantics.

Do not change relay or battery semantics.

Do not change selected surplus threshold semantics.

Do not reintroduce historical EV amp-policy fields:

```text
adapter.current_min_a
adapter.current_max_a
adapter.force_current_a
ev_min_current_a
ev_max_current_a
ev_force_current_a
deprecated_current_min_a
deprecated_current_max_a
deprecated_force_current_a
```

Do not reintroduce legacy policy sensor tests:

```text
policy_ev_current_a
policy_relay1_command
policy_relay2_command
policy_battery_target_w
```

Do not remove valid EV power helpers:

```text
ev_power_w_to_current_a
ev_current_a_to_power_w
ev_min_current_a_from_min_absorb_w
ev_max_current_a_from_max_absorb_w
```

Do not remove e2e actuator current assertions.

## Work Plan

### 1. Fix per-EV measured power in `device_read_model.py`

Inspect:

```text
modules/ems_adapter/device_read_model.py
```

Find EV state construction in `build_device_states()` or the equivalent function.

Measured power for each EV charger must use that EV device's own adapter values:

```python
ev_current_a_to_power_w(
    current_a,
    device.adapter.phases,
    device.adapter.voltage_v,
)
```

Use safe numeric fallbacks:

```text
phases -> 1
voltage_v -> 230
```

Do not use these for per-device measured power:

```text
cfg.first_device_by_kind('EV_CHARGER')
_ev_phases(cfg)
_ev_voltage_v(cfg)
top-level cfg.ev_charger_phases
top-level cfg.ev_voltage_v
```

Remove `_ev_phases(cfg)` and `_ev_voltage_v(cfg)` if they become unused. If they remain for compatibility or debug output, document the reason in the final response.

Add or update a unit test with two EV devices:

```text
EV_A:
  phases = 1
  voltage_v = 230
  measured current = 10 A
  expected measured power = 2300 W

EV_B:
  phases = 3
  voltage_v = 230
  measured current = 10 A
  expected measured power = 6900 W
```

Also test missing or `None` adapter values if the existing test style supports it:

```text
missing/None phases -> fallback 1
missing/None voltage_v -> fallback 230
```

Do not add tests for historical amp-policy field names.

### 2. Keep selected-EV context clean

Search for:

```text
_cfg_with_selected_ev_scalars
ev_power_step_w(selected)
ev_power_step_w(selected_ev_cfg)
```

Acceptance:

```text
_cfg_with_selected_ev_scalars
```

must be absent.

Do not recompute EV power step from a partially initialized selected EV object. Prefer already-normalized context values such as:

```text
selected_ev.power_step_w
```

For trace/debug payloads, an existing normalized attribute fallback is acceptable:

```python
getattr(selected_ev, "ev_power_step_w", 0)
```

Keep or add a regression test that covers:

```text
adapter.phases = 1.0
adapter.voltage_v = 230.0
adapter.current_step_a = 1.0
selected EV context builds without calling EV power helper with None
```

If private helper testing is inappropriate, cover this through `compute_net_zero_engine_outputs()`.

### 3. Remove active refactor/legacy vocabulary from docs and test names

Search active docs and tests:

```text
README.md
docs/**
tests/**
```

for:

```text
legacy
compat
scalar
refactor
migration
EmsConfig
policy_ev_current_a
policy_relay1_command
policy_relay2_command
policy_battery_target_w
```

Rewrite active user/dev docs to current architecture vocabulary:

```text
device registry
runtime device state
device_policies
target_w
policy_decision_trace
actuator_writer_trace
```

Historical migration/refactor content belongs under:

```text
docs/archive/
```

Review at least:

```text
tests/e2e_entity/e2e_refactoring.md
docs/user/operointi.md
docs/dev/arkkitehtuuri.md
README.md
```

Rename stale test names instead of deleting useful tests. Example:

```text
test_dispatch_state_applier_uses_device_trace_when_legacy_sensor_conflicts
```

should become something current-architecture oriented, for example:

```text
test_dispatch_state_applier_uses_device_trace_dispatch
```

Allowed remaining historical vocabulary only in:

```text
docs/archive/**
progress notes clearly marked historical
```

### 4. Review CoreConfig top-level EV convenience fields

Search for:

```text
ev_charger_phases
ev_voltage_v
ev_force_on
ev_current_step_a
ev_priority
```

Classify each remaining use:

```text
A. active business logic dependency
B. trace/debug only
C. test helper only
D. unused
E. external IO compatibility
```

Remove unused fields.

For active business logic dependencies, prefer replacing them with device-native reads from:

```text
cfg.devices[device_id].adapter
cfg.devices[device_id].policy
cfg.devices[device_id].capabilities
```

Do not make this phase overly invasive. If removal would require broader engine redesign, leave the field in place and explicitly document why it remains.

Acceptance:

```text
No selected-EV business logic depends on top-level EV scalar mirrors.
Remaining top-level EV fields are trace/debug/test/external compatibility only, or explicitly justified.
```

### 5. Final repository searches

Before finishing, run searches for:

```text
_cfg_with_selected_ev_scalars
legacy_relay_flags
policy_ev_current_a
policy_relay1_command
policy_relay2_command
policy_battery_target_w
current_min_a
current_max_a
force_current_a
ev_min_current_a
ev_max_current_a
ev_force_current_a
deprecated_current_min_a
deprecated_current_max_a
deprecated_force_current_a
```

These must be absent from active code/tests/docs. They are allowed only in:

```text
docs/archive/**
progress notes clearly marked historical
```

Also search:

```text
legacy
compat
scalar
refactor
migration
EmsConfig
```

These should not appear in active docs or test names unless clearly justified.

Document any remaining references and why they are allowed.

## Verification Commands

Run targeted tests first:

```bash
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_ev_power.py
pytest -q tests/unit/test_dispatch_state_applier.py
pytest -q tests/unit/test_core_config.py
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
```

Then run the full suite:

```bash
pytest -q
```

## Final Acceptance Criteria

The cleanup is complete when:

1. EV measured power in `device_read_model.py` uses each EV device's own adapter phases and voltage.
2. Multi-EV measured power tests prove per-device phases/voltage are respected.
3. `_cfg_with_selected_ev_scalars` remains absent.
4. EV power step is not recomputed from partially initialized selected EV objects.
5. Active writer/dispatch/engine tests do not mention obsolete legacy policy sensor names.
6. Active docs/test names no longer describe current behavior as legacy/refactor compatibility.
7. Top-level EV convenience fields are removed or explicitly justified as trace/debug/external compatibility.
8. EV watt-policy semantics remain unchanged.
9. Full test suite passes.

## Final Response Requirements For Next Session

In the final response, report:

```text
Changed files
Behavioral changes, if any
Remaining justified legacy/compat/scalar/refactor references
Targeted test results
Full pytest result
```
