# Codex Task: Refactor EV_CHARGER to Watt-Based Capabilities and Replace `force_current_a` with `force_on`

## Context

The current `EV_CHARGER` implementation mixes two different configuration models:

1. EMS/core policy is partly watt-based through device capabilities:
   - `capabilities.min_absorb_w`
   - `capabilities.max_absorb_w`
   - `capabilities.step_w`

2. EV charger adapter policy is partly ampere-based:
   - `adapter.current_min_a`
   - `adapter.current_max_a`
   - `adapter.current_step_a`
   - `adapter.force_current_a`
   - `adapter.phases`
   - `adapter.voltage_v`

This creates ambiguity because the same physical limits are represented in two places and two units. It also makes `EV_CHARGER` behave differently from `RELAY`, even though both are absorbable surplus loads from the EMS/core perspective.

The desired refactor is:

- Core and policy logic should use watts.
- EV adapter/writer logic should convert watts to amps only at the actuator boundary.
- User-configured EV min/max limits should be `capabilities.min_absorb_w` and `capabilities.max_absorb_w`.
- `adapter.current_min_a` and `adapter.current_max_a` should be removed.
- `adapter.force_current_a` should be removed.
- EV should use `policy.force_on`, same as relay.
- When `policy.force_on == true`, EV should charge at `capabilities.max_absorb_w`.
- `adapter.phases` and `adapter.voltage_v` should define the W/A conversion.
- `adapter.current_step_a` should define the charger selector resolution.

## High-Level Goal

Make `EV_CHARGER` a watt-based EMS device:

```text
EMS/core:
  min_absorb_w
  max_absorb_w
  force_on
  target_w

EV adapter/writer:
  current_a selector
  current_step_a
  phases
  voltage_v
  W -> A conversion
```

After this refactor, `EV_CHARGER` and `RELAY` should share the same high-level policy semantics:

```text
force_on == true
  RELAY      -> command max_absorb_w by turning relay on
  EV_CHARGER -> command max_absorb_w by enabling charger and setting current selector
```

## Non-Goals

Do not introduce a new `force_target_w` policy in this task.

Do not keep `force_current_a` as a compatibility alias unless the existing config loader absolutely requires a transitional migration path. Prefer removing it cleanly and updating tests/config fixtures.

Do not keep `current_min_a` or `current_max_a` as policy fields under `adapter`.

Do not change unrelated relay semantics except where shared helper code can be simplified safely.

## Current Problem Summary

The current EV surplus threshold appears to be based on the ampere range:

```text
threshold_w = (current_max_a - current_min_a) * phases * 230
```

This is confusing because:

- `max_absorb_w` may exist separately.
- `min_absorb_w` may exist separately.
- `voltage_v` is configured but the current implementation may use hardcoded 230 V in some paths.
- `current_max_a` and `max_absorb_w` can drift out of sync.
- `current_min_a` and `min_absorb_w` can drift out of sync.
- `force_current_a` is ampere-based while the rest of the target contract is becoming watt-based.

The refactor should make the relationship explicit:

```text
per_amp_w = phases * voltage_v

derived_min_current_a = ceil_to_supported_step(min_absorb_w / per_amp_w)
derived_max_current_a = floor_to_supported_step(max_absorb_w / per_amp_w)
derived_step_w        = current_step_a * per_amp_w
```

## Desired Configuration Shape

### Before

```yaml
kind: EV_CHARGER
capabilities:
  min_absorb_w: input_number.ems_ev_min_absorb_w
  max_absorb_w: input_number.ems_ev_max_absorb_w
  step_w: input_number.ems_ev_step_w

adapter:
  enabled: switch.charger_control
  current_a: number.charger_current_level
  current_min_a: input_number.ems_ev_min_current_a
  current_max_a: input_number.ems_ev_max_current_a
  current_step_a: input_number.ems_ev_current_step_a
  phases: input_number.ems_ev_charger_phases
  voltage_v: input_number.ems_ev_voltage_v
  force_current_a: input_number.ems_ev_force_current_a
```

### After

```yaml
kind: EV_CHARGER
capabilities:
  min_absorb_w: input_number.ems_ev_min_absorb_w
  max_absorb_w: input_number.ems_ev_max_absorb_w

policy:
  force_on: input_boolean.ems_ev_force_on

adapter:
  enabled: switch.charger_control
  current_a: number.charger_current_level
  current_step_a: input_number.ems_ev_current_step_a
  phases: input_number.ems_ev_charger_phases
  voltage_v: input_number.ems_ev_voltage_v
```

