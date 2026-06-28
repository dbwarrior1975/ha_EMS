# Codex Task: Remove `current_a` from EV Core Decision Pipeline

## Objective

Refactor EV_CHARGER core decision flow so that EV charging decisions are target-watt-native.

The current intermediate pipeline is wrong:

```text
capabilities W
  -> derived current A
  -> load_projection returns A
  -> engine converts A to W
  -> writer converts W to A
```

The desired pipeline is:

```text
capabilities W
  -> load_projection / engine returns target_w
  -> writer converts target_w to current_a
```

This task must remove the active `current_a` intermediate representation from the EV core decision pipeline.

## Core Rule

After this task:

```text
No EV core decision function may return current_a as its primary output.
```

EV current in amps may exist only in these places:

```text
1. EV W/A helper functions
2. EV actuator writer
3. runtime/debug/trace fields
4. tests specifically covering W/A conversion or writer output
```

EV current in amps must not be used as the internal policy decision output in:

```text
load_projection.py
engine.py
net-zero core decision flow
force_on handling
manual / net-zero / max-export / cheap-grid EV mode decisions
```

## Non-Goals

Do not redo the whole EV watt-based refactor.

Do not change the selected surplus threshold semantics unless a failing test proves it is necessary.

Do not reintroduce:

```text
adapter.current_min_a
adapter.current_max_a
adapter.force_current_a
```

Do not add `force_target_w`.

Do not move W/A conversion earlier in the pipeline. W/A conversion belongs at the writer boundary.

## Required End State

The EV command pipeline must look like this:

```text
EV config:
  capabilities.min_absorb_w
  capabilities.max_absorb_w
  policy.force_on
  adapter.current_step_a
  adapter.phases
  adapter.voltage_v

Core strategy:
  returns ev_target_w

Engine:
  stores/emits device_policy.target_w

Writer:
  converts target_w -> current_a
  writes charger selector
```

There must be no active production pipeline like this:

```text
ev_strategy_current_a()
  -> ev_current_a_to_power_w(...)
  -> device_policy.target_w
  -> ev_power_w_to_current_a(...)
```

That `A -> W -> A` roundtrip must be removed from active EV control logic.

---

## Phase 1: Locate Current Amp-Based EV Decision Flow

Search the repository for:

```text
ev_strategy_current_a
ev_current_a
ev_min_current_a
ev_max_current_a
ev_current_a_to_power_w
ev_power_w_to_current_a
force_on
max_absorb_w
min_absorb_w
```

Identify all active production references in:

```text
modules/ems_core/net_zero/load_projection.py
modules/ems_core/net_zero/engine.py
modules/ems_core/domain/models.py
modules/ems_adapter/runtime_context.py
ems_actuator_writers.py
```

Classify each reference as one of:

```text
A. allowed helper/writer/debug usage
B. forbidden core decision usage
C. compatibility-only usage
D. test-only usage
```

Only category A, C, and D may remain after this task.

Category B must be removed.

---

## Phase 2: Replace EV Strategy API

### Required change

Replace this conceptual API:

```python
ev_strategy_current_a(...)
```

with this conceptual API:

```python
ev_strategy_target_w(...)
```

The new function must return watts, not amps.

Suggested signature shape:

```python
def ev_strategy_target_w(
    *,
    profiles,
    ev_force_on: bool,
    ev_hard_off_active: bool,
    burn_active: bool,
    hard_off_allowed: bool,
    low_pv_safety_block: bool,
    min_absorb_w: float,
    max_absorb_w: float,
    # include existing required state inputs here
) -> float:
    ...
```

Adapt to the actual project style, but the output must be watt-based.

### Required behavior

Preserve the already selected semantic from the previous refactor:

```text
force_on overrides optimization modes but not safety/device availability.
```

Therefore:

```text
if safety/device/hard-off condition blocks EV:
    return 0

elif policy.force_on:
    return capabilities.max_absorb_w

elif NET_ZERO burn_active:
    return capabilities.max_absorb_w

elif restore/minimum-charge behavior is required:
    return capabilities.min_absorb_w

elif EV should be off:
    return 0

else:
    return existing mode-specific target expressed in watts
```

Do not return derived current values from this function.

### Explicit mapping examples

#### Force on

Before:

```text
force_on -> ev_max_current_a -> current_a_to_power_w -> target_w
```

After:

```text
force_on -> max_absorb_w
```

#### Net-zero burn

Before:

```text
burn_active -> ev_max_current_a
```

After:

```text
burn_active -> max_absorb_w
```

#### Hard off

Before:

```text
hard_off -> 0 A
```

After:

```text
hard_off -> 0 W
```

#### Restore minimum

Before:

```text
restore_min -> ev_min_current_a
```

After:

```text
restore_min -> min_absorb_w
```

Only use `min_absorb_w` if this matches the existing state semantics. If the existing state means fully off, return `0`.

---

## Phase 3: Update Engine to Consume `target_w` Directly

In `modules/ems_core/net_zero/engine.py`, remove the active pattern:

```python
ev_current_a = ev_strategy_current_a(...)
ev_target_w = ev_current_a_to_power_w(ev_current_a, ...)
```

Replace it with:

```python
ev_target_w = ev_strategy_target_w(...)
```

Then pass `ev_target_w` directly into the device policy output.

The engine must not derive EV policy target watts from EV current.

Allowed exception:

```text
Measured current_a from the actual charger may still be converted to measured power for telemetry/debug.
```

Forbidden:

```text
Policy target current_a -> policy target_w
```

Allowed:

```text
Actual measured current_a -> measured current power estimate
```

---

## Phase 4: Keep W/A Conversion Only in Writer

The EV actuator writer is the only active production layer that should convert desired EV target watts to charger amps.

Writer flow must remain:

```text
device_policy.target_w
  -> clamp to capabilities.min_absorb_w / max_absorb_w
  -> convert target_w to supported current_a
  -> write current selector
```

The writer may continue using:

```text
ev_power_w_to_current_a(...)
ev_min_current_a_from_min_absorb_w(...)
ev_max_current_a_from_max_absorb_w(...)
```

Do not move these conversions back into engine or load_projection.

---

## Phase 5: Restrict Derived Current Fields

Derived current fields may remain for compatibility, trace, or writer support, but they must not be used as policy decision inputs.

Allowed:

```text
ev_derived_min_current_a in debug/trace
ev_derived_max_current_a in debug/trace
derived current in writer conversion
derived current in unit tests for ev_power.py
```

Forbidden:

```text
load_projection choosing EV target by returning ev_max_current_a
engine choosing EV target by converting ev_current_a to W
force_on implemented as max_current_a
NET_ZERO burn implemented as max_current_a
restore_min implemented as min_current_a inside core strategy
```

If `CoreConfig` still exposes:

```text
cfg.ev_min_current_a
cfg.ev_max_current_a
```

then after this task they must be treated as compatibility/debug fields only.

They must not be used by the EV core decision strategy.

---

## Phase 6: Tests to Update or Add

Add or update tests so the new contract is enforced.

### 1. Force-on returns max watts

Create or update a test around load projection / engine:

```text
Given:
  policy.force_on = true
  max_absorb_w = 6440

Expect:
  EV strategy target_w == 6440
  engine device_policy.target_w == 6440
```

Do not assert that load projection returns `28 A`.

Writer tests may still assert the final selector current.

### 2. Net-zero burn returns max watts

```text
Given:
  burn_active = true
  max_absorb_w = 6440

Expect:
  EV strategy target_w == 6440
```

### 3. Hard-off returns zero watts

```text
Given:
  EV hard_off is active or safety blocks charging

Expect:
  EV strategy target_w == 0
```

### 4. Restore-min returns min watts where applicable

```text
Given:
  existing logic would previously restore min current
  min_absorb_w = 1380

Expect:
  EV strategy target_w == 1380
```

If the correct semantic is off, assert `0` instead. Do not assert min amps in core tests.

### 5. Engine does not A->W target conversion

Add a regression test or structural assertion where practical:

```text
engine receives/produces EV target_w directly
```

Avoid tests that require engine policy target to be derived from `ev_current_a`.

### 6. Writer remains the only W->A target conversion layer

Writer tests should continue to assert:

```text
target_w = 6440
phases = 1
voltage_v = 230
current_step_a = compatible value

expected selector current = derived supported current
```

But this must be a writer test, not a load_projection or engine decision test.

---

## Phase 7: Search-Based Acceptance Checks

Before finishing, run repository search.

### These may remain only in helper/writer/debug/test contexts

```text
ev_min_current_a
ev_max_current_a
ev_current_a_to_power_w
ev_power_w_to_current_a
```

### These must not remain as active core strategy outputs

```text
ev_strategy_current_a
return cfg.ev_max_current_a
return cfg.ev_min_current_a
```

Especially inspect:

```text
modules/ems_core/net_zero/load_projection.py
modules/ems_core/net_zero/engine.py
```

There should be no EV policy path equivalent to:

```text
force_on -> max_current_a -> current_a_to_power_w -> target_w
```

There should only be:

```text
force_on -> max_absorb_w -> target_w
```

---

## Acceptance Criteria

The task is complete only when all of these are true:

1. Active EV core decision logic returns target watts, not current amps.
2. `ev_strategy_current_a` is removed, renamed, or no longer used in production EV decision flow.
3. A new or updated `ev_strategy_target_w` function exists, or equivalent target-watt-native logic exists.
4. `policy.force_on == true` produces `target_w = capabilities.max_absorb_w` before the writer layer.
5. `NET_ZERO burn_active` produces `target_w = capabilities.max_absorb_w` before the writer layer.
6. Hard-off/safety-blocked EV produces `target_w = 0`.
7. Restore-min behavior, if applicable, uses `target_w = capabilities.min_absorb_w`, not `ev_min_current_a`.
8. `engine.py` no longer computes policy `ev_target_w` by converting a strategy-returned `current_a`.
9. W/A target conversion happens only in the writer or EV helper tests.
10. Existing EV writer behavior remains correct: `target_w -> supported current_a -> charger selector`.
11. All updated tests pass.
12. Progress document is updated with what was changed, which old A-based decision paths were removed, and which A-based references remain and why they are allowed.

---

## Verification Commands

Run at minimum:

```bash
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_ev_power.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
```

If available and not too slow, also run:

```bash
pytest -q tests/e2e_entity/
pytest -q
```

---

## Final Required Progress Note

Update the progress markdown with a section named:

```text
Phase 9: Remove EV current_a from core decision pipeline
```

Include:

```text
- Replaced EV core strategy output from current_a to target_w.
- Removed A -> W -> A policy roundtrip.
- force_on now maps directly to max_absorb_w before writer.
- NET_ZERO burn now maps directly to max_absorb_w before writer.
- hard_off maps directly to 0 W before writer.
- W -> A conversion remains only in EV writer / EV power helpers.
- Remaining amp references are limited to writer, helper, debug, compatibility, or tests.
```
