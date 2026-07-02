# Codex task: fix dispatch command canonical stability for CLEAR_ALL / policy inactive

## Purpose

Production observation after adding `policy_engine.diagnostics_interval_seconds`:

```yaml
ems:
  policy_engine:
    interval_seconds: 5
    diagnostics_interval_seconds: 30
```

Expected behavior in a stable state:

```text
policy_diagnostics should publish:
  - when canonical output changes;
  - or at least every diagnostics_interval_seconds, default 30 seconds;
  - or when warning/error/input-quality changes.
```

Observed behavior:

```text
sensor.ems_policy_diagnostics_pyscript still updates every 5 seconds.
policy_engine_diagnostics_publish_reason = canonical_changed.
device_policies_hash remains stable across samples.
```

The production samples show that the likely changing canonical output is the surplus dispatch command.

## Production evidence

Two consecutive production samples had the same stable policy situation:

```yaml
control: MANUAL
goal: NET_ZERO
dominant_limitation: USER_MANUAL_OVERRIDE
explanation: User manual control active

surplus_policy_active: false
surplus_device_dispatch_decision: CLEAR_ALL
surplus_device_dispatch_action: CLEAR_ALL
surplus_explanation: Policy inactive -> clear all surplus states

device_policies_hash: 3686d89ac782f72e
policy_engine_diagnostics_publish_reason: canonical_changed
```

But these values changed between samples:

```yaml
# sample 1
surplus_freeze_until_ts: 1782968842.4231586
policy_engine_last_tick_ts: 1782968842.4231586

# sample 2
surplus_freeze_until_ts: 1782968872.4212813
policy_engine_last_tick_ts: 1782968872.4212813
```

The key problem:

```text
surplus_freeze_until_ts equals now_ts / policy_engine_last_tick_ts
for CLEAR_ALL / policy inactive.
```

Because `surplus_freeze_until_ts` is part of `dispatch_command_hash`, the dispatch command hash changes every policy run even though the semantic command is unchanged.

This causes:

```text
now_ts changes every run
-> surplus_freeze_until_ts changes every run
-> dispatch_command_hash changes every run
-> canonical_changed = True every run
-> policy_diagnostics publishes every 5 seconds
-> diagnostics_interval_seconds is effectively bypassed
```

This is not primarily a diagnostics throttling bug. It is a canonical payload stability bug.

## Root cause to verify

Inspect the surplus dispatch code. There is likely logic similar to:

```python
def compute_surplus_device_dispatch(inp, now_ts, freeze_s=30):
    if not inp.policy_active:
        return SurplusDispatchDecision(
            clear_all=True,
            freeze_until_ts=now_ts,
            explanation='Policy inactive -> clear all surplus states',
        )
```

or equivalent command-building logic that places `now_ts` into `surplus_freeze_until_ts` for `CLEAR_ALL`.

This makes an idempotent clear command appear different every run.

## Required semantic fix

`CLEAR_ALL` / policy inactive must be idempotent and stable across identical runs.

A clear command is not a future freeze command.

Therefore `CLEAR_ALL` should not carry a now-derived `surplus_freeze_until_ts` in the canonical dispatch command payload or hash.

Preferred behavior:

```python
if not inp.policy_active:
    return SurplusDispatchDecision(
        clear_all=True,
        freeze_until_ts=None,
        explanation='Policy inactive -> clear all surplus states',
    )
```

Equivalent acceptable behavior:

```text
- keep internal timestamp if some non-canonical internal state truly needs it;
- but normalize `surplus_freeze_until_ts` to None / empty / stable value for:
  - dispatch command canonical attrs;
  - dispatch_command_hash;
  - policy_diagnostics canonical output comparison.
```

Do not include `now_ts` in the dispatch command hash for stable `CLEAR_ALL` / no-op / inactive-policy commands.

## Important distinction

This task does not forbid future freeze timestamps in real activation/release commands.

For example, this may remain valid if it represents a real future freeze:

```python
return SurplusDispatchDecision(
    activate=target_device_id,
    freeze_until_ts=now_ts + freeze_s,
    explanation='Activate surplus device and freeze selection window',
)
```

But clear/no-op/inactive-policy commands must not get a changing now timestamp unless it is semantically required and excluded from canonical hash comparison.

## Scope

This is a narrow bugfix.

Do not change:

```text
- NET_ZERO formulas;
- device policy expected values;
- writer command semantics;
- policy_engine interval behavior;
- diagnostics_interval_seconds behavior;
- canonical output entity IDs;
- writer/dispatch trigger contracts;
- E2E business expectations.
```

Do not redesign the dispatch state machine in this task.

Fix canonical stability for stable clear/no-op/inactive dispatch payloads.

## Desired behavior after fix

Given stable inputs:

```yaml
control: MANUAL
surplus_policy_active: false
surplus_device_dispatch_action: CLEAR_ALL
surplus_device_dispatch_decision: CLEAR_ALL
device_policies_hash: 3686d89ac782f72e
net_zero_input_quality: ok
net_zero_input_warnings: []
```

Expected timer behavior with:

```yaml
policy_engine:
  interval_seconds: 5
  diagnostics_interval_seconds: 30
```

should be:

```text
t=0:
  policy_diagnostics publishes
  reason = startup or interval or canonical_changed if first post-fix canonical stabilization

t=5:
  no policy_diagnostics publish
  internal reason would be throttled

t=10:
  no policy_diagnostics publish

t=15:
  no policy_diagnostics publish

t=20:
  no policy_diagnostics publish

t=25:
  no policy_diagnostics publish

t=30:
  policy_diagnostics publishes
  reason = interval
```

The dispatch command hash must remain stable across the t=5..t=25 runs if the semantic dispatch command remains `CLEAR_ALL`.

## Implementation guidance

### 1. Fix dispatch decision construction

Find the `policy_active == False` / policy inactive branch in surplus dispatch calculation.

Change it from now-derived freeze timestamp to stable no-freeze value.

Preferred:

```python
freeze_until_ts=None
```

If the model type requires a numeric value, use a stable neutral value consistently, but prefer `None` if attrs and hash code already support it.

### 2. Normalize canonical dispatch attrs if necessary

If there are multiple paths that may produce clear/no-op commands with `freeze_until_ts=now_ts`, add a normalization helper near dispatch command attrs/hash construction.

Example:

```python
def _canonical_surplus_freeze_until_ts_for_dispatch(attrs):
    action = attrs.get('surplus_device_dispatch_action')
    decision = attrs.get('surplus_device_dispatch_decision')
    freeze_until_ts = attrs.get('surplus_freeze_until_ts')

    if action in ('CLEAR_ALL', 'NOOP', ''):
        return None
    if decision in ('CLEAR_ALL', 'NOOP', ''):
        return None
    return freeze_until_ts
```

Then use the normalized value in both:

```text
- dispatch_command attrs if that attr is meant to be canonical;
- dispatch_command_hash input.
```

Be careful: do not hide real future freeze timestamps for real activation/release commands.

### 3. Keep diagnostics honest

After the fix, `sensor.ems_policy_diagnostics_pyscript` may still show `surplus_freeze_until_ts`, but for `CLEAR_ALL` it should be one of:

```text
None
""
0 only if project convention already uses 0 as neutral
```

Avoid showing current `now_ts` for `CLEAR_ALL` because it is misleading and high-churn.

### 4. Update hash logic if needed

Current dispatch hash likely includes:

```python
_payload_hash({
    'surplus_device_dispatch_action': attrs.get('surplus_device_dispatch_action'),
    'surplus_device_dispatch_decision': attrs.get('surplus_device_dispatch_decision'),
    'surplus_device_dispatch_device_id': attrs.get('surplus_device_dispatch_device_id'),
    'surplus_device_dispatch_target': attrs.get('surplus_device_dispatch_target'),
    'surplus_device_targets': attrs.get('surplus_device_targets'),
    'surplus_freeze_until_ts': attrs.get('surplus_freeze_until_ts'),
    'surplus_state_clear_reason': attrs.get('surplus_state_clear_reason'),
})
```

For clear/no-op, ensure the value used for `surplus_freeze_until_ts` is stable.

Preferred:

```python
'surplus_freeze_until_ts': _canonical_surplus_freeze_until_ts_for_dispatch(attrs)
```

or fix earlier so `attrs['surplus_freeze_until_ts']` is already stable.

## Tests to add

### Unit test: policy inactive dispatch is stable

Add a unit test close to the surplus dispatch function:

```text
test_policy_inactive_clear_all_dispatch_is_stable_across_now_ts
```

Scenario:

```text
Given equivalent input with policy_active=False
When compute_surplus_device_dispatch(..., now_ts=100)
And compute_surplus_device_dispatch(..., now_ts=105)
Then:
  action/decision are CLEAR_ALL
  freeze_until_ts is None/stable in both
  canonical dispatch payloads are equal
```

Expected:

```text
Changing now_ts alone must not change CLEAR_ALL canonical dispatch payload.
```

### Unit test: dispatch hash stable for repeated CLEAR_ALL

Add:

```text
test_dispatch_command_hash_stable_for_repeated_clear_all
```

Scenario:

```text
Build dispatch attrs for CLEAR_ALL at t=100 and t=105.
Only now_ts-derived fields differ before normalization.
Compute dispatch_command_hash.
Expected hashes are equal.
```

### Timer/diagnostics integration test

Add:

```text
test_policy_diagnostics_throttled_for_repeated_policy_inactive_clear_all
```

Scenario:

```text
Given:
  policy_engine.interval_seconds = 5
  policy_engine.diagnostics_interval_seconds = 30
  control = MANUAL
  surplus_policy_active = False
  dispatch action = CLEAR_ALL
  stable device_policies_hash
  stable policy_state_hash
  net_zero_input_quality = ok
  net_zero_input_warnings = []

When:
  run timer policy at t=100
  run timer policy again at t=105

Then:
  first run may publish diagnostics
  second run must not publish diagnostics
  second run reason should be throttled internally
  dispatch_command_hash must be unchanged
```

If test infrastructure cannot assert "not published" directly, assert equivalent publish-decision helper state and stable dispatch hash.

### Regression test: real activation freeze still changes when appropriate

Add or preserve a test proving real future freeze commands still retain freeze timestamp when semantically needed.

Example:

```text
test_surplus_activate_keeps_future_freeze_until_ts
```

Scenario:

```text
Given activation threshold crossed
When dispatch action is ACTIVATE
Then:
  freeze_until_ts == now_ts + freeze_s
```

This prevents over-normalizing all freeze timestamps.

## Tests to run

Run focused tests:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_surplus_dispatch.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_engine.py
```

Use actual file names if the project uses different names for surplus dispatch tests.

Run E2E:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/e2e_entity
```

Run full suite:

```bash
PYTHONPATH=modules python3 -m pytest -q
```

## Grep checks

Search for now-derived freeze in clear/no-op branches:

```bash
rg "freeze_until_ts=.*now|now_ts.*freeze|CLEAR_ALL|policy_active" modules ems_*.py tests
```

Search dispatch hash inputs:

```bash
rg "dispatch_command_hash|surplus_freeze_until_ts" modules ems_*.py tests
```

Expected after fix:

```text
- CLEAR_ALL / policy inactive does not assign now_ts to canonical surplus_freeze_until_ts.
- dispatch_command_hash uses stable freeze value for CLEAR_ALL / NOOP.
- ACTIVATE or real future freeze paths may still use now_ts + freeze_s.
```

## Acceptance criteria

Functional:

```text
- policy inactive CLEAR_ALL dispatch is stable across repeated identical timer runs.
- CLEAR_ALL does not include now_ts-derived surplus_freeze_until_ts in canonical payload/hash.
- dispatch_command_hash does not change when only now_ts changes in a stable CLEAR_ALL state.
- policy_diagnostics does not publish every 5 seconds in stable policy inactive CLEAR_ALL state.
- policy_diagnostics still publishes immediately when canonical output truly changes.
- policy_diagnostics still publishes at diagnostics_interval_seconds when nothing changes.
```

Safety:

```text
- Real activation/release freeze semantics are not broken.
- NET_ZERO formulas are unchanged.
- Device policy outputs are unchanged.
- Writer/dispatch trigger contracts are unchanged.
- E2E business expectations are unchanged.
```

Observability:

```text
- policy_engine_diagnostics_publish_reason should be interval in stable state every ~30s.
- It should not be canonical_changed every 5s when device_policies_hash and semantic dispatch command are stable.
```

## Production validation steps

After deployment with:

```yaml
ems:
  policy_engine:
    interval_seconds: 5
    diagnostics_interval_seconds: 30
```

and optionally:

```yaml
recorder:
  exclude:
    entities:
      - sensor.ems_policy_diagnostics_pyscript
```

Observe `sensor.ems_policy_diagnostics_pyscript`.

In stable manual-control / policy inactive state, verify across at least 60 seconds:

```text
device_policies_hash remains stable.
surplus_device_dispatch_action remains CLEAR_ALL.
surplus_device_dispatch_decision remains CLEAR_ALL.
surplus_freeze_until_ts is None/stable, not equal to policy_engine_last_tick_ts.
policy_engine_diagnostics_publish_reason is not canonical_changed every 5 seconds.
policy_diagnostics updates roughly every 30 seconds with reason interval.
```

If `policy_engine_diagnostics_publish_reason` still reports `canonical_changed` every 5 seconds, inspect:

```text
dispatch_command_hash
policy_state_hash
device_policies_hash
surplus_freeze_until_ts
surplus_state_clear_reason
surplus_device_targets
```

to identify the remaining unstable canonical field.

## Final desired state

Stable clear/no-op dispatch commands must be idempotent.

A repeated policy-inactive `CLEAR_ALL` command should not look like a new command just because wall-clock time advanced.

This allows `diagnostics_interval_seconds` to work as intended:

```text
canonical change -> immediate diagnostics
warning/error change -> immediate diagnostics
no meaningful change -> diagnostics at interval, default 30 seconds
```
