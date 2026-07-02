# Codex task: lock EMS canonical output and diagnostics entity IDs

## Purpose

After the policy-engine timer-loop refactor, runtime input entity IDs are now config-driven read targets sampled by the policy loop timer. That solves the old mismatch where runtime inputs were configurable in grouped config but still hardcoded in Pyscript `@state_trigger` decorators.

However, the same reasoning does **not** apply to EMS canonical output bus entities.

These surfaces are currently shown in config:

```yaml
policy_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript

diagnostics_outputs:
  policy_diagnostics: sensor.ems_policy_diagnostics_pyscript
  actuator_writer_trace: sensor.ems_actuator_writer_trace
  dispatch_state_applier_trace: sensor.ems_dispatch_state_applier_trace
```

The `policy_outputs` surfaces are not ordinary user-renamable outputs. They are EMS internal canonical command/state bus surfaces.

If a user changes:

```yaml
policy_outputs:
  device_policies: sensor.my_custom_device_policies
```

then the policy engine may publish to the custom entity, but the actuator writer may still be hardcoded to trigger from:

```text
sensor.ems_device_policies_pyscript
```

That would break the command chain.

Therefore these entity IDs must be treated as fixed canonical EMS surfaces unless the downstream writer/dispatch trigger layer also becomes dynamic. This task chooses the safer clean-slate approach: **lock them**.

## Scope

This task only updates the config contract and documentation for EMS output surfaces.

Do not reopen the policy-engine timer-loop refactor.

Do not change NET_ZERO formulas.

Do not change E2E business expected values.

Do not make writer/dispatch triggers dynamic in this task.

## Required contract

### Runtime inputs

Runtime inputs remain config-driven read targets:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  pv_power_w: sensor.pv_instant_power_w
```

These may be user-configurable because the policy engine samples them through grouped config on the timer.

### Policy engine

Policy engine interval remains configurable:

```yaml
policy_engine:
  interval_seconds: 5
```

### Canonical policy outputs

These must be fixed EMS internal bus surfaces:

```yaml
policy_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript
```

They are not user-overridable unless the downstream trigger layer is also changed.

### Diagnostics outputs

For now, diagnostics outputs should also be fixed to avoid documentation, dashboard, and test ambiguity:

```yaml
diagnostics_outputs:
  policy_diagnostics: sensor.ems_policy_diagnostics_pyscript
  actuator_writer_trace: sensor.ems_actuator_writer_trace
  dispatch_state_applier_trace: sensor.ems_dispatch_state_applier_trace
```

These are less dangerous than `policy_outputs`, but keeping them fixed makes the surface contract easier for users and future developers.

## Preferred implementation

Use one of these two approaches.

### Option A: keep config keys but validate exact canonical values

If the config still contains `policy_outputs` and `diagnostics_outputs`, validate that the values exactly match the canonical EMS entity IDs.

Valid:

```yaml
policy_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript
```

Invalid:

```yaml
policy_outputs:
  device_policies: sensor.my_custom_device_policies
```

Expected error:

```text
policy_outputs.device_policies is a fixed EMS canonical bus entity.
Expected: sensor.ems_device_policies_pyscript
Got: sensor.my_custom_device_policies
```

Do the same for `dispatch_command`, `policy_state`, and the diagnostics outputs.

### Option B: remove output sections from user config entirely

Remove `policy_outputs` and `diagnostics_outputs` from user-facing config examples and define them in code as constants.

Example:

```python
CANONICAL_POLICY_OUTPUTS = {
    "device_policies": "sensor.ems_device_policies_pyscript",
    "dispatch_command": "sensor.ems_surplus_dispatch_command_pyscript",
    "policy_state": "sensor.ems_policy_state_pyscript",
}

CANONICAL_DIAGNOSTICS_OUTPUTS = {
    "policy_diagnostics": "sensor.ems_policy_diagnostics_pyscript",
    "actuator_writer_trace": "sensor.ems_actuator_writer_trace",
    "dispatch_state_applier_trace": "sensor.ems_dispatch_state_applier_trace",
}
```

The loader then populates the runtime registry from constants.

This is the cleaner long-term model, but it may require more mechanical config/test updates.

### Recommendation

Prefer **Option A** if you want the smallest safe follow-up after the timer-loop commit.

Prefer **Option B** if the cleanup is small and tests make it safe.

Do not leave the current ambiguous state where config appears to allow arbitrary output entity IDs while writer/dispatch triggers still assume fixed canonical names.

## Validation rules

Add config validation for:

```text
policy_outputs.device_policies
policy_outputs.dispatch_command
policy_outputs.policy_state
diagnostics_outputs.policy_diagnostics
diagnostics_outputs.actuator_writer_trace
diagnostics_outputs.dispatch_state_applier_trace
```

Rules:

```text
- missing policy_outputs section:
    acceptable only if loader fills canonical defaults from code