`capabilities.step_w` can either be:

1. Removed for EV and derived from `current_step_a * phases * voltage_v`, or
2. Kept as optional metadata if the surrounding schema requires it.

Prefer deriving EV step watts from `current_step_a`, because charger actuator resolution is natively ampere-based.

## Target Semantics

### EV Power Conversion

Use configured voltage, not a hardcoded constant.

```python
per_amp_w = phases * voltage_v
power_w = current_a * per_amp_w
current_a = power_w / per_amp_w
```

### Derived Current Bounds

The EV writer should derive current bounds from capabilities:

```python
raw_min_a = min_absorb_w / (phases * voltage_v)
raw_max_a = max_absorb_w / (phases * voltage_v)
```

Suggested rounding:

```text
derived_min_current_a = ceil_to_supported_step(raw_min_a)
derived_max_current_a = floor_to_supported_step(raw_max_a)
```

Rationale:

- Min current is rounded up so the requested minimum power is actually reachable.
- Max current is rounded down so the configured max power is never exceeded.
- Final current must respect `current_step_a`.

### `force_on`

For EV:

```text
if policy.force_on:
    target_w = capabilities.max_absorb_w
```

Then writer converts:

```text
target_w -> current_a
```

For relay, existing behavior should remain:

```text
if policy.force_on:
    relay on / target_w = max_absorb_w
```

### Safety and Availability

`force_on` should override optimization decisions, but it must not override safety/device availability constraints.

Suggested precedence:

```python
if not device_available_or_safe:
    target_w = 0
elif policy.force_on:
    target_w = capabilities.max_absorb_w
else:
    target_w = normal_mode_logic()
```

Do not let `force_on` command an unavailable or unsafe charger.

## Surplus Threshold Decision

Use one explicit watt-based interpretation. Avoid ampere-range-based thresholding.

Recommended default for this project:

```text
EV_CHARGER surplus_threshold_w = max_absorb_w - min_absorb_w
```

This preserves the current apparent “min -> max incremental surplus” meaning, but expresses it through capabilities instead of adapter ampere fields.

However, if the actual runtime behavior treats EV as off -> max during surplus activation, use:

```text
EV_CHARGER surplus_threshold_w = max_absorb_w
```

Implementation choice:

- Inspect existing activation/release behavior.
- Pick exactly one interpretation.
- Encode it in tests and trace fields.
- Do not leave mixed semantics where threshold is incremental but command is off -> max without explicit naming.

If choosing incremental threshold, name/debug it clearly:

```text
incremental_surplus_threshold_w = max_absorb_w - min_absorb_w
```

## Proposed Implementation Phases

### Phase 1: Add Central EV W/A Helper Functions

Target file candidates:

- `modules/ems_core/domain/ev_power.py`

Add or update helpers so all EV conversions use the same implementation.

Required helper behavior:

```python
def ev_per_amp_w(phases: int, voltage_v: float) -> float:
    ...

def ev_current_a_to_power_w(current_a: float, phases: int, voltage_v: float) -> float:
    ...

def ev_power_w_to_current_a(
    power_w: float,
    *,
    phases: int,
    voltage_v: float,
    min_absorb_w: float,
    max_absorb_w: float,
    current_step_a: int | float,
) -> int | float:
    ...
```

Also add helpers for derived bounds:

```python
def ev_min_current_a_from_min_absorb_w(
    min_absorb_w: float,
    *,
    phases: int,
    voltage_v: float,
    current_step_a: int | float,
) -> int | float:
    ...

def ev_max_current_a_from_max_absorb_w(
    max_absorb_w: float,
    *,
    phases: int,
    voltage_v: float,
    current_step_a: int | float,
) -> int | float:
    ...
```

Rules:

- Use `voltage_v` from config.
- Remove hardcoded `230` from EV conversion paths.
- Clamp output current to the derived min/max current range.
- Quantize output current to `current_step_a`.

Add unit tests for:

- 1-phase 230 V conversion.
- 3-phase 230 V conversion.
- Non-230 voltage conversion if voltage is configurable.
- Min rounding up.
- Max rounding down.
- Step quantization.
- No max overrun.

### Phase 2: Update EV Config Schema / Models

Target file candidates:

- Core config/domain model files defining `CoreEvAdapterConfig`
- Adapter config loader files
- Config validation files
- Fixtures/examples under config or tests

