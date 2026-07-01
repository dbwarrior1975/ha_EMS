# Codex review notes: derive NET_ZERO inputs inside EMS

## Review decision

The phase plan is approved as an implementation baseline, but it needs the clarifications below before coding starts.

The main goal is correct and should remain unchanged:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  pv_power_w: sensor.pv_instant_power_2
```

EMS must derive internally:

```text
remaining_quarter_s
remaining_quarter_min
rpnz_w
required_power_w
required_power_consumption_kw
pv_power_kw
```

`rpnz_w` and `required_power_consumption_kw` may remain internal `NetZeroState` fields. They must not remain accepted runtime config fields, runtime aliases, runtime registry keys, or HA sensor reads.

## Overall assessment

The plan is directionally strong and implementation-ready after these changes. The ordering is correct:

1. Add pure derived NET_ZERO input module.
2. Clean runtime config contract.
3. Clean runtime entity registry.
4. Add raw `pv_power_w` to runtime measurements.
5. Build `NetZeroState` from internal derived values.
6. Publish raw and derived values only as diagnostics.
7. Replace old template-sensor triggers with raw measurement triggers.
8. Update configs, tests, and docs.
9. Run full tests and grep acceptance.

Do not combine this task with business-behavior changes in the NET_ZERO engine. Preserve the existing `NetZeroState` interface for this pass.

---

## Required clarification 1: raw runtime entity IDs are also state-trigger contract IDs

The new config contract looks configurable, but the Pyscript `@state_trigger` remains static at import time.

If the implementation uses:

```python
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

then these raw runtime entity IDs must be documented as stable production contract IDs for low-latency trigger behavior.

Add this note to the task/docs:

```text
The raw runtime entity IDs are stable state-trigger contract IDs. Changing them in EMS_config.yaml changes read-time inputs, but does not change the static Pyscript @state_trigger expression unless the code is updated. For low-latency production behavior, keep these entity IDs stable or update the trigger expression accordingly.
```

Acceptance addition:

```text
Active docs must not imply that runtime.grid_power_w, runtime.quarter_energy_balance_kwh, or runtime.pv_power_w are freely renameable without considering Pyscript trigger latency.
```

---

## Required clarification 2: `pv_power_kw` grep acceptance must be precise

`pv_power_kw` should be removed as a runtime alias / runtime registry key, but it is still a useful local derived value because the engine and diagnostics may naturally use kW.

Forbidden final uses:

```text
runtime alias: pv_power_kw
runtime registry key: ENT['pv_power_kw']
config field: runtime.pv_power_kw
HA sensor read: get_float(entities['pv_power_kw'], ...)
```

Allowed final uses:

```text
local variable: pv_power_kw = None if m.pv_power_w is None else m.pv_power_w / 1000.0
engine call argument if the core engine expects kW
diagnostics attribute: pv_power_kw
unit tests for local conversion / diagnostics
```

Update the grep acceptance language accordingly. Do not remove `pv_power_kw` diagnostics merely because the string appears in `ems_policy_engine.py`.

Suggested grep refinement:

```bash
rg "pv_power_kw" modules/ems_adapter ems_policy_engine.py tests
```

Allowed hits:

```text
ems_policy_engine.py local conversion from pv_power_w
diagnostics attrs
tests asserting no runtime alias / registry key exists
tests asserting diagnostics contains pv_power_kw
```

Not allowed hits:

```text
runtime_alias_index()/build_runtime_aliases() exposes pv_power_kw
build_runtime_entities_from_grouped_config() exposes ENT['pv_power_kw']
policy engine reads entities['pv_power_kw']
config accepts runtime.pv_power_kw
```

---

## Required clarification 3: define `remaining_template_minutes()` exactly

The old HA `Required Power Consumption` template uses minutes and ignores seconds. RPNZ uses seconds. Preserve this distinction in the first pass.

Define:

```python
def remaining_template_minutes(now_ts: float | datetime) -> int:
    return 15 - (minute % 15)
```

Important boundary behavior:

```text
12:00:00 -> 15
12:00:01 -> 15
12:14:59 -> 1
12:15:00 -> 15
```

Add explicit tests:

```text
remaining_template_minutes at quarter boundary returns 15
remaining_template_minutes one second before quarter boundary returns 1
required-power golden cases preserve minute-based behavior and do not switch to second-based behavior
```

Do not “improve” this formula to use seconds in this task. That would be a behavior change and should be a separate task if desired later.

---

## Required clarification 4: avoid ambiguous rounding golden cases

Python `round()` and HA/Jinja rounding can differ around `.5` boundaries depending on exact usage and type conversion.

For this pass, golden tests should avoid `.5` boundary cases unless the desired rounding behavior is explicitly asserted.

Add this instruction:

```text
Choose required-power and RPNZ golden cases that do not land exactly on x.5 W boundaries, unless the test intentionally defines the Python-vs-Jinja rounding contract.
```

