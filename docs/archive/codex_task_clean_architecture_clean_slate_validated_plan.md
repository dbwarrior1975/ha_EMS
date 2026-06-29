# Clean Architecture Clean Slate - Validated Execution Plan

Date: 2026-06-29

Source document: `codex_task_clean_architecture_clean_slate.md`

This document validates the cleanup proposal against the current repository
state and turns it into a phased implementation plan for a later session.

## Validation Summary

The cleanup is feasible, but not as one blind removal pass.

Current production already enters through grouped config and returns
`CoreConfig` from `read_config()`, but several compatibility layers are still
active:

1. `EmsConfig` still exists as a scalar compatibility model.
2. `ems_policy_engine.py` still exposes `_read_scalar_config_view()`.
3. `config_loader.py` still converts both directions between `CoreConfig` and
   `EmsConfig`.
4. `device_read_model.py` still accepts `Union[EmsConfig, CoreConfig]`.
5. Runtime alias tests still require scalar keys such as `relay1_power_kw`,
   `charger_current`, and `actuator_ev_current_a`.
6. `ems_policy_engine.py` still has scalar fallback reads for relay policy
   flags and device entity refs.
7. Historical EV amp-policy rejection logic still exists in active config
   validation.

The safe order is:

1. Remove explicit historical EV amp-policy rejection memory.
2. Remove `EmsConfig -> CoreConfig` and `CoreConfig -> EmsConfig` bridge code
   from active production.
3. Make device read model `CoreConfig` only.
4. Replace policy-engine scalar fallback reads with device-runtime reads.
5. Shrink runtime aliases and their tests.
6. Update active docs/examples/tests so they describe only the current model.

## Current Classification Snapshot

| Reference | Current location | Classification | Action |
| --- | --- | --- | --- |
| `EmsConfig` dataclass | `modules/ems_core/domain/models.py` | compatibility model | Isolate or remove after consumers are migrated |
| `build_ems_config_from_grouped_config` | `modules/ems_adapter/config_loader.py`, tests | scalar compatibility view | Remove after parity tests are rewritten |
| `build_ems_config_from_core_config` | `modules/ems_adapter/config_loader.py`, `ems_policy_engine.py` | scalar compatibility view | Remove after `_read_scalar_config_view` is removed |
| `build_core_config_from_legacy_config` | `modules/ems_adapter/config_loader.py` | legacy bridge | Search-confirm, then remove |
| `_read_scalar_config_view` | `ems_policy_engine.py`, contract tests | compatibility test hook | Remove or move to archived compatibility helper |
| `build_runtime_aliases` / `runtime_alias_index` | `modules/ems_adapter/config_loader.py`, contract tests | external IO compatibility plus scalar legacy | Shrink in phases; do not remove all aliases at once |
| `_device_configs_from_legacy_config` | `modules/ems_adapter/device_read_model.py` | legacy synthesis | Remove after tests stop passing `EmsConfig` |
| `build_device_configs(Union[EmsConfig, CoreConfig])` | `modules/ems_adapter/device_read_model.py` | mixed active/legacy API | Make `CoreConfig` only |
| `_device_entity_ref(..., legacy_key)` | `ems_policy_engine.py` | scalar fallback | Replace with device runtime lookup |
| `relay1_*` / `relay2_*` scalar config fields | `CoreConfig` derived fields, tests, docs | compatibility aliases | Remove only after engine/test helpers use device registry directly |
| `charger_control` / `charger_current` | config examples, runtime aliases, writer fallback | external HA entity names and legacy scalar keys | Keep HA entity IDs; remove scalar runtime-key dependency where possible |
| `actuator_ev_current_a` | writer/tests/runtime registry | current actuator boundary | Keep; this is valid EVSE amp actuator IO |
| `current_min_a` / `current_max_a` / `force_current_a` | validation branch and rejection tests | rejected historical config | Remove from active code/tests |
| `ev_min_current_a` / `ev_max_current_a` / `deprecated_*` | runtime absence tests | historical memory test | Remove explicit absence tests after registry contract is rewritten |
| `ev_min_current_a_from_min_absorb_w` / `ev_max_current_a_from_max_absorb_w` | EV W/A helper code | valid actuator/debug helper | Keep |

## Feasibility Verdict

The source plan is implementable with these constraints:

1. Do not remove `actuator_ev_current_a`, `charger_control`, or
   `charger_current` merely because they contain current/charger wording.
   They are current Home Assistant actuator/entity names.
2. Do not remove EV current conversion helper functions. They are required at
   the EVSE actuator/debug boundary.
3. Do not remove `build_runtime_aliases` in the first pass. It also powers
   runtime entity registry construction and test harness behavior.
