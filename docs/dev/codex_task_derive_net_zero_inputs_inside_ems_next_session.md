# Codex task: derive NET_ZERO inputs inside EMS - reviewed next-session plan

## Purpose

This document supersedes `docs/dev/codex_task_derive_net_zero_inputs_inside_ems.md` for the next implementation session.

Goal: remove Home Assistant template-derived NET_ZERO runtime inputs from the EMS runtime contract and derive them inside EMS from raw runtime measurements.

Old runtime contract:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  required_power_w: sensor.required_power_consumption
  rpnz_w: sensor.ems_calculated_required_power_for_net_zero
  pv_power_w: sensor.pv_instant_power_2
```

New runtime contract:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  pv_power_w: sensor.pv_instant_power_2
```

EMS must internally derive:

```text
remaining_quarter_s
remaining_quarter_min
rpnz_w
required_power_w
required_power_consumption_kw
pv_power_kw
```

`rpnz_w` and `required_power_consumption_kw` may remain `NetZeroState` fields. They must not remain accepted runtime config fields, runtime aliases, runtime registry keys, or HA sensor reads.

The review notes in `docs/dev/codex_review_notes_derive_net_zero_inputs_phase_plan.md` are accepted as implementation guardrails. All required clarifications are relevant and should be applied before coding starts.

## Review of the previous plan

The previous plan is directionally correct, but make these corrections during implementation:

1. Treat `pv_power_w` as a first-class raw runtime input. Current code exposes `pv_power_kw` through `runtime_alias_index()` but does not add `ent['pv_power_w']` in `build_runtime_entities_from_grouped_config()`. Fix this explicitly.
2. Add `pv_power_w` to `RuntimeMeasurements` or otherwise pass it through a single raw runtime path. Avoid reading PV through a legacy `pv_power_kw` alias in the policy engine.
3. Remove `required_power_consumption_kw`, `required_power_w`, and `rpnz_w` from runtime aliases and runtime entity registry. Re-add derived values only as local variables and diagnostics attrs.
4. Preserve the existing `NetZeroState` interface for the first pass. Do not combine this task with engine behavior changes.
5. Make time-dependent tests deterministic. Do not rely on real current time in unit, contract, or e2e tests.
6. Update trigger source checks. The current `@state_trigger` still points at `sensor.required_power_consumption` and `sensor.ems_calculated_required_power_for_net_zero`.
7. Document that raw runtime entity IDs are also static Pyscript trigger contract IDs. Changing `EMS_config.yaml` affects read-time inputs, but not low-latency trigger expressions.
8. Define safe degraded behavior for missing or invalid raw NET_ZERO inputs. The policy loop must not crash on `unknown`, `unavailable`, empty, or invalid values.
9. Keep volatile raw/derived diagnostics out of canonical command/state hashes.
10. Because the worktree may already include unrelated changes, avoid broad rewrites and do not revert files.

## Current code touchpoints

Primary files:

```text
modules/ems_core/domain/models.py
modules/ems_core/net_zero/balance.py
modules/ems_core/net_zero/derived_inputs.py      # new
modules/ems_adapter/config_loader.py
modules/ems_adapter/runtime_context.py
ems_policy_engine.py
tests/entity_ids.py
tests/helpers.py
```

Important current references to remove or migrate:

```text
CoreRuntimeConfig.required_power_w
CoreRuntimeConfig.rpnz_w
build_runtime_aliases(): required_power_consumption_kw alias
build_runtime_aliases(): rpnz_w alias
build_runtime_entities_from_grouped_config(): required_power_consumption_kw/rpnz_w/pv_power_kw alias ingestion
ems_policy_engine_loop(): state_trigger old HA template sensors
ems_policy_engine_loop(): get_float(entities['rpnz_w'], ...)
ems_policy_engine_loop(): get_float(entities['required_power_consumption_kw'], ...)
ems_policy_engine_loop(): get_float(entities['pv_power_kw'], None)
```

