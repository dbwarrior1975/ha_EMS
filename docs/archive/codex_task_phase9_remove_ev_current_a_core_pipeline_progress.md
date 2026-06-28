# Codex Task: Remove `current_a` from EV Core Decision Pipeline - Progress

Source task: [codex_task_phase9_remove_ev_current_a_core_pipeline.md](/home/virtamik/code/ha_EMS/codex_task_phase9_remove_ev_current_a_core_pipeline.md)

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Locate Current Amp-Based EV Decision Flow | Done | Audited the active EV decision path and classified remaining `current_a` references. Core decision usage in `modules/ems_core/net_zero/load_projection.py` and `modules/ems_core/net_zero/engine.py` was the only forbidden category; runtime/debug and writer usage remain allowed. |
| 2. Replace EV Strategy API | Done | Replaced `ev_strategy_current_a(...)` with `ev_strategy_target_w(...)`, converted EV core policy flow to watt targets, and kept W/A conversion at the writer boundary. |
| 3. Update Engine to Consume `target_w` Directly | Done | Removed the active `current_a -> target_w` policy roundtrip from engine control flow. Engine now accepts `ev_strategy_target_w(...)` output directly and only converts measured charger current for telemetry/debug purposes. |
| 4. Keep W/A Conversion Only in Writer | Done | Verified that active W -> A target conversion remains only in `ems_actuator_writers.py`. Engine/load_projection no longer convert policy targets to current, and writer tests cover watt-target to selector-current behavior. |
| 5. Restrict Derived Current Fields | Done | Removed remaining EV core decision dependence on `ev_min_current_a` / `ev_max_current_a` in engine stepping and max-hold logic. Legacy amp fields remain only as compatibility/debug data, not as EV policy decision inputs. |
| 6. Tests to Update or Add | Done | Added regressions for capability-max watt semantics, watt-based restore-min assertions, and writer-only W -> A conversion. Verified unit and contract coverage for the updated EV target-watt contract. |
| 7. Search-Based Acceptance Checks | Done | Verified by repository search that `ev_strategy_current_a` and `return cfg.ev_*current_a` are gone from active core EV decision flow. Remaining amp references are confined to helper, writer, debug, compatibility, measured-runtime, or tests. |
| 8. Acceptance Wrap-Up | Done | Phase 1-7 acceptance checks and required unit/contract regressions pass for the EV target-watt contract. |

## Phase 1 Classification Snapshot

### Allowed helper / writer / debug usage

- `modules/ems_core/domain/models.py`
  - legacy EV amp fields are compatibility model inputs / derived fields
- `modules/ems_adapter/runtime_context.py`
  - EV amp fields are runtime/debug trace values
- `ems_actuator_writers.py`
  - EV watts are converted to current at the writer boundary

### Forbidden core decision usage

- `modules/ems_core/net_zero/load_projection.py`
  - replaced the active EV policy output with watts
- `modules/ems_core/net_zero/engine.py`
  - EV decision flow now carries `target_w` instead of `current_a`

### Test-only usage

- `tests/unit/test_load_projection.py`
- `tests/unit/test_engine.py`
- other EV tests and fixtures that intentionally validate conversion / writer semantics

## Completed Work

### Phase 1

- Located the active EV amp-based decision flow.
- Confirmed the relevant production references were concentrated in:
  - `modules/ems_core/net_zero/load_projection.py`
  - `modules/ems_core/net_zero/engine.py`
  - `modules/ems_core/domain/models.py`
  - `modules/ems_adapter/runtime_context.py`
  - `ems_actuator_writers.py`
- Classified the remaining references:
  - helper / writer / debug usage: allowed
  - core decision usage: removed or replaced
  - test-only usage: allowed

### Phase 2

- Introduced `ev_strategy_target_w(...)` as the EV strategy entry point.
- Updated EV mode selection in `modules/ems_core/net_zero/engine.py` to carry watt targets through policy evaluation.
- Kept EV current conversion at the actuator boundary.
- Preserved the selected semantic that `force_on` overrides optimization, but not safety/device blocking.

### Phase 3

- Removed the active engine pattern that derived EV target watts from a strategy-returned current value.
- Passed `target_w` directly from EV strategy output into device policies.
- Kept measured charger current only as an input for runtime/safety state and telemetry/debug derivations.

### Phase 4

- Verified the active production EV writer flow remains:
  - `device_policy.target_w`
  - capability clamp against `min_absorb_w` / `max_absorb_w`
  - `target_w -> supported current_a` conversion in writer
  - charger enable/current selector write
- Confirmed `ev_power_w_to_current_a(...)` and derived-current helpers are used in active production only at the writer boundary.
- Confirmed engine and load projection do not convert EV policy targets from watts back to amps.

### Phase 5

- Removed core EV step quantization dependence on `cfg.ev_min_current_a` / `cfg.ev_max_current_a`.
- Switched primary EV envelope quantization to watt-space using:
  - `ev_min_power_w(cfg)`
  - `ev_max_power_w(cfg)`
  - `ev_power_step_w(cfg)`
- Replaced EV max-hold comparison in engine from measured-current-vs-max-current to measured-power-vs-max-power.
- Left legacy amp fields in config/runtime only as compatibility/debug values.

### Phase 6

- Added a regression proving `force_on` uses EV capability max watts directly, not compatibility current-derived max power.
- Added a load-projection regression proving `burn_active` returns capability max watts even when current-based compatibility fields do not match.
- Updated restore-min engine assertions to check watt targets via `ev_min_power_w(cfg)` instead of amp-derived expectations.
- Added a writer regression covering exact `target_w = 6440` -> selector `28 A` conversion in the writer layer.
- Updated EV power helpers to prefer capability watt fields when they are present, keeping compatibility current fields as fallback only.

### Phase 7

- Searched `modules/ems_core/net_zero/load_projection.py` and `modules/ems_core/net_zero/engine.py` for:
  - `ev_strategy_current_a`
  - `return cfg.ev_max_current_a`
  - `return cfg.ev_min_current_a`
- Confirmed those forbidden core-strategy outputs no longer exist.
- Confirmed remaining `ev_current_a_to_power_w(...)` in engine are measured-current helper uses, not policy-target derivations.
- Confirmed remaining `ev_power_w_to_current_a(...)` production usage is only in `ems_actuator_writers.py`.

## Phase 9: Remove EV current_a from core decision pipeline

- Replaced EV core strategy output from `current_a` to `target_w`.
- Removed A -> W -> A policy roundtrip.
- `force_on` now maps directly to `max_absorb_w` before writer.
- `NET_ZERO` burn now maps directly to `max_absorb_w` before writer.
- `hard_off` maps directly to `0 W` before writer.
- W -> A conversion remains only in EV writer / EV power helpers.
- Remaining amp references are limited to writer, helper, debug, compatibility, or tests.

## Verification

- `pytest -q tests/unit/test_load_projection.py tests/unit/test_engine.py`
- `pytest -q tests/unit/test_writer_semantics.py tests/unit/test_ev_power.py`
- `pytest -q tests/contract/test_grouped_config_runtime_parity.py tests/contract/test_runtime_entity_registry_contract.py`
- `pytest -q tests/unit/test_load_projection.py`
- `pytest -q tests/unit/test_engine.py`
- `pytest -q tests/unit/test_ev_power.py`
- `pytest -q tests/unit/test_writer_semantics.py`
- `python3 -m py_compile modules/ems_core/net_zero/load_projection.py modules/ems_core/net_zero/engine.py tests/unit/test_load_projection.py`
