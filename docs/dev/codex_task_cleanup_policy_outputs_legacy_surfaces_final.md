# Codex task: Clean-slate cleanup of policy outputs and legacy refactor leftovers

## Context

EMS/Pyscript has been refactored away from using `sensor.ems_policy_decision_trace_pyscript` as an accidental command/state bus.

Current intended runtime contract:

```text
sensor.ems_device_policies_pyscript
  -> actuator_writer canonical input

sensor.ems_surplus_dispatch_command_pyscript
  -> dispatch_state_applier canonical input

sensor.ems_policy_state_pyscript
  -> policy_engine previous-state input
```

Canonical runtime sensors now use **content-hash state values** instead of monotonic counters:

```text
device_policies_hash / device_policies_version
dispatch_command_hash / dispatch_command_version
policy_state_hash / policy_state_version
```

The next cleanup must be done as a **clean-slate breaking refactor**. This EMS installation is still under controlled development use, so do not preserve old dashboard entities or old config names for compatibility. The operator can handle config/dashboard transitions manually.

---

## Goal

Remove unnecessary legacy outputs and refactor leftovers in one pass.

Final architecture must have only two output categories:

1. **Runtime contract outputs** — required for normal production control.
2. **Diagnostics outputs** — useful for explanation/debug, never used as a command/state bus.

There must be no `legacy_dashboard_outputs` section, no optional legacy surplus summary sensor support, and no compatibility fallback to the old `decision_trace` name.

---

## Desired final config shape

### Required production runtime outputs

```yaml
policy_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript
```

These three are the only policy outputs required for normal control.

### Diagnostics outputs

Rename the old `decision_trace` concept into a diagnostics-oriented name.

Preferred final config:

```yaml
diagnostics_outputs:
  policy_diagnostics: sensor.ems_policy_diagnostics_pyscript
  actuator_writer_trace: sensor.ems_actuator_writer_trace
  dispatch_state_applier_trace: sensor.ems_dispatch_state_applier_trace
```

Alternative acceptable policy diagnostics entity name if it fits the codebase better:

```yaml
diagnostics_outputs:
  policy_explanation: sensor.ems_policy_explanation_pyscript
```

Do **not** keep `policy_outputs.decision_trace` as an alias. Do **not** publish `sensor.ems_policy_decision_trace_pyscript` anymore.

### Removed legacy dashboard outputs

Delete support for these old one-field surplus summary outputs completely:

```yaml
surplus_policy_active: binary_sensor.ems_net_zero_surplus_policy_active_pyscript
surplus_next_target: sensor.ems_net_zero_surplus_next_target_pyscript
surplus_next_threshold: sensor.ems_net_zero_surplus_next_threshold_kw_pyscript
surplus_release_candidate: sensor.ems_net_zero_surplus_release_candidate_pyscript
surplus_explanation: sensor.ems_net_zero_surplus_explanation_pyscript
```

Do not move these under `legacy_dashboard_outputs`. Do not make them optional. Remove publication, config fields, readiness checks, tests, docs, and examples for these standalone entities.

Equivalent information may remain inside `policy_diagnostics` attributes and/or `dispatch_command` attributes.

---

## Required implementation work

### 1. Refactor config model as a breaking cleanup

Find the current config classes / loaders for `policy_outputs`.

Expected current shape likely includes fields like:

```text
decision_trace
device_policies
dispatch_command
policy_state
surplus_policy_active
surplus_next_target
surplus_next_threshold
surplus_release_candidate
surplus_explanation
actuator_writer_trace
```

Change the model so only these are valid/required under `policy_outputs`:

```text
device_policies
dispatch_command
policy_state
```

Add a separate diagnostics config object:

```text
diagnostics_outputs.policy_diagnostics
diagnostics_outputs.actuator_writer_trace
diagnostics_outputs.dispatch_state_applier_trace
```

Clean-slate requirements:

- Do not support `policy_outputs.decision_trace`.
- Do not map old `policy_outputs.decision_trace` to `diagnostics_outputs.policy_diagnostics`.
- Do not support old `policy_outputs.actuator_writer_trace`.
- Do not support old surplus summary outputs.
- Do not emit deprecation warnings; this is not a compatibility release.
- If old fields remain in config, fail clearly during config validation with an actionable error.

Suggested validation error style:

```text
Unsupported legacy policy_outputs field: decision_trace. Use diagnostics_outputs.policy_diagnostics instead.
```

and:

```text
Unsupported legacy policy_outputs field: surplus_policy_active. Standalone surplus summary sensors were removed; use policy_diagnostics or dispatch_command attributes instead.
```

---

### 2. Rename policy decision trace entity

Rename the published policy diagnostics entity from:

```text
sensor.ems_policy_decision_trace_pyscript
```

to preferred:

```text
sensor.ems_policy_diagnostics_pyscript
```