Remove these EV adapter fields:

```yaml
adapter.current_min_a
adapter.current_max_a
adapter.force_current_a
```

Add or reuse:

```yaml
policy.force_on
```

Keep these adapter fields:

```yaml
adapter.enabled
adapter.current_a
adapter.current_step_a
adapter.phases
adapter.voltage_v
```

Ensure EV capabilities require or resolve:

```yaml
capabilities.min_absorb_w
capabilities.max_absorb_w
```

Validation requirements:

```text
min_absorb_w > 0
max_absorb_w >= min_absorb_w
phases > 0
voltage_v > 0
current_step_a > 0
```

Also validate that at least one valid current selector value exists between derived min/max current:

```text
derived_min_current_a <= derived_max_current_a
```

Prefer validating against `current_step_a` as well, if helper behavior supports exact supported-current enumeration.

### Phase 3: Update Runtime Read Model

Target file candidates:

- `modules/ems_adapter/device_read_model.py`
- Any runtime context builder that reads EV adapter fields

Remove reads of:

```text
current_min_a
current_max_a
force_current_a
```

Read/resolve:

```text
policy.force_on
capabilities.min_absorb_w
capabilities.max_absorb_w
adapter.current_step_a
adapter.phases
adapter.voltage_v
```

Expose trace/debug fields:

```text
ev_per_amp_w
ev_derived_min_current_a
ev_derived_max_current_a
ev_derived_step_w
ev_current_power_w
ev_force_on
```

Do not expose `force_current_a` in new trace output except possibly in a deprecated migration warning, if needed.

### Phase 4: Update Surplus Target Construction

Target file candidates:

- `modules/ems_core/net_zero/surplus_device_targets.py`
- `modules/ems_core/net_zero/engine.py`

Replace ampere-range-based EV threshold calculation:

```python
threshold_w = (current_max_a - current_min_a) * phases * 230
```

with watt-based capability calculation.

Recommended:

```python
threshold_w = max_absorb_w - min_absorb_w
```

Alternative if the implementation chooses off -> max semantics:

```python
threshold_w = max_absorb_w
```

Rules:

- Do not use `adapter.current_min_a`.
- Do not use `adapter.current_max_a`.
- Do not hardcode `230`.
- If `adjustable_surplus_activation_w > 0` currently overrides threshold, preserve that override unless there is an explicit reason to remove it.
- Update tests to document the selected threshold semantics.

### Phase 5: Update Load Projection / Mode Logic

Target file candidates:

- `modules/ems_core/net_zero/load_projection.py`
- `modules/ems_core/net_zero/engine.py`

Replace EV `force_current_a` handling with `force_on`.

Current conceptual behavior to remove:

```text
force_current_a is interpreted as direct ampere target or floor
```

New behavior:

```text
force_on true -> target_w = max_absorb_w
```

Mode behavior guidance:

#### MANUAL / MANUAL_SAFE

If `force_on` is true:

```text
target_w = max_absorb_w
```

If false:

```text
normal manual behavior / no forced EV charge
```

#### NET_ZERO

If `force_on` is true:

```text
target_w = max_absorb_w
```

Otherwise normal net-zero EV logic.

#### MAX_EXPORT

Decide explicitly whether `force_on` is allowed to override max-export mode.

Recommended:

```text
MAX_EXPORT means do not consume intentionally, so force_on should either:
  A) be ignored in MAX_EXPORT, or
  B) override only if manual policy is considered stronger than mode.
```

Pick one and encode it in tests.

For a simple user mental model, prefer:

```text
force_on overrides optimization mode but not safety.
```

That means force_on can charge even in MAX_EXPORT, because the user explicitly requested charging.

#### CHEAP_GRID_CHARGE

If `force_on` is true, charge at `max_absorb_w`.

Otherwise keep existing cheap-grid behavior.

### Phase 6: Update EV Actuator Writer

Target file candidates:

- `ems_actuator_writers.py`

Remove dependency on:

```text
adapter.current_min_a
adapter.current_max_a
adapter.force_current_a
```

Writer should receive or resolve:

```text
target_w
capabilities.min_absorb_w
capabilities.max_absorb_w
adapter.current_step_a
adapter.phases
adapter.voltage_v
adapter.current_a
adapter.enabled
```

Writer behavior:

#### For `target_w <= 0`

```text
turn charger switch off
set current selector to derived_min_current_a if selector requires non-zero floor
```

Do not write 0 A unless the charger selector supports it and current code already does that safely.

