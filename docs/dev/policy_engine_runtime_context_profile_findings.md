# Policy engine runtime context profile findings

## Original production sample

Observed before this change set:

```yaml
policy_engine_total_tick_duration_ms: 907
policy_engine_read_runtime_context_ms: 491
policy_engine_read_measurements_ms: 62
policy_engine_policy_compute_ms: 222
policy_engine_hash_ms: 73
policy_engine_canonical_publish_ms: 18
```

## What `read_runtime_context` did before optimization

Per real policy run it rebuilt:

- `CoreConfig` through `build_core_config_from_grouped_reader(...)`
- runtime entity registry through `build_runtime_entities_from_grouped_config(...)`
- EV-derived registry values
- config trace status

Only grouped YAML parse and validation were cached by file signature.

## What is now cached

Static cache in `modules/ems_adapter/runtime_context.py` now stores:

- grouped config path
- grouped config `mtime_ns`
- grouped config size
- parsed grouped config
- validation result
- runtime entity registry built from grouped YAML
- compiled CoreConfig static plan with explicit dynamic refs
- cache hit and miss counters

The cache is resettable through `_reset_runtime_context_config_cache()` for tests.

## What remains dynamic on every run

These values are still read fresh on every real policy run:

- HA-backed values used by `build_core_config_from_grouped_reader(...)`
- control selections such as `adjustable_surplus_load`
- numeric thresholds such as `battery_protect_soc`
- boolean dashboard controls such as EV `force_on`
- per-device priorities and similar policy inputs

`CoreConfig` itself is not cached across runs.

## Static plan model

Phase 5 Option B is now implemented.

The grouped-config loader compiles a static plan keyed by grouped config file signature:

- static YAML structure is compiled once
- HA-backed dynamic leaves are represented as `DynamicConfigRef(path, entity_id, value_type, default)`
- every real policy run reads those refs fresh
- the run materializes a fresh resolved config tree
- a fresh `CoreConfig` is built from that materialized tree

One compatibility override is preserved explicitly:

- `HOME_BATTERY.policy.priority` still falls back to the first resolved EV priority when its own HA-backed value is absent, matching the pre-plan behavior

## Added diagnostics

Policy diagnostics now expose:

- previous diagnostics publish duration via `policy_engine_previous_diagnostics_publish_ms`
- diagnostics publish attempt marker via `policy_engine_last_diagnostics_publish_attempted`
- policy compute sub-metrics:
  - `policy_engine_guard_compute_ms`
  - `policy_engine_haeo_plan_compute_ms`
  - `policy_engine_net_zero_compute_ms`
- hash sub-metrics:
  - `policy_engine_device_policies_hash_ms`
  - `policy_engine_dispatch_command_hash_ms`
  - `policy_engine_policy_state_hash_ms`
  - `policy_engine_warning_signature_hash_ms`
- runtime context metrics:
  - `policy_engine_config_signature_ms`
  - `policy_engine_static_context_cache_hit`
  - `policy_engine_static_context_cache_hits`
  - `policy_engine_static_context_cache_misses`
  - `policy_engine_static_context_build_ms`
  - `policy_engine_dynamic_config_reads_ms`
  - `policy_engine_runtime_entity_registry_ms`
  - `policy_engine_core_config_build_ms`

These fields are diagnostics-only and are excluded from canonical hash inputs.

## Timing model

Runtime context timing is now split more honestly:

- `policy_engine_static_context_build_ms`:
  grouped YAML validation, runtime entity registry build, and static plan compilation on cache miss
- `policy_engine_dynamic_config_reads_ms`:
  HA-backed config value reads performed while materializing the cached plan
- `policy_engine_core_config_build_ms`:
  fresh `CoreConfig` construction from the already materialized values

`policy_engine_unaccounted_ms` is now interpreted against the published diagnostics snapshot boundary.
That means:

- the snapshot includes work completed before the current diagnostics publish call
- the current diagnostics publish wall time is not guessed into the same snapshot
- `policy_engine_previous_diagnostics_publish_ms` carries the last completed diagnostics publish duration

This removes one major source of misleading unaccounted time in diagnostics snapshots.

## Tests run

Executed locally:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_engine.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py
PYTHONPATH=modules python3 -m pytest -q tests/contract/test_grouped_config_runtime_parity.py
PYTHONPATH=modules python3 -m pytest -q tests/contract/test_runtime_entity_registry_contract.py
PYTHONPATH=modules python3 -m pytest -q tests/contract/test_grouped_config_contract.py
PYTHONPATH=modules python3 -m pytest -q tests/e2e_entity
PYTHONPATH=modules python3 -m pytest -q
```

Result:

- full suite passed
- `356 passed, 1 xfailed`
- the existing HAEO future-semantics xfail remained unchanged

## Local timing caveat

Local pytest runs validate correctness, cache invalidation, and diagnostics boundaries.
They do not reproduce Home Assistant plus Pyscript runtime overhead accurately enough to claim the production timing delta in advance.

## Production validation checklist

After deployment, inspect:

```yaml
policy_engine_total_tick_duration_ms:
policy_engine_read_runtime_context_ms:
policy_engine_config_signature_ms:
policy_engine_static_context_cache_hit:
policy_engine_static_context_cache_hits:
policy_engine_static_context_cache_misses:
policy_engine_static_context_build_ms:
policy_engine_dynamic_config_reads_ms:
policy_engine_runtime_entity_registry_ms:
policy_engine_core_config_build_ms:
policy_engine_policy_compute_ms:
policy_engine_guard_compute_ms:
policy_engine_haeo_plan_compute_ms:
policy_engine_net_zero_compute_ms:
policy_engine_hash_ms:
policy_engine_device_policies_hash_ms:
policy_engine_dispatch_command_hash_ms:
policy_engine_policy_state_hash_ms:
policy_engine_warning_signature_hash_ms:
policy_engine_previous_diagnostics_publish_ms:
policy_engine_unaccounted_ms:
```

Expected direction:

- cache hits should dominate after the first run
- `policy_engine_static_context_build_ms` should be near zero on cache-hit runs
- `policy_engine_runtime_entity_registry_ms` should be near zero on cache-hit runs
- dashboard-driven HA values should still affect the next real policy run
- if `policy_engine_core_config_build_ms` remains dominant even after the static-plan split, profile that builder path directly before introducing any additional cache
