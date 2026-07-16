# EMS E2E entity conventions

## Purpose

E2E scenarios execute the same canonical policy -> dispatch applier -> writer path
as production. Scenario YAML is a human-readable fixture definition; the harness
materializes strict runtime schema version 5 packets for:

```text
policy_config
measurements
policy_state
```

The policy loop then consumes them through the production runtime context.

## Scenario and harness rules

1. Build the harness from the scenario's own `EMS_config.yaml` unless the test is
   explicitly a root-config contract test.
2. Resolve global entities from `h.ent`.
3. Resolve device entities with `h.device_entity(device_id, field)`.
4. Do not import hard-coded entity registries into the E2E execution path.
5. One harness step calls `ems_policy_engine_loop(trigger_reason='e2e')` and then
   continues through the same dispatch-applier and writer chain as production.
6. `policy_diagnostics.runtime_input_contract` must be `direct_tick_frame_v5`.
7. E2E runs publish diagnostics on every step even when timer production would
   throttle an unchanged diagnostics payload.

## Preferred assertions

Policy diagnostics / canonical outputs:

- `device_policies`
- `surplus_dispatch_action`
- `surplus_dispatch_device_id`
- `surplus_dispatch_contract == 'device_id_primary'`
- `producer_request_source == 'grid_feedback'` in active NET_ZERO producer cases
- `producer_allocated_w_by_id`
- `producer_effective_hard_ceiling_w_by_id`
- `unserved_production_w`

Dispatch state applier trace:

- source entity and command version are current
- active surplus IDs match the canonical command
- invalid command paths fail closed

Writer trace:

- battery actions from `batteries[device_id]`
- EV/relay actions from `devices[device_id]`
- `policy_target_w` matches canonical `DevicePolicy`
- invalid entity registry mappings fail closed

## Directional scenarios

E2E coverage should include:

1. measured grid feedback changes producer request in the correct direction
2. EV `FORCE_ON` does not get added as a second producer feed-forward term
3. producer hard ceiling limits allocation and exposes unserved demand
4. `BATTERY_PROTECT` forces producer ceiling to zero
5. lower-priority producer opens only after higher-priority hard ceiling
6. ramp transient alone does not open a lower-priority producer
7. 0-primary topology remains valid
8. multiple devices receive independent final `DevicePolicy` values
9. RPNZ and RPC use the same second-based `control_horizon_s`
10. whole-minute boundaries do not create RPC step changes
11. primary fallback skip/effective/unserved diagnostics match the selected device
12. n−1 surplus release uses persisted activation order, margin-adjusted device power and one release per settle freeze
13. the remaining anchor device keeps the RPNZ deadband release rule