## Implementation order

### 1. Add pure derived input module first

Create:

```text
modules/ems_core/net_zero/derived_inputs.py
tests/unit/test_net_zero_derived_inputs.py
```

Suggested model:

```python
@dataclass(frozen=True)
class NetZeroDerivedInputs:
    remaining_quarter_s: float
    remaining_quarter_min: float
    rpnz_w: int
    required_power_w: int
    required_power_consumption_kw: float
    input_quality: str = 'ok'
    input_warnings: tuple[str, ...] = ()
```

Suggested functions:

```python
def seconds_until_next_quarter(now_ts: float | datetime) -> float:
    ...

def remaining_template_minutes(now_ts: float | datetime) -> int:
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
    remaining_min: float,
    export_balance_stop_kwh: float = 0.130,
) -> int:
    ...

def derive_net_zero_inputs(
    *,
    quarter_energy_balance_kwh: object,
    grid_power_w: object,
    now_ts: float | datetime,
) -> NetZeroDerivedInputs:
    ...
```

RPNZ formula:

```python
remaining_s = max(seconds_until_next_quarter(now_ts), 30.0)
rpnz_w = round(-(quarter_energy_balance_kwh * 3600.0 / remaining_s) * 1000.0)
```

Required power formula should preserve the current HA template behavior in the first pass:

```python
if quarter_energy_balance_kwh >= 0.130:
    required_power_w = 0
else:
    power_kw = grid_power_w / 1000.0
    remaining_min = 15 - (minute % 15)
    estimated_balance_delta_kwh = power_kw * remaining_min / 60.0
    required_consumption_kwh = quarter_energy_balance_kwh + estimated_balance_delta_kwh
    required_consumption_kw = required_consumption_kwh * 60.0 / remaining_min
    required_power_w = round(required_consumption_kw * -1000.0)
```

Note: the HA required-power template uses minutes and ignores seconds. RPNZ uses seconds. Preserve that distinction unless a separate behavior-change task is created.

Define the minute helper exactly:

```python
def remaining_template_minutes(now_ts: float | datetime) -> int:
    return 15 - (minute % 15)
```

Boundary behavior:

```text
12:00:00 -> 15
12:00:01 -> 15
12:14:59 -> 1
12:15:00 -> 15
```

Do not improve required-power calculation to second precision in this task.

Safe raw input behavior:

```text
If quarter_energy_balance_kwh is missing/invalid:
  use 0.0 for derived NET_ZERO values
  input_quality = degraded_missing_quarter_balance
  add a warning naming the missing/invalid input

If grid_power_w is missing/invalid:
  use 0.0 for required-power derivation
  input_quality = degraded_missing_grid_power
  add a warning naming the missing/invalid input

If both are missing/invalid:
  input_quality = degraded_missing_multiple_inputs

If both are valid:
  input_quality = ok
```

PV missing/unavailable is not a NET_ZERO derivation failure: keep `pv_power_w = None` and `pv_power_kw = None`, and preserve safe EV hardoff behavior.

Rounding test rule: choose required-power and RPNZ golden cases that do not land exactly on x.5 W boundaries unless the test intentionally defines the Python-vs-Jinja rounding contract.

Minimum unit tests:

```text
quarter balance 0 at quarter start -> rpnz_w 0
negative balance with 900 s remaining -> positive rpnz_w
positive balance with 900 s remaining -> negative rpnz_w
remaining_s clamps to 30 s for RPNZ
remaining_template_minutes at quarter boundary returns 15
remaining_template_minutes one second before quarter boundary returns 1
required-power formula uses remaining_template_minutes, not remaining seconds
quarter_energy_balance_kwh >= 0.130 -> required_power_w 0
required-power golden cases matching the old HA formula
grid power sign convention preserved
datetime and float timestamp inputs both work
missing/invalid quarter_energy_balance_kwh produces safe degraded output
missing/invalid grid_power_w produces safe degraded required-power output
rounding golden cases avoid unintended .5 W ambiguity
```

