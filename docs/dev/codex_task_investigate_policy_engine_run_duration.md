# Codex task: investigate high policy_engine_run_duration_ms

## Purpose

Production samples after diagnostics throttling and dispatch canonical stability fixes show that `policy_diagnostics` now publishes at the expected interval, not every 5 seconds.

However, the latest production diagnostics show surprisingly high policy run duration:

```yaml
policy_engine_run_duration_ms: 391
policy_engine_run_duration_ms: 402
policy_engine_publish_ms: 15
```

This suggests that the major cost is not the final sensor publish step alone.

The current task is **investigation and instrumentation first**, not premature optimization.

The goal is to explain where ~400 ms per real policy run is spent and identify the next safe optimization target.

## Current production facts

Known from production samples:

```yaml
ems:
  policy_engine:
    interval_seconds: 5
    diagnostics_interval_seconds: 30
```

Observed stable state:

```yaml
policy_engine_diagnostics_publish_reason: interval
device_policies_hash: stable
surplus_device_dispatch_action: NOOP
surplus_device_dispatch_decision: NOOP
surplus_freeze_until_ts: stable
policy_engine_publish_ms: 15
policy_engine_run_duration_ms: 391-402
```

Interpretation:

```text
- diagnostics throttling is working;
- dispatch canonical stability is improved;
- publish_ms is only around 15 ms;
- total run duration is still around 400 ms;
- therefore most time is likely spent before or outside the measured publish phase.
```

## Important question

Determine what `policy_engine_run_duration_ms` actually measures.

The current code may calculate it before diagnostics publish, after canonical publish, or around only part of the policy loop.

Before optimizing anything, clarify:

```text
- Does policy_engine_run_duration_ms include read_runtime_context?
- Does it include HA entity reads?
- Does it include config loading / YAML parsing?
- Does it include device registry construction?
- Does it include measurement reading?
- Does it include derived NET_ZERO input calculation?
- Does it include policy engine compute?
- Does it include hash computation / JSON serialization?
- Does it include canonical sensor publish?
- Does it include policy_diagnostics publish?
```

If the existing metric does not cover the whole timer run, rename or supplement it so diagnostics are unambiguous.

## Scope

This is a focused profiling/instrumentation task.

Do not change business behavior.

Do not change:

```text
- NET_ZERO formulas;
- device policy outputs;
- dispatch semantics;
- writer/dispatch trigger contracts;
- canonical output entity IDs;
- policy_engine.interval_seconds behavior;
- diagnostics_interval_seconds behavior;
- E2E business expected values.
```

Do not start with caching or refactoring before measurements show where time is spent.

## Hypotheses to test

Investigate these likely cost centers.

### Hypothesis A: runtime context/config loading is expensive

`read_runtime_context(...)` may be doing expensive work every real policy run.

Possible costs:

```text
- YAML/config file read
- config parsing/validation
- grouped config model construction
- runtime entity registry construction
- device registry construction
- compatibility/dual-read checks
```

If this dominates, optimization may involve caching validated config/registry and invalidating on reload/config file change.

### Hypothesis B: HA state/entity reads are expensive

Reading many entities/attributes through Pyscript/HA can be costly.

Possible costs:

```text
- grid_power_w read
- quarter_energy_balance_kwh read
- pv_power_w read
- previous policy_state read
- previous_device_state read
- active surplus devices read
- relay/EV state reads
- config-related state reads if any remain
```

If this dominates, optimization may involve minimizing reads, caching static registry/config, or reading only required dynamic entities.

### Hypothesis C: attrs payload construction is expensive

The policy output attrs payload is large.

Possible costs:

```text
- building large nested attrs dict
- copying attrs into diagnostics_attrs
- formatting/normalizing lists of device targets
- large previous state structures
```

If this dominates, optimization may involve splitting canonical attrs from diagnostics attrs and constructing heavy diagnostics only when diagnostics will be published.

### Hypothesis D: hash computation / JSON serialization is expensive

Canonical hash functions probably serialize nested payloads.

Possible costs:

```text
- device_policies hash
- dispatch_command hash
- policy_state hash
- warning signature hash
- attrs normalization before hash
```

If this dominates, optimization may involve hashing smaller canonical payloads and avoiding full attrs hashing/copying.

### Hypothesis E: core policy compute is expensive

The actual policy engine may be costly.

Possible costs:

```text
- NET_ZERO derived inputs
- surplus allocator
- EV hardoff/restore_min state machine
- HAE/O plan logic
- capability evaluation
- policy state reconstruction
```

If this dominates, optimization should target the specific compute phase, but only after phase timing proves it.

### Hypothesis F: diagnostics-only work is still being done every run

Even if `policy_diagnostics` is only published every 30 seconds, the code may still build the full diagnostics payload every 5 seconds.

This is important.

Expected efficient model:

```text
Every real policy run:
  build canonical payloads needed for control and hashes

Only when diagnostics should publish:
  build or enrich large diagnostics-only attrs
  add timing/publish decision fields
  publish policy_diagnostics
```

If full diagnostics attrs are built every run, throttling reduces recorder/event load but not CPU load.

## Required instrumentation

Add phase timing fields to `sensor.ems_policy_diagnostics_pyscript`.

Minimum required fields:

```yaml
policy_engine_total_tick_duration_ms: 420
policy_engine_read_runtime_context_ms: 120
policy_engine_read_measurements_ms: 40
policy_engine_derive_inputs_ms: 5
policy_engine_policy_compute_ms: 90
policy_engine_build_attrs_ms: 80
policy_engine_hash_ms: 20
policy_engine_canonical_publish_ms: 15
policy_engine_diagnostics_decision_ms: 1
policy_engine_diagnostics_build_ms: 40
policy_engine_diagnostics_publish_ms: 10
policy_engine_unaccounted_ms: 19
```

If the current code structure cannot support all fields safely, start with these:

```yaml
policy_engine_total_tick_duration_ms
policy_engine_read_runtime_context_ms
policy_engine_read_measurements_ms
policy_engine_policy_compute_ms
policy_engine_build_attrs_ms
policy_engine_hash_ms
policy_engine_canonical_publish_ms
policy_engine_diagnostics_build_ms
policy_engine_diagnostics_publish_ms
policy_engine_unaccounted_ms
```

### Definitions

Use precise definitions:

```text
policy_engine_total_tick_duration_ms:
  wall-clock duration from start of real timer/manual/e2e run to after all publishes attempted.

policy_engine_read_runtime_context_ms:
  time spent in read_runtime_context(...) and immediate config/entity registry setup.

policy_engine_read_measurements_ms:
  time spent reading dynamic HA runtime measurements and previous state entities.

policy_engine_derive_inputs_ms:
  time spent deriving rpnz_w, required_power_w, required_power_consumption_kw and related raw input diagnostics.

policy_engine_policy_compute_ms:
  time spent in pure policy decision logic after measurements are available.

policy_engine_build_attrs_ms:
  time spent building canonical attrs and base diagnostics attrs.

policy_engine_hash_ms:
  time spent computing device_policies_hash, dispatch_command_hash, policy_state_hash and warning signature.

policy_engine_canonical_publish_ms:
  time spent publishing canonical bus sensors:
    - device_policies
    - dispatch_command
    - policy_state
    - previous_device_state if still in this phase

policy_engine_diagnostics_decision_ms:
  time spent deciding whether policy_diagnostics should publish.

policy_engine_diagnostics_build_ms:
  time spent building diagnostics-only payload fields.

policy_engine_diagnostics_publish_ms:
  time spent publishing policy_diagnostics if published, otherwise 0.

policy_engine_unaccounted_ms:
  total minus measured phase durations.
```

Use simple `time.time()` deltas. Avoid expensive profiling libraries.

Keep Pyscript AST compatibility in mind.

## Critical measurement rule

Do not add timing fields to canonical sensors.

Timing fields must be diagnostics-only.

They must not affect:

```text
device_policies_hash
dispatch_command_hash
policy_state_hash
canonical sensor attrs
writer/dispatch triggers
```