If exact compatibility is required, implement and test a dedicated rounding helper instead of relying on incidental behavior.

---

## Required clarification 5: define missing/unavailable raw input behavior

The plan already handles missing PV carefully. It must also define behavior for missing or invalid `grid_power_w` and `quarter_energy_balance_kwh`.

Recommended safe behavior:

```text
If quarter_energy_balance_kwh is missing/invalid:
  use 0.0 as safe fallback for derived NET_ZERO values
  set diagnostics net_zero_input_quality = degraded_missing_quarter_balance
  include net_zero_input_warnings with the missing entity/key

If grid_power_w is missing/invalid:
  use 0.0 for required-power derivation
  set diagnostics net_zero_input_quality = degraded_missing_grid_power
  include net_zero_input_warnings with the missing entity/key

If both are valid:
  net_zero_input_quality = ok
```

Alternative acceptable safe behavior:

```text
If a required raw NET_ZERO input is unavailable:
  rpnz_w = 0
  required_power_w = 0
  required_power_consumption_kw = 0
  diagnostics clearly reports unavailable input
```

Choose one behavior and test it. Do not allow the policy loop to crash because one raw measurement is temporarily `unknown`, `unavailable`, empty, or invalid.

Suggested tests:

```text
quarter_energy_balance_kwh unavailable -> safe derived output and degraded diagnostics
grid_power_w unavailable -> safe required-power output and degraded diagnostics
pv_power_w unavailable -> pv_power_w None, pv_power_kw None, EV hardoff behavior remains safe
invalid numeric strings do not crash the policy loop
```

---

## Required clarification 6: diagnostics may update every loop, canonical hashes must not include volatile diagnostics

After this refactor, `sensor.ems_policy_diagnostics_pyscript` will likely change every 30 seconds because it contains live raw/derived fields:

```text
remaining_quarter_s
grid_power_w
quarter_energy_balance_kwh
pv_power_w
rpnz_w
required_power_w
required_power_consumption_kw
```

This is acceptable for diagnostics.

Add this explicit non-goal / invariant:

```text
It is acceptable that policy_diagnostics changes on each policy loop because it contains live raw/derived measurements.
Canonical output sensors must remain content-hash scoped to command/state payloads only.
Do not include volatile diagnostics-only fields such as remaining_quarter_s, raw measurements, or derived debug values in the canonical device_policies, dispatch_command, or policy_state hashes unless they actually change the command/state payload.
```

Acceptance additions:

```text
sensor.ems_device_policies_pyscript hash changes only when device_policies payload changes
sensor.ems_surplus_dispatch_command_pyscript hash changes only when dispatch command payload changes
sensor.ems_policy_state_pyscript hash changes only when persistent policy state payload changes
policy_diagnostics may update every 30 s
```

---

## Required clarification 7: add explicit “do not reintroduce HA template sensors” checks

The old HA-template sensors must not remain in active runtime paths:

```text
sensor.required_power_consumption
sensor.ems_calculated_required_power_for_net_zero
```

Add source checks/tests that fail if `ems_policy_engine.py` still reads:

```python
entities['rpnz_w']
entities['required_power_consumption_kw']
entities['required_power_w']
```

Add source checks/tests that fail if `runtime_context.py` still exposes:

```python
ENT['rpnz_w']
ENT['required_power_consumption_kw']
ENT['required_power_w']
ENT['pv_power_kw']
```

Allowed final references to `rpnz_w` and `required_power_consumption_kw`:

```text
NetZeroState fields
internal derived input module/tests
policy diagnostics attrs
engine business logic using nz.rpnz_w and nz.required_power_consumption_kw
release/migration notes
legacy rejection tests
```

Not allowed:

```text
runtime config field
runtime alias
runtime entity registry key
HA sensor read
active Pyscript state_trigger old template sensors
```

---

## Required clarification 8: keep any `quarter_energy_balance` alias internal and transitional

The plan allows both:

```python
ent['quarter_energy_balance'] = runtime.get('quarter_energy_balance_kwh')
ent['quarter_energy_balance_kwh'] = runtime.get('quarter_energy_balance_kwh')
```

This is acceptable only if current readers/tests still require the shorter internal key.

Add this acceptance rule:

```text
If quarter_energy_balance remains as an internal compatibility alias, document it as internal/transitional only. Do not expose it in active config examples or user docs as a public runtime contract. The public config key is quarter_energy_balance_kwh.
```

Preferred clean final state:

```text
runtime config key: quarter_energy_balance_kwh
runtime registry key: quarter_energy_balance_kwh
internal code gradually migrates away from quarter_energy_balance alias
```

---

## Concrete additions to the existing phase plan

### Add to Phase 1: pure derived input module

Additional tests:

```text
remaining_template_minutes(quarter boundary) == 15
remaining_template_minutes(one second before quarter boundary) == 1
required-power formula uses remaining_template_minutes, not remaining seconds
missing/invalid raw inputs handled by chosen safe behavior
rounding tests avoid unintended .5 boundary ambiguity
```

