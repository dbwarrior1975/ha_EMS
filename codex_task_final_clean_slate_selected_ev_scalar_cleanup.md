# Codex Task: Final Clean-Slate Pass — Remove Selected-EV Scalar View and Remaining Refactor Smell

## Goal

Finish the clean-slate architecture goal so the repository reads as if the current device/CoreConfig/target_w architecture was the original design.

The current intended architecture is:

```text
Grouped EMS_config.yaml
  -> CoreConfig
  -> runtime device registry
  -> device-native measurements
  -> device-based net-zero engine
  -> device_policies[device_id].target_w
  -> actuator writers
```

The remaining cleanup target is not functional correctness. The current business logic already works. The target is architectural clarity:

```text
No selected EV scalar compatibility view.
No test helper shorthand that implies relay1/relay2/charger scalar state.
No active docs/test names that talk about legacy/refactor history.
No current business logic that looks like it evolved from scalar relay/EV config.
```

---

## Architectural rule

Do not preserve historical concepts in active code, tests, or docs.

Current tests should assert what is valid now, not what used to be invalid or ignored.

Current code should expose current concepts directly, not via compatibility/scalar mirrors.

---

## Non-goals

Do not change EV watt-based business semantics.

Do not change selected surplus threshold semantics.

Do not change relay/battery behavior.

Do not reintroduce EV amp policy fields:

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

Do not remove valid EV current helper functions used at writer/debug/measured-state boundaries:

```text
ev_power_w_to_current_a
ev_current_a_to_power_w
ev_min_current_a_from_min_absorb_w
ev_max_current_a_from_max_absorb_w
```

Do not remove e2e actuator current assertions.

Do not remove internal trace fields merely because they include `current_a`, if they describe actuator output or measured actuator state.

---

# Phase 1: Inventory remaining scalar/refactor smell

Search the repository for:

```text
_cfg_with_selected_ev_scalars
ev_charger_phases
ev_voltage_v
ev_force_on
ev_current_step_a
ev_priority
adjustable_surplus_load
adjustable_primary_load
charger_on
charger_current_a
relay1_on
relay2_on
legacy
compat
scalar
EmsConfig
policy_ev_current_a
policy_relay1_command
policy_relay2_command
policy_battery_target_w
current_min_a
current_max_a
force_current_a
```

Classify each reference as:

```text
A. valid current architecture
B. selected-device scalar mirror to remove
C. test helper shorthand to rewrite
D. active docs/test names remembering refactor history
E. archived history allowed
F. external IO compatibility required
```

Remove or rewrite B, C, and D.

For F, document why it must remain.

---

# Phase 2: Remove selected EV scalar view

## Problem

The current engine still uses a selected EV scalar mirror through a helper such as:

```text
_cfg_with_selected_ev_scalars(...)
```

This creates fields like:

```text
ev_charger_phases
ev_voltage_v
ev_force_on
ev_current_step_a
ev_priority
adjustable_surplus_load
adjustable_primary_load
```

from the selected EV device.

This works, but it makes the architecture look like:

```text
CoreConfig.devices[EV]
  -> selected.ev_* scalar mirror
  -> engine/load_projection
```

The clean architecture should be:

```text
CoreConfig.devices[EV]
  -> selected EV device object/capabilities/policy/adapter
  -> engine/load_projection
```

## Tasks

1. Locate `_cfg_with_selected_ev_scalars(...)` and all call sites.
2. Remove the helper if possible.
3. Refactor EV engine/load_projection helpers to accept explicit device-native inputs:
   - selected EV device id
   - selected EV device config
   - capabilities
   - policy
   - adapter
   - selected EV runtime state
4. Avoid reading selected EV values through top-level `cfg.ev_*` scalar mirrors.
5. Keep global config values global only if they are truly global.
6. If some scalar fields are still needed temporarily, rename them to make scope explicit and add a removal note in progress. Preferred outcome is removal.

Preferred final shape:

```python
ev_strategy_target_w(
    ev_device=selected_ev,
    ev_state=selected_ev_state,
    measurements=m,
    ...
)
```

or equivalent.

Not preferred:

```python
ev_strategy_target_w(cfg_with_selected_ev_scalars, ...)
```

## Acceptance for this phase

Search should not find active use of:

```text
_cfg_with_selected_ev_scalars
```

EV decisions should not depend on selected EV values copied into top-level `cfg.ev_*` scalar fields.

---

# Phase 3: Make EV load projection device-native

## Problem

EV load projection and strategy should not require a scalar `cfg` view for EV-specific properties.

## Tasks

Inspect:

```text
modules/ems_core/net_zero/load_projection.py
modules/ems_core/engine.py
```

Refactor function signatures and internal logic so EV-specific data comes from device-native structures.

Ensure these semantics remain unchanged:

```text
force_on == true -> target_w == max_absorb_w
hard/off -> target_w == 0
NET_ZERO burn -> target_w == max_absorb_w
normal NET_ZERO stepping uses derived power step from current_step_a/phases/voltage_v
min/max target bounds use min_absorb_w/max_absorb_w
```

W/A conversion remains allowed only through EV power helpers and writer/debug/measured-state logic.

## Tests to keep/update

Keep tests for:

```text
force_on maps to max_absorb_w
hard_off maps to 0 W
restore/min behavior uses min_absorb_w
target_w stepping uses derived power step
writer converts target_w -> current_a
```

Rename any test names that imply core policy is current-based.

---

# Phase 4: Remove test helper scalar shorthands

