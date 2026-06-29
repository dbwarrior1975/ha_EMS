# EV_CHARGER Deprecated Amp Config Cleanup Plan

## Goal

Remove deprecated EV amp policy fields from user-facing YAML and active implementation:

- `adapter.current_min_a`
- `adapter.current_max_a`
- `adapter.force_current_a`
- `ev_min_current_a`
- `ev_max_current_a`
- `ev_force_current_a`

After cleanup, EV policy/config must be watt-native:

- `capabilities.min_absorb_w`
- `capabilities.max_absorb_w`
- `policy.force_on`
- `adapter.current_a`
- `adapter.current_step_a`
- `adapter.phases`
- `adapter.voltage_v`

If EV current limits are needed internally for writer/debug behavior, derive them from watt limits, phases, voltage, and current step. Do not treat derived current values as user-configurable policy.

## Current Findings

The repo is clean in Git, but deprecated amp fields still exist in active paths:

- `EMS_config.yaml` and `example_EMS_config.yaml` still expose `adapter.current_min_a`, `adapter.current_max_a`, and `adapter.force_current_a`.
- `tests/e2e_entity/**/EMS_config.yaml` fixtures still expose those adapter fields.
- `modules/ems_core/domain/models.py` still defines `CoreEvAdapterConfig.current_min_a/current_max_a/force_current_a`.
- `modules/ems_core/domain/models.py` still defines `CoreConfig.ev_min_current_a/ev_max_current_a/ev_force_current_a`.
- `modules/ems_adapter/config_loader.py` still aliases and resolves the deprecated fields.
- `modules/ems_adapter/runtime_context.py` still exposes `ev_min_current_a`, `ev_max_current_a`, and `ev_force_current_a` as live runtime fields.
- `modules/ems_core/net_zero/engine.py` still copies deprecated fields into selected EV runtime config.
- `modules/ems_core/domain/ev_power.py` has derived-current helpers. These are acceptable only as watt-derived adapter helpers, not user config fields.

## Implementation Progress

### Phase 1 Status: Completed

Search run:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" EMS_config.yaml example_EMS_config.yaml modules tests docs README.md
```

Classification summary:

- `remove`: `EMS_config.yaml`, `example_EMS_config.yaml`, `docs/user/config_examples.md`, `README.md`, `docs/user/operointi.md`, `docs/user/EMS_parametrointi_guide.md`, `docs/dev/arkkitehtuuri.md`, `modules/ems_core/domain/models.py`, `modules/ems_adapter/config_loader.py`, `modules/ems_adapter/runtime_context.py`, `modules/ems_core/net_zero/engine.py`, grouped-config fixtures under `tests/e2e_entity/**/EMS_config.yaml`, and active tests/runtime parity fixtures that still assume live deprecated fields.
- `allow-derived`: watt-to-current helper names in `modules/ems_core/domain/ev_power.py` and derived debug fields such as `ev_derived_min_current_a`, `ev_derived_max_current_a`, and `ev_derived_step_w`.
- `allow-rejection-test`: new or updated tests that explicitly assert `adapter.current_min_a`, `adapter.current_max_a`, and `adapter.force_current_a` are rejected by grouped-config validation.
- `allow-validation-message`: fail-fast validation text in `modules/ems_adapter/config_loader.py`.
- `allow-archive`: `docs/archive/**` and this task/progress document.

Active implementation files to edit:

- `modules/ems_core/domain/models.py`
- `modules/ems_adapter/config_loader.py`
- `modules/ems_adapter/runtime_context.py`
- `modules/ems_core/net_zero/engine.py`
- supporting active tests that still use deprecated live/runtime fields

### Phase 2-8 Status: Completed

Completed implementation work:

- Removed deprecated EV amp adapter fields from `EMS_config.yaml`, `example_EMS_config.yaml`, `docs/user/config_examples.md`, and grouped-config e2e fixtures under `tests/e2e_entity/**/EMS_config.yaml`.
- Removed deprecated amp fields from active dataclasses and grouped-config build paths in `modules/ems_core/domain/models.py` and `modules/ems_adapter/config_loader.py`.
- Added fail-fast grouped-config validation for deprecated `adapter.current_min_a`, `adapter.current_max_a`, and `adapter.force_current_a`.
- Removed deprecated runtime alias keys and deprecated runtime registry echo fields from `modules/ems_adapter/runtime_context.py`.
- Removed deprecated selected-EV scalar copies from `modules/ems_core/net_zero/engine.py`; active EV decisions now stay watt-native.
- Updated unit, contract, smoke, and e2e-support tests to use watt-native EV config and to assert deprecated field rejection.
- Updated active docs in `README.md`, `docs/user/**`, and `docs/dev/arkkitehtuuri.md` to describe watt-native EV behavior.

### Phase 9 Status: Completed

Final search run:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" EMS_config.yaml example_EMS_config.yaml modules tests docs README.md
```

Allowed remaining references after cleanup:

- `modules/ems_core/domain/ev_power.py`
  - `allow-derived`: watt-to-current helper function names used for writer/debug derivation.
- `modules/ems_adapter/runtime_context.py`
  - `allow-derived`: derived debug calculations for `ev_derived_min_current_a` and `ev_derived_max_current_a`.
- `modules/ems_adapter/config_loader.py`
  - `allow-validation-message`: deprecated-field rejection text.
  - `allow-derived`: numeric validation helpers that verify watt/current-step compatibility.
- `tests/unit/test_config_loader.py`
  - `allow-rejection-test`: explicit validation-rejection coverage for deprecated adapter fields.
- `tests/contract/test_runtime_entity_registry_contract.py`
  - `allow-rejection-test`: explicit contract assertions that removed runtime keys are absent.
- `docs/archive/**`
  - `allow-archive`: historical notes and prior task/progress documents.

Verification summary:

- Required targeted tests passed.
- Full suite result: `264 passed, 1 xfailed`.
- The single expected xfail is `tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/test_01_internal_plan_homebattery_primary_ev_adjustable.py`, which is already marked as future EMS-internal HAEO combo semantics work.

## Non-Goals

- Do not add `force_target_w`.
- Do not reintroduce amp-based policy semantics under another name.
- Do not change unrelated relay behavior.
- Do not change selected EV surplus threshold semantics unless an existing or updated test proves the change is required.
- Do not treat `docs/archive/**` as active user-facing docs.

## Phase 1: Search And Classify

Run:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" EMS_config.yaml example_EMS_config.yaml modules tests docs README.md
```

Classify each remaining reference:

- `remove`: active implementation, user-facing config, active docs, normal tests/fixtures.
- `allow-derived`: helper names or debug output that clearly derive current from watt configuration.
- `allow-rejection-test`: tests that verify deprecated fields fail validation.
- `allow-validation-message`: explicit fail-fast error text.
- `allow-archive`: `docs/archive/**` or old task/progress docs.

Acceptance for this phase:

- A short list exists of active implementation files to edit.
- Any intentionally allowed references are documented before implementation starts.

## Phase 2: Remove User-Facing YAML Fields

Remove these fields from:

- `EMS_config.yaml`
- `example_EMS_config.yaml`
- `tests/e2e_entity/**/EMS_config.yaml`
- `docs/user/config_examples.md`

Fields to remove:

```yaml
current_min_a: ...
current_max_a: ...
force_current_a: ...
```

Keep these fields:

```yaml
capabilities:
  min_absorb_w: ...
  max_absorb_w: ...
