# EV Charger Watt-Based Refactor Progress

Source task: [codex_task_ev_charger_watt_based_force_on_refactor.md](/home/virtamik/code/ha_EMS/codex_task_ev_charger_watt_based_force_on_refactor.md)

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Add Central EV W/A Helper Functions | Done | Added central helpers in `modules/ems_core/domain/ev_power.py` and expanded unit coverage in `tests/unit/test_ev_power.py`. Verified with targeted unit tests. |
| 2. Update EV Config Schema / Models | Done | Core EV config now models `policy.force_on`, derives EV current bounds from watt capabilities, validates representable W/A ranges, and treats legacy amp fields as deprecated compatibility inputs rather than primary policy fields. |
| 3. Update Runtime Read Model | Done | Runtime EV read model now resolves `force_on`, uses configured `voltage_v` for EV power conversion, and exposes derived EV debug fields (`ev_per_amp_w`, derived current bounds, derived step watts, current power). |
| 4. Update Surplus Target Construction | Done | Replaced EV adjustable threshold construction with watt-based `max_absorb_w - min_absorb_w` semantics, preserved `adjustable_surplus_activation_w` override, and added explicit threshold-source trace fields. |
| 5. Update Load Projection / Mode Logic | Done | EV mode logic now uses `policy.force_on` instead of `force_current_a`, applies force-on as max-watt/max-current intent across manual/net-zero/max-export/cheap-charge modes, and keeps low-PV battery safety able to hard-off EV even when force-on is set. |
| 6. Update EV Actuator Writer | Done | EV writer now derives selector current from watt targets and watt capabilities, uses configured voltage/phases/step, and disables the charger with derived-min selector on zero/blocked targets. |
| 7. Update Tests | Done | Updated writer, grouped-config parity, and smoke expectations to the watt-based EV contract; targeted regression pack passes. |
| 8. Update Examples and Documentation | Pending | Not started. |

## Completed Work

### Phase 1

- Added centralized EV conversion helpers:
  - `ev_per_amp_w(...)`
  - `ev_current_a_to_power_w(...)`
  - `ev_min_current_a_from_min_absorb_w(...)`
  - `ev_max_current_a_from_max_absorb_w(...)`
  - `ev_power_w_to_current_a(...)`
- Removed hardcoded `230 V` from the new conversion path by making voltage explicit in helper APIs.
- Kept legacy compatibility helpers in place for the remaining refactor phases.
- Added unit coverage for:
  - 1-phase and 3-phase conversion
  - non-230 V conversion
  - min current rounding up
  - max current rounding down
  - step quantization
  - max clamp / representability guard

### Phase 2

- Added `force_on` to EV policy models and grouped-config validation.
- Switched derived EV min/max current compatibility fields to come from:
  - `capabilities.min_absorb_w`
  - `capabilities.max_absorb_w`
  - `adapter.current_step_a`
  - `adapter.phases`
  - `adapter.voltage_v`
- Relaxed EV `capabilities.step_w` from required to optional in grouped config; EV runtime now derives step watts from adapter resolution.
- Added numeric validation that rejects EV watt ranges that cannot be represented by the configured charger step/phases/voltage.
- Kept these legacy grouped-config fields as transitional compatibility inputs:
  - `adapter.current_min_a`
  - `adapter.current_max_a`
  - `adapter.force_current_a`
- Updated `example_EMS_config.yaml` and `EMS_config.yaml` to add `policy.force_on`.

### Phase 3

- Updated EV runtime registry output to expose:
  - `force_on`
  - `min_absorb_w`
  - `max_absorb_w`
  - `ev_per_amp_w`
  - `ev_derived_min_current_a`
  - `ev_derived_max_current_a`
  - `ev_derived_step_w`
  - `ev_current_power_w`
- Stopped using deprecated EV amp fields as the primary runtime source for EV policy semantics.
- Fixed EV measured-power conversion in `device_read_model` to use configured `voltage_v` instead of relying on the default voltage path.
- Derived EV `step_w` from charger selector resolution when building runtime device configs from grouped core config.

### Phase 4

- Replaced amp-range-based EV surplus threshold construction in `modules/ems_core/net_zero/surplus_device_targets.py`.
- Selected one explicit EV activation semantic based on current behavior:
  - `incremental_surplus_threshold_w = max_absorb_w - min_absorb_w`
- Removed the hardcoded `230 V` path from EV adjustable-threshold construction by using watt capabilities directly.
- Preserved `adjustable_surplus_activation_w` as an explicit threshold override for both EV and battery adjustable targets.
- Added threshold trace/debug metadata to surplus target payloads:
  - `threshold_source`
  - `incremental_surplus_threshold_w` for the EV incremental-threshold path
- Updated unit tests to encode the selected EV threshold semantics and trace output.
- Fixed a multi-EV engine test fixture to include the now-required EV `policy.force_on` field.

## Verification

