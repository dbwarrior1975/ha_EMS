# Codex Task: Clean Architecture Cleanup After EV/Device Refactors

## Goal

Clean up the remaining refactor/compatibility layers so the repository looks like the current architecture was designed this way from the beginning.

The target architecture is:

```text
Grouped EMS_config.yaml
  -> CoreConfig
  -> device registry / runtime context
  -> device-based net-zero engine
  -> device_policies with target_w
  -> actuator writers
```

The desired business model is:

```text
EV_CHARGER:
  policy/config in watts
  min_absorb_w / max_absorb_w / force_on
  writer converts target_w -> current_a only at actuator boundary

RELAY:
  policy/config in watts
  force_on / surplus_allowed / max_absorb_w
  writer converts target_w -> on/off

Battery:
  policy/config in watts
  writer converts target_w -> charge/discharge command
```

The cleanup goal is **clean slate**, not migration support.

After this cleanup, the code, tests, docs, and examples should not look like they evolved through several legacy formats.

---

## Architectural decision: clean slate, not migration guard

The architecture owner has decided that rejected historical concepts should not remain in active tests, schemas, validation branches, docs, or business logic.

Therefore:

```text
Current architecture tests should assert what is valid now,
not what used to be invalid.
```

Do not keep tests whose only purpose is to remember rejected historical EV amp-policy fields.

Do not keep custom validation branches whose only purpose is to emit special migration errors for historical fields.

The preferred behavior is:

```text
Those fields simply do not exist in the current schema/config model.
```

A generic unknown-field/schema failure is acceptable if a user provides obsolete fields.

---

## Historical EV amp-policy concepts to erase from active code

Remove active references to:

```text
adapter.current_min_a
adapter.current_max_a
adapter.force_current_a
ev_min_current_a
ev_max_current_a
ev_force_current_a
deprecated_current_min_a
deprecated_current_max_a
deprecated_force_current_a
```

These references are allowed only in:

```text
docs/archive/**
progress/history notes clearly marked historical
```

They should not appear in:

```text
active config examples
active user docs
active dev docs
normal schema/config loader code
runtime registry
business logic
writer logic
unit tests
contract tests
e2e tests
custom validation error text
```

---

## Non-goals

Do not change the current EV watt-based business semantics.

Do not change selected surplus threshold semantics.

Do not reintroduce EV amp policy fields.

Do not add `force_target_w`.

Do not remove EV current helpers used by writer/debug/measured-state conversion:

```text
ev_power_w_to_current_a
ev_current_a_to_power_w
ev_min_current_a_from_min_absorb_w
ev_max_current_a_from_max_absorb_w
```

Those helpers are valid because the EVSE actuator is amp-based.

Do not remove useful tests that protect the current architecture.

Do not remove public compatibility helpers if there is evidence they are still required by production scripts. If unsure, stop and ask.

---

## Current suspected cleanup targets

Known or suspected compatibility leftovers:

```text
build_core_config_from_legacy_config(...)
EmsConfig scalar compatibility path
build_ems_config_from_grouped_config(...)
build_ems_config_from_core_config(...)
_read_scalar_config_view(...)
build_runtime_aliases(...)
_device_configs_from_legacy_config(...)
build_device_configs(cfg: Union[EmsConfig, CoreConfig])
legacy relay scalar fallback paths
_device_entity_ref(..., legacy_key)
tests/e2e_entity/e2e_refactoring.md
legacy fallback tests that only protect obsolete scalar sensor paths
custom validation/rejection tests for historical EV amp-policy fields
```

Treat this list as a starting point. Confirm each item by repository search before deleting it.

---

# Phase 1: Inventory and classification

Search the repository for these symbols and concepts:

```text
EmsConfig
build_core_config_from_legacy_config
build_ems_config_from_grouped_config
build_ems_config_from_core_config
_read_scalar_config_view
build_runtime_aliases
_device_configs_from_legacy_config
build_device_configs
_device_entity_ref
legacy_key
relay1_power_kw
relay2_power_kw
relay1_priority
relay2_priority
relay1_surplus_allowed
relay2_surplus_allowed
relay1_force_on
relay2_force_on
charger_control
charger_current
actuator_ev_current_a
legacy scalar
legacy sensor
current_min_a
current_max_a
force_current_a
ev_min_current_a
ev_max_current_a
ev_force_current_a
deprecated_current_min_a
deprecated_current_max_a
deprecated_force_current_a
```

Classify each reference:

```text
A. current architecture and still valid
B. compatibility wrapper not used by production
C. test helper only
D. stale documentation / refactor history
E. rejected historical concept that should be erased
F. required external API / uncertain
```

Remove B, C where tests can be migrated, D from active docs/tests, and E from active code/tests/docs.

For category F, stop and ask before removing.

Deliverable for this phase:

```text
Add a short classification table to the progress markdown.
```

---

