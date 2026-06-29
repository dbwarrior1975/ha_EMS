# Codex Task: Selected EV Scalar Cleanup - Session 2 Plan

## Context

This is the continuation plan for:

```text
codex_task_final_clean_slate_selected_ev_scalar_cleanup.md
```

The goal is still a clean-slate current architecture:

```text
Grouped EMS_config.yaml
  -> CoreConfig
  -> runtime device registry
  -> device-native measurements
  -> device-based net-zero engine
  -> device_policies[device_id].target_w
  -> actuator writers
```

Current business behavior is assumed correct. This task is about removing the
remaining selected-EV scalar compatibility shape from active code/tests/docs.

## Current Snapshot

Important current findings:

1. `modules/ems_core/net_zero/engine.py` still defines and uses
   `_cfg_with_selected_ev_scalars(cfg, device_id)`.
2. `compute_net_zero_engine_outputs(...)` currently builds:

   ```python
   selected_ev_cfg = _cfg_with_selected_ev_scalars(cfg, selected_ev_device_id)
   ```

   and then passes that scalar-shaped object through EV policy, primary-EV
   stepping, battery authority, and trace output.
3. `modules/ems_core/net_zero/load_projection.py::ev_strategy_target_w(...)`
   reads EV data from scalar-looking `cfg.ev_force_on` and `ev_max_power_w(cfg)`.
4. `tests/helpers.py::make_m(...)` still accepts scalar shorthand parameters:

   ```text
   charger_on
   charger_current_a
   relay1_on
   relay2_on
   ```

   and expands them into `ev_states` / `relay_states`.
5. Active docs and tests still contain legacy/migration vocabulary. Some is
   valid when describing removed surfaces or external compatibility, but it must
   be reviewed and justified.

Do not touch unrelated worktree changes. At the time this plan was created,
`git status --short` showed unrelated zip file changes and a
`codex_task_final_clean_slate_selected_ev_scalar_cleanup.md:Zone.Identifier`
sidecar.

## Non-Goals

Do not change EV watt-based business semantics.

Do not change selected surplus threshold semantics.

Do not change relay/battery behavior.

Do not remove writer/debug/measured-state EV current helpers:

```text
ev_power_w_to_current_a
ev_current_a_to_power_w
ev_min_current_a_from_min_absorb_w
ev_max_current_a_from_max_absorb_w
```

Do not remove e2e actuator current assertions. EV current remains valid at the
actuator/writer/debug boundary.

Do not reintroduce removed EV amp-policy fields:

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

## Phase 1: Baseline Inventory

Run these searches before editing:

```bash
rg -n "_cfg_with_selected_ev_scalars|ev_strategy_target_w|_ev_policy_mode_and_target_w|_primary_ev_step_target_w|_primary_power_envelope_w|selected_ev_cfg" modules/ems_core/net_zero tests/unit/test_engine.py tests/unit/test_load_projection.py tests/helpers.py
rg -n "def make_m|charger_on|charger_current_a|relay1_on|relay2_on" tests/helpers.py tests/unit tests/contract tests/e2e_entity
rg -n "legacy|compat|scalar|EmsConfig|refactor|migration|policy_ev_current_a|policy_relay1_command|policy_relay2_command|policy_battery_target_w" README.md docs/dev docs/user tests modules ems_policy_engine.py ems_actuator_writers.py
```

Classify each finding as:

```text
A. current device-native architecture
B. selected-EV scalar mirror to remove
C. test helper shorthand to rewrite
D. active docs/test naming that remembers migration history
E. archived history allowed
F. external IO/debug compatibility that must remain justified
```

Record the classification in a progress section at the end of this file.

## Phase 2: Introduce Device-Native EV Runtime View

Create a small internal representation for the selected EV in
`modules/ems_core/net_zero/engine.py`. Keep it private and local to the engine
unless a better existing domain model already fits.

Suggested shape:

```python
def _selected_ev_context(cfg, device_id):
    return SimpleNamespace(
        device_id=device_id,
        device=device,
        adapter=device.adapter,
        capabilities=device.capabilities,
        policy=device.policy,
        current_step_a=...,
        phases=...,
        voltage_v=...,
        min_absorb_w=...,
        max_absorb_w=...,
        power_step_w=...,
        force_on=...,
        hard_off_pv_threshold_kw=...,
        hard_off_low_pv_cycles=...,
        hard_off_release_cycles=...,
        priority=...,
    )
```

