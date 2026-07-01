# Codex task: Derive RPNZ and required power inside EMS from raw runtime inputs

## Context

EMS currently imports five runtime sensor values from Home Assistant:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  required_power_w: sensor.required_power_consumption
  rpnz_w: sensor.ems_calculated_required_power_for_net_zero
  pv_power_w: sensor.pv_instant_power_2
```

The last two are HA template-derived values used only by EMS:

```yaml
required_power_w: sensor.required_power_consumption
rpnz_w: sensor.ems_calculated_required_power_for_net_zero
```

Clean-slate target: remove these HA-template-derived EMS inputs from the runtime contract and compute them inside EMS from raw measurements.

New runtime contract:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  pv_power_w: sensor.pv_instant_power_2
```

EMS must internally derive:

```text
rpnz_w
required_power_w
required_power_consumption_kw
remaining_quarter_s
remaining_quarter_min
```

This should preserve current business behavior while moving NET_ZERO math into testable EMS Python code.

---

## Non-goals

Do not change EV, relay, battery, surplus dispatch, hardoff, force-on, or writer business semantics unless required to preserve the existing behavior under the new input model.

Do not reintroduce old policy trace / decision trace command bus behavior.

Do not keep `required_power_w` or `rpnz_w` as accepted runtime config fields for compatibility. EMS is still in dev use; this is a breaking clean-slate change.

---

## High-level design

Before:

```text
Home Assistant templates
  -> sensor.required_power_consumption
  -> sensor.ems_calculated_required_power_for_net_zero
  -> EMS runtime input
  -> policy engine
```

After:

```text
Raw HA measurements
  -> grid_power_w
  -> quarter_energy_balance_kwh
  -> pv_power_w
  -> EMS internal derived NET_ZERO inputs
  -> policy engine
```

Keep the existing core engine interface stable in the first pass if practical:

```python
NetZeroState(
    rpnz_w=...,                    # now internally derived
    required_power_consumption_kw=..., # now internally derived from required_power_w / 1000
)
```

This keeps the refactor focused on input derivation and avoids mixing in unrelated business changes.

---

## Phase 1: Config contract cleanup

Update config validation so that `ems.runtime` allows and requires only:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  pv_power_w: sensor.pv_instant_power_2
```

Remove these from the active runtime config contract:

```yaml
runtime:
  required_power_w: ...
  rpnz_w: ...
```

Add explicit legacy rejection messages instead of generic unknown-field errors:

```text
runtime.required_power_w is no longer accepted; required power is derived inside EMS from grid_power_w, quarter_energy_balance_kwh, and remaining quarter time.

runtime.rpnz_w is no longer accepted; RPNZ is derived inside EMS from quarter_energy_balance_kwh and remaining quarter time.
```

Update all active configs:

```text
EMS_config.yaml
example_EMS_config.yaml
tests/e2e_entity/**/EMS_config.yaml
docs/user/config_examples.md
```

Acceptance criteria:

```bash
pytest -q tests/unit/test_config_loader.py tests/contract/test_grouped_config_contract.py tests/smoke/test_release_example_config_loads.py
```

Required tests:

- New runtime config with only `grid_power_w`, `quarter_energy_balance_kwh`, and `pv_power_w` validates as production-ready.
- `runtime.required_power_w` is rejected with a clear message.
- `runtime.rpnz_w` is rejected with a clear message.
- Old five-sensor runtime config is not production-ready.

---

## Phase 2: Domain models

Update `CoreRuntimeConfig` from the old five-input model to the new raw-input-only model.

Target shape:

```python
@dataclass
class CoreRuntimeConfig:
    grid_power_w: EntityRef
    quarter_energy_balance_kwh: EntityRef
    pv_power_w: EntityRef
```

Remove runtime config fields for:

```text
required_power_w
rpnz_w
```

Add a small internal derived model, for example:

```python
@dataclass(frozen=True)
class NetZeroDerivedInputs:
    remaining_quarter_s: float
    remaining_quarter_min: float
    rpnz_w: int
    required_power_w: int
    required_power_consumption_kw: float
```

Keep `NetZeroState` unchanged in the first pass if feasible:

```python
@dataclass
class NetZeroState:
    rpnz_w: float
    required_power_consumption_kw: float
```

This allows the existing policy computation to keep its current signature while changing only the source of the values.

---

## Phase 3: Add internal NET_ZERO derived input module

Add a focused module, for example:

```text
modules/ems_core/net_zero/derived_inputs.py
```

The module should contain pure functions, with deterministic tests:

```python
def seconds_until_next_quarter(now_ts: float | datetime) -> float:
    ...


