# Pyscript startup/runtime warning investigation

## Summary

The dispatch_command / policy_state refactor did not make the EMS core
business logic hang. It did, however, increased the number of canonical sensor
updates during startup, which made existing Pyscript runtime weaknesses more
visible:

1. `EMS_config.yaml` was read synchronously from disk inside triggered
   Pyscript loops.
2. `ems_actuator_writers.py` used dynamic `globals().get(...)` indirection for
   imported runtime/config functions and HA adapter functions.

The repeated `Unknown config field` errors were still a deploy-version mismatch:
the running `config_loader.py` did not match the deployed `EMS_config.yaml`.
The warnings in this investigation explain why startup looked noisy and fragile
after the refactor.

## Blocking read/open source

The blocking I/O warning came from this call chain:

```text
ems_policy_engine_loop
  -> read_runtime_context
     -> _read_grouped_runtime_candidate
        -> load_and_validate_grouped_ems_config
           -> load_grouped_ems_config
              -> Path('/config/EMS_config.yaml').read_text(...)

ems_dispatch_state_applier_loop
  -> read_runtime_entities
     -> read_runtime_context
        -> same path

ems_actuator_writers_loop
  -> read_runtime_entities / read_core_config
     -> read_runtime_context
        -> same path
```

Before the fix, policy, dispatch, and writer loops could all reread and
revalidate the YAML file.

## Cache behavior

`runtime_context.py` now caches the parsed grouped config and validation result
by:

```text
path
mtime_ns
size
```

The runtime still rebuilds `CoreConfig` on each loop using current HA entity
values, so `input_number` / `input_select` configuration changes remain live.
Only the YAML file read and validation are cached until the file signature
changes.

## Coroutine warning source

The exact runtime object that produced:

```text
RuntimeWarning: coroutine 'EvalFuncVarClassInst.__call__' was never awaited
```

cannot be proven from local unit tests alone because it depends on Pyscript's
runtime wrappers. The strongest code-level evidence was in
`ems_actuator_writers.py`, where imported functions were reloaded through
`globals().get(...)` and called through local variables:

```python
reader = globals().get('read_runtime_entities')
reader(...)

reader = globals().get('read_core_config')
reader(...)
```

Similar dynamic calls existed for `get_attr` and `publish_sensor`.

These production paths now use direct imported global names. Tests still replace
those globals explicitly when needed, but production no longer fetches callable
objects dynamically from Pyscript globals.

## Can the warnings prevent EMS operation?

The blocking I/O warning by itself is not a functional failure, but repeated
blocking reads inside startup-triggered loops can delay Home Assistant's event
loop and make EMS startup appear stuck.

The unawaited coroutine warning is more serious. If it comes from a Pyscript
wrapped callable, the intended call may not execute. Removing dynamic callable
indirection from the writer removes the most suspicious production pattern.

The config validation exceptions are fatal for that loop execution. If the
deployed config and deployed `config_loader.py` disagree, policy/dispatch/writer
loops will keep failing until the files are version-aligned.

## Minimal fixes applied

1. Added mtime/size-based grouped config cache in `runtime_context.py`.
2. Kept `CoreConfig` rebuilds live against HA entity readers.
3. Replaced dynamic runtime/config loader calls in `ems_actuator_writers.py`
   with direct imports.
4. Replaced dynamic HA adapter callable calls in writer with direct global
   function calls.
5. Added regression tests for cache behavior and dynamic-call avoidance.

## Tests

Relevant tests:

```text
tests/contract/test_grouped_config_runtime_parity.py
  test_read_runtime_context_caches_grouped_config_until_file_signature_changes

tests/unit/test_writer_semantics.py
  test_writer_runtime_config_loaders_are_direct_imports_not_pyscript_globals
```

The existing writer semantics tests also guard that actuator behavior and
idempotency did not change.

## Production rollout notes

Deploy the Python files and `EMS_config.yaml` as a matched set:

```text
/config/pyscript/ems_policy_engine.py
/config/pyscript/ems_dispatch_state_applier.py
/config/pyscript/ems_actuator_writers.py
/config/pyscript/modules/ems_adapter/config_loader.py
/config/pyscript/modules/ems_adapter/runtime_context.py
/config/pyscript/modules/ems_core/domain/models.py
/config/EMS_config.yaml
```

After restart, validate:

```text
sensor.ems_device_policies_pyscript
sensor.ems_surplus_dispatch_command_pyscript
sensor.ems_policy_state_pyscript
```

The first YAML read can still happen during startup. Repeated `read_text` /
`open` warnings for `/config/EMS_config.yaml` should stop unless the file is
edited between loop runs.