- missing diagnostics_outputs section:
    acceptable only if loader fills canonical defaults from code

- matching canonical value:
    accepted

- different entity ID:
    hard validation error

- unknown key:
    hard validation error

- wrong type / non-string value:
    hard validation error
```

Use clear error messages that explain these are fixed EMS surfaces.

## Required canonical constants

Define canonical output IDs in one place.

Suggested module, depending on current layout:

```text
modules/ems_core/domain/constants.py
```

or equivalent.

Suggested constants:

```python
CANONICAL_POLICY_OUTPUT_DEVICE_POLICIES = "sensor.ems_device_policies_pyscript"
CANONICAL_POLICY_OUTPUT_DISPATCH_COMMAND = "sensor.ems_surplus_dispatch_command_pyscript"
CANONICAL_POLICY_OUTPUT_POLICY_STATE = "sensor.ems_policy_state_pyscript"

CANONICAL_DIAGNOSTICS_POLICY = "sensor.ems_policy_diagnostics_pyscript"
CANONICAL_DIAGNOSTICS_ACTUATOR_WRITER_TRACE = "sensor.ems_actuator_writer_trace"
CANONICAL_DIAGNOSTICS_DISPATCH_STATE_APPLIER_TRACE = "sensor.ems_dispatch_state_applier_trace"
```

or grouped dict constants.

Avoid duplicating these strings across loader, Pyscript files, tests, and docs.

## Important architectural distinction to document

Document this clearly:

```text
runtime:
  user-configurable read targets sampled by policy_engine timer

policy_engine:
  user-configurable scheduler settings

policy_outputs:
  fixed canonical EMS command/state bus surfaces

diagnostics_outputs:
  fixed EMS diagnostic surfaces for now
```

Do not describe `policy_outputs` as ordinary user-configurable entity IDs.

## Writer/dispatch trigger note

Do not change these triggers in this task unless already necessary for a failing test:

```text
sensor.ems_device_policies_pyscript -> actuator writer
sensor.ems_surplus_dispatch_command_pyscript -> dispatch state applier
sensor.ems_policy_state_pyscript -> policy previous-state input
```

The point of this task is to align config semantics with current trigger reality.

If future work wants dynamic output bus entities, that must be a separate architecture task that includes dynamic writer/dispatch trigger registration.

## Documentation updates

Update active docs to state:

```text
EMS canonical output bus entity IDs are fixed.
They are intentionally not user-renamable because downstream Pyscript writer
and dispatch triggers consume those canonical surfaces.
```

Update at least:

```text
README.md
docs/dev/arkkitehtuuri.md
docs/dev/ems_step_model.md
docs/dev/testausautomaatio.md
tests/e2e_entity/e2e_conventions.md
example_EMS_config.yaml
EMS_config.yaml
```

If `policy_outputs` / `diagnostics_outputs` remain in config examples, add a comment:

```yaml
# Fixed EMS canonical surfaces. Do not rename unless the downstream trigger layer is changed too.
policy_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript
```

For diagnostics:

```yaml
# Fixed EMS diagnostic surfaces used by docs, dashboards and tests.
diagnostics_outputs:
  policy_diagnostics: sensor.ems_policy_diagnostics_pyscript
  actuator_writer_trace: sensor.ems_actuator_writer_trace
  dispatch_state_applier_trace: sensor.ems_dispatch_state_applier_trace
