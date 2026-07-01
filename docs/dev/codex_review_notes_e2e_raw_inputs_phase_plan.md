# Codex review notes: E2E NET_ZERO raw runtime inputs + expect_derived phase plan

## Review decision

The phase plan is approved as the implementation baseline.

The plan is correctly scoped and cautious:

- production already reads raw runtime inputs: `grid_power_w`, `quarter_energy_balance_kwh`, and `pv_power_w`;
- production already calls `derive_net_zero_inputs()`;
- the current E2E harness still contains a legacy compatibility layer for `rpnz_w`, `required_power_consumption_kw`, and `pv_power_kw`;
- the right long-term direction is to migrate E2E scenarios toward raw runtime inputs plus explicit `expect_derived` assertions.

The plan should be implemented with the clarifications below.

## Main recommendation

Do not attempt a mass migration of all E2E scenarios in one pass.

Use the existing legacy shim only as a migration aid. Add `expect_derived`, migrate critical scenarios first, then gradually remove the monkey-patch and legacy intent path.

The final E2E goal remains:

```python
{
    'at_s': 210,
    'set': {
        E['grid_power_w']: 1200.0,
        E['quarter_energy_balance_kwh']: -0.001917,
        E['pv_power_w']: 2500.0,
    },
    'expect_derived': {
        'rpnz_w': {'value': 10, 'tolerance': 2},
        'required_power_consumption_kw': {'value': -0.4, 'tolerance': 0.01},
        'remaining_quarter_s': 690,
        'remaining_template_minutes': 12,
    },
    'expect_device_policies': {
        'HOME_BATTERY': {
            'target_w': -1800,
        },
        'EV_CHARGER': {
            'enabled': False,
            'mode': 'hard_off',
        },
    },
}
```

This makes E2E scenarios production-realistic while preserving the RPNZ/RPC business intent that existing expected values were built on.

## Required clarification 1: prefer one `net_zero_intent` block over many long legacy aliases

The plan currently suggests adding explicit aliases such as:

```text
legacy_net_zero_intent_rpnz_w
legacy_net_zero_intent_required_power_consumption_kw
legacy_net_zero_intent_required_power_w
legacy_net_zero_intent_pv_power_kw
```

This is acceptable for a very short transition, but do not let it become the preferred pattern.

Prefer a single migration-only block for any remaining derived intent:

```python
'net_zero_intent': {
    'rpnz_w': 500,
    'required_power_consumption_kw': 2.6,
    'pv_power_kw': 8.0,
}
```

Rules:

1. `net_zero_intent` is test-only migration syntax.
2. It must not look like production runtime input.
3. New or migrated scenarios should prefer raw runtime inputs plus `expect_derived`.
4. If long legacy aliases are introduced, document them as temporary and track their removal.

## Required clarification 2: `expect_derived` must read effective harness state after `h.step()`

`expect_derived` must validate the actual raw inputs that the policy loop sees.

Do not compute `expect_derived` only from values explicitly present in the current step dict, because some values may be inherited from earlier steps.

Correct behavior:

```text
1. Apply step['set'] to the harness.
2. Resolve effective current raw state from the harness:
   - grid_power_w
   - quarter_energy_balance_kwh
   - pv_power_w
   - current deterministic time / at_s
3. Compute derived values using production derive_net_zero_inputs().
4. Compare to expect_derived.
5. Fail as fixture error if the raw inputs do not produce the declared intent.
```

Suggested implementation note:

```python
def _effective_runtime_value(h, entity_key: str) -> float:
    entity_id = h.ent[entity_key]
    return h.get_float(entity_id)
```

or equivalent, as long as it reads the effective harness state after the step has been applied.

Failure should be a fixture error, not a policy regression:

```text
Invalid E2E fixture: raw runtime inputs do not produce expected NET_ZERO derived intent.
```

Include:

- step index;
- optional step note;
- field name;
- actual value;
- expected value;
- tolerance.

## Required clarification 3: pilot raw-input step must prove monkey-patch is inactive

The plan allows raw-mode steps and legacy steps to coexist during migration. That is good.

However, the first raw-input pilot must prove that it really uses production `derive_net_zero_inputs()`.

Add an assertion or test-only flag such as:

```python
assert h._legacy_derived_override_active is False
```

for raw-mode steps.

Suggested rule:

```text
If a step uses raw runtime inputs and no legacy/net_zero_intent values,
the E2E harness must not monkey-patch derive_net_zero_inputs().
```

This prevents a false migration where a scenario looks raw-input-based but still runs the legacy derived override.

Final steady state must not contain:

```python
self.policy_mod['derive_net_zero_inputs'] = self._derive_net_zero_inputs_for_test
```

except possibly in temporary migration tests explicitly named as such.

## Required clarification 4: define default tolerances

`expect_derived` supports scalar and dict forms. Define clear comparison behavior.

Recommended defaults:

```text
rpnz_w:
  exact or ±1 W

required_power_w:
  exact or ±1 W

required_power_consumption_kw:
  exact if generated by helper, otherwise ±0.001 kW or explicit tolerance

remaining_quarter_s:
  exact

remaining_quarter_min:
  exact

pv_power_kw:
  exact or ±0.001 kW if included
```

Implementation options:

1. Use exact comparison for scalar values.
2. Require dict form whenever tolerance is needed:

```python
'expect_derived': {
    'required_power_consumption_kw': {'value': -3.4, 'tolerance': 0.01},
}
```

Do not use hidden large tolerances. The point of `expect_derived` is to catch fixture drift.

## Required clarification 5: migration helper must handle `export_balance_stop_kwh` as a hard edge

The helper that converts legacy intent into raw inputs must account for the production rule:

```python
if quarter_energy_balance_kwh >= 0.130:
    required_power_w = 0
```

If a helper is asked to create raw inputs for a nonzero required-power intent while the derived balance would trigger this stop rule, fail explicitly.

Example fixture construction error:

```text
Cannot construct raw NET_ZERO inputs:
requested required_power_consumption_kw != 0, but quarter_energy_balance_kwh >= export_balance_stop_kwh would force required_power_w = 0 in production.
```

Do not silently generate raw inputs that production will clamp to a different required-power value.

## Required clarification 6: track legacy usage count through migration

The migration plan should include a visible metric after each phase.

Suggested command:

```bash
rg "E\['(rpnz_w|required_power_consumption_kw|required_power_w|pv_power_kw)'\]" tests/e2e_entity | wc -l
```

Also track possible monkey-patch references:

```bash
rg "derive_net_zero_inputs.*_for_test|policy_mod\['derive_net_zero_inputs'\]|monkeypatch.*derive_net_zero_inputs" tests/e2e_entity tests/helpers.py
```

Report counts in the session/PR summary:

```text
Legacy NET_ZERO E2E direct-key count before: N
Legacy NET_ZERO E2E direct-key count after:  M
Raw-input + expect_derived pilot scenarios added: K
```

This prevents the migration shim from becoming permanent by accident.

## Additional implementation guidance

### Keep policy expected values stable by default

When migrating a step:

1. Convert fixture inputs.
2. Add `expect_derived`.
3. Keep `expect_device_policies`, `expect_policy`, `expect_values`, writer expectations, and dispatch expectations unchanged.
4. Run the story.
5. If any policy/writer/dispatch expectation changes, stop and classify the reason.

Classification required for any expected-value change:

```text
A) old fixture was mathematically inconsistent and the new raw fixture preserves intended business situation;
B) business behavior intentionally changed;
C) old test expectation was wrong;
D) production bug found.
```

Default assumption: preserve existing business expected values.

### Use production helper functions for time

Migration helpers and `expect_derived` checks should use the same production functions as EMS:

```python
seconds_until_next_quarter(...)
remaining_template_minutes(...)
derive_net_zero_inputs(...)
```

Do not reimplement quarter math in the E2E runner unless the test is explicitly testing helper equivalence.

### PV unit rule

Final raw input uses watts:

```python
E['pv_power_w']: 2500.0
```

Legacy migration may accept:

```python
E['pv_power_kw']: 2.5
```

or:

```python
'net_zero_intent': {
    'pv_power_kw': 2.5,
}
```

but it must convert to:

```python
E['pv_power_w']: 2500.0
```

Final migrated scenarios should not use `pv_power_kw`.

## Recommended pilot

Start with a small pilot from:

```text
tests/e2e_entity/net_zero_ev_adjustable_load/test_02_release_and_hard_off_hold.py
```

Pilot steps:

1. Implement `expect_derived`.
2. Add the raw input fixture helper.
3. Migrate one step only.
4. Assert raw-mode does not use the legacy monkey-patch.
5. Run:

```bash
./run_pytest.sh tests/unit/test_net_zero_derived_inputs.py
./run_pytest.sh tests/e2e_entity/net_zero_ev_adjustable_load/test_02_release_and_hard_off_hold.py
```

If the pilot passes without expected-value changes, continue the same story.

## Acceptance criteria for this follow-up

### Functional

```text
- E2E runner supports expect_derived.
- expect_derived uses effective harness state after the step is applied.
- expect_derived calls production derive_net_zero_inputs().
- Raw-input steps can run without monkey-patching derive_net_zero_inputs().
- Legacy steps can still run during migration.
- At least one critical E2E step is migrated to raw inputs + expect_derived.
```

### Safety

```text
- No broad expected-value rewrites.
- Any changed expected value is explicitly classified.
- Legacy RPNZ/RPC direct keys are counted and reported.
- `pv_power_kw` is not introduced as final raw input.
```

### Tests

Run at minimum:

```bash
./run_pytest.sh tests/unit/test_net_zero_derived_inputs.py
./run_pytest.sh tests/contract/test_grouped_config_runtime_parity.py
./run_pytest.sh tests/e2e_entity/net_zero_ev_adjustable_load
./run_pytest.sh tests/e2e_entity/net_zero_priority_order_quarter
```

Before calling the migration phase complete, run:

```bash
./run_pytest.sh tests/e2e_entity
pytest -q
```

## Final target

The final steady-state E2E suite should:

```text
- feed production-equivalent raw runtime inputs;
- use production derive_net_zero_inputs();
- keep RPNZ/RPC business intent visible through expect_derived;
- avoid direct legacy runtime keys;
- avoid derive_net_zero_inputs monkey-patching in normal E2E execution.
```

The current phase plan is approved with these clarifications.