Rules:

1. This context may normalize entity-ref strings and numeric values.
2. It must not copy selected EV data into top-level `cfg.ev_*` names.
3. If no EV exists, return an explicit empty/disabled context instead of a
   scalar-shaped fake config.
4. Preserve current behavior for grouped-config entity refs: a non-empty entity
   string such as `input_boolean.ems_ev_force_on` must not become truthy merely
   because it is a string.

Acceptance:

```bash
rg -n "selected\\.ev_|selected_ev_cfg\\.ev_" modules/ems_core/net_zero/engine.py
```

should be empty or limited to code being actively removed in this phase.

## Phase 3: Refactor EV Power Helpers at Call Sites

Replace call-site dependence on scalar-shaped selected EV config in:

```text
modules/ems_core/net_zero/engine.py::_ev_policy_mode_and_target_w
modules/ems_core/net_zero/engine.py::_primary_ev_step_target_w
modules/ems_core/net_zero/engine.py::_primary_power_envelope_w
modules/ems_core/net_zero/load_projection.py::ev_strategy_target_w
```

Preferred direction:

```python
ev_strategy_target_w(
    profiles,
    ev_context=selected_ev,
    haeo=normalized_haeo,
    burn_active=ev_burn_for_cycle,
)
```

or explicit parameters if that is clearer:

```python
ev_strategy_target_w(
    profiles,
    force_on=selected_ev.force_on,
    max_absorb_w=selected_ev.max_absorb_w,
    haeo=normalized_haeo,
    burn_active=ev_burn_for_cycle,
)
```

Preserve these semantics exactly:

```text
DEGRADED -> EV target 0 W
MANUAL/MANUAL_SAFE + force_on -> max_absorb_w
MANUAL/MANUAL_SAFE without force_on -> 0 W
NET_ZERO + force_on -> max_absorb_w
NET_ZERO + burn_active -> max_absorb_w
MAX_EXPORT without force_on -> 0 W
CHEAP_GRID_CHARGE default -> max_absorb_w
CHEAP_GRID_CHARGE + HAEO ev_target_kw -> watt target
primary EV stepping uses current_step_a * phases * voltage_v as watt step
restore_min uses min_absorb_w
hard_off uses 0 W
```

Use EV W/A conversion helpers only to derive device watt resolution from EV
adapter properties or measured runtime current.

Targeted tests after this phase:

```bash
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_engine.py
```

## Phase 4: Remove `_cfg_with_selected_ev_scalars`

Once all call sites use the device-native context, delete:

```text
modules/ems_core/net_zero/engine.py::_cfg_with_selected_ev_scalars
```

Also remove `from types import SimpleNamespace` if it is no longer needed. If a
new context still uses `SimpleNamespace`, keep the import but ensure the new
object does not expose selected-device values under top-level `ev_*` scalar
mirror names.

Acceptance:

```bash
rg -n "_cfg_with_selected_ev_scalars" modules tests README.md docs/dev docs/user
```

Expected result: no active code/test/doc hits.

## Phase 5: Rewrite Measurement Test Helpers

In `tests/helpers.py`, remove `make_m(...)` parameters:

```text
charger_on
charger_current_a
relay1_on
relay2_on
```

Add explicit current-architecture helper constructors if useful:

```python
def ev_state(*, enabled=False, active=None, current_a=0):
    ...

def relay_state(*, active=False, surplus_allowed=None, force_on=None):
    ...
```

Rewrite current callers to pass device-native state:

```python
make_m(
    ev_states={
        "EV_CHARGER": ev_state(enabled=True, active=True, current_a=10),
    },
    relay_states={
        "RELAY1": relay_state(active=True),
        "RELAY2": relay_state(active=False),
    },
)
```

Known current callers include:

```text
tests/unit/test_device_read_model.py
tests/unit/test_engine.py
```

Do not rename e2e test files merely because names contain realistic device IDs
or behavior such as `relay1_on_then_release_under_force`; only remove helper API
shorthand that implies scalar measurement construction.

Targeted tests after this phase:

```bash
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
```

Acceptance:

```bash
rg -n "def make_m|charger_on|charger_current_a|relay1_on|relay2_on" tests/helpers.py tests/unit tests/contract tests/e2e_entity
```

Allowed remaining hits only if they are not helper parameters and are explicitly
justified, for example user-facing wording that means actual charger enabled
state.

## Phase 6: Review CoreConfig Top-Level EV Fields