#### For `target_w > 0`

```text
turn charger switch on
convert target_w to supported current_a
write current_a selector
```

Conversion:

```text
current_a = quantized_clamped_current_for_target_w(
    target_w,
    min_absorb_w,
    max_absorb_w,
    current_step_a,
    phases,
    voltage_v,
)
```

Must never exceed derived max current.

Must not command below derived min current when charger is on.

### Phase 7: Update Tests

Update existing tests and add new tests.

Known relevant test candidates:

- `tests/unit/test_ev_power.py`
- `tests/unit/test_surplus_device_targets.py`
- Tests covering config loading/validation
- Tests covering `load_projection.py`
- Tests covering `ems_actuator_writers.py`
- Any engine tests using EV fixtures

Required test scenarios:

#### EV conversion

```text
1-phase: 28 A * 230 V = 6440 W
3-phase: 28 A * 230 V = 19320 W
voltage_v is honored, not hardcoded
```

#### Derived bounds

```text
min_absorb_w = 1380 W, phases = 1, voltage_v = 230 -> min_A = 6
max_absorb_w = 6440 W, phases = 1, voltage_v = 230 -> max_A = 28
```

#### Step quantization

Example:

```text
target_w = 2300 W
phases = 1
voltage_v = 230
current_step_a = 4
valid currents around target: 8 A / 12 A depending existing rounding policy
```

Keep existing expected rounding direction if the project already defines it. If not, choose and document it.

#### Max clamp

```text
target_w > max_absorb_w -> derived max current only
```

#### Min clamp

```text
0 < target_w < min_absorb_w -> derived min current if charger is on
```

#### Force on

```text
policy.force_on = true
max_absorb_w = 6440 W
phases = 1
voltage_v = 230
expected command current = 28 A
expected charger enabled = true
```

#### Force off / no force

```text
policy.force_on = false
normal optimization result is used
```

#### Removed fields

Config using these fields should fail validation or be ignored with explicit deprecation warning, depending migration decision:

```yaml
adapter.current_min_a
adapter.current_max_a
adapter.force_current_a
```

Prefer failing fast in tests unless backward compatibility is required.

### Phase 8: Update Examples and Documentation

Update any YAML examples, README snippets, comments, and Home Assistant helper recommendations.

Replace:

```yaml
input_number.ems_ev_min_current_a
input_number.ems_ev_max_current_a
input_number.ems_ev_force_current_a
```

with:

```yaml
input_number.ems_ev_min_absorb_w
input_number.ems_ev_max_absorb_w
input_boolean.ems_ev_force_on
```

Keep:

```yaml
input_number.ems_ev_current_step_a
input_number.ems_ev_charger_phases
input_number.ems_ev_voltage_v
```

Add documentation:

```text
EV_CHARGER min/max are configured in watts.
The current selector is an actuator detail.
The EMS derives current from watts using phases and voltage.
force_on commands max_absorb_w.
```

## Suggested Code-Level Helper Design

Example implementation sketch:

```python
from __future__ import annotations

import math


def ev_per_amp_w(phases: int | float, voltage_v: int | float) -> float:
    p = float(phases)
    v = float(voltage_v)
    if p <= 0:
        raise ValueError("EV charger phases must be positive")
    if v <= 0:
        raise ValueError("EV charger voltage_v must be positive")
    return p * v


def _ceil_to_step(value: float, step: float) -> float:
    if step <= 0:
        raise ValueError("current_step_a must be positive")
    return math.ceil(value / step) * step


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        raise ValueError("current_step_a must be positive")
    return math.floor(value / step) * step


def ev_min_current_a_from_min_absorb_w(
    min_absorb_w: float,
    *,
    phases: int | float,
    voltage_v: int | float,
    current_step_a: int | float,
) -> float:
    if min_absorb_w <= 0:
        raise ValueError("EV min_absorb_w must be positive")
    return _ceil_to_step(min_absorb_w / ev_per_amp_w(phases, voltage_v), float(current_step_a))


def ev_max_current_a_from_max_absorb_w(
    max_absorb_w: float,
    *,
    phases: int | float,
    voltage_v: int | float,
    current_step_a: int | float,
) -> float:
    if max_absorb_w <= 0:
        raise ValueError("EV max_absorb_w must be positive")
    return _floor_to_step(max_absorb_w / ev_per_amp_w(phases, voltage_v), float(current_step_a))


def ev_current_a_to_power_w(
    current_a: float,
    *,
    phases: int | float,
    voltage_v: int | float,
) -> float:
    return float(current_a) * ev_per_amp_w(phases, voltage_v)


def ev_power_w_to_supported_current_a(
    target_w: float,
    *,
    min_absorb_w: float,
    max_absorb_w: float,
    phases: int | float,
    voltage_v: int | float,
    current_step_a: int | float,
) -> float:
    min_a = ev_min_current_a_from_min_absorb_w(
        min_absorb_w,
        phases=phases,
        voltage_v=voltage_v,
        current_step_a=current_step_a,
    )
    max_a = ev_max_current_a_from_max_absorb_w(
        max_absorb_w,
        phases=phases,
        voltage_v=voltage_v,
        current_step_a=current_step_a,
    )

    if min_a > max_a:
        raise ValueError("EV watt limits cannot be represented by configured current_step_a/phases/voltage_v")

    if target_w <= 0:
        return min_a

    target_a = target_w / ev_per_amp_w(phases, voltage_v)

    # Use nearest supported step by default.
    # If the existing implementation uses floor/ceil semantics, preserve that instead.
    quantized_a = round(target_a / float(current_step_a)) * float(current_step_a)

    return min(max(quantized_a, min_a), max_a)
```

