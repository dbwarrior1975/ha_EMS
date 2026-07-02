# Review notes for Codex: reduce policy engine timer load phase plan

## Reviewed plan

Reviewed file:

```text
codex_task_reduce_policy_engine_timer_load_v2_reviewed_phase_plan.md
```

The plan is broadly good and should be accepted with a few required clarifications before implementation.

Overall rating:

```text
8.5 / 10
```

## Summary verdict

The plan's main direction is correct:

```text
- keep policy decisions responsive with policy_engine.interval_seconds = 5;
- publish policy_diagnostics less often when nothing meaningful changes;
- publish policy_diagnostics immediately when canonical output changes;
- publish policy_diagnostics immediately when warning/error/input-quality state changes;
- keep manual/e2e runs deterministic by forcing diagnostics publication;
- make the fixed 2s scheduler skip path genuinely cheap.
```

The phase order is also good:

```text
1. config model and validation
2. fast timer skip path
3. diagnostics throttling
4. payload boundaries and timing diagnostics
5. documentation
6. regression tests and grep checks
```

This is the right order because it avoids mixing performance optimization, canonical bus semantics, writer/dispatch trigger behavior, and test expectation changes into one uncontrolled change.

## What is good in the plan

### 1. Correct runtime rule

The target runtime rule is right:

```text
Timer-run:
  run policy calculation on interval_seconds cadence
  publish canonical outputs normally
  publish policy_diagnostics only if:
    - canonical output changed
    - warning/error/input-quality signature changed
    - diagnostics_interval_seconds has elapsed
    - this is the first successful run

Manual/e2e-run:
  run policy immediately
  always publish policy_diagnostics
```

This matches the intended production rule:

```text
policy_diagnostics is published:
  - when canonical output changes;
  - or at least every diagnostics_interval_seconds, default 30 seconds;
  - or when error/warning/input-quality changes.
```

Important: canonical and warning/error changes must not wait for the 30 second interval.

### 2. Correct fast skip path

The proposed fast skip path is correct:

```text
2s tick, interval not elapsed:
  time.time()
  update in-memory ticks/skips
  return

No config/runtime-context read.
No entity read.
No hash computation.
No publish_sensor call.
No policy compute.
```

This is the key optimization for reducing idle timer overhead.

### 3. Correct use of cached interval

Using cached `effective_interval_seconds` and `effective_diagnostics_interval_seconds` is the right approach.

The plan's second gate after config read is also acceptable:

```text
1. fast cached gate before config/runtime reads
2. config/runtime read only when cached gate passes
3. second gate with freshly read config interval
```

This handles the tradeoff where config changes may be applied on the next real run or after manual/reload, while keeping most skip ticks cheap.

### 4. Correctly avoids changing canonical publish semantics too early

The plan correctly recognizes that:

```text
"Publish canonical sensor only when hash changes"
```

is a larger contract change than diagnostics throttling.

Do not implement this aggressively unless writer/dispatch trigger semantics are audited and covered by tests.

The safer first implementation is:

```text
- throttle policy_diagnostics;
- do not add new volatile timing/publish fields to canonical sensors;
- keep canonical publish cadence unchanged unless a separate tested audit proves it safe to change.
```

### 5. Correct payload boundary direction

The plan correctly states that timing and publish-decision fields must be diagnostics-only.

Good target:

```text
policy_diagnostics:
  broad diagnostics payload
  timing fields
  publish decision fields
  diagnostics publish reason

canonical sensors:
  no new volatile timing/publish-only fields
```

This is important because adding timing counters to `sensor.ems_device_policies_pyscript` would worsen the current payload problem.

## Required clarifications before implementation

### 1. Do not silently accept invalid diagnostics interval config

The proposed runtime helper includes this pattern:

```python
if interval_seconds in (None, '', False):
    return 30.0
```

This is too permissive if applied to raw YAML/config input.

Required clarification:

```text
Config loader must reject invalid values:
  - bool
  - string
  - entity ref
  - 0
  - negative
  - values below 5

Runtime helper may be defensive only after validated CoreConfig exists.
Invalid YAML must not silently default to 30 seconds.
```

Acceptable split:

```text
config_loader.py:
  strict validation and clear errors

ems_policy_engine.py runtime helper:
  defensive fallback only for already-constructed config objects or test stubs
```

Required tests:

```text
test_policy_engine_diagnostics_interval_rejects_bool
test_policy_engine_diagnostics_interval_rejects_non_numeric
test_policy_engine_diagnostics_interval_rejects_entity_ref
test_policy_engine_diagnostics_interval_rejects_0
test_policy_engine_diagnostics_interval_rejects_negative
test_policy_engine_diagnostics_interval_rejects_2
```

### 2. Keep warning/error/input-quality signature minimal

The proposed warning signature included fields such as:

```text
guard_profile
dominant_limitation
config_status
```

Be careful. Some of these may be ordinary policy explanation fields rather than actual warning/error/input-quality state.

If they change frequently during normal control, they will defeat diagnostics throttling by forcing frequent diagnostics publishes.

Required clarification:

```text
First implementation warning signature should include only stable warning/error/input-quality fields.
Do not include normal policy explanation fields that may change during ordinary control.
```

Recommended first-pass signature:

```python
def _policy_warning_signature(attrs):
    return _payload_hash({
        'net_zero_input_quality': attrs.get('net_zero_input_quality', ''),
        'net_zero_input_warnings': attrs.get('net_zero_input_warnings', ()),
        'config_status': attrs.get('config_status', ''),
        'runtime_error': attrs.get('runtime_error', ''),
    })
```

Only include `config_status` or `runtime_error` if those fields actually exist and are stable.

Avoid in the first pass unless proven stable:

```text
dominant_limitation
normal policy reason fields
normal explanation fields
timer counters
timestamps
run duration values
publish decision booleans
```

Minimum acceptable implementation:

```text
warning_state_changed = False
```

with a TODO, if there are no stable warning/error/input-quality fields yet.

### 3. Timing and publish-decision fields must be diagnostics-only

Required clarification:

```text
Add timing/publish fields only to policy_diagnostics attrs.
Do not add them to:
  - sensor.ems_device_policies_pyscript attrs
  - sensor.ems_surplus_dispatch_command_pyscript attrs
  - sensor.ems_policy_state_pyscript attrs
  - any canonical hash input
```

Diagnostics-only fields include:

```text
policy_engine_run_duration_ms
policy_engine_publish_ms
policy_engine_published_device_policies
policy_engine_published_dispatch_command
policy_engine_published_policy_state
policy_engine_published_policy_diagnostics
policy_engine_diagnostics_publish_reason
policy_engine_last_diagnostics_publish_ts
policy_engine_diagnostics_interval_seconds
```

Required tests:

```text
diagnostics-only timing fields do not change device_policies_hash
diagnostics-only timing fields do not change dispatch_command_hash
diagnostics-only timing fields do not change policy_state_hash
```

### 4. Be precise about previous hash/signature update timing

The plan says to update previous hashes at the end of a successful policy run.

Clarify this to avoid stale or false state transitions:

```text
Compute new canonical hashes first.
Use old in-memory hashes to determine canonical_changed.
Make publish decisions.
Attempt sensor publishes.
Only then update previous hash/signature state for the completed run.
```

If `publish_sensor` can fail or raise, do not mark a failed publish as successfully published.

Recommended behavior:

```text
- previous canonical hashes may be updated after successful policy run/publish-decision completion;
- last_diagnostics_publish_ts must be updated only when policy_diagnostics was actually published;
- policy_engine_published_* booleans should reflect actual publish attempts/results, not just desired state.
```

### 5. Do not change E2E business expectations

This task is performance/observability work.

Required constraint:

```text
No E2E business expected values may change because of this task.
```

Do not change expected values for:

```text
HOME_BATTERY target_w
EV target_w
relay target_w
enabled/mode/reason values
dispatch action/decision/target
writer output expectations
NET_ZERO derived values
```

E2E may be adjusted only for diagnostics publication mechanics if necessary, and `trigger_reason='e2e'` should force diagnostics publication to avoid timing-dependent tests.

### 6. Do not change writer/dispatch trigger contract

This task must not redesign writer/dispatch triggering.

Do not change canonical entity IDs.

Do not make downstream writer/dispatch triggers dynamic.

Do not change the semantic contract of:

```text
sensor.ems_device_policies_pyscript -> actuator writer
sensor.ems_surplus_dispatch_command_pyscript -> dispatch state applier
sensor.ems_policy_state_pyscript -> policy previous-state input
```

## Specific feedback by phase

### Phase 1: config model and validation

Approved with one clarification:

```text
The config loader must strictly reject invalid diagnostics_interval_seconds values.
Do not let invalid YAML silently default to 30 seconds.
```

Expected model:

```python
@dataclass
class CorePolicyEngineConfig:
    interval_seconds: float = 5.0
    diagnostics_interval_seconds: float = 30.0
```

Expected validation:

```text
default: 30
minimum: 5
numeric config constant only
bool rejected
string/entity-ref rejected
unknown policy_engine key rejected
```

### Phase 2: fast timer skip path

Approved.

The cached fast gate is the right implementation.

Required behavior:

```text
skip tick:
  increments in-memory tick/skip counters only
  does not read config
  does not read runtime context
  does not read entities
  does not compute hashes
  does not publish sensors
  does not run policy compute
```

The second gate after config read is acceptable and should be documented.

### Phase 3: diagnostics throttling

Approved with warning-signature clarification.

Required publish priority:

```text
manual/e2e
startup
canonical_changed
warning_changed
interval
throttled
```

Do not check the interval before canonical/warning changes.

This test must exist:

```text
canonical_changed=True before diagnostics interval -> publish, reason=canonical_changed
```

This test must also exist:

```text
warning_state_changed=True before diagnostics interval -> publish, reason=warning_changed
```

### Phase 4: payload boundaries and timing diagnostics

Approved with strict diagnostics-only scope.

Recommended first implementation:

```text
- throttle only policy_diagnostics;
- add timing and publish-decision fields only to policy_diagnostics;
- do not add new volatile fields to canonical sensors;
- do not change canonical publish cadence unless explicitly tested and audited.
```

Canonical publish-only-on-hash-change can be a later task if this phase would become too risky.

### Phase 5: documentation

Approved.

Documentation must include:

```text
Policy engine computes on policy_engine.interval_seconds.
Policy diagnostics publish immediately on canonical output change or warning/error/input-quality change.
Otherwise timer-run diagnostics publish at most once per policy_engine.diagnostics_interval_seconds.
Manual and E2E runs force diagnostics publication.
The 2s scheduler skip path intentionally does not read config/runtime context.
Config interval changes may apply on next real policy run or manual/reload.
```

Recorder recommendation should be included as operational guidance:

```yaml
recorder:
  exclude:
    entities:
      - sensor.ems_policy_diagnostics_pyscript
```

Important wording:

```text
Recorder exclusion is a performance recommendation, not a correctness requirement.
```

### Phase 6: regression and grep checks

Approved.

Full test suite should pass.

Required safety checks:

```text
NET_ZERO formulas unchanged.
Canonical output entity IDs unchanged.
Writer/dispatch trigger contract unchanged.
Diagnostics-only fields do not affect canonical hashes.
No E2E business expected values changed.
```

## Additional recommended tests

Add or verify these tests explicitly:

```text
test_diagnostics_interval_invalid_yaml_does_not_default_silently
test_fast_skip_does_not_call_read_runtime_context
test_fast_skip_does_not_call_publish_sensor
test_fast_skip_does_not_call_hash_helpers
test_fast_skip_does_not_call_policy_compute
test_timer_diagnostics_throttled_when_no_changes_before_interval
test_timer_diagnostics_published_on_interval_when_no_changes
test_timer_diagnostics_published_immediately_on_canonical_change
test_timer_diagnostics_published_immediately_on_warning_change
test_e2e_forces_diagnostics_publish_every_step
test_manual_forces_diagnostics_publish_every_run
test_timing_fields_are_diagnostics_only
```

## Acceptance additions

Add these to final acceptance criteria:

```text
Invalid diagnostics_interval_seconds config values fail validation and do not silently default.

Warning/error/input-quality signature does not include volatile fields or ordinary policy explanation fields.

Timing and publish-decision fields are diagnostics-only.

Canonical sensors are not enlarged with new volatile timing/publish attrs.

Previous hash/signature state is updated only after the run reaches the publish-decision phase successfully.

No E2E business expected values changed.
```

## Final recommendation

Proceed with implementation after applying the clarifications above.

The plan is directionally correct and appropriately conservative.

Expected production impact:

```text
- 5 second policy responsiveness preserved;
- large diagnostics payload no longer published every policy run;
- 2 second scheduler skip ticks become cheap;
- recorder exclusion remains a useful additional optimization;
- future load issues become easier to diagnose through run/publish timing metrics.
```

The most important guardrails are:

```text
1. Do not silently accept invalid config.
2. Do not let warning signature include frequently changing normal policy explanation fields.
3. Do not add volatile timing/publish fields to canonical sensors.
4. Do not change E2E business expectations.
5. Do not change writer/dispatch trigger contracts.
```
