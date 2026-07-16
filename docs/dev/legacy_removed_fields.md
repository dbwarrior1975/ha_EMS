# Removed legacy/refactor remnants

This document records the active DEV cleanup policy for EMS runtime, diagnostics, templates, and scenario terminology.

## Canonical contract

The current production contract is strict runtime v5:

- `direct_tick_frame_v5`
- `schema_version: 5`
- device configuration under `devices[device_id]`
- device-owned `capabilities`, `policy`, `adapter`, and optional `guard`
- ordered `primary_consuming_device_ids`
- canonical outputs: `device_policies`, `dispatch_command`, `policy_state`, `policy_diagnostics`, `actuator_writer_trace`

## Removed or renamed from active code/diagnostics

- `HaeoNetZeroPlan.primary_load` was removed. HAEO NET_ZERO plans use `primary_consuming_device_id` only.
- Public policy diagnostics no longer publish `primary_consuming_device_id` as an alias. Use `effective_primary_consuming_device_id` for the selected runtime primary.
- Writer trace no longer uses `policy_source`; the canonical trace key is `device_policy_contract`.
- Internal EV policy staging was renamed from `ev_policies_by_id` to `ev_policy_specs_by_id`.
- Active EV writer/engine mode variables use `ev_device_mode` terminology instead of `ev_policy_mode`.

## Canonical Home Assistant helper names

- `input_select.ems_primary_consuming_device` is the canonical selector helper for the first configured primary consuming device.
- `input_number.ems_home_battery_surplus_priority` is the canonical helper for the home-battery surplus priority when the battery is configured as a surplus-capable device.

The older helper names `input_select.ems_adjustable_primary_load` and `input_number.ems_adjustable_surplus_load_priority` are not used by active templates or scenario configs after this cleanup.

## Still intentionally rejected by schema/tests

The following terms may exist only in removed-field rejection tests, migration notes, or audit tooling:

- `adjustable_surplus_load`
- `adjustable_surplus_activation_w`
- `activation_threshold_w`
- runtime-injected `required_power_w`
- runtime-injected `rpnz_w`
- runtime-injected `pv_power_kw`
- singular config `primary_consuming_device_id`
- removed writer fields such as `policy_source` and `ev_policy_mode`

These are not runtime inputs in the current contract. Derived values are computed internally from raw measurements.