- `pytest -q tests/unit/test_ev_power.py`
- `pytest -q tests/unit/test_haeo_horizon.py`
- `pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py tests/unit/test_device_read_model.py tests/contract/test_grouped_config_contract.py tests/contract/test_runtime_entity_registry_contract.py tests/contract/test_grouped_config_runtime_parity.py`
- `pytest -q tests/unit/test_surplus_device_targets.py`
- `pytest -q tests/unit/test_engine.py`

### Phase 5

- Replaced EV load-projection mode semantics in `modules/ems_core/net_zero/load_projection.py`:
  - `MANUAL` / `MANUAL_SAFE`: `force_on` commands EV at max current.
  - `NET_ZERO`: `force_on` overrides optimizer mode to max current.
  - `MAX_EXPORT`: selected the explicit project semantic that `force_on` overrides optimization mode and still charges EV.
  - `CHEAP_GRID_CHARGE`: `force_on` resolves to max current instead of legacy direct-amp forcing.
- Updated `modules/ems_core/net_zero/engine.py` to carry EV `force_on` and `voltage_v` in the selected EV runtime config.
- Removed runtime dependence on `force_current_a` for EV mode decisions in phase-5 paths.
- Preserved safety precedence by keeping low-PV battery-discharge protection able to force EV `hard_off` even when `force_on == true`.
- Updated EV current/power conversions in engine projection paths to use configured `voltage_v` rather than implicit 230 V fallback semantics where selected EV config is available.
- Added/updated unit coverage for:
  - EV `force_on` behavior in manual/manual-safe/net-zero/cheap-charge/max-export projection logic
  - `MAX_EXPORT + force_on` engine behavior
  - low-PV safety blocking EV even when `force_on` is enabled

## Verification

- `pytest -q tests/unit/test_load_projection.py`
- `pytest -q tests/unit/test_engine.py`
- `pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py`
- `pytest -q tests/contract/test_grouped_config_runtime_parity.py tests/contract/test_runtime_entity_registry_contract.py`

### Phase 6

- Updated `ems_actuator_writers.py` EV handling to remove dependence on:
  - `adapter.current_min_a`
  - `adapter.current_max_a`
  - `adapter.force_current_a`
- Writer now resolves EV command current from:
  - device-policy `target_w`
  - `min_absorb_w`
  - `max_absorb_w`
  - `current_step_a`
  - `phases`
  - `voltage_v`
- Replaced legacy selector-current targeting with watt-to-current conversion via central EV power helpers.
- Selected the explicit phase-6 writer semantic for non-positive EV targets:
  - `target_w <= 0` disables the charger switch
  - current selector is restored to derived minimum current instead of using legacy configured amp floors
- Preserved safety precedence:
  - capability-blocked EV absorb requests become `hard_off`
  - hard-off also restores the selector to the derived minimum current
- Updated writer unit coverage to encode:
  - voltage-aware target conversion
  - derived-min restore on zero target
  - derived-min restore on hard-off
  - multi-EV runtime registry targeting without legacy min/max amp adapter fields

## Verification

- `pytest -q tests/unit/test_writer_semantics.py`
- `python3 -m py_compile ems_actuator_writers.py`

### Phase 7

- Expanded test coverage around the selected watt-based EV contract:
  - EV conversion and current-bound helper tests remain green under voltage-aware conversion.
  - Writer unit tests now assert watt-target-driven selector commands instead of legacy amp-policy behavior.
  - Writer zero-target semantics are now encoded as:
    - disable charger switch
    - restore selector to derived minimum current
  - Hard-off semantics are now encoded as:
    - disable charger switch
    - restore selector to derived minimum current
- Updated grouped-config parity/smoke paths so writer tests accept runtime EV watt capability fields provided as grouped-config entity references.
- Updated multi-EV writer tests to use runtime `min_absorb_w` / `max_absorb_w` + `current_step_a` / `phases` / `voltage_v` instead of legacy adapter min/max current fields.
- Preserved the project-selected quantization behavior in tests:
  - selector current is chosen from the charger-supported current resolution implied by `current_step_a`
  - current is clamped to the representable range derived from `min_absorb_w` / `max_absorb_w`
- Updated grouped-config-backed e2e scenario fixtures under `tests/e2e_entity/`:
  - EV device `policy.force_on` is now present in the grouped-config scenario YAMLs
  - single-EV scenario expectations now reflect derived minimum selector current (`8 A` in the default 230 V / 1-phase / 4 A-step setup)
  - release/hard-off writer expectations now reflect `target_zero_disable` plus derived-min selector restore where applicable
  - one EV-primary ramp e2e expectation was updated to match the selected quantized selector current (`23 A`)

## Verification

- `pytest -q tests/unit/test_ev_power.py tests/unit/test_surplus_device_targets.py tests/unit/test_load_projection.py tests/unit/test_engine.py tests/unit/test_config_loader.py tests/unit/test_core_config.py tests/unit/test_device_read_model.py tests/unit/test_writer_semantics.py tests/contract/test_grouped_config_contract.py tests/contract/test_runtime_entity_registry_contract.py tests/contract/test_grouped_config_runtime_parity.py tests/smoke/test_release_example_config_loads.py`
- `python3 -m py_compile ems_actuator_writers.py`
- `pytest -q tests/e2e_entity/`