Run:

```bash
pytest -q tests/unit/test_net_zero_derived_inputs.py
```

### 2. Clean config contract

Update `CoreRuntimeConfig`:

```python
@dataclass
class CoreRuntimeConfig:
    grid_power_w: EntityRef
    quarter_energy_balance_kwh: EntityRef
    pv_power_w: EntityRef
```

Update `validate_grouped_ems_config()`:

```text
required runtime keys: grid_power_w, quarter_energy_balance_kwh, pv_power_w
legacy runtime keys rejected: required_power_w, rpnz_w
runtime.pv_power_kw rejected if present
unknown runtime keys rejected
```

Add explicit messages:

```text
runtime.required_power_w is no longer accepted; required power is derived inside EMS from grid_power_w, quarter_energy_balance_kwh, and current quarter time.

runtime.rpnz_w is no longer accepted; RPNZ is derived inside EMS from quarter_energy_balance_kwh and current quarter time.
```

Update `build_core_config_from_grouped_reader()` to stop requiring and populating the removed fields.

Update `build_runtime_aliases()`:

```text
remove required_power_consumption_kw alias
remove rpnz_w alias
remove pv_power_kw alias
```

`pv_power_kw` must become a policy-engine local conversion from raw `pv_power_w`, not a runtime alias.

Run:

```bash
pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py tests/contract/test_grouped_config_contract.py tests/smoke/test_release_example_config_loads.py
```

### 3. Clean runtime entity registry

Update `build_runtime_entities_from_grouped_config()`:

```python
ent['grid_power_w'] = runtime.get('grid_power_w')
ent['quarter_energy_balance'] = runtime.get('quarter_energy_balance_kwh')
ent['quarter_energy_balance_kwh'] = runtime.get('quarter_energy_balance_kwh')  # if tests expect canonical key
ent['pv_power_w'] = runtime.get('pv_power_w')
```

Remove registry exposure for:

```text
required_power_consumption_kw
required_power_w
rpnz_w
pv_power_kw
```

Keep any compatibility alias for `quarter_energy_balance` only if existing policy/tests still require it. If it remains, document it as internal/transitional only. Do not expose `quarter_energy_balance` in active config examples or user docs as a public runtime contract. The public config key is `quarter_energy_balance_kwh`.

Preferred clean final state:

```text
runtime config key: quarter_energy_balance_kwh
runtime registry key: quarter_energy_balance_kwh
internal code gradually migrates away from quarter_energy_balance alias
```

Run:

```bash
pytest -q tests/contract/test_runtime_entity_registry_contract.py tests/contract/test_grouped_config_runtime_parity.py
```

### 4. Update runtime measurements

Update `RuntimeMeasurements`:

```python
pv_power_w: Optional[float] = None
```

Update `read_measurements()`:

```python
pv_power_w=get_float(entities['pv_power_w'], None)
```

If missing PV should be treated as unavailable, keep `None`. Do not default missing PV to `0` unless existing hardoff behavior explicitly requires it.

For grid and quarter balance, prefer a raw read that can distinguish invalid values for diagnostics. If the current HA adapter fallback path always returns `0`, add policy-engine or adapter-level quality detection only if feasible without broad rewrites. At minimum, derived diagnostics must expose the fallback behavior clearly.

Update helpers:

```text
tests/helpers.py
tests/entity_ids.py
```

Remove old test entity IDs:

```text
rpnz_w
required_power_consumption_kw
required_power_w
pv_power_kw
```

Add:

```text
pv_power_w
quarter_energy_balance_kwh if useful
```

### 5. Update policy engine

In `ems_policy_engine.py`:

```python
from ems_core.net_zero.derived_inputs import derive_net_zero_inputs
```

Replace old construction:

```python
remaining_s = ...
nz = NetZeroState(
    rpnz_w=get_float(entities['rpnz_w'], compute_rpnz_w(...)),
    required_power_consumption_kw=get_float(entities['required_power_consumption_kw'], 0),
)
```

with:

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
pv_power_kw = None if m.pv_power_w is None else m.pv_power_w / 1000.0
```

Then pass:

```python
pv_power_kw=pv_power_kw
```

Do not read old HA-template sensors as fallbacks.

Additional source-level invariants:

```text
policy engine never reads entities['rpnz_w']
policy engine never reads entities['required_power_consumption_kw']
policy engine never reads entities['required_power_w']
policy engine never reads entities['pv_power_kw']
pv_power_kw is only a local conversion from m.pv_power_w
```

### 6. Update policy diagnostics

Add raw and derived attrs before publishing diagnostics:

```python
attrs.update(
    {
        'runtime_input_contract': 'raw_measurements_only',
        'net_zero_derived_source': 'internal',
        'net_zero_input_quality': derived.input_quality,
        'net_zero_input_warnings': derived.input_warnings,
        'grid_power_w': m.grid_power_w,
        'quarter_energy_balance_kwh': m.quarter_energy_balance_kwh,
        'pv_power_w': m.pv_power_w,
        'pv_power_kw': pv_power_kw,
        'remaining_quarter_s': derived.remaining_quarter_s,
        'remaining_quarter_min': derived.remaining_quarter_min,
        'rpnz_w': derived.rpnz_w,
        'required_power_w': derived.required_power_w,
        'required_power_consumption_kw': derived.required_power_consumption_kw,
    }
)
```

Do not make diagnostics a command source or runtime source.

Diagnostics may update every policy loop because they contain live raw/derived measurements. Canonical output sensors must remain content-hash scoped to command/state payloads only. Do not include volatile diagnostics-only fields such as `remaining_quarter_s`, raw measurements, or derived debug values in `device_policies`, `dispatch_command`, or `policy_state` hashes unless they actually change that payload.

### 7. Update triggers

Current trigger is stale:

```python
@state_trigger('... sensor.required_power_consumption or sensor.ems_calculated_required_power_for_net_zero')
```

Replace with raw runtime sensors:

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
```

Keep the periodic trigger because derived values depend on time even when raw sensors are unchanged.

Add source checks that fail if old sensors appear in active triggers.

The raw measurement entity IDs in `@state_trigger` are stable trigger contract IDs:

```text
Changing runtime.grid_power_w, runtime.quarter_energy_balance_kwh, or runtime.pv_power_w in EMS_config.yaml changes read-time inputs, but it does not change the static Pyscript @state_trigger expression. For low-latency production behavior, keep these entity IDs stable or update the decorator expression too.
```

Active docs must not imply that these runtime entity IDs are freely renameable without considering Pyscript trigger latency.

### 8. Update configs and tests

Remove from all active `EMS_config.yaml` files:

```yaml
required_power_w: sensor.required_power_consumption
rpnz_w: sensor.ems_calculated_required_power_for_net_zero
```

Required active files include:

```text
EMS_config.yaml
example_EMS_config.yaml
tests/e2e_entity/**/EMS_config.yaml
docs/user/config_examples.md
```

For tests that currently seed:

```python
E['rpnz_w']
E['required_power_consumption_kw']
```

replace with raw values:

```python
E['quarter_energy_balance']
E['grid_power_w']
```

Use helpers to derive raw fixture inputs from desired old expectations:

```python
def balance_for_rpnz_w(rpnz_w: float, remaining_s: float) -> float:
    return -(rpnz_w / 1000.0) * remaining_s / 3600.0
```

If a test needs a specific `required_power_consumption_kw`, prefer setting `grid_power_w` and `quarter_energy_balance_kwh` through a helper that mirrors `compute_required_power_w()`. Keep fixed timestamps so remaining time is known.

### 9. Update docs

Update active docs only, not archive docs:

```text
README.md
docs/user/EMS_parametrointi_guide.md
docs/user/operointi.md
docs/user/config_examples.md
docs/user/releasenotes.md
docs/dev/arkkitehtuuri.md
docs/dev/e2e_tests_stories.md
docs/dev/testausautomaatio.md
```

Document:

```text
runtime.required_power_w removed
runtime.rpnz_w removed
sensor.required_power_consumption no longer an EMS input
sensor.ems_calculated_required_power_for_net_zero no longer an EMS input
derived values are visible from sensor.ems_policy_diagnostics_pyscript attrs
raw runtime entity IDs are static Pyscript trigger contract IDs for low-latency updates
```

## Acceptance checks

Targeted tests during implementation:

```bash
pytest -q tests/unit/test_net_zero_derived_inputs.py
pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py
pytest -q tests/contract/test_grouped_config_contract.py tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/smoke/test_release_example_config_loads.py
```

Full check:

```bash
pytest -q
```

Grep checks:

```bash
rg "sensor.required_power_consumption|sensor.ems_calculated_required_power_for_net_zero" ems_*.py modules tests docs/user docs/dev README.md
rg "required_power_w|rpnz_w" EMS_config.yaml example_EMS_config.yaml tests/e2e_entity
rg "required_power_consumption_kw|rpnz_w|pv_power_kw" modules/ems_adapter ems_policy_engine.py tests
rg "entities\\['rpnz_w'\\]|entities\\['required_power_consumption_kw'\\]|entities\\['required_power_w'\\]|entities\\['pv_power_kw'\\]" ems_policy_engine.py tests
```

Allowed final hits:

```text
release notes and migration docs
legacy rejection tests
NetZeroState fields
internal derived input tests
policy diagnostics attrs
engine business logic using nz.rpnz_w and nz.required_power_consumption_kw
pv_power_kw local conversion from pv_power_w
pv_power_kw diagnostics attr
tests asserting no runtime alias / registry key exists
```

Not allowed final hits:

```text
active state_trigger old HA template sensors
active runtime config required_power_w or rpnz_w
runtime aliases for required_power_consumption_kw, rpnz_w, or pv_power_kw
runtime entity registry keys required_power_consumption_kw, required_power_w, rpnz_w, or pv_power_kw
policy engine get_float() reads from old derived sensor entities
policy engine entities[...] reads for old derived keys or pv_power_kw
```

## Production validation after deployment

Verify Home Assistant diagnostics:

```yaml
sensor.ems_policy_diagnostics_pyscript:
  runtime_input_contract: raw_measurements_only
  net_zero_derived_source: internal
  net_zero_input_quality: ok
  grid_power_w: <raw grid>
  quarter_energy_balance_kwh: <raw balance>
  pv_power_w: <raw pv>
  pv_power_kw: <raw pv / 1000 or null>
  remaining_quarter_s: <computed>
  remaining_quarter_min: <computed>
  rpnz_w: <computed>
  required_power_w: <computed>
  required_power_consumption_kw: <computed>
```

Trigger validation:

```text
Change sensor.average_active_power_2 -> diagnostics updates and required power may change.
Change sensor.hourly_energy_balance -> diagnostics updates and RPNZ / required power may change.
Change sensor.pv_instant_power_2 -> hardoff / release-ready diagnostics may change.
No sensor changes -> derived time-dependent values update on the 30 s periodic loop.
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

Hash stability validation:

```text
sensor.ems_device_policies_pyscript hash changes only when device_policies payload changes.
sensor.ems_surplus_dispatch_command_pyscript hash changes only when dispatch command payload changes.
sensor.ems_policy_state_pyscript hash changes only when persistent policy state payload changes.
sensor.ems_policy_diagnostics_pyscript may update every 30 s.
```

Writer and dispatch source validation:

```yaml
sensor.ems_actuator_writer_trace:
  policy_source_reason: canonical

sensor.ems_dispatch_state_applier_trace:
  dispatch_source_reason: canonical
```