The entity can keep broadly the same attributes, but it must be clearly treated as diagnostics only.

Recommended attributes to include:

```text
diagnostics_contract: policy_explanation_only
runtime_contract: false
policy_output_contract: device_policy_primary
policy_trace_canonical_contract: device_policies

device_policies_hash
device_policies_state_kind
device_policies_version

dispatch_command_hash if available/relevant
policy_state_hash if available/relevant
```

Do not publish the old entity name as a duplicate mirror.

Do not use this diagnostics entity as the canonical source for writer, dispatch applier, or policy previous-state.

---

### 3. Remove runtime fallback dependency on old decision_trace

Audit and remove fallback reads from the old trace entity.

Important grep targets:

```bash
rg "policy_decision_trace|decision_trace|ems_policy_decision_trace" .
rg "policy_diagnostics|policy_explanation|diagnostics_outputs" .
rg "policy_outputs" modules ems_*.py tests docs
rg "surplus_policy_active|surplus_next_target|surplus_next_threshold|surplus_release_candidate|surplus_explanation" .
rg "policy_source_reason|dispatch_source_reason" .
```

Expected runtime behavior:

- `actuator_writer` reads only `sensor.ems_device_policies_pyscript`.
- `dispatch_state_applier` reads only `sensor.ems_surplus_dispatch_command_pyscript`.
- `policy_engine` reads only `sensor.ems_policy_state_pyscript` for previous HAEO/force-on state.
- `policy_diagnostics` is never required for normal control.

Final expected diagnostics:

```text
policy_source_reason: canonical
dispatch_source_reason: canonical
```

Do not retain fallback source reasons such as:

```text
fallback_policy_decision_trace
fallback_deprecated_policy_diagnostics
legacy_trace
```

If canonical runtime input is missing or invalid, fail safe and report the canonical source error in writer/dispatch diagnostics. Do not silently fall back to diagnostics payloads.

---

### 4. Delete legacy surplus summary sensors

Completely remove these standalone publication targets:

```text
binary_sensor.ems_net_zero_surplus_policy_active_pyscript
sensor.ems_net_zero_surplus_next_target_pyscript
sensor.ems_net_zero_surplus_next_threshold_kw_pyscript
sensor.ems_net_zero_surplus_release_candidate_pyscript
sensor.ems_net_zero_surplus_explanation_pyscript
```

Remove all related:

- config fields
- dataclass/model fields
- default config entries
- YAML examples
- grouped production readiness requirements
- publication calls
- tests that assert these entities exist
- docs that describe them as outputs
- dashboard compatibility language

Keep the underlying diagnostic facts only where useful inside:

```text
sensor.ems_policy_diagnostics_pyscript attributes
sensor.ems_surplus_dispatch_command_pyscript attributes
```

Do not create a `legacy_dashboard_outputs` section.

---

### 5. Update tests

Add or update tests for these contracts.

#### Required runtime-only config test

A config containing only this under `policy_outputs` must load and be production-ready:

```yaml
policy_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript
```

Expected:

```text
config_grouped_production_ready: true
no missing decision_trace error
no missing surplus summary output error
```

#### Diagnostics config test

A config containing diagnostics under the new section must load:

```yaml
diagnostics_outputs:
  policy_diagnostics: sensor.ems_policy_diagnostics_pyscript
  actuator_writer_trace: sensor.ems_actuator_writer_trace
  dispatch_state_applier_trace: sensor.ems_dispatch_state_applier_trace
```

Expected:

```text
policy diagnostics publication target = sensor.ems_policy_diagnostics_pyscript
writer trace target = sensor.ems_actuator_writer_trace
dispatch trace target = sensor.ems_dispatch_state_applier_trace
```

#### Legacy config rejection tests

Old config must fail clearly if it still contains removed fields:

```yaml
policy_outputs:
  decision_trace: sensor.ems_policy_decision_trace_pyscript
```

Expected error includes:

```text
Unsupported legacy policy_outputs field: decision_trace
```

Old surplus summary outputs must also fail clearly:

```yaml
policy_outputs:
  surplus_policy_active: binary_sensor.ems_net_zero_surplus_policy_active_pyscript
  surplus_next_target: sensor.ems_net_zero_surplus_next_target_pyscript
  surplus_next_threshold: sensor.ems_net_zero_surplus_next_threshold_kw_pyscript
  surplus_release_candidate: sensor.ems_net_zero_surplus_release_candidate_pyscript
  surplus_explanation: sensor.ems_net_zero_surplus_explanation_pyscript
```

Expected error mentions unsupported legacy surplus summary fields.

#### Runtime source tests

Assert writer and dispatch applier use canonical sensors only:

```text
actuator_writer_trace.policy_source_reason == canonical
dispatch_state_applier_trace.dispatch_source_reason == canonical
```

