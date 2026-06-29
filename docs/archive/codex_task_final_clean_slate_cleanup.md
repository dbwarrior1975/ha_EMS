# Codex Task: Final Clean-Slate Architecture Cleanup

## Goal

Finish the next clean-slate cleanup pass after the EV/device/CoreConfig refactors.

The current business architecture should look intentional and current, not like it still remembers rejected interim concepts.

This task has four concrete goals:

```text
1. Remove policy_outputs.surplus_dispatch_decision from the active config contract.
2. Remove legacy policy sensor ENT keys and related guard tests from writer tests.
3. Add generic strict unknown-field validation without mentioning historical EV field names.
4. Remove RuntimeMeasurements relay1/relay2/charger scalar dependency and device_read_model legacy_relay_flags.
```

The result should preserve current business behavior while removing compatibility/refactor artifacts.

---

## Architectural principles

Current architecture:

```text
Grouped EMS_config.yaml
  -> CoreConfig
  -> runtime device registry
  -> device-based policy engine
  -> device_policies with target_w
  -> actuator writers
```

EV_CHARGER policy is watt-native:

```text
min_absorb_w
max_absorb_w
force_on
target_w
```

EV current is valid only in:

```text
writer target_w -> current_a conversion
EV power helper tests
runtime/debug derived current fields
measured actuator state -> estimated measured power
e2e actuator output assertions
```

Do not reintroduce rejected historical EV policy fields:

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

Do not add tests that explicitly mention those historical field names.

---

## Non-goals

Do not change core EV watt-based semantics.

Do not change selected surplus threshold semantics.

Do not change relay business semantics.

Do not remove valid EV current helpers:

```text
ev_power_w_to_current_a
ev_current_a_to_power_w
ev_min_current_a_from_min_absorb_w
ev_max_current_a_from_max_absorb_w
```

Do not remove e2e actuator current assertions.

Do not remove current `policy_decision_trace` / `device_policy` functionality.

---

# Phase 1: Remove policy_outputs.surplus_dispatch_decision from active config contract

## Problem

The config still requires or exposes:

```yaml
policy_outputs:
  surplus_dispatch_decision: sensor.ems_net_zero_surplus_dispatch_decision_pyscript
```

But the current dispatch information is already carried through policy decision trace attributes such as:

```text
surplus_device_dispatch_action
surplus_device_dispatch_target
surplus_device_dispatch_device_id
```

The standalone `surplus_dispatch_decision` policy output appears to be a stale output contract.

## Tasks

Search for:

```text
surplus_dispatch_decision
ems_net_zero_surplus_dispatch_decision
```

Remove it from active config contract:

```text
CorePolicyOutputsConfig
config validation requirements
EMS_config.yaml
example_EMS_config.yaml
tests/e2e_entity/**/EMS_config.yaml
tests/helpers.py
contract tests expecting this output
docs that describe it as an active output
```

If an internal `outputs.surplus_dispatch_decision` field still exists and is genuinely used inside engine output/trace, either:

```text
A. remove it if unused
B. keep it only as internal trace data, not as a required HA policy output entity
```

Preferred final state:

```text
No required policy_outputs.surplus_dispatch_decision in user config.
Dispatch decision details are exposed through policy_decision_trace/device trace attributes.
```

## Verification

Run:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
```

---

# Phase 2: Remove legacy policy sensor ENT keys from writer tests

## Problem

Writer tests still seed legacy policy sensor keys such as:

```text
policy_battery_target_w
policy_ev_current_a
policy_relay1_command
policy_relay2_command
```

Some tests exist mainly to prove that writer ignores these old sensors.

That is no longer useful under the clean-slate architecture goal. Writer tests should describe the current contract:

```text
writer consumes device_policies
writer writes actuator entities
writer skips without device_policy
```

They should not keep memory of obsolete policy sensor concepts.

## Tasks

Inspect:

```text
tests/unit/test_writer_semantics.py
```

Remove or rewrite tests whose main purpose is:

```text
writer ignores legacy policy sensors
device_policy wins over legacy policy sensors
writer does not fallback to legacy command/current sensors
```

Remove test ENT seed values such as:

```text
policy_battery_target_w
policy_ev_current_a
policy_relay1_command
policy_relay2_command
```

Keep or rewrite tests around current behavior:

```text
without device_policy -> writer skips
with EV device_policy target_w -> writer writes supported current_a
with RELAY device_policy target_w > 0 -> writer turns relay on
with RELAY device_policy target_w == 0 -> writer turns relay off
with BATTERY device_policy target_w -> writer writes correct battery command
mode skip/off/hard_off semantics are respected
```

Preferred final state:

```text
Writer tests do not know about obsolete policy sensor names.
Writer tests only assert current device_policy-based behavior.
```

## Verification

Run:

```bash
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/e2e_entity/
```

---

# Phase 3: Add generic strict unknown-field validation

## Problem

The clean-slate approach removed custom migration errors for historical fields.

However, the grouped config should still reject unknown fields generically. Otherwise obsolete or misspelled fields can silently remain in YAML without affecting runtime.

The validation must be generic. It must not mention historical EV field names.

## Tasks

Add strict unknown-field validation for grouped config sections.

At minimum, validate unknown keys under:

```text
ems
ems.devices.<device_id>
ems.devices.<device_id>.capabilities
ems.devices.<device_id>.policy
ems.devices.<device_id>.adapter
policy_outputs
```

Use current supported fields only.

For example, EV_CHARGER adapter supports:

```text
enabled
current_a
current_step_a
phases
voltage_v
```

EV_CHARGER capabilities supports:

```text
min_absorb_w
max_absorb_w
```

EV_CHARGER policy supports:

```text
force_on
surplus_allowed if currently supported by shared policy model
```

RELAY and BATTERY must similarly allow only their current fields.

## Tests

Add generic unknown-field tests that use neutral names, not historical EV field names.

Good test examples:

```yaml
ems:
  devices:
    EV:
      kind: EV_CHARGER
      adapter:
        unexpected_field: input_number.foo