Inspect:

```text
modules/ems_core/domain/models.py
tests/helpers.py::make_cfg
modules/ems_adapter/config_loader.py
modules/ems_adapter/device_read_model.py
tests/contract/test_grouped_config_contract.py
tests/contract/test_grouped_config_runtime_parity.py
```

Current likely compatibility fields:

```text
CoreConfig.ev_charger_phases
CoreConfig.ev_voltage_v
CoreConfig.ev_force_on
CoreConfig.ev_current_step_a
```

Classify each as:

```text
A. true global setting
B. selected-device mirror to remove
C. derived debug convenience
D. external IO/runtime compatibility
```

Do not remove category D blindly. If loader/adapter compatibility still requires
a field, document why and ensure the net-zero engine no longer depends on it for
selected EV decisions.

Acceptance for this phase is architectural, not necessarily total field removal:

```text
engine/load_projection do not require selected EV top-level scalar mirrors
device-specific config lives under devices[device_id]
remaining top-level EV fields are justified compatibility/debug surfaces
```

## Phase 7: Active Docs and Test Vocabulary Cleanup

Search:

```bash
rg -n "legacy|compat|scalar|EmsConfig|refactor|migration|policy_ev_current_a|policy_relay1_command|policy_relay2_command|policy_battery_target_w" README.md docs/dev docs/user tests modules ems_policy_engine.py ems_actuator_writers.py
```

Handle active findings:

1. If historical, move the content to `docs/archive/`.
2. If current architecture, rewrite using current terms:

   ```text
   device registry
   device_policies
   target_w
   runtime device state
   policy_decision_trace
   actuator_writer_trace
   external/debug compatibility
   ```

3. If a compatibility reference must remain, name the boundary explicitly:

   ```text
   Home Assistant entity compatibility
   deprecated debug surface
   external IO adapter fallback
   ```

Do not erase valid user-facing documentation for existing Home Assistant helper
entity IDs such as:

```text
input_select.ems_adjustable_surplus_load
input_select.ems_adjustable_primary_load
input_number.ems_ev_current_step_a
input_number.ems_ev_charger_phases
input_number.ems_ev_voltage_v
```

Those are external configuration entities, not necessarily internal scalar
architecture.

## Phase 8: Final Verification

Run targeted tests first, then broader tests:

```bash
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_ev_power.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/unit/test_dispatch_state_applier.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
pytest -q
```

If a listed test file does not exist, skip it and record that explicitly.

Final acceptance searches:

```bash
rg -n "_cfg_with_selected_ev_scalars" modules tests README.md docs/dev docs/user
rg -n "policy_ev_current_a|policy_relay1_command|policy_relay2_command|policy_battery_target_w|legacy_relay_flags" modules tests README.md docs/dev docs/user
rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" modules tests EMS_config.yaml example_EMS_config.yaml README.md docs/dev docs/user
rg -n "charger_on|charger_current_a|relay1_on|relay2_on" tests/helpers.py tests/unit tests/contract tests/e2e_entity
```

Expected:

1. `_cfg_with_selected_ev_scalars` absent from active code/tests/docs.
2. Removed EV amp-policy field names absent from active code/tests/docs.
3. Policy scalar compatibility names absent unless archived or explicitly
   justified as external/debug compatibility.
4. `make_m(...)` no longer accepts scalar shorthand parameters.

## Progress Log

Update this section while working.

### Phase 1: Baseline Inventory

Status: completed

Files changed: none

Findings:

```text
A. Current device-native architecture:
- modules/ems_core/net_zero/engine.py role/device selection helpers
- tests using ev_states / relay_states maps directly

B. Selected-EV scalar mirror to remove:
- modules/ems_core/net_zero/engine.py::_cfg_with_selected_ev_scalars
- engine call sites passing selected_ev_cfg through EV policy / primary EV / trace
- modules/ems_core/net_zero/load_projection.py::ev_strategy_target_w(cfg, ...)

C. Test helper shorthand to rewrite:
- tests/helpers.py::make_m(charger_on, charger_current_a, relay1_on, relay2_on)
- tests/unit/test_engine.py shorthand make_m callers
- tests/unit/test_device_read_model.py shorthand make_m callers

D. Active docs/test naming that remembers migration history:
- docs/dev and docs/user contain explicit compatibility / legacy boundary notes
- contract tests still cover grouped-config alias compatibility on purpose

E. Archived history allowed:
- docs/archive/*

F. External IO/debug compatibility that remains justified:
- CoreConfig top-level EV alias fields used by loader/runtime parity/debug surfaces
- adapter/runtime_context current-derivation helpers
```