No test should depend on `policy_decision_trace` or `policy_diagnostics` as command/state source.

#### E2E device policies tests

Update test helpers so device policy expectations read:

```text
sensor.ems_device_policies_pyscript
```

not the diagnostics trace mirror.

This was a known clean-slate leftover.

#### Hash-state tests must still pass

Keep/strengthen tests that verify:

```text
same semantic device_policies payload -> same device_policies_hash
changed device_policies payload -> changed device_policies_hash
same dispatch payload -> same dispatch_command_hash
changed dispatch payload -> changed dispatch_command_hash
same policy_state payload -> same policy_state_hash
changed policy_state payload -> changed policy_state_hash
```

---

### 6. Update docs and examples

Update documentation so it no longer says canonical state/version is a monotonically increasing counter.

Docs should state:

```text
Canonical command/state sensors use content-hash state values.
The actual payload is in attributes.
The state changes only when the semantic payload changes.
```

Update architecture docs to show only:

```text
policy_outputs:
  device_policies
  dispatch_command
  policy_state

diagnostics_outputs:
  policy_diagnostics
  actuator_writer_trace
  dispatch_state_applier_trace
```

Remove language that implies `policy_decision_trace` is a policy output contract.

Remove docs/examples for standalone surplus summary sensors. Do not describe them as optional legacy outputs.

---

## Acceptance criteria

Run:

```bash
pytest -q
```

Expected:

```text
all tests pass, existing xfail acceptable if unrelated
```

Manual grep expectations:

```bash
rg "ems_policy_decision_trace|policy_decision_trace|decision_trace" ems_*.py modules tests docs
```

Expected:

```text
no active runtime/config/test/doc references
```

Allowed only if unavoidable in:

- migration note explaining that the old field was removed
- test asserting old config is rejected
- release note / changelog

Not allowed in:

- actuator writer source path
- dispatch applier source path
- policy engine previous-state source path
- config model as accepted field
- grouped config examples
- architecture docs as active contract

```bash
rg "surplus_policy_active|surplus_next_target|surplus_next_threshold|surplus_release_candidate|surplus_explanation" ems_*.py modules tests docs
```

Expected:

```text
no standalone entity output support remains
```

Allowed only if unavoidable in:

- test asserting old config is rejected
- release note / changelog
- diagnostics attribute names only where they are still intentionally part of policy diagnostics payload

Production validation expectations after deployment:

```text
sensor.ems_device_policies_pyscript.state = content hash
sensor.ems_surplus_dispatch_command_pyscript.state = content hash
sensor.ems_policy_state_pyscript.state = content hash

sensor.ems_policy_diagnostics_pyscript exists if diagnostics enabled
sensor.ems_policy_decision_trace_pyscript no longer exists / is no longer published

sensor.ems_actuator_writer_trace.attrs.policy_source_reason = canonical
sensor.ems_dispatch_state_applier_trace.attrs.dispatch_source_reason = canonical

No repeated blocking EMS_config.yaml read_text/open warnings.
No RuntimeWarning: coroutine 'EvalFuncVarClassInst.__call__' was never awaited.
```

---

## Non-goals

Do not change business semantics in this task:

- no EV hard_off behavior changes
- no EV primary / HOME_BATTERY primary behavior changes
- no RPNZ deadband changes
- no threshold tuning changes
- no battery discharge logic changes

This task is structural cleanup only.

---

## Suggested implementation order

1. Replace config model with clean-slate `policy_outputs` + `diagnostics_outputs` separation.
2. Delete old `decision_trace` config support and old entity publication.
3. Add `policy_diagnostics` publication target.
4. Delete standalone surplus summary output config and publication.
5. Remove writer/dispatch fallbacks to trace/diagnostics payloads.
6. Update E2E helper reads from trace to canonical `device_policies`.
7. Add tests that reject old config fields explicitly.
8. Update docs and example config.
9. Run full test suite.
10. Grep for old active-contract names and remove remaining accidental dependencies.

---

## Review notes for next session

When reviewing Codex output, check specifically:

```bash
rg "policy_decision_trace|decision_trace|ems_policy_decision_trace" .
rg "policy_diagnostics|policy_explanation|diagnostics_outputs" .
rg "surplus_policy_active|surplus_next_target|surplus_next_threshold|surplus_release_candidate|surplus_explanation" .
rg "policy_source_reason|dispatch_source_reason" .
rg "device_policies_hash|dispatch_command_hash|policy_state_hash" .
pytest -q
```

The key design tests:

```text
Can EMS run normal production control with only:
  device_policies
  dispatch_command
  policy_state
configured under policy_outputs?

Are diagnostics fully separate:
  policy_diagnostics
  actuator_writer_trace
  dispatch_state_applier_trace

Are old decision_trace and standalone surplus summary outputs gone rather than deprecated?
```

If yes, the cleanup succeeded.
