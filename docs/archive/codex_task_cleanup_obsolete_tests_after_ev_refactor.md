# Codex Task: Clean Up Tests Made Obsolete by Recent EV Refactors

## Goal

Clean up tests that became obsolete after the EV_CHARGER watt-based refactor and legacy amp-policy removal.

Do **not** remove tests that still protect the new architecture:

```text
EV policy = watts
EV writer = W -> A actuator conversion
EV current values = allowed only in writer/helper/debug/measured-state contexts
```

Optimize for removing obsolete legacy coverage while keeping useful regression protection.

---

## Phase 1: Search and classify legacy test coverage

Search the test tree for:

```text
current_min_a
current_max_a
force_current_a
ev_min_current_a
ev_max_current_a
ev_force_current_a
deprecated_current_min_a
deprecated_current_max_a
deprecated_force_current_a
compute_surplus_dispatch
SurplusTargetConfig
device_target_to_legacy_target
device_dispatch_to_legacy_dispatch
legacy_policy
legacy sensor
ev_strategy_current_a
actuator_ev_current_a
target_current_a
```

Classify each hit as:

```text
A. keep: protects current architecture
B. remove: only tests obsolete legacy API
C. consolidate: duplicate transitional regression coverage
D. rename: valid test, but old name implies wrong semantics
```

Do not remove tests merely because they mention `current_a`. EV current is still valid in writer, actuator, measured-state, and EV power helper tests.

---

## Phase 2: Remove legacy surplus allocator tests if production API is unused

Inspect:

```text
tests/unit/test_surplus_allocator.py
```

This file likely tests the old API:

```text
SurplusTargetConfig
active_stack()
next_target()
release_target()
compute_surplus_dispatch()
```

The current canonical path should be device-id based:

```text
SurplusDeviceTarget
compute_surplus_device_dispatch()
device_id
threshold_w
```

If the old API is unused in production code, remove:

```text
tests/unit/test_surplus_allocator.py
```

Then remove the unused production functions if safe:

```text
active_stack
next_target
release_target
compute_surplus_dispatch
SurplusTargetConfig
```

If the old API is still used in production, do not remove these tests. Add a progress note explaining why they remain.

Expected reduction:

```text
about 8 tests
```

---

## Phase 3: Remove legacy device mapping tests if mappers are unused

Inspect:

```text
tests/unit/test_surplus_device_targets.py
```

Likely obsolete tests:

```text
test_device_target_export_mapping_preserves_threshold_and_state
test_device_dispatch_export_mapping_maps_device_id_to_decision_name
```

They test legacy mapper helpers such as:

```text
device_target_to_legacy_target(...)
device_targets_to_legacy_targets(...)
device_dispatch_to_legacy_dispatch(...)
```

If these mapper helpers are unused in production, remove those two tests and the unused mapper helpers.

Keep tests that validate current watt-based surplus target construction.

---

## Phase 4: Consolidate writer legacy fallback tests

Inspect:

```text
tests/unit/test_writer_semantics.py
```

Look for multiple tests that verify the same old migration behavior:

```text
writer does not use legacy policy sensors
writer skips or ignores stale legacy command/current sensors
device_policy wins over legacy policy sensor values
```

Keep at most one or two high-value contract tests, for example:

```text
writer skips command without device_policy
writer uses device_policy even when stale legacy sensor values conflict
```

Consider removing or consolidating overlapping tests such as:

```text
test_writer_relay_without_device_policy_does_not_use_legacy_command
test_writer_ev_without_device_policy_does_not_use_legacy_current_even_without_device_id
test_writer_battery_does_not_fallback_to_legacy_policy_target_without_device_policy
test_writer_ev_does_not_fallback_to_legacy_current_without_device_policy
test_writer_relay_device_policy_overrides_legacy_command
test_writer_relay_does_not_fallback_to_legacy_command_with_device_id
test_writer_loop_uses_device_policies_when_legacy_policy_sensors_conflict
```

Do not remove writer tests that assert current valid behavior:

```text
target_w -> supported current_a
zero target disables charger and restores derived minimum current
hard_off restores derived minimum selector current
force_on/max_absorb_w maps to expected selector current
```

Expected reduction:

```text
about 4-5 tests
```

---

## Phase 5: Consolidate dispatch state legacy sensor tests

Inspect:

```text
tests/unit/test_dispatch_state_applier.py
```

Candidate tests:

```text
test_dispatch_state_applier_uses_device_trace_when_legacy_sensor_conflicts
test_dispatch_state_applier_ignores_legacy_sensor_without_device_trace
```

Keep the strongest contract test that proves canonical device trace wins over legacy sensor state.

Consider removing or merging the weaker duplicate test if it only exists for transitional legacy coverage.

Expected reduction:

```text
about 1 test
```

---

## Phase 6: Remove dead EV current seed values from tests

Inspect:

```text
tests/contract/test_grouped_config_runtime_parity.py
```

Look for stale seed values like:

```python
'input_number.ems_ev_garage_min_current_a': 6,
'input_number.ems_ev_garage_max_current_a': 16,
```

If these entities are no longer referenced by config or runtime logic, remove the seed values.

Do not remove the test itself if it still validates grouped EV boundary/selection behavior.

---

## Phase 7: Rename valid tests with misleading old names

Inspect:

```text
tests/unit/test_engine.py
```

Candidate rename:

```text
test_engine_primary_ev_current_uses_configurable_step_size
```

Suggested new name:

```text
test_engine_primary_ev_target_w_uses_derived_power_step
```

The test is likely still useful, but the old name implies that core policy uses current directly. The new architecture should express this as target watts using a derived power step.

Do not remove this test unless it no longer validates meaningful behavior.

---

## Phase 8: Keep these tests

Do **not** remove these categories.

### Deprecated config rejection

Keep tests asserting old fields are rejected:

```text
adapter.current_min_a
adapter.current_max_a
adapter.force_current_a
```

These prevent accidental reintroduction.

### Runtime registry absence

Keep tests asserting these are not exposed:

```text
ev_min_current_a
ev_max_current_a
ev_force_current_a
deprecated_current_min_a
deprecated_current_max_a
deprecated_force_current_a
```

### EV power conversion helpers

Keep:

```text
tests/unit/test_ev_power.py
```

These protect writer/helper W/A conversion and derived current bounds.

### E2E actuator current assertions

Do not remove e2e assertions such as:

```text
actuator_ev_current_a
target_current_a
```

Those are valid because the Home Assistant charger selector is still amp-based.

---

## Phase 9: Documentation / non-test cleanup

Inspect:

```text
tests/e2e_entity/e2e_refactoring.md
```

If it is now only a stale migration plan, either:

```text
move it to docs/archive/
```

or shorten it to a historical note.

Do not let stale refactor planning docs imply that old EV amp-policy config is still supported.

---

## Verification commands

After each removal/consolidation step, run targeted tests.

Minimum:

```bash
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_dispatch_state_applier.py
pytest -q tests/unit/test_engine.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/unit/test_config_loader.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/unit/test_ev_power.py
```

Then run:

```bash
pytest -q
```

---

## Acceptance criteria

The cleanup is complete when:

1. Obsolete legacy surplus allocator tests are removed or explicitly justified as still needed.
2. Unused legacy device mapping tests/helpers are removed or explicitly justified as still needed.
3. Duplicate writer legacy fallback tests are consolidated while preserving one clear contract test.
4. Duplicate dispatch legacy sensor tests are consolidated if safe.
5. Dead EV current seed values are removed.
6. Misleading current-policy test names are renamed to target-watt semantics.
7. Tests that protect current architecture remain.
8. Full test suite passes.
9. Progress markdown is updated with:
   - tests removed
   - tests consolidated
   - tests renamed
   - production helper functions removed, if any
   - remaining legacy references and why they are allowed

---

## Expected outcome

Likely reduction:

```text
10-16 tests
```

Do not optimize for the largest possible reduction. Optimize for removing obsolete legacy coverage while keeping regression protection for the new EV watt-based architecture.