## Problem

Production `RuntimeMeasurements` is now device-native, but some test helpers still accept scalar shorthand names:

```text
charger_on
charger_current_a
relay1_on
relay2_on
```

Those are converted into:

```text
ev_states[device_id]
relay_states[device_id]
```

This is functionally harmless, but it makes tests read like the old scalar architecture.

## Tasks

Inspect test helpers, especially:

```text
make_m(...)
tests/helpers.py
tests/unit/**
tests/contract/**
tests/e2e_entity/**
```

Remove helper parameters such as:

```text
charger_on
charger_current_a
relay1_on
relay2_on
```

Rewrite tests to provide device-native state directly:

```python
make_m(
    ev_states={
        "EV_CHARGER": {
            "enabled": True,
            "active": True,
            "current_a": 10.0,
        },
    },
    relay_states={
        "RELAY1": {"active": True},
        "RELAY2": {"active": False},
    },
)
```

If a helper is needed, create current-architecture helpers with explicit names:

```python
ev_state(enabled=True, active=True, current_a=10.0)
relay_state(active=True)
```

Do not keep scalar shorthand names.

## Acceptance for this phase

Search in active test code should not find test helper parameters:

```text
charger_on
charger_current_a
relay1_on
relay2_on
```

Exception: archived docs/history only.

---

# Phase 5: Remove active legacy/refactor vocabulary from docs and test names

## Problem

Active docs and test names still include vocabulary such as:

```text
legacy
compat
scalar
EmsConfig parity
legacy policy sensors
legacy sensor conflicts
```

Some of these were useful during migration but now conflict with the clean-slate goal.

## Tasks

Search active docs and tests for:

```text
legacy
compat
scalar
EmsConfig
refactor
migration
policy_ev_current_a
policy_relay1_command
policy_relay2_command
policy_battery_target_w
```

Handle findings:

1. If the content is historical, move it to:

```text
docs/archive/
```

2. If the content describes current architecture, rewrite it using current terms:
   - device registry
   - device_policies
   - target_w
   - runtime device state
   - policy_decision_trace
   - actuator_writer_trace

3. Rename tests whose names remember obsolete conflicts.

Example rename:

```text
test_dispatch_state_applier_uses_device_trace_when_legacy_sensor_conflicts
```

to:

```text
test_dispatch_state_applier_applies_device_trace_action
```

or:

```text
test_dispatch_state_applier_uses_device_trace_dispatch
```

## Acceptance for this phase

Active docs and test names should not read like migration notes.

Allowed remaining historical references:

```text
docs/archive/**
progress markdown explicitly labeled historical
```

---

# Phase 6: Review CoreConfig top-level fields

## Problem

`CoreConfig` may still contain top-level scalar fields that are actually selected-device mirrors rather than true global config.

Potential candidates:

```text
ev_charger_phases
ev_voltage_v
ev_force_on
ev_current_step_a
ev_priority
adjustable_surplus_load
adjustable_primary_load
```

Some fields may be genuinely global. Do not remove blindly.

## Tasks

Classify remaining `CoreConfig` top-level scalar fields:

```text
A. true global policy/engine setting
B. device-specific field that belongs under devices[device_id]
C. derived convenience/debug field
D. external IO compatibility field
```

Remove or migrate category B.

Document category A and D.

Preferred final state:

```text
CoreConfig has global EMS settings and devices.
Device-specific settings live under devices[device_id].
No selected-device scalar mirrors are part of normal engine input.
```

---

# Phase 7: Final repository search acceptance

Before finishing, run searches for these terms:

```text
_cfg_with_selected_ev_scalars
charger_on
charger_current_a
relay1_on
relay2_on
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

Expected:

## Must be absent from active code/tests/docs

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

## Should be absent from active test helper APIs

```text
charger_on
charger_current_a
relay1_on
relay2_on
```

Allowed only if:
- archived historical docs
- generated progress notes explicitly marked historical
- external IO compatibility with clear justification

Document every remaining reference.

---

# Phase 8: Tests and verification

Run targeted tests after each meaningful change.

Minimum final verification:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_ev_power.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/unit/test_dispatch_state_applier.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
pytest -q
```

If a test does not exist, skip it and record that in progress.

---

# Final acceptance criteria

This task is complete when:

1. `_cfg_with_selected_ev_scalars` is removed from active code.

2. EV engine/load_projection logic consumes selected EV data through device-native structures, not top-level selected EV scalar mirrors.

3. `RuntimeMeasurements` tests use `ev_states` and `relay_states`, not `charger_on`, `charger_current_a`, `relay1_on`, or `relay2_on` shorthand parameters.

4. Active docs and test names no longer present current behavior as a legacy/compatibility/refactor migration.

5. `CoreConfig` top-level fields are either true globals or explicitly justified external compatibility fields.

6. Device-specific configuration lives under `devices[device_id]`.

7. EV policy remains watt-native.

8. Writer remains the W -> A actuator boundary for EV.

9. Full test suite passes.

---

# Progress note required

Create or update a progress markdown section:

```text
Final Clean-Slate Pass: remove selected EV scalar view
```

For each phase, record:

```text
status
files changed
functions removed
function signatures changed
tests rewritten
tests renamed
docs moved or rewritten
remaining searched references
why each remaining reference is allowed
tests run and results
```

Do not claim completion if active business logic still depends on selected EV scalar mirrors.

Do not claim completion if active tests still use scalar measurement shorthand as the primary way to construct EV/relay state.
