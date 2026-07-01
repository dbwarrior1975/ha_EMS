# Codex review notes: policy outputs / legacy surfaces cleanup phase plan

Date: 2026-07-01  
Context: Review feedback for `codex_task_cleanup_policy_outputs_legacy_surfaces_phase_plan.md`

## Summary verdict

The phase plan is technically sound and the ordering is mostly correct:

1. config contract first
2. runtime entity registry second
3. remove runtime fallbacks before deleting old published sensors
4. rename/publish diagnostics after runtime paths no longer depend on trace
5. strengthen hash-state tests
6. update docs and examples last
7. run full verification and acceptance greps

However, this cleanup must be treated as a clean-slate breaking cleanup. EMS is still only in dev use, so do **not** preserve dashboard compatibility, old aliases, deprecated config fields, old entity ids, or transitional legacy support.

The current plan is acceptable as a base, but it should be tightened in the following areas before implementation.

---

## 1. Make the clean-slate principle explicit

Add this principle near the start of the plan:

```text
This is a clean-slate breaking cleanup. Do not preserve dashboard compatibility, legacy aliases, old entity ids, deprecated config fields, or fallback reads from diagnostics. If an old field appears in active config, fail validation with a clear error. If a canonical runtime sensor is missing at startup, use explicit safe behavior instead of falling back to diagnostics/trace payloads.
```

Rationale:

The goal is not a compatibility migration. The goal is to remove refactor leftovers in one pass. Dashboard transitions can be managed manually by the user.

---

## 2. Remove `trace` from the new active contract vocabulary

The plan currently suggests diagnostics attributes such as:

```yaml
policy_trace_canonical_contract: device_policies
```

Do not keep `trace` terminology in active runtime/diagnostics payloads unless it is only in a release note or legacy rejection test.

Use names like:

```yaml
diagnostics_contract: policy_explanation_only
runtime_contract: false
canonical_policy_output_contract: device_policies
policy_output_contract: device_policy_primary
```

or:

```yaml
policy_diagnostics_contract: explanation_only
policy_diagnostics_runtime_source: false
canonical_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript
```

Acceptance requirement:

```text
No active payload field should be named `policy_trace_*`.
```

Allowed exceptions:

```text
- legacy rejection tests
- release/migration notes saying that the old trace surface was removed
- docs/archive/** if archive is intentionally excluded from active greps
```

---

## 3. Rename internal `decision_trace` module/helpers in the same cleanup if practical

The plan says that `modules/ems_core/diagnostics/decision_trace.py` may be renamed later.

Because this is a clean-slate cleanup, prefer renaming it in the same implementation:

```text
modules/ems_core/diagnostics/decision_trace.py
-> modules/ems_core/diagnostics/policy_diagnostics.py
```

Also update test names/helpers where practical:

```text
test_decision_trace.py
-> test_policy_diagnostics.py
```

If this rename causes disproportionate churn, Codex may keep the internal filename temporarily, but then it must create an explicit same-task subphase:

```text
Phase 4b: rename remaining internal decision_trace symbols to policy_diagnostics
```

Do not leave the old module name as an indefinite cleanup item.

---

## 4. Add explicit Pyscript `state_trigger` verification

The previous production problem was not just payload shape. It was also that runtime triggers were attached to the wrong surfaces.

Add this grep/check to the verification commands:

```bash
rg "state_trigger|time_trigger" ems_*.py
```

Acceptance requirements:

```text
- actuator writer state_trigger must point to the canonical device_policies entity
- dispatch state applier state_trigger must point to the canonical dispatch_command entity
- policy engine must not use policy_diagnostics / old trace as previous-state input
- no state_trigger may point to sensor.ems_policy_decision_trace_pyscript
- no state_trigger may point to sensor.ems_policy_diagnostics_pyscript for runtime command/state behavior
```

Expected runtime model:

```text
sensor.ems_device_policies_pyscript
  -> actuator writer

sensor.ems_surplus_dispatch_command_pyscript
  -> dispatch state applier

sensor.ems_policy_state_pyscript
  -> policy engine previous-state input

sensor.ems_policy_diagnostics_pyscript
  -> diagnostics/dashboard only
```

---

## 5. Add cold-start / missing canonical sensor tests after fallback removal

Removing fallbacks is correct, but startup must still be safe when canonical sensors do not exist yet.

Add tests in the fallback-removal phase:

### Writer cold start

```text
Given sensor.ems_device_policies_pyscript is missing or invalid:
- writer must not read policy_diagnostics
- writer must not read old policy_decision_trace
- writer must not write unsafe actuator targets
- writer diagnostics must report missing/invalid canonical device_policies
```

### Dispatch applier cold start

```text
Given sensor.ems_surplus_dispatch_command_pyscript is missing or invalid:
- dispatch applier must not read policy_diagnostics
- dispatch applier must not read old policy_decision_trace
- dispatch applier must perform safe NOOP behavior
- dispatch diagnostics must report missing/invalid canonical dispatch_command
```

### Policy engine previous-state cold start

```text
Given sensor.ems_policy_state_pyscript is missing or invalid:
- policy engine must use empty/default previous-state
- policy engine must not read policy_diagnostics
- policy engine must not read old policy_decision_trace
- policy engine must publish a fresh policy_state output on the next loop
```

