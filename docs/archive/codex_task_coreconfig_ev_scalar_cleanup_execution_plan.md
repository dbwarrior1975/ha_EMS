# CoreConfig EV Scalar Cleanup: Execution Plan for Next Session

## Purpose

This document refines `codex_task_remove_coreconfig_ev_scalar_mirrors.md` into a safer implementation plan.

The cleanup is worth doing, but it should not be executed as one broad search-and-delete pass. The key risk is mixing three different concepts:

1. Top-level EV scalar mirrors on `CoreConfig`.
2. External Home Assistant entity names such as `input_number.ems_ev_current_step_a`.
3. The `CoreConfig.ev_charger` convenience pointer to the first/default EV device.

Only item 1 should be removed in the main cleanup. Item 2 is valid external IO compatibility. Item 3 is not a scalar mirror; treat it separately.

## Current Findings

Top-level EV scalar mirrors are currently defined in:

```text
modules/ems_core/domain/models.py
```

Fields to remove from `CoreConfig`:

```text
ev_charger_phases
ev_voltage_v
ev_force_on
ev_hard_off_pv_threshold_kw
ev_hard_off_low_pv_cycles
ev_hard_off_release_cycles
ev_current_step_a
ev_priority
```

They are populated twice:

```text
modules/ems_core/domain/models.py: CoreConfig.__post_init__()
modules/ems_adapter/config_loader.py: _populate_core_config_derived_fields()
```

`ev_power_step_w(cfg)` still has a scalar fallback:

```text
modules/ems_core/domain/ev_power.py
```

It first accepts `ev_power_step_w`/`step_w`, but then falls back to:

```text
cfg.ev_current_step_a
cfg.ev_charger_phases
cfg.ev_voltage_v
```

The engine is mostly device-native already. One notable fallback remains:

```text
modules/ems_core/net_zero/engine.py
```

Inside `_selected_ev_context()`, string-valued `policy.force_on` falls back to:

```text
getattr(cfg, 'ev_force_on', False)
```

This must be removed or replaced before deleting `CoreConfig.ev_force_on`.

The stale naming cleanups are straightforward:

```text
modules/ems_adapter/config_loader.py: _validate_ev_numeric_current_compatibility
modules/ems_core/net_zero/engine.py: implicit_legacy_default
README.md: implicit_legacy_default
```

## Recommended Scope

Do this in three commits or at least three testable phases.

1. Mechanical naming cleanup.
2. EV power helper and test-helper cleanup.
3. `CoreConfig` scalar field removal.

Do not start by removing dataclass fields. That will create noisy failures in tests and helpers before the real business-logic dependencies are visible.

## Phase 1: Mechanical Naming Cleanup

Rename:

```text
_validate_ev_numeric_current_compatibility
```

to:

```text
_validate_ev_watt_limits_match_adapter_resolution
```

or:

```text
_validate_ev_watt_limits_supported_by_adapter
```

Keep behavior unchanged.

Rename trace reason:

```text
implicit_legacy_default
```

to:

```text
implicit_primary_equals_surplus
```

Update assertions and active docs. Archived docs can keep old text.

Verification:

```bash
pytest -q tests/unit/test_config_loader.py tests/unit/test_engine.py
rg -n "_validate_ev_numeric_current_compatibility|implicit_legacy_default" modules tests README.md docs/dev docs/user
```

Expected: no active references.

## Phase 2: Clean EV Power Step API

The cleanest local change is to make `ev_power_step_w()` no longer require top-level EV scalar fields.

Preferred implementation:

```python
def ev_power_step_w(obj):
    configured_step_w = _cfg_capability_power_w(obj, 'ev_power_step_w', 'power_step_w', 'step_w')
    if configured_step_w is not None:
        return configured_step_w

    adapter = getattr(obj, 'adapter', None)
    if adapter is not None:
        return ev_current_a_to_power_w(
            getattr(adapter, 'current_step_a', 1) or 1,
            getattr(adapter, 'phases', 1) or 1,
            getattr(adapter, 'voltage_v', DEFAULT_EV_VOLTAGE_V) or DEFAULT_EV_VOLTAGE_V,
        )

    raise AttributeError('ev_power_step_w requires step_w/power_step_w or an EV adapter')
```

Alternative: remove `ev_power_step_w()` entirely and use `ev_current_a_to_power_w(current_step_a, phases, voltage_v)` at call sites. This is also clean, but causes more test churn.

Update `tests/helpers.py` so it does not set:

```text
cfg.ev_charger_phases
cfg.ev_current_step_a
cfg.ev_voltage_v
cfg.ev_force_on
```

The helper already builds `CoreEvChargerDeviceConfig`. Derived test helpers should read from:

```text
cfg.device_by_id('EV_CHARGER').adapter
cfg.device_by_id('EV_CHARGER').capabilities
cfg.device_by_id('EV_CHARGER').policy
```

Keep convenience keyword arguments like `ev_current_step_a` in `make_cfg()` if tests use them. Those are test input shorthand, not `CoreConfig` fields.

Verification:

```bash
pytest -q tests/unit/test_ev_power.py tests/unit/test_load_projection.py tests/unit/test_haeo_net_zero_plan.py tests/unit/test_engine.py
rg -n "cfg\\.ev_charger_phases|cfg\\.ev_current_step_a|cfg\\.ev_voltage_v|cfg\\.ev_force_on" tests modules
```

Expected: no production reads; remaining test shorthand only if local to `make_cfg()` input data and not assigned onto `CoreConfig`.

## Phase 3: Remove CoreConfig EV Scalar Mirrors

Remove these dataclass fields from `CoreConfig`:

```text
ev_charger_phases
ev_voltage_v
ev_force_on
ev_hard_off_pv_threshold_kw
ev_hard_off_low_pv_cycles
ev_hard_off_release_cycles
ev_current_step_a
ev_priority
```

Remove their population from:

```text
CoreConfig.__post_init__()
_populate_core_config_derived_fields()
```

Before removing `ev_force_on`, fix `_selected_ev_context()`:

Current problematic fallback:

```python
force_on = bool(getattr(cfg, 'ev_force_on', False))
```

Recommended replacement:

```python
force_on = False
```

Reason: by the time engine runs, grouped config values should be resolved. A raw entity-id string must not become true, and falling back to a top-level mirror defeats the cleanup.

Keep these fields for now:

```text
ev_charger
home_battery
deadband_w
ramp_max_w
strict_limits_max_w
...
```

`ev_charger` is a device pointer, not a scalar mirror. It can be renamed later to something like `default_ev_charger` or removed after auditing all call sites, but including it in the scalar cleanup increases risk without improving watt-policy correctness.

Verification:

```bash
pytest -q tests/unit/test_core_config.py tests/unit/test_config_loader.py tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py tests/unit/test_ev_power.py tests/unit/test_writer_semantics.py
pytest -q tests/contract/test_grouped_config_contract.py tests/contract/test_grouped_config_runtime_parity.py tests/contract/test_runtime_entity_registry_contract.py
```

Then run:

```bash
rg -n "ev_charger_phases|ev_voltage_v|ev_force_on|ev_hard_off_pv_threshold_kw|ev_hard_off_low_pv_cycles|ev_hard_off_release_cycles|ev_current_step_a|ev_priority" modules tests README.md docs/dev docs/user example_EMS_config.yaml
```

Classify remaining references:

```text
Allowed: YAML/entity keys in examples, e2e configs, runtime alias mapping, HA IO docs.
Allowed: engine trace attrs such as ev_force_on and ev_current_step_a if sourced from selected_ev context.
Allowed: test input shorthand inside make_cfg() and e2e fixtures.
Not allowed: CoreConfig field definitions or reads from cfg.<field>.
Not allowed: population from cfg.ev_charger into cfg.ev_*.
```

## External IO Compatibility Boundary

Do not rename Home Assistant entity IDs as part of this cleanup:

```text
input_number.ems_ev_charger_phases
input_number.ems_ev_voltage_v
input_boolean.ems_ev_force_on
input_number.ems_ev_hard_off_pv_threshold_kw
input_number.ems_ev_hard_off_low_pv_cycles
input_number.ems_ev_hard_off_release_cycles
input_number.ems_ev_current_step_a
input_number.ems_surplus_ev_priority
```

These names are external IO compatibility. They are acceptable when mapped into:

```text
devices[EV_CHARGER].adapter
devices[EV_CHARGER].policy
devices[EV_CHARGER].capabilities
```

They are not acceptable as top-level `CoreConfig` business fields.

## Tests to Add or Adjust

Add a focused unit test in `tests/unit/test_core_config.py`:

```python
def test_core_config_does_not_expose_ev_scalar_mirrors(...):
    cfg = build_core_config_from_grouped_reader(...)
    assert not hasattr(cfg, 'ev_charger_phases')
    assert not hasattr(cfg, 'ev_voltage_v')
    assert not hasattr(cfg, 'ev_force_on')
    assert not hasattr(cfg, 'ev_current_step_a')
    assert not hasattr(cfg, 'ev_priority')
```

Add or adjust an engine test to prove selected EV context reads the selected EV device directly:

```text
two EV devices with different phases/current_step/force_on
selected adjustable EV is not the first EV
trace target/step/force values match the selected EV
```

For `ev_power_step_w`, update tests to use either:

```text
object with step_w/power_step_w
EV device or object with adapter
explicit ev_current_a_to_power_w()
```

Do not preserve tests that require `cfg.ev_charger_phases`.

## Documentation Cleanup Guidance

Active docs may still mention `ev_force_on` and HA entity names. That is fine when explaining user parameters.

Rewrite active docs only where they describe current internals as:

```text
legacy
compat
scalar
migration
refactor
```

Use current terms instead:

```text
grouped config
device registry
device-native runtime state
device_policies
target_w
policy_decision_trace
actuator_writer_trace
external Home Assistant IO compatibility
```

Do not spend time rewriting archived progress notes.

## Final Acceptance Search

Run:

```bash
rg -n "_cfg_with_selected_ev_scalars|implicit_legacy_default|_validate_ev_numeric_current_compatibility|policy_ev_current_a|policy_relay1_command|policy_relay2_command|policy_battery_target_w|current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" modules tests README.md docs/dev docs/user
```

Expected: no active references.

Run:

```bash
rg -n "cfg\\.ev_charger_phases|cfg\\.ev_voltage_v|cfg\\.ev_force_on|cfg\\.ev_hard_off_pv_threshold_kw|cfg\\.ev_hard_off_low_pv_cycles|cfg\\.ev_hard_off_release_cycles|cfg\\.ev_current_step_a|cfg\\.ev_priority" modules tests
```

Expected: no references.

Run full suite:

```bash
pytest -q
```

## Practical Recommendation

Start with the mechanical renames and `ev_power_step_w()` cleanup. After those pass, remove the `CoreConfig` fields. If the full field removal becomes noisy, stop after proving there are no production `cfg.ev_*` reads and leave a smaller follow-up for test-helper cleanup. Do not compromise by keeping `CoreConfig.__post_init__()` scalar population; that is the core architectural smell this task is meant to remove.