## Diagnostics publication nuance

Because diagnostics are throttled, phase timing should still be visible.

Recommended behavior:

```text
- Always keep latest phase timings in memory.
- Publish them in policy_diagnostics when diagnostics publish occurs.
- If diagnostics are throttled, do not publish just to expose timing.
```

This means production diagnostics may show the timing from the latest published diagnostics run, not every 5s run. That is acceptable.

Optional better behavior:

```text
Maintain rolling counters/aggregates in memory:
  - last_run_duration_ms
  - max_run_duration_ms_since_last_diagnostics
  - avg_run_duration_ms_since_last_diagnostics
  - runs_since_last_diagnostics
```

Then every 30 seconds, diagnostics can report a small aggregate without publishing every run.

Suggested optional fields:

```yaml
policy_engine_runs_since_last_diagnostics: 6
policy_engine_run_duration_last_ms: 402
policy_engine_run_duration_avg_ms: 397
policy_engine_run_duration_max_ms: 421
```

Keep this simple if implemented.

## Investigation report required

After instrumentation, Codex must produce a short report in the commit notes or a markdown file, for example:

```text
docs/dev/policy_engine_runtime_profile_findings.md
```

Report should include:

```text
- representative timing sample from tests or local HA-like run if available;
- which phase dominates the ~400 ms duration;
- whether diagnostics payload is built every run or only when published;
- whether read_runtime_context reloads/parses config every run;
- whether canonical publish still happens every run;
- recommended next optimization task, if any.
```

Do not make unsupported claims. If local tests cannot reproduce production timing, say so.

## Specific code inspection targets

Inspect and time these functions or equivalent current names:

```text
ems_policy_engine_tick
ems_policy_engine_loop
run_policy_loop
read_runtime_context
read_measurements
derive_net_zero_inputs
evaluate_policy / policy engine compute
net_zero_attrs / attrs construction
_device_policies_hash
_dispatch_command_hash
_policy_state_hash
_policy_warning_signature
publish_sensor calls
```

Use actual current function names from the repo.

## Possible next optimizations to evaluate, not necessarily implement

### Optimization candidate 1: cache static config/registry

If `read_runtime_context` dominates:

```text
Cache validated CoreConfig and device/runtime registry between runs.
Invalidate on:
  - Pyscript reload;
  - manual reload service if exists;
  - config file mtime change if feasible and cheap;
  - explicit config reload trigger.
```

Do not implement this unless measurements show config/context read dominates and a safe invalidation model is clear.

### Optimization candidate 2: build diagnostics only when publishing

If `build_attrs` or diagnostics construction dominates:

```text
Build only canonical control payloads every 5s.
Build full diagnostics attrs only when:
  - diagnostics interval elapsed;
  - canonical output changed;
  - warning/error state changed;
  - manual/e2e run.
```

This is likely a strong optimization if diagnostics attrs are large.

### Optimization candidate 3: canonical publish only on hash change

If canonical publish or event bus load still matters:

```text
Publish:
  sensor.ems_device_policies_pyscript only when device_policies_hash changes
  sensor.ems_surplus_dispatch_command_pyscript only when dispatch_command_hash changes
  sensor.ems_policy_state_pyscript only when policy_state_hash changes
```

This is a larger semantic change and must be separate or heavily tested.

### Optimization candidate 4: split canonical attrs from diagnostics attrs

If large canonical attrs cause CPU/event bus/recorder overhead:

```text
sensor.ems_device_policies_pyscript:
  canonical writer payload only

sensor.ems_policy_diagnostics_pyscript:
  broad explanation/debug/timing payload
```

This is architecturally desirable but should be a separate task unless instrumentation shows it is the dominant cost and tests are comprehensive.

## Tests to add

### Unit/integration tests for instrumentation presence

Add tests that diagnostics attrs include timing fields:

```text
test_policy_diagnostics_contains_phase_timing_fields
```

Expected fields at minimum:

```text
policy_engine_total_tick_duration_ms
policy_engine_read_runtime_context_ms
policy_engine_policy_compute_ms
policy_engine_hash_ms
policy_engine_canonical_publish_ms
policy_engine_diagnostics_publish_ms
policy_engine_unaccounted_ms
```

Values should be numeric and non-negative.

### Hash safety tests

Add/confirm:

```text
test_phase_timing_fields_do_not_change_device_policies_hash
test_phase_timing_fields_do_not_change_dispatch_command_hash
test_phase_timing_fields_do_not_change_policy_state_hash
```

### E2E determinism

Ensure E2E remains deterministic:

```text
trigger_reason='e2e' still publishes diagnostics every run;
timing values may be present but must not be asserted exactly unless mocked;
business expected values unchanged.
```

### Optional aggregate tests

If rolling aggregates are added:

```text
test_policy_engine_timing_aggregates_reset_after_diagnostics_publish
test_policy_engine_timing_aggregates_track_max_and_avg
```

## Grep checks

Run:

```bash
rg "policy_engine_.*_ms|total_tick_duration|unaccounted_ms" ems_*.py modules tests docs
```

Expected:

```text
- timing fields are diagnostics-only
- tests cover presence and hash safety
```

Run:

```bash
rg "policy_engine_run_duration_ms" ems_*.py modules tests docs
```

Expected:

```text
- old ambiguous metric is either clearly defined or replaced/supplemented
- docs explain what it measures
```

Run:

```bash
rg "read_runtime_context|read_measurements|derive_net_zero_inputs|publish_sensor" ems_policy_engine.py modules tests
```

Expected:

```text
- phase timing brackets the suspected expensive operations
```

## Tests to run

Focused tests:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_engine.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py
```

E2E:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/e2e_entity
```

Full suite:

```bash
PYTHONPATH=modules python3 -m pytest -q
```

## Acceptance criteria

Functional:

```text
- diagnostics include clear phase timing fields.
- timing fields are numeric and non-negative.
- timing fields are diagnostics-only.
- timing fields do not affect canonical hashes.
- E2E business expectations do not change.
- diagnostics throttling behavior does not regress.
```

Investigation:

```text
- It is clear what policy_engine_run_duration_ms currently measures.
- It is clear whether ~400 ms is dominated by:
  - read_runtime_context/config;
  - HA entity reads;
  - policy compute;
  - attrs construction;
  - hashing;
  - canonical publish;
  - diagnostics build/publish;
  - or something unaccounted.
```

Documentation/report:

```text
- A short findings report is added or included in commit notes.
- The report identifies the likely next optimization target.
- The report avoids speculative claims not supported by timing data.
```

Safety:

```text
- No NET_ZERO formula changes.
- No writer/dispatch contract changes.
- No canonical output entity ID changes.
- No device policy/dispatch business expectation changes.
```

## Production validation

After deployment, observe `sensor.ems_policy_diagnostics_pyscript` over several diagnostics intervals.

Record fields:

```yaml
policy_engine_total_tick_duration_ms:
policy_engine_read_runtime_context_ms:
policy_engine_read_measurements_ms:
policy_engine_derive_inputs_ms:
policy_engine_policy_compute_ms:
policy_engine_build_attrs_ms:
policy_engine_hash_ms:
policy_engine_canonical_publish_ms:
policy_engine_diagnostics_decision_ms:
policy_engine_diagnostics_build_ms:
policy_engine_diagnostics_publish_ms:
policy_engine_unaccounted_ms:
```

Interpretation examples:

```text
If read_runtime_context_ms is high:
  investigate config/registry caching.

If build_attrs_ms or diagnostics_build_ms is high:
  build diagnostics only when publishing and split canonical attrs.

If hash_ms is high:
  reduce canonical hash payloads.

If canonical_publish_ms is high:
  consider publish-only-on-hash-change in a separate task.

If unaccounted_ms is high:
  timing brackets are incomplete; improve instrumentation before optimizing.
```

## Final desired output

This task should not guess why `policy_engine_run_duration_ms` is around 400 ms.

It should make the runtime cost visible.

After this task, the next optimization should be selected based on measured phase timings, not intuition.