```

```yaml
ems:
  devices:
    RELAY1:
      kind: RELAY
      policy:
        extra_policy_flag: input_boolean.foo
```

Expected behavior:

```text
validation fails
error identifies the unknown path generically
```

Example acceptable error style:

```text
Unknown config field: ems.devices.EV.adapter.unexpected_field
```

Do not add tests that mention:

```text
current_min_a
current_max_a
force_current_a
```

Preferred final state:

```text
Unknown fields are rejected by generic schema validation.
Historical field names are not remembered in active tests or custom validation branches.
```

## Verification

Run:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
```

---

# Phase 4: Remove RuntimeMeasurements relay1/relay2/charger scalar dependency and legacy_relay_flags

## Problem

Runtime measurements still expose or depend on scalar fields such as:

```text
charger_on
charger_current_a
relay1_on
relay2_on
```

The current architecture should use device-id-native maps:

```text
ev_states[device_id]
relay_states[device_id]
```

`device_read_model.py` also contains:

```text
legacy_relay_flags
```

This is a clear remaining refactor artifact.

## Tasks

Inspect:

```text
modules/ems_core/domain/models.py
modules/ems_core/engine.py
modules/ems_core/net_zero/load_projection.py
modules/ems_adapter/device_read_model.py
modules/ems_runtime/ems_policy_engine.py
```

Replace scalar relay/EV measurement dependency with device-state maps.

Target model:

```text
RuntimeMeasurements.ev_states[device_id]
RuntimeMeasurements.relay_states[device_id]
```

Remove primary business dependency on:

```text
m.charger_on
m.charger_current_a
m.relay1_on
m.relay2_on
```

If some transition helper requires a selected EV, use explicit selected-device structures:

```text
selected_ev_device_id
selected_ev_state
```

Do not use generic scalar names like `charger_current_a` as the primary model.

Remove from `device_read_model.py`:

```text
legacy_relay_flags
```

Relay states should come from:

```text
m.relay_states[device_id]
```

If a relay state is missing, handle it through the current availability/unwired semantics.

Preferred final state:

```text
RuntimeMeasurements is device-id-native for relay and EV runtime state.
device_read_model has no legacy_relay_flags.
Core business logic does not depend on relay1/relay2/charger scalar measurement fields.
```

## Verification

Run:

```bash
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/e2e_entity/
```

---

# Phase 5: Repository search acceptance

Before finishing, run searches for:

```text
surplus_dispatch_decision
ems_net_zero_surplus_dispatch_decision
policy_ev_current_a
policy_relay1_command
policy_relay2_command
policy_battery_target_w
legacy_relay_flags
relay1_on
relay2_on
charger_on
charger_current_a
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

Expected result:

## Must be absent from active code/tests/docs

```text
policy_ev_current_a
policy_relay1_command
policy_relay2_command
policy_battery_target_w
legacy_relay_flags
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

## May remain only if justified

```text
surplus_dispatch_decision
relay1_on
relay2_on
charger_on
charger_current_a
```

Allowed only if:

```text
they are internal trace/backward-compatible external IO fields,
not primary business logic dependencies
```

Prefer removing them from primary business logic.

Document any remaining references in the progress markdown with justification.

---

# Final acceptance criteria

The task is complete when:

1. `policy_outputs.surplus_dispatch_decision` is no longer required or documented as an active user config output.

2. Dispatch decision details are exposed through current trace/device-policy mechanisms.

3. Writer tests no longer seed or assert obsolete legacy policy sensor keys.

4. Writer tests describe only current `device_policies` behavior.

5. Generic unknown-field validation exists for grouped config.

6. Unknown-field validation tests use neutral field names, not historical EV field names.

7. Runtime measurement logic is device-id-native for EV and relay state.

8. `legacy_relay_flags` is removed.

9. No active tests or validation branches explicitly preserve historical EV amp-policy fields.

10. Full test suite passes.

---

# Verification commands

Run targeted tests after each phase and then full suite:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
pytest -q
```

---

# Progress note required

Update or create a progress markdown section:

```text
Final Clean-Slate Cleanup: policy outputs, writer tests, strict schema, device-native measurements
```

For each phase, record:

```text
status
files changed
functions/fields removed
tests removed
tests rewritten
tests added
tests run
remaining references to searched terms
why each remaining reference is allowed
```

Do not claim completion if historical EV amp-policy fields remain in active tests, active docs, validation branches, or business logic.