### Add to Phase 2: config contract

Additional assertions:

```text
runtime.required_power_w rejected with explicit derived-inside-EMS message
runtime.rpnz_w rejected with explicit derived-inside-EMS message
runtime.pv_power_kw rejected if present
runtime only accepts grid_power_w, quarter_energy_balance_kwh, pv_power_w
```

### Add to Phase 3: runtime entity registry

Additional assertions:

```text
ENT contains pv_power_w
ENT does not contain pv_power_kw
ENT does not contain required_power_consumption_kw
ENT does not contain required_power_w
ENT does not contain rpnz_w
quarter_energy_balance alias, if present, is internal only
```

### Add to Phase 5: policy engine

Additional assertions:

```text
policy engine never reads entities['rpnz_w']
policy engine never reads entities['required_power_consumption_kw']
policy engine never reads entities['required_power_w']
policy engine never reads entities['pv_power_kw']
pv_power_kw is only local conversion from m.pv_power_w
```

### Add to Phase 6: diagnostics

Required diagnostics attrs:

```yaml
runtime_input_contract: raw_measurements_only
net_zero_derived_source: internal
net_zero_input_quality: ok | degraded_missing_quarter_balance | degraded_missing_grid_power | degraded_missing_multiple_inputs
grid_power_w: <raw or fallback>
quarter_energy_balance_kwh: <raw or fallback>
pv_power_w: <raw or null>
pv_power_kw: <raw / 1000 or null>
remaining_quarter_s: <computed>
remaining_quarter_min: <computed>
rpnz_w: <computed>
required_power_w: <computed>
required_power_consumption_kw: <computed>
```

### Add to Phase 7: triggers

Additional note:

```text
The raw measurement entity IDs used in @state_trigger are stable trigger contract IDs. If these entity IDs are changed in config, low-latency state-trigger behavior requires updating the decorator expression as well.
```

Additional source checks:

```text
active @state_trigger contains sensor.average_active_power_2
active @state_trigger contains sensor.hourly_energy_balance
active @state_trigger contains sensor.pv_instant_power_2
active @state_trigger does not contain sensor.required_power_consumption
active @state_trigger does not contain sensor.ems_calculated_required_power_for_net_zero
```

---

## Updated acceptance checks

Run full tests:

```bash
pytest -q
```

Recommended targeted checks:

```bash
pytest -q tests/unit/test_net_zero_derived_inputs.py
pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py
pytest -q tests/contract/test_grouped_config_contract.py tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/smoke/test_release_example_config_loads.py
```

Grep checks:

```bash
rg "sensor.required_power_consumption|sensor.ems_calculated_required_power_for_net_zero" ems_*.py modules tests docs/user docs/dev README.md
rg "required_power_w|rpnz_w" EMS_config.yaml example_EMS_config.yaml tests/e2e_entity
rg "required_power_consumption_kw|rpnz_w|pv_power_kw" modules/ems_adapter ems_policy_engine.py tests
rg "entities\['rpnz_w'\]|entities\['required_power_consumption_kw'\]|entities\['required_power_w'\]|entities\['pv_power_kw'\]" ems_policy_engine.py tests
```

Allowed final hits:

```text
release notes and migration docs
legacy rejection tests
NetZeroState fields
internal derived input tests
policy diagnostics attrs
engine business logic using nz.rpnz_w and nz.required_power_consumption_kw
pv_power_kw local conversion from pv_power_w and diagnostics attr
```

Not allowed final hits:

```text
active state_trigger old HA template sensors
active runtime config required_power_w or rpnz_w
runtime aliases for required_power_consumption_kw, rpnz_w, required_power_w, or pv_power_kw
runtime entity registry keys required_power_consumption_kw, required_power_w, rpnz_w, or pv_power_kw
policy engine get_float() reads from old derived sensor entities
policy engine entities[...] reads for old derived keys
```

---

## Production validation additions

After deployment, verify:

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
No sensor changes -> time-dependent derived values update on the 30 s periodic loop.
```

Canonical output validation remains unchanged:

```yaml
sensor.ems_device_policies_pyscript:
  device_policies_state_kind: content_hash

sensor.ems_surplus_dispatch_command_pyscript:
  dispatch_command_state_kind: content_hash

sensor.ems_policy_state_pyscript:
  policy_state_state_kind: content_hash

sensor.ems_actuator_writer_trace:
  policy_source_reason: canonical

sensor.ems_dispatch_state_applier_trace:
  dispatch_source_reason: canonical
```

## Final review verdict

Proceed with implementation after applying these clarifications. The plan is strong and correctly scoped. The most important guardrails are:

```text
raw runtime inputs only in config
no HA-template-derived runtime reads
pv_power_w as first-class raw input
pv_power_kw only as local derived conversion / diagnostics
stable Pyscript trigger entity IDs documented
safe behavior for missing raw inputs
canonical hashes protected from volatile diagnostics fields
```