# Phase 2: Remove unused legacy CoreConfig builder

Target:

```text
modules/ems_adapter/config_loader.py
build_core_config_from_legacy_config(cfg: EmsConfig) -> CoreConfig
```

Task:

1. Confirm with search that `build_core_config_from_legacy_config` is not used in production.
2. If unused, remove it.
3. Remove imports only needed by that function.
4. Remove tests that exist solely for that function.
5. Rewrite any still-useful tests to use grouped config / CoreConfig directly.
6. Run targeted config tests.

Expected final state:

```text
CoreConfig is built from grouped config only.
No legacy EmsConfig -> CoreConfig bridge remains unless explicitly required.
```

Verification:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
```

---

# Phase 3: Retire EmsConfig as an active business config model

Current desired architecture should not require scalar `EmsConfig` as a live business config.

Task:

1. Search for active `EmsConfig` usage.
2. Separate:
   - tests/helpers that can be migrated to `CoreConfig`
   - production compatibility paths
   - type hints/imports that remain only because of old helpers
3. Migrate tests/helpers to construct `CoreConfig` directly.
4. Remove `build_ems_config_from_grouped_config(...)` if it is only a scalar compatibility view.
5. Remove `build_ems_config_from_core_config(...)` if it is only used by compatibility/tests.
6. Remove `_read_scalar_config_view(...)` if it is no longer needed.
7. Remove `EmsConfig` fields that exist only for old scalar business logic.

Important:

If `EmsConfig` is still used as a public API or external integration contract, do not remove it blindly. Instead:
- mark it as legacy
- isolate it under a clearly named compatibility module
- ensure current production flow does not depend on it

Preferred final state:

```text
CoreConfig is the only active business config model.
EmsConfig either removed or clearly isolated outside active production flow.
```

Verification:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/contract/test_grouped_config_contract.py
```

---

# Phase 4: Remove legacy device read model branch

Target:

```text
modules/ems_adapter/device_read_model.py
build_device_configs(cfg: Union[EmsConfig, CoreConfig])
_device_configs_from_legacy_config(...)
```

Task:

1. Confirm current production passes `CoreConfig`.
2. Remove `EmsConfig` support from `build_device_configs`.
3. Delete `_device_configs_from_legacy_config(...)` if unused.
4. Make `build_device_configs` accept `CoreConfig` only.
5. Update tests to use `CoreConfig`.
6. Remove stale imports/type unions.

Expected final state:

```text
device_read_model builds runtime device configs from CoreConfig only.
No scalar EmsConfig device synthesis remains.
```

Verification:

```bash
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
```

---

# Phase 5: Remove historical EV amp-policy rejection tests and custom validation branches

Targets:

```text
tests that assert adapter.current_min_a is rejected
tests that assert adapter.current_max_a is rejected
tests that assert adapter.force_current_a is rejected
custom validation branches that mention those historical fields
custom error messages that tell users to migrate from those fields
```

Task:

1. Search for all references to:
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
   ```
2. Remove active tests that exist only to assert special rejection of those fields.
3. Remove custom validation logic that exists only to produce special migration errors for those fields.
4. Ensure the current schema/config model simply does not define those fields.
5. If a user provides those fields, generic unknown-field/schema behavior is acceptable.
6. Keep only archived historical references under `docs/archive/**` or progress notes.

Expected final state:

```text
No active code or tests explicitly remember historical EV amp-policy fields.
```

Verification:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
```

---

# Phase 6: Shrink or remove runtime scalar alias layer

Target:

```text
build_runtime_aliases(...)
```

This layer may expose scalar aliases such as:

```text
relay1_power_kw
relay2_power_kw
relay1_priority
relay2_priority
relay1_surplus_allowed
relay2_surplus_allowed
relay1_force_on
relay2_force_on
charger_control
charger_current
actuator_ev_current_a
```

Task:

1. Identify which scalar aliases are still consumed by production.
2. For each production consumer, migrate it to read from the device registry / runtime device structure instead.
3. Remove aliases that are no longer consumed.
4. Keep only aliases that are unavoidable because of Home Assistant/Pyscript external sensor naming.
5. If aliases remain, document them as external IO compatibility, not business model.

Preferred final state:

```text
Policy engine reads device runtime data from device registry, not scalar legacy aliases.
```

Do this in small commits. This phase is more invasive than phases 2-5.

Verification:

```bash
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/e2e_entity/
```

---

# Phase 7: Remove legacy relay scalar fallback paths

Targets may include:

```text
_legacy_relay_scalar_to_w(...)
_relay_devices(cfg) fallback relay1/relay2 scalar config
_relay_runtime_candidates(...) scalar fallback path
relay1_* / relay2_* scalar config fields
```

Task:

1. Confirm grouped relay device config is the only supported production model.
2. Remove fallback logic that synthesizes relay devices from scalar `relay1_*` / `relay2_*` fields.
3. Ensure relay behavior still works through device definitions:
   - `capabilities.max_absorb_w`
   - `policy.force_on`
   - `policy.surplus_allowed`
   - `adapter.switch`
4. Update tests from scalar relay config to grouped relay device config.
5. Keep tests that verify current relay business semantics.

Expected final state:

```text
Relay handling is device-based only.
No relay1/relay2 scalar fallback creates business devices.
```

Verification:

```bash
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/unit/test_writer_semantics.py
```

---

# Phase 8: Remove legacy entity fallback helper usage

Target pattern:

```text
_device_entity_ref(..., legacy_key)
entities.get(legacy_key, '')
```

Task:

1. Identify all use sites.
2. Replace with direct device registry lookup where possible.
3. Remove `legacy_key` argument if no longer needed.
4. If a fallback is needed for external HA entity names, rename the helper to make that explicit, for example:
   - `_external_entity_ref(...)`
   - `_ha_entity_ref(...)`
5. Do not keep a vague `legacy_key` concept in current business logic.

Expected final state:

```text
Entity resolution uses device IDs and adapter fields.
Legacy scalar key fallback is removed or explicitly isolated as external IO compatibility.
```

Verification:

```bash
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/e2e_entity/
```

---

# Phase 9: Archive or remove stale refactor documentation

Target:

```text
tests/e2e_entity/e2e_refactoring.md
```

Task:

1. If this file is a stale migration/refactor plan, move it to:
   ```text
   docs/archive/e2e_refactoring_history.md
   ```
   or remove it.
2. Update references if any.
3. Ensure active docs do not imply old scalar/amp policy config is supported.

Also search active docs for stale terms:

```text
current_min_a
current_max_a
force_current_a
ev_force_current_a
legacy scalar
EmsConfig
```

Expected final state:

```text
Active docs describe only the current grouped/device/watt-based architecture.
Historical notes are clearly archived or removed.
```

---

# Phase 10: Consolidate remaining legacy fallback tests

After production cleanup, revisit tests.

Candidates to consolidate/remove:

```text
writer legacy policy sensor fallback tests
dispatch_state_applier legacy sensor fallback tests
scalar EmsConfig helper tests
legacy relay scalar fallback tests
historical EV amp-policy rejection tests
```

Keep tests that protect current architecture:

```text
valid grouped EV_CHARGER config loads
valid grouped RELAY config loads
runtime registry exposes current device fields
engine emits target_w by device ID
writer consumes device_policies
writer target_w -> EV current_a actuator
relay writer target_w -> on/off
e2e actuator outputs
```

Do not keep tests merely to preserve memory of rejected historical concepts.

Expected outcome:

```text
The test suite should read like it was written for the current architecture.
```

Verification:

```bash
pytest -q
```

---

# Phase 11: Final architecture assertions

Add or update tests that enforce the clean architecture.

Suggested assertions:

1. Grouped config examples contain only current EV fields:

```text
min_absorb_w
max_absorb_w
force_on
current_a
current_step_a
phases
voltage_v
```

2. Device read model accepts `CoreConfig`, not `EmsConfig`.

3. Net-zero engine emits device policy targets by device ID.

4. Writers consume `device_policies`, not legacy scalar command sensors.

5. Relay devices are loaded from grouped device definitions, not `relay1_*` scalar fields.

6. Config loader and schema define only the current supported config fields.

Do not add tests that explicitly mention rejected historical EV amp-policy field names unless they are in archived historical documentation tests.

---

# Final acceptance criteria

This cleanup is complete when:

1. Current production config path is:

```text
grouped YAML -> CoreConfig -> runtime device registry
```

2. `EmsConfig` is removed from active production flow or explicitly isolated outside active business logic.

3. Legacy scalar config builders are removed or archived.

4. Device read model does not synthesize runtime devices from scalar legacy config.

5. Policy engine and engine logic use device IDs / device registry, not scalar relay/EV aliases, except explicit external IO compatibility.

6. EV remains watt-policy-native:

```text
min_absorb_w
max_absorb_w
force_on
target_w
```

7. Historical EV amp-policy fields are absent from active code, tests, config examples, validation branches, and docs.

8. W/A conversion remains only in writer/helper/debug/measured-state contexts.

9. Relay handling is device-based.

10. Active docs and examples describe only the current architecture.

11. Full test suite passes.

---

# Verification commands

Run targeted tests after each phase, then full suite.

Minimum final verification:

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

---

# Progress note required

Create or update a progress markdown section:

```text
Architecture Cleanup: Clean slate device/CoreConfig model
```

For each phase, record:

```text
status
files changed
functions removed
tests updated
tests removed
tests renamed
tests run
remaining compatibility references
reason each remaining compatibility reference is allowed
```

Do not claim completion if any active business path still depends on scalar legacy config.

Do not claim completion if active tests or validation branches still explicitly preserve rejected historical EV amp-policy fields.