This preserves safe startup without reintroducing compatibility fallback.

---

## 6. Tighten surplus summary grep acceptance

The plan currently greps broadly for:

```bash
rg "surplus_policy_active|surplus_next_target|surplus_next_threshold|surplus_release_candidate|surplus_explanation" ems_*.py modules tests docs/user docs/dev
```

This can create noisy results because `surplus_explanation` is still useful as a payload attribute inside `policy_diagnostics` or `dispatch_command`.

Split the checks into two categories.

### Forbidden standalone entity/config/registry remnants

```bash
rg "surplus_policy_active_pys|surplus_next_target_pys|surplus_next_threshold_pys|surplus_release_candidate_pys|surplus_explanation_pys" ems_*.py modules tests docs/user docs/dev
```

```bash
rg "ems_net_zero_surplus_policy_active|ems_net_zero_surplus_next_target|ems_net_zero_surplus_next_threshold|ems_net_zero_surplus_release_candidate|ems_net_zero_surplus_explanation" ems_*.py modules tests docs/user docs/dev
```

These must not appear in active runtime/config/docs, except in legacy rejection tests or release notes.

### Allowed payload attributes

These may remain if they are attributes inside canonical/diagnostics payloads, not standalone sensors:

```text
surplus_policy_active
surplus_next_target
surplus_next_threshold_kw
surplus_release_candidate
surplus_explanation
surplus_device_targets
surplus_dispatch_decision
```

Acceptance rule:

```text
Standalone surplus summary sensors are removed. Surplus explanation fields may remain only as attributes of policy_diagnostics and/or dispatch_command payloads.
```

---

## 7. Strengthen config validation expectations

Because there is no need for backwards compatibility, old fields should not be silently ignored or mapped.

Add/confirm rejection tests:

```text
policy_outputs.decision_trace
  -> rejected with message pointing to diagnostics_outputs.policy_diagnostics

policy_outputs.actuator_writer_trace
  -> rejected with message pointing to diagnostics_outputs.actuator_writer_trace

policy_outputs.dispatch_state_applier_trace
  -> rejected with message pointing to diagnostics_outputs.dispatch_state_applier_trace

surplus_policy_active
surplus_next_target
surplus_next_threshold
surplus_release_candidate
surplus_explanation
  -> rejected with message saying standalone surplus summary outputs were removed
```

Also confirm:

```text
diagnostics_outputs.policy_diagnostics is accepted
diagnostics_outputs.actuator_writer_trace is accepted
diagnostics_outputs.dispatch_state_applier_trace is accepted
```

---

## 8. Clarify final active config shape

Final active config should be only:

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

Do not introduce:

```yaml
legacy_dashboard_outputs:
```

Do not support old aliases:

```yaml
policy_outputs:
  decision_trace: ...
  surplus_policy_active: ...
  surplus_next_target: ...
  surplus_next_threshold: ...
  surplus_release_candidate: ...
  surplus_explanation: ...
  actuator_writer_trace: ...
```

---

## 9. Tighten final grep acceptance

Final verification should include:

```bash
pytest -q
rg "state_trigger|time_trigger" ems_*.py
rg "ems_policy_decision_trace|policy_decision_trace|decision_trace" ems_*.py modules tests docs/user docs/dev
rg "policy_trace_" ems_*.py modules tests docs/user docs/dev
rg "surplus_policy_active_pys|surplus_next_target_pys|surplus_next_threshold_pys|surplus_release_candidate_pys|surplus_explanation_pys" ems_*.py modules tests docs/user docs/dev
rg "ems_net_zero_surplus_policy_active|ems_net_zero_surplus_next_target|ems_net_zero_surplus_next_threshold|ems_net_zero_surplus_release_candidate|ems_net_zero_surplus_explanation" ems_*.py modules tests docs/user docs/dev
rg "fallback_.*decision_trace|legacy_trace|fallback_deprecated_policy_diagnostics|fallback_device_policies_missing|fallback_dispatch_command" ems_*.py modules tests
```

Allowed final matches:

```text
- legacy rejection tests
- release/migration notes
- docs/archive/** if intentionally excluded from active acceptance greps
- payload attributes such as surplus_explanation when they are not standalone sensors
```

Forbidden final matches:

```text
- policy_decision_trace in writer/dispatch/policy-engine runtime read paths
- decision_trace as an accepted config field
- policy_trace_* active payload fields
- standalone surplus summary sensor publication
- standalone surplus summary registry keys
- old sensor.ems_policy_decision_trace_pyscript in active config/docs/tests except rejection/migration notes
```

---

## 10. Recommended implementation instruction to Codex

Use this as the implementation directive:

```text
Implement the cleanup as a clean-slate breaking refactor. Do not preserve legacy dashboard sensors, old policy_outputs fields, old entity ids, or fallback reads from diagnostics/trace. The only runtime policy outputs are device_policies, dispatch_command, and policy_state. The renamed diagnostics surface is policy_diagnostics and must be explanation-only, never a command/state source. Ensure startup remains safe when canonical sensors are missing, but do not use compatibility fallbacks. Update tests, configs, docs, greps, and state_trigger verification accordingly. Full pytest must pass.
```