Adjust type hints and rounding behavior to match project conventions.

## Migration Notes

This is a breaking config change unless compatibility is explicitly implemented.

Recommended approach:

1. Update examples and tests to new config.
2. Fail fast if old EV ampere policy fields are present.
3. Include a clear validation error:

```text
EV_CHARGER adapter.current_min_a/current_max_a/force_current_a are no longer supported.
Use capabilities.min_absorb_w, capabilities.max_absorb_w and policy.force_on instead.
```

If backward compatibility is required, add a temporary compatibility layer:

```text
current_min_a -> min_absorb_w = current_min_a * phases * voltage_v
current_max_a -> max_absorb_w = current_max_a * phases * voltage_v
force_current_a -> not directly migrated; use force_on or force target watts if later introduced
```

Prefer not to implement this compatibility layer unless needed.

## Acceptance Criteria

The task is complete when all of the following are true:

1. `EV_CHARGER` no longer requires or uses:
   - `adapter.current_min_a`
   - `adapter.current_max_a`
   - `adapter.force_current_a`

2. `EV_CHARGER` uses:
   - `capabilities.min_absorb_w`
   - `capabilities.max_absorb_w`
   - `policy.force_on`
   - `adapter.current_step_a`
   - `adapter.phases`
   - `adapter.voltage_v`

3. EV current bounds are derived from watt capabilities:

   ```text
   min_current_a = ceil_to_step(min_absorb_w / (phases * voltage_v))
   max_current_a = floor_to_step(max_absorb_w / (phases * voltage_v))
   ```

4. EV writer commands charger current by converting `target_w` to `current_a`.

5. `policy.force_on == true` commands EV to `capabilities.max_absorb_w`.

6. `force_on` does not override safety or device availability checks.

7. EV conversion code uses configured `voltage_v`; no EV conversion path hardcodes `230`.

8. Surplus threshold is watt-based and uses capabilities, not adapter ampere fields.

9. Unit tests cover:
   - W/A conversion
   - voltage usage
   - derived min/max current
   - step quantization
   - force_on behavior
   - surplus threshold behavior
   - removal of old fields

10. Config examples and docs are updated.

## Review Checklist

Before merging, inspect for any remaining references to:

```text
current_min_a
current_max_a
force_current_a
EV_PHASE_VOLTAGE_V = 230
```

Allowed exceptions:

- Historical migration comments
- Explicit validation error messages for removed fields
- Tests that assert old fields are rejected

No active runtime logic should depend on these removed fields.

## Suggested Search Commands for Codex

Use repository search for:

```text
current_min_a
current_max_a
force_current_a
EV_PHASE_VOLTAGE_V
ev_current_a_to_power_w
ev_power_w_to_selector_current_a
adjustable_surplus_activation_w
surplus_threshold
force_on
```

## Expected End State

The EV charger configuration should be understandable as:

```text
The user configures EV charging power in watts.
The adapter knows how to translate watts to charger amps.
The charger can be forced on with the same policy as relay.
```

Final mental model:

```text
RELAY:
  target_w -> on/off

EV_CHARGER:
  target_w -> current_a + enabled switch
```

No EMS policy decision should require the user or core logic to reason directly in amps.
