# Codex task: harden and optimize Phase 5 CoreConfig materialization

## Purpose

EMS Phase 5 has already introduced the right architectural direction:

```text
cached static config plan
+ fresh dynamic HA-backed config reads
+ CoreConfig materialization per real policy run
```

Do **not** restart the refactor from scratch.

This task is to review, harden, and optimize the existing Phase 5 implementation so the hot path cost of `read_runtime_context(...)` drops materially without freezing dashboard-controlled HA values.

---

## Current production evidence

Latest relevant production diagnostics from the Phase 5 implementation:

```yaml
policy_engine_trigger_mode: timer
policy_engine_interval_seconds: 5
policy_engine_static_context_cache_hit: true
policy_engine_static_context_cache_hits: 92
policy_engine_static_context_cache_misses: 2
policy_engine_static_context_build_ms: 0
policy_engine_runtime_entity_registry_ms: 0

policy_engine_dynamic_config_reads_ms: 121
policy_engine_core_config_build_ms: 327
policy_engine_read_runtime_context_ms: 459

policy_engine_total_tick_duration_ms: 895
policy_engine_read_measurements_ms: 63
policy_engine_derive_inputs_ms: 7
policy_engine_policy_compute_ms: 231
policy_engine_build_attrs_ms: 9
policy_engine_hash_ms: 72
policy_engine_canonical_publish_ms: 14
policy_engine_diagnostics_decision_ms: 1
policy_engine_diagnostics_build_ms: 5
policy_engine_previous_diagnostics_publish_ms: 3
policy_engine_unaccounted_ms: 34

policy_engine_guard_compute_ms: 3
policy_engine_haeo_plan_compute_ms: 7
policy_engine_net_zero_compute_ms: 221

policy_engine_device_policies_hash_ms: 23
policy_engine_dispatch_command_hash_ms: 37
policy_engine_policy_state_hash_ms: 8
policy_engine_warning_signature_hash_ms: 4
```

Interpretation:

```text
- Static context cache is working.
- Runtime entity registry build is out of the hot path on cache-hit runs.
- Metrics are now credible; unaccounted_ms is low enough to trust the phase breakdown.
- The remaining dominant cost inside read_runtime_context is CoreConfig materialization.
- Dynamic HA-backed config reads are also material, but must remain fresh every real policy run.
```

Approximate hot path proportions:

```text
read_runtime_context_ms      459 ms  ~= 51% of total_tick_duration_ms
core_config_build_ms         327 ms  ~= 71% of read_runtime_context_ms
dynamic_config_reads_ms      121 ms  ~= 26% of read_runtime_context_ms
policy_compute_ms            231 ms
hash_ms                       72 ms
read_measurements_ms          63 ms
```

The next optimization target is therefore **not** static cache creation. It is the existing CoreConfig materialization path.

---

## Current implementation assumptions

The reviewed Phase 5 package appears to contain at least these concepts:

```text
modules/ems_adapter/config_loader.py
  DynamicConfigRef
  CompiledCoreConfigPlan
  compile_core_config_plan_from_grouped_config(...)
  materialize_core_config_from_plan(...)

modules/ems_adapter/runtime_context.py
  cache stores/reuses core_config_plan
  cache-hit path materializes CoreConfig from cached plan
  dynamic_config_reads_ms is measured separately
  core_config_build_ms is measured separately from dynamic reads
```

Preserve this direction.

Do not introduce a second parallel config-plan abstraction unless there is a clear measured or correctness reason.

---

## Required outcome

On normal cache-hit production runs:

```text
policy_engine_static_context_cache_hit: true
policy_engine_static_context_build_ms: 0 or near 0
policy_engine_runtime_entity_registry_ms: 0 or near 0
policy_engine_dynamic_config_reads_ms: honest non-negative value
policy_engine_core_config_build_ms: materially lower than current ~327 ms
policy_engine_read_runtime_context_ms: materially lower than current ~459 ms
policy_engine_total_tick_duration_ms: materially lower than current ~895 ms
```

Concrete target for this task:

```text
Aim to reduce policy_engine_core_config_build_ms by at least 50% on cache-hit runs,
or document precisely why the remaining cost is unavoidable in Pyscript/HA.
```

Stretch target:

```text
policy_engine_core_config_build_ms < 100 ms on ordinary cache-hit runs.
policy_engine_read_runtime_context_ms < 250 ms on ordinary cache-hit runs.
```

Do not change business behavior to hit these targets.

---

## Non-negotiable correctness constraints

Dynamic HA-backed values must still update on the next real policy run.

Do not cache/freeze values from:

```text
- input_select control / goal / forecast / guard profiles
- input_number thresholds, limits, priorities, ramps, deadbands
- input_boolean force_on / enabled / surplus_allowed flags
- runtime sensor states
- previous EMS state sensors
- active surplus state sensors
- charger / relay / battery state inputs if used
```

Static data may be cached by config file signature:

```text
- grouped YAML parse result
- validation result
- static device definitions
- device IDs and kinds
- static capabilities and literal defaults
- entity-reference mapping
- DynamicConfigRef list
- static runtime/device registry structure
- canonical output entity IDs
- compiled CoreConfig construction plan
```

Never cache the full materialized `CoreConfig` across policy runs unless every dynamic field is replaced with fresh values before policy use. Prefer not to cache full `CoreConfig` at all.

---

## Main implementation task

### 1. Profile `materialize_core_config_from_plan(...)`

Add local timing brackets or temporary structured diagnostics to determine where the current ~327 ms is spent.

Likely suspects:

```text
- repeated deep copy of static dictionaries/lists/dataclasses
- rebuilding full device dataclass graphs every tick
- re-resolving literal/static defaults every tick
- repeated capability normalization
- repeated enum/string normalization
- repeated validation that only depends on static YAML
- repeated construction of unchanged nested structures
- broad attrs/config trace structures being copied into CoreConfig
```

Do not leave noisy temporary diagnostics in final canonical outputs.

If final new sub-metrics are kept, they must be diagnostics-only.

Possible useful new diagnostics-only fields:

```yaml
policy_engine_core_config_materialize_ms:
policy_engine_core_config_static_copy_ms:
policy_engine_core_config_dynamic_apply_ms:
policy_engine_core_config_device_materialize_ms:
policy_engine_core_config_trace_materialize_ms:
```

Use different names if better, but make them honest.

### 2. Move static work into `CompiledCoreConfigPlan`

The compiled plan should contain as much immutable/static work as possible.

Examples of work that should not happen every policy run on cache hit:

```text
- parsing or traversing grouped YAML shape
- deciding which fields are literal vs HA-backed references
- constructing DynamicConfigRef objects
- resolving static default values
- normalizing static device metadata
- sorting static device order / priorities when independent of dynamic values
- resolving device kinds and static capabilities
- building static registry skeletons
- validating static schema constraints
```

The per-run materialization step should ideally do only:

```text
- read dynamic values via DynamicConfigRef
- apply those dynamic values into a lightweight runtime config view
- build only the minimal mutable policy input required by the policy engine
```

### 3. Reduce dataclass/object graph rebuild cost

If the policy engine currently requires a full `CoreConfig` dataclass graph every run, optimize construction without compromising freshness.

Allowed approaches:

```text
A. Static skeleton + dynamic overlay
   Keep immutable/static nested objects in the plan and apply dynamic values into a small overlay object.

B. CoreConfigView / PolicyConfigView
   Introduce a lightweight per-run view that exposes the same fields the policy engine needs,
   backed by static plan + dynamic values.

C. Minimal materialized CoreConfig
   Continue returning CoreConfig but avoid rebuilding unchanged subgraphs.

D. Field-level materialization
   Materialize only fields used by the policy engine hot path.
```

Avoid unnecessary broad rewrites. Prefer the smallest design that produces a real measured drop.

If introducing `PolicyContext`, `CoreConfigView`, or similar, keep the migration contained and well-tested.

### 4. Keep dynamic reads explicit and testable

`DynamicConfigRef` or equivalent must remain visible and testable.

Each dynamic read should be attributable to:

```text
- config path / field path
- HA entity_id
- expected value type
- default/fallback behavior
```

`policy_engine_dynamic_config_reads_ms` must remain honest. It should not be hidden inside `core_config_build_ms` again.

### 5. Clean up only actually obsolete compatibility code

EMS is still in dev state and the next version does not need old config-shape compatibility, but do not remove code blindly.

Allowed cleanup:

```text
- remove dead legacy paths proven unused by tests and current config contract
- remove dual-read paths only if current tests/docs agree grouped config is the only supported production shape
- remove compatibility wrappers only after replacing tests that still depend on them
```

Do not perform large naming churn unless it directly clarifies the current Phase 5 architecture.

---

## Required tests

Keep the full existing suite green.

Add or harden tests specifically for the existing Phase 5 path.

### Dynamic freshness tests

Config file signature unchanged; cached plan hit; mutable HA-backed values changed between reads.

Required scenarios:

```text
test_dynamic_control_value_updates_with_compiled_plan_cache_hit
test_dynamic_goal_value_updates_with_compiled_plan_cache_hit
test_dynamic_forecast_profile_value_updates_with_compiled_plan_cache_hit
test_dynamic_guard_value_updates_with_compiled_plan_cache_hit

test_dynamic_input_number_threshold_updates_with_compiled_plan_cache_hit
test_dynamic_input_number_priority_updates_with_compiled_plan_cache_hit
test_dynamic_input_boolean_enabled_updates_with_compiled_plan_cache_hit
test_dynamic_input_boolean_force_on_updates_with_compiled_plan_cache_hit
```

At minimum each test must prove:

```text
1. First read builds or uses compiled plan.
2. Second read is a cache hit with unchanged config signature.
3. HA-backed value is changed between reads.
4. Returned policy input/CoreConfig reflects the new value.
5. No full static rebuild was required.
```

### Cache invalidation tests