def compute_rpnz_w(
    *,
    quarter_energy_balance_kwh: float,
    remaining_s: float,
) -> int:
    ...


def compute_required_power_w(
    *,
    quarter_energy_balance_kwh: float,
    grid_power_w: float,
    remaining_s: float,
    export_balance_stop_kwh: float = 0.130,
) -> int:
    ...


def derive_net_zero_inputs(
    *,
    quarter_energy_balance_kwh: float,
    grid_power_w: float,
    now_ts: float | datetime,
) -> NetZeroDerivedInputs:
    ...
```

### RPNZ semantics to preserve

Current HA template intent:

```jinja
{# RPNZ: the constant grid power that, if maintained from now until quarter end,
   brings hourly_energy_balance to zero.
   Positive = must import/charge.
   Negative = must export/discharge.
   Formula: -(balance_kWh × 3600 / remaining_s) × 1000
   Remaining clamped to 30 s minimum to prevent singularity at quarter boundary.
   At quarter start (balance=0): RPNZ=0. #}
```

Python equivalent target:

```python
remaining_s = max(seconds_until_next_quarter(now_ts), 30)
rpnz_w = round(-(quarter_energy_balance_kwh * 3600 / remaining_s) * 1000)
```

### Required power semantics to preserve

Current HA template intent:

```jinja
{% set transferred_energy_kWh = hourly_energy_balance | float %}
{% if transferred_energy_kWh >= 0.130 %}
  0
{% else %}
  {% set power_kW = average_active_power_2 | float / 1000 %}
  {% set remaining_minutes = (15 - now().minute % 15) %}
  {% set estimated_hourly_energy_production_kWh = power_kW * remaining_minutes / 60 %}
  {% set required_consumption_kWh = transferred_energy_kWh + estimated_hourly_energy_production_kWh %}
  {% set required_consumption_kW = required_consumption_kWh * 60 / remaining_minutes %}
  {{ required_consumption_kW * -1.0 }}
{% endif %}
```

Port this behavior carefully, but normalize EMS internal units to watts:

```text
required_power_w = round(required_consumption_kw * 1000)
required_power_consumption_kw = required_power_w / 1000.0
```

Important: the existing HA template uses `remaining_minutes = (15 - now().minute % 15)`, which ignores seconds. The RPNZ template uses seconds and clamps to 30 s. Decide deliberately whether to preserve this exact distinction or normalize both to `remaining_s / 60`. Prefer preserving observable behavior unless tests prove the normalized version is acceptable.

---

## Phase 4: Runtime registry cleanup

Update `modules/ems_adapter/runtime_context.py` and related registry tests.

Expose only raw runtime measurement keys:

```text
ENT['grid_power_w']
ENT['quarter_energy_balance_kwh']
ENT['pv_power_w']
```

Remove these registry keys if they exist:

```text
ENT['required_power_consumption_kw']
ENT['required_power_w']
ENT['rpnz_w']
```

Avoid ambiguous aliases such as `pv_power_kw` in the registry. Prefer:

```text
config/runtime: pv_power_w
policy engine local variable: pv_power_kw = pv_power_w / 1000.0
```

Acceptance criteria:

```bash
pytest -q tests/contract/test_runtime_entity_registry_contract.py tests/contract/test_grouped_config_contract.py
```

Required tests:

- Registry exposes `grid_power_w`, `quarter_energy_balance_kwh`, and `pv_power_w`.
- Registry does not expose `required_power_w`, `required_power_consumption_kw`, or `rpnz_w`.

---

## Phase 5: Policy engine input derivation

Update `ems_policy_engine.py` so that `NetZeroState` is built from internally derived values, not HA-template sensors.

Before, conceptually:

```python
nz = NetZeroState(
    rpnz_w=get_float(entities['rpnz_w'], fallback),
    required_power_consumption_kw=get_float(entities['required_power_consumption_kw'], 0),
)
```

After:

```python
derived = derive_net_zero_inputs(
    quarter_energy_balance_kwh=m.quarter_energy_balance_kwh,
    grid_power_w=m.grid_power_w,
    now_ts=now_ts,
)

nz = NetZeroState(
    rpnz_w=derived.rpnz_w,
    required_power_consumption_kw=derived.required_power_consumption_kw,
)
```

PV handling:

```python
pv_power_w = get_float(entities['pv_power_w'], None)
pv_power_kw = None if pv_power_w is None else pv_power_w / 1000.0
```

Then pass `pv_power_kw` into the existing policy computation as before.

Do not fallback to old HA-template sensors.

---

## Phase 6: Trigger model

Remove direct state triggers for the derived HA-template sensors:

```text
sensor.required_power_consumption
sensor.ems_calculated_required_power_for_net_zero
```

New policy engine triggers should include the raw runtime measurements:

```text
sensor.average_active_power_2
sensor.hourly_energy_balance
sensor.pv_instant_power_2
```

Keep profile triggers:

```text
input_select.ems_control_profile
input_select.ems_goal_profile
input_select.ems_guard_profile
input_select.ems_forecast_profile
```

Keep a periodic trigger, because derived values depend on time even if raw sensors do not change:

```python
@time_trigger('period(now, 30s)')
```

Target conceptual decorator:

```python
@time_trigger('period(now, 30s)')
@state_trigger(
    'input_select.ems_control_profile '
    'or input_select.ems_goal_profile '
    'or input_select.ems_guard_profile '
    'or input_select.ems_forecast_profile '
    'or sensor.average_active_power_2 '
    'or sensor.hourly_energy_balance '
    'or sensor.pv_instant_power_2'
)
def ems_policy_engine_loop():
    ...
```

Note: Pyscript `@state_trigger` entity IDs are effectively static at import time. In this cleanup, treat these raw runtime entities as stable production contract names. Do not claim runtime entity IDs are freely configurable for immediate trigger latency unless the trigger model is redesigned.

Required trigger tests / source checks:

- `ems_policy_engine.py` trigger contains `sensor.average_active_power_2`.
- `ems_policy_engine.py` trigger contains `sensor.hourly_energy_balance`.
- `ems_policy_engine.py` trigger contains `sensor.pv_instant_power_2`.
- `ems_policy_engine.py` trigger does not contain `sensor.required_power_consumption`.
- `ems_policy_engine.py` trigger does not contain `sensor.ems_calculated_required_power_for_net_zero`.

---

## Phase 7: Diagnostics

Update `sensor.ems_policy_diagnostics_pyscript` so production debugging shows both raw and derived values.

Add or preserve attributes like:

```yaml
runtime_input_contract: raw_measurements_only
net_zero_derived_source: internal

grid_power_w: -1200
quarter_energy_balance_kwh: -0.004
pv_power_w: 2500
pv_power_kw: 2.5

remaining_quarter_s: 742
remaining_quarter_min: 12.37

rpnz_w: 19
required_power_w: 820
required_power_consumption_kw: 0.82
```

This is important for dashboard and production troubleshooting. A user should be able to answer from policy diagnostics alone:

```text
What raw inputs did EMS see?
What derived RPNZ / required power did EMS compute?
How much quarter time was left?
Why did EV not trigger?
```

Do not make policy diagnostics a runtime command/state source.

---

## Phase 8: Test updates

### Config tests

Add/update tests for:

- New runtime config with only three raw inputs validates.
- Old `required_power_w` runtime field is rejected.
- Old `rpnz_w` runtime field is rejected.
- Old five-input runtime config is not production-ready.

### Derived calculation tests

Add unit tests for the new pure calculation module:

- `balance = 0` at quarter start -> `rpnz_w = 0`.
- Negative balance with `remaining_s = 900` -> positive `rpnz_w`.
- Positive balance with `remaining_s = 900` -> negative `rpnz_w`.
- `remaining_s` clamps to at least 30 s.
- `quarter_energy_balance_kwh >= 0.130` -> `required_power_w = 0`.
- Golden cases matching the current HA template behavior.
- Grid power sign convention is preserved.

### Policy engine tests

Update tests that currently seed:

```text
ENT['rpnz_w']
ENT['required_power_consumption_kw']
```

to seed:

```text
ENT['grid_power_w']
ENT['quarter_energy_balance_kwh']
```

Add helper functions if needed:

```python
def balance_for_rpnz_w(rpnz_w: float, remaining_s: float) -> float:
    return -(rpnz_w / 1000.0) * remaining_s / 3600.0
```

Use fixed `now_ts` values in tests so time-dependent derived values are deterministic.

### Runtime registry tests

- New raw inputs are present.
- Old derived inputs are absent.

### E2E tests

Update all `tests/e2e_entity/**/EMS_config.yaml` files to the new three-input runtime contract.

Where scenarios depend on specific RPNZ behavior, adjust fixture values using `quarter_energy_balance_kwh` and fixed/controlled time where available.

---

## Phase 9: Docs and dashboard cleanup

Update active user/dev docs:

```text
docs/user/EMS_parametrointi_guide.md
docs/user/operointi.md
docs/user/config_examples.md
docs/user/releasenotes.md
docs/dev/arkkitehtuuri.md
```

Document the new runtime contract:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  pv_power_w: sensor.pv_instant_power_2
```

Document that EMS internally derives:

```text
rpnz_w
required_power_w
required_power_consumption_kw
remaining_quarter_s
```

Add release note / migration note:

```text
Breaking change: runtime.required_power_w and runtime.rpnz_w were removed. EMS now derives required power and RPNZ internally from grid_power_w, quarter_energy_balance_kwh, and current quarter time. Remove sensor.required_power_consumption and sensor.ems_calculated_required_power_for_net_zero from EMS runtime config and HA dashboards unless kept for external comparison.
```

Dashboard guidance:

- Do not read `sensor.required_power_consumption` for EMS diagnostics.
- Do not read `sensor.ems_calculated_required_power_for_net_zero` for EMS diagnostics.
- Read derived values from `sensor.ems_policy_diagnostics_pyscript` attributes instead.

---

## Final acceptance criteria

Full test suite:

```bash
pytest -q
```

Grep acceptance:

```bash
rg "sensor.required_power_consumption|sensor.ems_calculated_required_power_for_net_zero" ems_*.py modules tests docs/user docs/dev
```

Allowed final hits:

```text
release note / migration note
legacy rejection tests
```

Not allowed:

```text
state_trigger
active EMS_config.yaml
example_EMS_config.yaml
tests/e2e_entity/**/EMS_config.yaml
runtime_context.py accepted runtime mapping
config_loader.py accepted runtime field
policy engine runtime read path
```

Additional greps:

```bash
rg "required_power_w|rpnz_w" EMS_config.yaml example_EMS_config.yaml tests/e2e_entity
```

No active runtime-config hits should remain.

```bash
rg "required_power_consumption_kw|rpnz_w" modules/ems_adapter ems_policy_engine.py tests
```

Allowed only where these are internal derived values, diagnostics attributes, `NetZeroState` fields, or tests for internal derived computation. They must not be runtime config fields or HA sensor reads.

---

## Production validation checklist

After deployment, verify in Home Assistant:

```yaml
sensor.ems_policy_diagnostics_pyscript:
  runtime_input_contract: raw_measurements_only
  net_zero_derived_source: internal
  grid_power_w: <raw grid>
  quarter_energy_balance_kwh: <raw balance>
  pv_power_w: <raw pv>
  remaining_quarter_s: <computed>
  rpnz_w: <computed>
  required_power_w: <computed>
  required_power_consumption_kw: <computed>
```

Trigger validation:

```text
Change sensor.average_active_power_2
  -> policy diagnostics updates and derived required power can change.

Change sensor.hourly_energy_balance
  -> policy diagnostics updates and RPNZ / required power can change.

Change sensor.pv_instant_power_2
  -> EV hardoff / release-ready diagnostics update.

No sensor changes
  -> remaining_quarter_s and derived values update at latest on the 30 s periodic policy loop.
```

Canonical output validation must remain true:

```yaml
sensor.ems_device_policies_pyscript:
  device_policies_state_kind: content_hash

sensor.ems_surplus_dispatch_command_pyscript:
  dispatch_command_state_kind: content_hash

sensor.ems_policy_state_pyscript:
  policy_state_state_kind: content_hash
```

Writer/dispatch source validation:

```yaml
sensor.ems_actuator_writer_trace:
  policy_source_reason: canonical

sensor.ems_dispatch_state_applier_trace:
  dispatch_source_reason: canonical
```

---

## Suggested implementation order

1. Config contract: runtime only `grid_power_w`, `quarter_energy_balance_kwh`, `pv_power_w`.
2. Domain model: remove `required_power_w` and `rpnz_w` from `CoreRuntimeConfig`.
3. Runtime registry: expose only raw input entities.
4. Add `derived_inputs.py` with pure tests and golden cases from current HA templates.
5. Policy engine: build `NetZeroState` from internal derived values.
6. Trigger model: replace derived HA sensor triggers with raw input triggers; keep periodic trigger.
7. Diagnostics: expose raw + derived values in `policy_diagnostics`.
8. Update e2e configs and tests.
9. Update docs and release note.
10. Run full pytest and grep acceptance.