policy:
  force_on: ...
adapter:
  current_a: ...
  current_step_a: ...
  phases: ...
  voltage_v: ...
```

Acceptance for this phase:

```bash
rg -n "current_min_a|current_max_a|force_current_a" EMS_config.yaml example_EMS_config.yaml tests/e2e_entity docs/user/config_examples.md
```

The command should return no active config/example references except tests that intentionally assert validation rejection.

## Phase 3: Remove Deprecated Fields From Config Models

Edit `modules/ems_core/domain/models.py`:

- Remove `CoreEvAdapterConfig.current_min_a`.
- Remove `CoreEvAdapterConfig.current_max_a`.
- Remove `CoreEvAdapterConfig.force_current_a`.
- Remove `CoreConfig.ev_min_current_a`.
- Remove `CoreConfig.ev_max_current_a`.
- Remove `CoreConfig.ev_force_current_a`.
- Remove compatibility derivation that populates those fields in `__post_init__`.
- Keep or introduce derived-only names only if needed, for example `ev_derived_min_current_a` and `ev_derived_max_current_a`.

Important:

- Active config objects must not expose user-configurable amp policy fields.
- Derived current values must come from `min_absorb_w`, `max_absorb_w`, `current_step_a`, `phases`, and `voltage_v`.

Acceptance for this phase:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a" modules/ems_core/domain/models.py
```

Only derived helper references or validation/rejection text may remain. Prefer no deprecated field references in `models.py`.

## Phase 4: Remove Config Loader Aliases And Parsing

Edit `modules/ems_adapter/config_loader.py`:

- Remove aliases:
  - `ev_min_current_a -> ems.devices.<ev>.adapter.current_min_a`
  - `ev_max_current_a -> ems.devices.<ev>.adapter.current_max_a`
  - `ev_force_current_a -> ems.devices.<ev>.adapter.force_current_a`
- Remove compatibility fill logic for `core_config.ev_min_current_a`, `core_config.ev_max_current_a`, and `core_config.ev_force_current_a`.
- Remove deprecated fields from `CoreEvAdapterConfig(...)` construction.
- Add fail-fast validation when grouped EV config contains any deprecated adapter field.

Suggested error messages:

```text
EV_CHARGER adapter.current_min_a is no longer supported. Use capabilities.min_absorb_w.
EV_CHARGER adapter.current_max_a is no longer supported. Use capabilities.max_absorb_w.
EV_CHARGER adapter.force_current_a is no longer supported. Use policy.force_on. When force_on is true, EV charges at capabilities.max_absorb_w.
```