### Phase 2: Device-Native EV Runtime View

Status: completed

Files changed:

```text
modules/ems_core/net_zero/engine.py
```

Function signatures changed:

```text
_selected_ev_context(cfg, device_id) added
_cfg_with_selected_ev_scalars(cfg, device_id) removed
```

### Phase 3: EV Power Call-Site Refactor

Status: completed

Files changed:

```text
modules/ems_core/net_zero/engine.py
modules/ems_core/net_zero/load_projection.py
tests/unit/test_load_projection.py
```

Tests run:

```text
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_engine.py
```

### Phase 4: Remove `_cfg_with_selected_ev_scalars`

Status: completed

Functions removed:

```text
modules/ems_core/net_zero/engine.py::_cfg_with_selected_ev_scalars
```

Acceptance search:

```text
rg -n "_cfg_with_selected_ev_scalars" modules tests README.md docs/dev docs/user
-> no hits
```

### Phase 5: Measurement Helper Rewrite

Status: completed

Tests rewritten:

```text
tests/helpers.py::make_m no longer accepts charger_on / charger_current_a / relay1_on / relay2_on
tests/helpers.py::ev_state(...) added
tests/helpers.py::relay_state(...) added
tests/unit/test_engine.py updated to ev_states
tests/unit/test_device_read_model.py updated to ev_states / relay_states
```

Acceptance search:

```text
rg -n "charger_on|charger_current_a|relay1_on|relay2_on" tests/helpers.py tests/unit tests/contract tests/e2e_entity
-> only remaining hits are test names / scenario file names, not helper parameters
```

### Phase 6: CoreConfig Top-Level Field Review

Status: completed

Classification:

```text
CoreConfig.ev_charger_phases -> D. external IO/runtime compatibility
CoreConfig.ev_voltage_v -> D. external IO/runtime compatibility
CoreConfig.ev_force_on -> D. external IO/runtime compatibility
CoreConfig.ev_current_step_a -> D. external IO/runtime compatibility

Engine/load_projection no longer depend on these top-level selected-device mirrors
for selected EV decisions. Active decision logic now uses selected_ev_context.
```

Remaining justified references:

```text
modules/ems_adapter/config_loader.py aliases grouped-config EV adapter/policy fields
modules/ems_adapter/device_read_model.py reads compatibility aliases for runtime mapping
tests/contract/test_grouped_config_contract.py and test_grouped_config_runtime_parity.py
verify those compatibility aliases intentionally
```

### Phase 7: Active Docs and Test Vocabulary Cleanup

Status: completed

Docs moved or rewritten:

```text
No active docs were rewritten in this pass.
Reviewed active hits and left them in place when they explicitly describe:
- compatibility/debug boundaries
- legacy/default behavior still intentionally supported
- migration plans/checklists under docs/dev
```

Remaining justified references:

```text
docs/dev/arkkitehtuuri.md and docs/user/* describe deprecated/compatibility surfaces explicitly
README.md documents compatibility diagnostics and implicit legacy default combo naming
docs/dev release/migration plan files are active planning docs, not runtime architecture leaks
```

### Phase 8: Final Verification

Status: completed

Tests run:

```text
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py tests/unit/test_writer_semantics.py tests/unit/test_ev_power.py tests/unit/test_surplus_device_targets.py tests/unit/test_dispatch_state_applier.py tests/contract/test_grouped_config_contract.py tests/contract/test_grouped_config_runtime_parity.py tests/contract/test_runtime_entity_registry_contract.py tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
pytest -q
```

Final search results:

```text
rg -n "_cfg_with_selected_ev_scalars" modules tests README.md docs/dev docs/user
-> no hits

rg -n "policy_ev_current_a|policy_relay1_command|policy_relay2_command|policy_battery_target_w|legacy_relay_flags" modules tests README.md docs/dev docs/user
-> no hits

rg -n "current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" modules tests EMS_config.yaml example_EMS_config.yaml README.md docs/dev docs/user
-> only valid EV power helper function names remain in active code

rg -n "charger_on|charger_current_a|relay1_on|relay2_on" tests/helpers.py tests/unit tests/contract tests/e2e_entity
-> only test/scenario names remain; helper shorthand removed
```