4. Do not remove `EmsConfig` until these consumers are migrated:
   `tests/helpers.py`, `modules/ems_core/guard/evaluator.py` type hints,
   `modules/ems_adapter/device_read_model.py`, config-loader parity tests, and
   `_read_scalar_config_view`.
5. Do not remove scalar relay fields from `CoreConfig` before
   `compute_net_zero_engine_outputs(...)` callers and tests stop passing
   `relay1_*` / `relay2_*` arguments.

## Phase 0: Baseline

Run before editing:

```bash
git status --short
rg -n "\bEmsConfig\b|build_core_config_from_legacy_config|build_ems_config_from_grouped_config|build_ems_config_from_core_config|_read_scalar_config_view|build_runtime_aliases|_device_configs_from_legacy_config|build_device_configs|_device_entity_ref|legacy_key" modules tests ems_policy_engine.py ems_actuator_writers.py docs README.md
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" modules tests ems_policy_engine.py ems_actuator_writers.py EMS_config.yaml example_EMS_config.yaml docs README.md
pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py tests/unit/test_device_read_model.py tests/contract/test_grouped_config_contract.py tests/contract/test_grouped_config_runtime_parity.py tests/contract/test_runtime_entity_registry_contract.py
```

Record baseline failures, if any, before cleanup.

## Phase 1: Remove Historical EV Amp-Policy Memory

Goal: active schema/tests stop explicitly remembering rejected fields.

Targets:

1. `tests/unit/test_config_loader.py::test_validate_rejects_deprecated_ev_adapter_fields`
2. `modules/ems_adapter/config_loader.py::_validate_deprecated_ev_adapter_fields`
3. call to `_validate_deprecated_ev_adapter_fields(...)`
4. `tests/contract/test_runtime_entity_registry_contract.py::test_runtime_registry_does_not_expose_removed_ev_amp_keys`

Implementation:

1. Delete the explicit deprecated-field validation helper and its call.
2. Delete the rejection test that asserts custom messages for
   `current_min_a`, `current_max_a`, and `force_current_a`.
3. Replace runtime registry absence assertions with current-positive registry
   assertions, for example valid watt fields and actuator fields.
4. Keep `test_validate_rejects_ev_limits_that_cannot_be_represented_by_current_step`;
   that protects current W/A actuator compatibility.

Verification:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" modules tests EMS_config.yaml example_EMS_config.yaml docs README.md
```

Allowed active hits after this phase:

1. `ev_min_current_a_from_min_absorb_w`
2. `ev_max_current_a_from_max_absorb_w`
3. `ev_derived_min_current_a`
4. `ev_derived_max_current_a`

Archive docs may still contain historical hits.

## Phase 2: Remove Scalar Config View From Policy Engine

Goal: policy runtime exposes only `CoreConfig`.

Targets:

1. `ems_policy_engine.py::_read_scalar_config_view`
2. import `build_ems_config_from_core_config`
3. contract tests that call `harness.policy_mod['_read_scalar_config_view']()`

Implementation:

1. Remove `_read_scalar_config_view()` from `ems_policy_engine.py`.
2. Remove `build_ems_config_from_core_config` import from `ems_policy_engine.py`.
3. Rewrite `tests/contract/test_grouped_config_runtime_parity.py` assertions to
   compare returned `CoreConfig` and runtime device registry directly.
4. Do not preserve a new scalar test hook.

Verification:

```bash
pytest -q tests/contract/test_grouped_config_runtime_parity.py
rg -n "_read_scalar_config_view|build_ems_config_from_core_config" ems_policy_engine.py tests modules
```

Expected remaining `build_ems_config_from_core_config` hits, if any, should be
inside config-loader compatibility tests only. Remove those in Phase 3.

## Phase 3: Remove EmsConfig Bridge Builders From Config Loader

Goal: grouped YAML builds `CoreConfig` only.

Targets:

1. `build_ems_config_from_grouped_config(...)`
2. `build_ems_config_from_grouped_reader(...)`
3. `build_ems_config_from_core_config(...)`
4. `build_core_config_from_legacy_config(...)`
5. `EmsConfig` import in `modules/ems_adapter/config_loader.py`
6. tests that validate scalar view parity

Implementation:

1. Search-confirm no production caller remains after Phase 2.
2. Remove the bridge builders.
3. Remove config-loader tests whose only purpose is scalar-view parity.
4. Rewrite useful tests to assert `CoreConfig` fields from
   `build_core_config_from_grouped_config(...)`.
5. Keep `build_core_config_from_grouped_config(...)` and
   `build_core_config_from_grouped_reader(...)`.

Verification:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
rg -n "build_ems_config_from_grouped_config|build_ems_config_from_grouped_reader|build_ems_config_from_core_config|build_core_config_from_legacy_config" modules tests ems_policy_engine.py
```