Acceptance for this phase:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a" modules/ems_adapter/config_loader.py
```

Remaining references should be only validation rejection text and rejection checks.

## Phase 5: Remove Runtime Registry Live Fields

Edit `modules/ems_adapter/runtime_context.py`:

- Remove live entity keys:
  - `ev_min_current_a`
  - `ev_max_current_a`
  - `ev_force_current_a`
- Remove deprecated adapter echo fields:
  - `deprecated_current_min_a`
  - `deprecated_current_max_a`
  - `deprecated_force_current_a`

Keep derived debug fields if useful:

- `ev_derived_min_current_a`
- `ev_derived_max_current_a`
- `ev_derived_step_w`

Acceptance for this phase:

```bash
rg -n "ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" modules/ems_adapter/runtime_context.py tests/contract/test_runtime_entity_registry_contract.py
```

The runtime registry must not expose the removed live fields.

## Phase 6: Update Net Zero EV Selected Config

Edit `modules/ems_core/net_zero/engine.py`:

- Remove selected EV copies of `ev_min_current_a`, `ev_max_current_a`, and `ev_force_current_a`.
- If selected config needs EV current bounds, derive them from:
  - `capabilities.min_absorb_w`
  - `capabilities.max_absorb_w`
  - `adapter.current_step_a`
  - `adapter.phases`
  - `adapter.voltage_v`
- Make sure `policy.force_on == true` means EV target intent is `capabilities.max_absorb_w`.

Acceptance for this phase:

```bash
rg -n "ev_min_current_a|ev_max_current_a|ev_force_current_a|force_current_a|current_min_a|current_max_a" modules/ems_core/net_zero
```

No active policy use should remain.

## Phase 7: Update Tests

Update or add tests for:

- Grouped EV config without deprecated amp fields loads successfully.
- Grouped EV config with `adapter.current_min_a` fails validation.
- Grouped EV config with `adapter.current_max_a` fails validation.
- Grouped EV config with `adapter.force_current_a` fails validation.
- Runtime entity registry no longer exposes `ev_min_current_a`, `ev_max_current_a`, or `ev_force_current_a`.
- Runtime/debug may expose derived fields such as `ev_derived_min_current_a`, `ev_derived_max_current_a`, and `ev_derived_step_w`.
- EV `force_on` still results in max watt target behavior.
- Writer still converts target watts to supported `current_a`.

Likely files:

- `tests/unit/test_config_loader.py`
- `tests/unit/test_core_config.py`
- `tests/unit/test_engine.py`
- `tests/unit/test_load_projection.py`
- `tests/unit/test_writer_semantics.py`
- `tests/contract/test_grouped_config_contract.py`
- `tests/contract/test_runtime_entity_registry_contract.py`
- `tests/contract/test_grouped_config_runtime_parity.py`
- `tests/e2e_entity/scenario_harness.py`
- `tests/e2e_entity/**/scenario_steps.py`

## Phase 8: Update Active Docs

Update active docs:

- `README.md`
- `docs/user/operointi.md`
- `docs/user/EMS_parametrointi_guide.md`
- `docs/user/config_examples.md`
- `docs/dev/arkkitehtuuri.md`

Document final EV model:

- EV min/max are configured in watts.
- The current selector is an adapter detail.
- EMS derives supported current from watts using phases, voltage, and `current_step_a`.
- `force_on` commands `capabilities.max_absorb_w`.

Acceptance for this phase:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a" README.md docs/user docs/dev
```

Only intentional historical or migration-warning references should remain. `docs/archive/**` is excluded from this acceptance check.

## Phase 9: Final Search Acceptance

Run:

```bash
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" EMS_config.yaml example_EMS_config.yaml modules tests docs README.md
```

Allowed remaining references:

- Derived helper names in `modules/ems_core/domain/ev_power.py`, if still named that way.
- Tests that assert deprecated fields are rejected.
- Validation error text.
- `docs/archive/**`.
- Historical task/progress docs, if any remain.

All remaining references must be listed in the implementation progress note with the reason they are allowed.

## Verification Commands

Run at minimum:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_haeo_net_zero_plan.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/smoke/test_release_example_config_loads.py
```

If time allows:

```bash
pytest -q tests/e2e_entity/
pytest -q
```

## Completion Criteria

The cleanup is complete when:

- User-facing EV config no longer contains `adapter.current_min_a`, `adapter.current_max_a`, or `adapter.force_current_a`.
- Normal EV adapter schema no longer exposes those fields.
- Config loader does not create live aliases for `ev_min_current_a`, `ev_max_current_a`, or `ev_force_current_a`.
- Runtime registry does not expose those as live normal fields.
- Active net zero/runtime logic does not depend on amp policy fields.
- EV force behavior uses only `policy.force_on`.
- Old YAML fields fail validation with clear messages.
- Tests pass.
