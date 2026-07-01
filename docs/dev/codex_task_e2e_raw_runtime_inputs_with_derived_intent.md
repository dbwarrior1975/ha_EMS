# Codex task: move E2E NET_ZERO fixtures to raw runtime inputs with derived intent assertions

## Purpose

The previous NET_ZERO refactor moved `rpnz_w` and `required_power_consumption_kw` out of the EMS runtime contract. EMS production now derives those values internally from raw runtime measurements:

```yaml
runtime:
  grid_power_w: sensor.average_active_power_2
  quarter_energy_balance_kwh: sensor.hourly_energy_balance
  pv_power_w: sensor.pv_instant_power_w
```

The current E2E compatibility shim preserves old scenario expectations by treating legacy `rpnz_w`, `required_power_consumption_kw`, and `pv_power_kw` as test-only intent values. This was a good regression-preservation step, but it still means some E2E scenarios do not fully exercise the same raw-input -> `derive_net_zero_inputs()` -> policy path as production.

This task defines the best long-term compromise:

1. E2E scenarios must ultimately feed EMS the same raw runtime inputs as production.
2. Scenario readability should be preserved by documenting or asserting the derived RPNZ/RPC meaning of those raw inputs.
3. Legacy RPNZ/RPC shims should be used only as migration aids, not as the final E2E execution model.

## Target E2E model

Each E2E step should eventually use raw EMS runtime inputs:

```yaml
E:
  grid_power_w: 1200
  quarter_energy_balance_kwh: -0.001917
  pv_power_w: 2500
```

Then the step should include a machine-checkable derived-intent assertion:

```yaml
expect_derived:
  rpnz_w: 10
  required_power_consumption_kw: -0.4
  remaining_quarter_s: 690
  remaining_template_minutes: 12
```

Policy and actuator expectations remain normal:

```yaml
expect_device_policies:
  HOME_BATTERY:
    target_w: -1800
  EV_CHARGER:
    enabled: false
    mode: hard_off
```

This makes the scenario both:

- production-realistic: EMS receives only raw runtime inputs;
- human-readable: the test still states the RPNZ/RPC business situation that the step is about.

## Do not use comments only

Comments such as:

```yaml
# means rpnz_w ~= 10 and RPC ~= -0.4
```

are useful, but not sufficient. They can become stale.

Prefer a real assertion block:

```yaml
expect_derived:
  rpnz_w: 10
  required_power_consumption_kw: -0.4
```

The E2E harness must verify that the raw inputs and `at_s` actually produce those derived values through the production `derive_net_zero_inputs()` function.

## Final rule for E2E inputs

A step may use either raw inputs:

```yaml
E:
  grid_power_w: ...
  quarter_energy_balance_kwh: ...
  pv_power_w: ...
```

or a temporary migration-only intent form:

```yaml
net_zero_intent:
  rpnz_w: ...
  required_power_consumption_kw: ...
  pv_power_w: ...
```

but the final persisted scenario form should be raw input + `expect_derived`.

Do not keep steps that mix inconsistent raw and derived truth sources.

Invalid final form:

```yaml
E:
  rpnz_w: -100
  required_power_consumption_kw: -0.4
  grid_power_w: 1200
  quarter_energy_balance_kwh: 0.001
```

This is invalid because `rpnz_w`, `required_power_consumption_kw`, `grid_power_w`, and `quarter_energy_balance_kwh` are not independent in the new model.

## Transition strategy

### Phase 1: keep the current legacy shim temporarily

Keep the existing test-only legacy compatibility shim for now. It is useful because it preserves old business expectations and prevents accidental expected-value churn.

However, rename or document it clearly as:

```text
legacy_net_zero_intent
```

or equivalent. It must not look like a production runtime input path.

### Phase 2: add raw-input E2E mode

Add or formalize a mode where each step feeds:

```yaml
E:
  grid_power_w: ...
  quarter_energy_balance_kwh: ...
  pv_power_w: ...
```

and uses production `derive_net_zero_inputs()`.

Add `expect_derived` checks for:

```yaml
expect_derived:
  rpnz_w: ...
  required_power_w: ...
  required_power_consumption_kw: ...
  remaining_quarter_s: ...
  remaining_template_minutes: ...
```

Use tolerances where needed:

```yaml
expect_derived:
  rpnz_w:
    value: 10
    tolerance: 2
  required_power_consumption_kw:
    value: -0.4
    tolerance: 0.01
```

A compact scalar form is also acceptable when exact values are stable.

### Phase 3: build a migration helper

Create helper functions that convert legacy test intent into raw inputs.

Suggested helpers:

```python
def balance_for_rpnz_w(*, rpnz_w: float, remaining_s: float) -> float:
    return -(rpnz_w / 1000.0) * remaining_s / 3600.0
```

and a helper that solves `grid_power_w` from desired required-power intent:

```python
def grid_power_for_required_power_kw(
    *,
    required_power_consumption_kw: float,
    quarter_energy_balance_kwh: float,
    remaining_template_minutes: int,
) -> float:
    ...
```

The migration helper should produce:

```yaml
E:
  grid_power_w: <computed>
  quarter_energy_balance_kwh: <computed>
  pv_power_w: <computed>

expect_derived:
  rpnz_w: <legacy intent>
  required_power_consumption_kw: <legacy intent>
```

This helper may be used to generate or update fixtures, but the final E2E runtime path should still call the production `derive_net_zero_inputs()`.

### Phase 4: migrate critical scenarios first

Do not migrate all E2E scenarios in one blind sweep.

Start with the highest-value scenarios:

1. EV hardoff / restore_min scenarios.
2. HOME_BATTERY primary + EV surplus threshold scenarios.
3. Active surplus release around RPNZ practical-zero.
4. Quarter-boundary scenarios.
5. Battery import/export correction scenarios.

For each migrated step:

1. Provide raw `grid_power_w`, `quarter_energy_balance_kwh`, and `pv_power_w`.
2. Add `expect_derived`.
3. Keep the existing policy/actuator expected values unless a reviewer explicitly approves a business-semantics change.

### Phase 5: remove monkey-patching

When migrated scenarios cover the important paths, remove the E2E monkey-patch that overrides:

```python
derive_net_zero_inputs
```

The final E2E suite should exercise the production function.

It is acceptable to keep helper functions that calculate fixture values before the scenario runs. It is not acceptable long-term to patch the production derived-input function during the policy loop.

## Consistency rules

If a step provides both raw inputs and derived intent, verify consistency.

Example:

```yaml
E:
  grid_power_w: 1200
  quarter_energy_balance_kwh: -0.001917
  pv_power_w: 2500

expect_derived:
  rpnz_w: 10
  required_power_consumption_kw: -0.4
```

The harness should compute derived values from raw inputs and `at_s`, then compare them to `expect_derived`.

If they do not match, fail with a fixture error, not a policy failure:

```text
Invalid E2E fixture: raw runtime inputs do not produce the expected NET_ZERO derived intent.
```

If a step provides legacy intent and raw inputs at the same time, they must be mathematically consistent within tolerance. Otherwise, fail early.

## Desired E2E debug separation

The final model should make failures easier to classify:

1. `expect_derived` fails:
   - raw fixture is wrong;
   - time/quarter assumptions changed;
   - derived NET_ZERO formula changed.

2. `expect_derived` passes but policy expectation fails:
   - policy behavior changed.

3. Policy expectation passes but writer/dispatch expectation fails:
   - downstream canonical output or actuator writer behavior changed.

This is the main reason to keep `expect_derived` as a real assertion instead of a comment.

## Production equivalence requirement

E2E should eventually use the same raw inputs as production:

```yaml
grid_power_w
quarter_energy_balance_kwh
pv_power_w
```

and the same derived function:

```python
derive_net_zero_inputs(...)
```

No E2E-only monkey patch should remain in the final steady state.

Allowed test-only utilities:

- fixture generation helpers;
- `expect_derived` assertion helpers;
- tolerance helpers;
- deterministic time helpers.

Not allowed in the final steady state:

- patching `derive_net_zero_inputs()` during policy execution;
- treating `rpnz_w` or `required_power_consumption_kw` as EMS runtime entity inputs;
- silently accepting inconsistent legacy intent + raw input combinations.

## PV unit requirement

The final raw input key is:

```yaml
pv_power_w
```

Therefore the E2E input value must be watts, not kilowatts.

Legacy migration may convert:

```yaml
pv_power_kw: 2.5
```

to:

```yaml
pv_power_w: 2500
```

but final E2E fixtures should use `pv_power_w` directly.

Production config must likewise point `pv_power_w` at a sensor whose state is in watts.

## Suggested acceptance checks

### Tests

Run:

```bash
pytest -q
```

Add targeted tests for:

```text
expect_derived passes when raw inputs produce the declared RPNZ/RPC values
expect_derived fails clearly when raw inputs are inconsistent
legacy intent helper converts rpnz_w + required_power_consumption_kw into raw inputs
pv_power_kw legacy value converts to pv_power_w during migration only
raw-input E2E scenario uses production derive_net_zero_inputs()
```

### Grep checks

Final steady-state grep should show no active E2E runtime use of legacy keys:

```bash
rg "E\['rpnz_w'\]|E\['required_power_consumption_kw'\]|E\['required_power_w'\]|E\['pv_power_kw'\]" tests/e2e_entity tests/helpers.py
```

Allowed during migration:

```text
legacy intent conversion helper
migration tests
explicit rejection/consistency tests
```

Not allowed in final steady state:

```text
legacy RPNZ/RPC keys used as direct policy-loop inputs
derive_net_zero_inputs monkey patch in normal E2E execution
```

### Source checks

Ensure E2E tests can prove production path:

```bash
rg "derive_net_zero_inputs" tests/e2e_entity tests/helpers.py
```

Allowed:

```text
calling the production function for expect_derived
fixture generation helpers
unit tests
```

Not allowed in final steady state:

```text
self.policy_mod['derive_net_zero_inputs'] = ...
monkeypatch.setattr(..., 'derive_net_zero_inputs', ...)
```

## Recommended Codex instruction

Do not change policy, actuator, or device expected values merely to make E2E tests green.

If expected values change, classify and document the reason:

```text
A) old fixture was mathematically inconsistent and the new raw-input fixture preserves the intended business situation;
B) the business behavior intentionally changed;
C) test expectation was wrong;
D) production bug found.
```

Default to preserving existing business expected values and migrating the fixture data around them.

## Final target

The final E2E style should look like this:

```yaml
- at_s: 210
  E:
    grid_power_w: 1200
    quarter_energy_balance_kwh: -0.001917
    pv_power_w: 2500

  expect_derived:
    rpnz_w:
      value: 10
      tolerance: 2
    required_power_consumption_kw:
      value: -0.4
      tolerance: 0.01
    remaining_quarter_s: 690
    remaining_template_minutes: 12

  expect_device_policies:
    HOME_BATTERY:
      target_w: -1800
    EV_CHARGER:
      enabled: false
      mode: hard_off
```

This keeps E2E scenarios production-realistic while preserving the RPNZ/RPC intent that existing business expectations were built on.