## Phase 4: Make Device Read Model CoreConfig-Only

Goal: no runtime device synthesis from scalar `EmsConfig`.

Targets:

1. `modules/ems_adapter/device_read_model.py`
2. `_device_configs_from_legacy_config(...)`
3. `build_device_configs(cfg: Union[EmsConfig, CoreConfig])`
4. `build_device_states(cfg: Union[EmsConfig, CoreConfig], ...)`
5. `build_devices(cfg: Union[EmsConfig, CoreConfig], ...)`
6. `tests/helpers.py::make_cfg`

Implementation:

1. Update tests/helpers so `make_cfg(...)` returns a `CoreConfig` or introduce
   a new `make_core_cfg(...)` and migrate tests in small groups.
2. Remove `_device_configs_from_legacy_config`.
3. Change public signatures to accept `CoreConfig`.
4. Remove `_is_core_config` branching once all callers are CoreConfig.
5. Remove `EmsConfig` import from `device_read_model.py`.

Verification:

```bash
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
rg -n "_device_configs_from_legacy_config|Union\\[EmsConfig, CoreConfig\\]|\\bEmsConfig\\b" modules/ems_adapter/device_read_model.py tests/helpers.py
```

## Phase 5: Retire EmsConfig Dataclass Or Isolate It

Goal: `EmsConfig` is absent from active business flow.

Current active references include:

1. `modules/ems_core/domain/models.py`
2. `tests/helpers.py`
3. `modules/ems_core/guard/evaluator.py` type hint
4. any tests still constructing `EmsConfig`

Implementation:

1. Change `evaluate_guard(..., cfg: EmsConfig)` type hint to a structural
   config type or `CoreConfig`; it currently reads only guard threshold fields
   that `CoreConfig` already exposes as derived fields.
2. Migrate tests from `EmsConfig()` to grouped/CoreConfig helpers.
3. If no active references remain, remove `EmsConfig` from
   `modules/ems_core/domain/models.py`.
4. If an external compatibility need is discovered, move `EmsConfig` to a
   clearly named compatibility module and document why it remains.

Stop condition:

If a production script outside tests imports `EmsConfig` as an external API,
stop and ask before deleting it.

Verification:

```bash
pytest -q tests/unit/test_evaluator.py tests/unit/test_engine.py tests/unit/test_load_projection.py
rg -n "\\bEmsConfig\\b" modules tests ems_policy_engine.py ems_actuator_writers.py
```

## Phase 6: Remove Policy Engine Scalar Fallback Reads

Goal: policy loop reads device runtime entries, not scalar aliases.

Targets:

1. `_device_entity_ref(..., legacy_key)`
2. `entities.get('relay1_surplus_allowed', '')`
3. `entities.get('relay2_surplus_allowed', '')`
4. `entities.get('relay1_force_on', '')`
5. `entities.get('relay2_force_on', '')`
6. `get_attr(..., 'prev_relay1_force_on', ...)`
7. `get_attr(..., 'prev_relay2_force_on', ...)`

Implementation:

1. Replace `_device_entity_ref` with direct runtime device entity lookup.
2. If a fallback is still needed for HA external naming, rename it to make the
   boundary explicit, for example `_ha_entity_ref`.
3. Make relay surplus/force values come from `m.relay_states`.
4. Keep `prev_force_on_device_ids` as the canonical previous-force state.
5. Remove old `prev_relay*_force_on` trace fallback after e2e tests seed
   canonical previous state.

Verification:

```bash
pytest -q tests/unit/test_engine.py
pytest -q tests/e2e_entity/net_zero_force_on_battery_support
pytest -q tests/e2e_entity/
rg -n "_device_entity_ref|legacy_key|relay1_surplus_allowed|relay2_surplus_allowed|relay1_force_on|relay2_force_on|prev_relay1_force_on|prev_relay2_force_on" ems_policy_engine.py tests/e2e_entity
```

Expected remaining hits may exist in scenario YAML/entity IDs until Phase 7.

## Phase 7: Shrink Runtime Alias Layer

Goal: runtime aliases represent external IO only, not the business model.

Targets:

1. `build_runtime_aliases(...)`
2. `runtime_alias_index(...)`
3. `tests/contract/test_grouped_config_contract.py`
4. `tests/contract/test_runtime_entity_registry_contract.py`
5. `tests/e2e_entity/scenario_harness.py`

Implementation:

1. Split aliases into two categories:
   - required external IO aliases
   - obsolete scalar business aliases
2. Keep required external IO aliases such as actuator entity IDs.
3. Remove business aliases once no production/test code consumes them:
   `relay1_power_kw`, `relay2_power_kw`, `relay1_priority`,
   `relay2_priority`, `ev_priority`, scalar policy flags.
4. Update scenario harness to use device registry paths instead of scalar
   alias keys.

Verification:

```bash
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/e2e_entity/
rg -n "relay1_power_kw|relay2_power_kw|relay1_priority|relay2_priority|ev_priority|relay1_surplus_allowed|relay2_surplus_allowed|relay1_force_on|relay2_force_on" modules tests ems_policy_engine.py
```

## Phase 8: Remove Relay Scalar Derived Fields

Goal: relay handling is device-registry based.

Targets:

1. `CoreConfig.relay1_power_kw`
2. `CoreConfig.relay2_power_kw`
3. `CoreConfig.relay1_priority`
4. `CoreConfig.relay2_priority`
5. `CoreConfig.relay1`
6. `CoreConfig.relay2`
7. engine fallback helpers that synthesize relay behavior from scalar fields

Implementation:

1. Update engine helpers to use `cfg.devices_by_kind('RELAY')` and explicit
   device IDs.
2. Update tests to assert relay devices by ID and capability fields.
3. Remove derived relay scalar fields only after all direct users are gone.

Verification:

```bash
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/e2e_entity/
rg -n "relay1_power_kw|relay2_power_kw|relay1_priority|relay2_priority|cfg\\.relay1|cfg\\.relay2" modules tests
```

## Phase 9: Active Docs And Examples Cleanup

Goal: active docs read like the current architecture was designed this way.

Targets:

1. `README.md`
2. `docs/dev/**`
3. `docs/user/**`
4. `tests/e2e_entity/e2e_refactoring.md`
5. `EMS_config.yaml`
6. `example_EMS_config.yaml`

Implementation:

1. Remove references that describe scalar legacy layers as active design.
2. Keep references to actual HA entity IDs such as `switch.charger_control`
   and `number.charger_current_level`.
3. Replace `relay1_*` / `relay2_*` examples with device-registry wording where
   the text discusses architecture, not HA entity IDs.
4. Archive historical notes under `docs/archive/**`.

Verification:

```bash
rg -n "legacy scalar|EmsConfig|current_min_a|current_max_a|force_current_a|ev_force_current_a" README.md docs/dev docs/user tests/e2e_entity
pytest -q tests/smoke/test_release_example_config_loads.py
```

## Phase 10: Final Architecture Assertions

Goal: tests enforce the clean slate architecture.

Add or update tests for:

1. grouped config builds `CoreConfig`;
2. device read model accepts `CoreConfig` only;
3. runtime registry exposes device registry and actuator IO, not scalar
   business aliases;
4. engine emits `device_policies` with `target_w` by device ID;
5. writer consumes `device_policies`;
6. EV W/A conversion remains at writer/helper/debug boundary only.

Final verification:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
pytest -q
```

Final audit:

```bash
rg -n "\\bEmsConfig\\b|build_core_config_from_legacy_config|build_ems_config_from_grouped_config|build_ems_config_from_core_config|_read_scalar_config_view|_device_configs_from_legacy_config|_device_entity_ref|legacy_key" modules tests ems_policy_engine.py ems_actuator_writers.py README.md docs/dev docs/user
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" modules tests ems_policy_engine.py ems_actuator_writers.py EMS_config.yaml example_EMS_config.yaml README.md docs/dev docs/user
rg -n "relay1_power_kw|relay2_power_kw|relay1_priority|relay2_priority|relay1_surplus_allowed|relay2_surplus_allowed|relay1_force_on|relay2_force_on" modules tests ems_policy_engine.py README.md docs/dev docs/user
```

Allowed final active hits should be explicitly documented. Likely allowed:

1. `actuator_ev_current_a` as the EVSE selector actuator.
2. `charger_control` and `charger_current` as actual Home Assistant entity IDs
   if those are still the deployed entity names.
3. EV current conversion helper function names.
4. Archive docs under `docs/archive/**`.

## Progress Section Template

Use this in the implementation session:

```text
## Architecture Cleanup: Clean Slate Device/CoreConfig Model

### Phase N
Status:
Files changed:
Functions removed:
Tests updated:
Tests removed:
Tests renamed:
Tests run:
Remaining compatibility references:
Reason each remaining reference is allowed:
```

Do not claim completion while active production paths still depend on scalar
legacy config, or while active tests/custom validation branches explicitly
preserve rejected historical EV amp-policy field names.