```text
test_compiled_core_config_plan_cache_miss_on_first_read
test_compiled_core_config_plan_cache_hit_when_signature_unchanged
test_compiled_core_config_plan_invalidates_when_config_signature_changes
test_compiled_core_config_plan_reset_for_tests
```

### Metrics tests

```text
test_runtime_context_metrics_split_dynamic_reads_from_core_config_materialization
test_core_config_materialization_metrics_are_non_negative
test_core_config_materialization_metrics_are_diagnostics_only
test_context_cache_metrics_do_not_change_device_policies_hash
test_context_cache_metrics_do_not_change_dispatch_command_hash
test_context_cache_metrics_do_not_change_policy_state_hash
```

### Behavioral safety tests

Keep existing E2E expectations unchanged.

Add targeted tests if any refactor touches:

```text
- EV restore_min / hard_off semantics
- HOME_BATTERY primary + EV surplus combo
- relay priorities and thresholds
- surplus release / dispatch canonical payload
- NET_ZERO quarter/RPNZ calculations
```

---

## Validation commands

Focused tests:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_engine.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py
PYTHONPATH=modules python3 -m pytest -q tests/contract/test_grouped_config_runtime_parity.py
PYTHONPATH=modules python3 -m pytest -q tests/contract/test_runtime_entity_registry_contract.py
PYTHONPATH=modules python3 -m pytest -q tests/contract/test_grouped_config_contract.py
```

E2E:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/e2e_entity
```

Full suite:

```bash
PYTHONPATH=modules python3 -m pytest -q
```

Grep checks:

```bash
rg "DynamicConfigRef|CompiledCoreConfigPlan|compile_core_config_plan|materialize_core_config" modules tests docs ems_*.py
rg "core_config_build_ms|dynamic_config_reads_ms|static_context_cache|runtime_entity_registry_ms" modules tests docs ems_*.py
rg "build_core_config_from_grouped_reader" modules tests docs ems_*.py
rg "policy_engine_.*_ms|previous_diagnostics_publish_ms|unaccounted_ms" modules tests docs ems_*.py
```

Expected grep interpretation:

```text
- Existing Phase 5 concepts are reused, not duplicated under another abstraction.
- build_core_config_from_grouped_reader is not the production hot path if compiled plan cache is available.
- dynamic_config_reads_ms remains separate and honest.
- timing/cache metrics are diagnostics-only.
```

---

## Production validation checklist

After deployment, collect stable cache-hit diagnostics from `sensor.ems_policy_diagnostics_pyscript`.

Required fields:

```yaml
policy_engine_static_context_cache_hit:
policy_engine_static_context_cache_hits:
policy_engine_static_context_cache_misses:
policy_engine_static_context_build_ms:
policy_engine_runtime_entity_registry_ms:
policy_engine_dynamic_config_reads_ms:
policy_engine_core_config_build_ms:
policy_engine_read_runtime_context_ms:
policy_engine_total_tick_duration_ms:
policy_engine_policy_compute_ms:
policy_engine_net_zero_compute_ms:
policy_engine_hash_ms:
policy_engine_unaccounted_ms:
```

Pass criteria:

```text
- static_context_cache_hit is usually true after first run
- static_context_build_ms is near 0 on cache-hit runs
- runtime_entity_registry_ms is near 0 on cache-hit runs
- core_config_build_ms is materially lower than ~327 ms
- read_runtime_context_ms is materially lower than ~459 ms
- total_tick_duration_ms is materially lower than ~895 ms
- unaccounted_ms remains low, ideally < 100 ms on ordinary runs
- dashboard changes affect the next real policy run
```

If `core_config_build_ms` remains >200 ms on ordinary cache-hit runs, document exactly what remains inside materialization and propose the next split.

---

## Stop conditions

Stop and fix before proceeding if any of these happen:

```text
- input_select/input_number/input_boolean values are frozen on cache hits
- config signature changes do not invalidate the compiled plan
- invalid config file changes silently keep using stale valid config
- policy outputs change unexpectedly
- E2E business expectations change
- canonical hashes change only because timing/cache fields changed
- dynamic_config_reads_ms becomes 0 while HA-backed dynamic refs still exist
- core_config_build_ms is reduced only by hiding work in another unmeasured bucket
- unaccounted_ms grows above 100 ms on ordinary runs without explanation
```

---

## Important semantic rules to preserve

Do not change EMS policy semantics as part of this performance task.

Preserve:

```text
- watt-native EV policy
- HOME_BATTERY primary + EV surplus split
- EV restore_min and hard_off behavior
- RPNZ / quarter balancing formulas
- surplus CLEAR_ALL canonical stability
- canonical output hash scopes
- diagnostics throttling behavior
```

This task is an architecture/performance hardening task, not a behavior change task.

---

## Final instruction

The previous static cache optimization succeeded but did not remove the main hot-path cost.

The task is now to make the already-introduced Phase 5 architecture pay off:

```text
Reuse cached static plan.
Read dynamic HA values fresh.
Materialize only what policy actually needs.
Measure honestly.
Keep behavior identical.
```