```

## Tests to add/update

### Config validation tests

Add tests for canonical policy outputs:

```text
test_policy_outputs_defaults_to_canonical_values_if_missing
test_policy_outputs_accepts_exact_canonical_values
test_policy_outputs_rejects_custom_device_policies_entity
test_policy_outputs_rejects_custom_dispatch_command_entity
test_policy_outputs_rejects_custom_policy_state_entity
test_policy_outputs_rejects_unknown_key
test_policy_outputs_rejects_non_string_value
```

Add tests for diagnostics outputs:

```text
test_diagnostics_outputs_defaults_to_canonical_values_if_missing
test_diagnostics_outputs_accepts_exact_canonical_values
test_diagnostics_outputs_rejects_custom_policy_diagnostics_entity
test_diagnostics_outputs_rejects_custom_actuator_writer_trace_entity
test_diagnostics_outputs_rejects_custom_dispatch_state_applier_trace_entity
test_diagnostics_outputs_rejects_unknown_key
test_diagnostics_outputs_rejects_non_string_value
```

### Runtime registry tests

Add or update tests proving the registry uses canonical output entity IDs after config loading.

Expected:

```text
entities['device_policies'] == sensor.ems_device_policies_pyscript
entities['dispatch_command'] == sensor.ems_surplus_dispatch_command_pyscript
entities['policy_state'] == sensor.ems_policy_state_pyscript
entities['policy_diagnostics'] == sensor.ems_policy_diagnostics_pyscript
entities['actuator_writer_trace'] == sensor.ems_actuator_writer_trace
entities['dispatch_state_applier_trace'] == sensor.ems_dispatch_state_applier_trace
```

### Trigger/source tests

Add source tests or grep checks proving canonical writer/dispatch triggers still target the canonical surfaces:

```text
sensor.ems_device_policies_pyscript
sensor.ems_surplus_dispatch_command_pyscript
```

Do not require these triggers to become dynamic.

## Grep checks

Run:

```bash
rg "policy_outputs|diagnostics_outputs" EMS_config.yaml example_EMS_config.yaml docs tests modules ems_*.py
```

Expected:

```text
- config examples either omit these sections or show fixed canonical values
- docs describe them as fixed surfaces
- tests validate rejection of custom values
```

Run:

```bash
rg "sensor\.ems_device_policies_pyscript|sensor\.ems_surplus_dispatch_command_pyscript|sensor\.ems_policy_state_pyscript" ems_*.py modules tests docs
```

Expected:

```text
- canonical constants
- writer/dispatch triggers
- config examples
- docs explaining stable bus surfaces
```

Suspicious:

```text
- duplicated literal strings spread across many files instead of shared constants
- docs saying these are user-renamable
```

Run:

```bash
rg "sensor\.my_custom_device_policies|custom_device_policies|custom_dispatch_command|custom_policy_state" tests docs
```

Expected:

```text
Only rejection tests or examples explaining invalid config.
```

## Acceptance criteria

### Functional

```text
- policy_outputs are not user-overridable.
- diagnostics_outputs are not user-overridable, or are explicitly validated as fixed for now.
- Missing output sections either default to canonical constants or are required with exact values.
- Custom entity IDs fail config validation with clear errors.
- Runtime registry still resolves all output surfaces to canonical entity IDs.
- Writer/dispatch triggers continue to consume the canonical output sensors.
```

### Safety

```text
- No changes to NET_ZERO formulas.
- No changes to policy-engine timer-loop behavior.
- No E2E business expected values changed.
- No dynamic writer/dispatch trigger registration introduced.
- No removal of canonical hash-state sensors.
```

### Documentation

```text
- Active docs distinguish runtime inputs from canonical output bus surfaces.
- Docs no longer imply policy_outputs are user-renamable.
- Config examples either omit output surfaces or mark them as fixed.
```

### Tests

Run:

```bash
python3 -m pytest -q tests/unit/test_config_loader.py
python3 -m pytest -q tests/unit/test_core_config.py
python3 -m pytest -q tests/contract
python3 -m pytest -q tests/e2e_entity
python3 -m pytest -q
```

Use the repository-standard wrapper if applicable.

## Non-goals

Do not do these in this task:

```text
- do not make writer triggers dynamic;
- do not redesign canonical bus surfaces;
- do not remove hash-state canonical outputs;
- do not change timer-loop scheduling;
- do not change runtime input config behavior;
- do not change device policy or actuator expected values;
- do not change NET_ZERO derived-input formulas;
- do not split device_policies attrs vs diagnostics attrs in this task unless it is already trivial and separately tested.
```

## Final desired state

The config contract should be easy to explain:

```text
runtime:
  configurable input read targets

policy_engine:
  configurable timer cadence

policy_outputs:
  fixed EMS internal command/state bus surfaces

diagnostics_outputs:
  fixed EMS diagnostics surfaces
```

This removes the current ambiguity without expanding scope into dynamic writer/dispatch trigger registration.
