from ems_core.net_zero.derived_inputs import derive_net_zero_inputs

DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'
WRITER_TRACE = 'sensor.ems_actuator_writer_trace'
_FORBIDDEN_STEP_KEYS = (
    'expect_policy_values',
)
_FORBIDDEN_POLICY_FIELDS = (
    'policy_source',
    'ev_policy_mode',
)
_FORBIDDEN_DISPATCH_FIELDS = (
    'adjustable_active',
    'relay1_active',
    'relay2_active',
)
_FORBIDDEN_VALUE_ENTITY_IDS = (
    'input_boolean.ems_surplus_relay1_active',
    'input_boolean.ems_surplus_adjustable_active',
    'input_boolean.ems_surplus_relay2_active',
)
_FORBIDDEN_WRITER_FIELDS = (
    'policy_source',
)
_FORBIDDEN_WRITER_BRANCHES = (
    'ev',
    'relay1',
    'relay2',
)


def _device_policy_by_id(policy_trace, device_id):
    policies = policy_trace.get('device_policies') or ()
    for policy in policies:
        if isinstance(policy, dict) and policy.get('device_id') == device_id:
            return policy
    return None


def _registry(h):
    if h is None or not hasattr(h, 'ent'):
        raise TypeError('e2e helpers require a QuarterScenarioHarness with scenario registry')
    return h.ent


def _entity(h, key):
    ent = _registry(h)
    entity_id = ent.get(key)
    if not entity_id:
        raise KeyError(f"missing runtime entity key={key} config={getattr(h, 'scenario_config_path', None)}")
    return entity_id


def _optional_entity(h, key):
    return _registry(h).get(key)


def _configured_device_order(active_ids, h=None):
    if h is not None:
        ordered = list(active_ids or ())
        index = {device_id: pos for pos, device_id in enumerate(ordered)}
        devices = (_registry(h).get('devices') or {})
        def _priority(device_id):
            device = devices.get(device_id) or {}
            entity_id = device.get('priority')
            if entity_id:
                return h.get(entity_id, 0)
            return None

        return sorted(
            ordered,
            key=lambda device_id: (
                _priority(device_id) is None,
                -float(_priority(device_id) or 0),
                index[device_id],
            ),
        )

    raise TypeError('e2e helpers require a QuarterScenarioHarness with scenario registry')


def _assert_no_deprecated_e2e_fields(idx, step):
    note = step['note']
    for key in _FORBIDDEN_STEP_KEYS:
        assert key not in step, (
            f"step={idx} note={note} forbidden_step_key={key} "
            f"use canonical device-policy/device-dispatch assertions instead"
        )

    for field in step.get('expect_policy', {}):
        assert field not in _FORBIDDEN_POLICY_FIELDS, (
            f"step={idx} note={note} forbidden_policy_field={field} "
            f"use canonical policy trace fields instead"
        )

    for field in step.get('expect_dispatch_state', {}):
        assert field not in _FORBIDDEN_DISPATCH_FIELDS, (
            f"step={idx} note={note} forbidden_dispatch_field={field} "
            f"use active_surplus_device_ids or device_dispatch_* instead"
        )

    for entity_id in step.get('expect_values', {}):
        assert entity_id not in _FORBIDDEN_VALUE_ENTITY_IDS, (
            f"step={idx} note={note} forbidden_expect_value_entity={entity_id} "
            f"deprecated policy/surplus mirror entities are not allowed in e2e asserts"
        )

    for branch, expected_fields in step.get('expect_writer_trace', {}).items():
        assert branch not in _FORBIDDEN_WRITER_BRANCHES, (
            f"step={idx} note={note} forbidden_writer_branch={branch} "
            f"use device ids under writer_trace.devices instead"
        )
        for field in expected_fields:
            assert field not in _FORBIDDEN_WRITER_FIELDS, (
                f"step={idx} note={note} forbidden_writer_field={branch}.{field} "
                f"writer policy_source is not allowed in e2e asserts"
            )


def _writer_trace_branch(writer_trace, branch):
    if branch == 'victron':
        batteries = writer_trace.get('batteries') or {}
        return batteries.get('HOME_BATTERY')
    devices = writer_trace.get('devices') or {}
    return devices.get(branch)


def _effective_runtime_value(h, key):
    entity_id = _entity(h, key)
    return h.get(entity_id)


def _coerce_expected_number(expected_spec):
    if isinstance(expected_spec, dict):
        return expected_spec['value'], expected_spec.get('tolerance', 0)
    return expected_spec, 0


def _assert_expected_number(actual, expected_spec, context):
    expected, tolerance = _coerce_expected_number(expected_spec)
    if tolerance:
        delta = abs(float(actual) - float(expected))
        assert delta <= float(tolerance), (
            f"{context} actual={actual} expected={expected} tolerance={tolerance}"
        )
        return
    assert actual == expected, (
        f"{context} actual={actual} expected={expected} tolerance=0"
    )


def _assert_expected_derived(idx, step, h):
    expected_derived = step.get('expect_derived')
    if not expected_derived:
        return

    note = step['note']
    actual = derive_net_zero_inputs(
        quarter_energy_balance_kwh=_effective_runtime_value(h, 'quarter_energy_balance_kwh'),
        grid_power_w=_effective_runtime_value(h, 'grid_power_w'),
        now_ts=h.now,
    )
    actual_by_field = {
        'rpnz_w': actual.rpnz_w,
        'required_power_w': actual.required_power_w,
        'required_power_consumption_kw': actual.required_power_consumption_kw,
        'remaining_quarter_s': actual.remaining_quarter_s,
        'remaining_quarter_min': actual.remaining_quarter_min,
        'control_horizon_s': actual.control_horizon_s,
        'input_quality': actual.input_quality,
        'input_warnings': actual.input_warnings,
    }
    for field, expected_spec in expected_derived.items():
        assert field in actual_by_field, (
            f"Invalid E2E fixture: raw runtime inputs do not produce expected NET_ZERO derived intent "
            f"(step={idx} note={note} unknown_field={field})"
        )
        context = (
            "Invalid E2E fixture: raw runtime inputs do not produce expected NET_ZERO derived intent "
            f"(step={idx} note={note} field={field})"
        )
        actual_value = actual_by_field[field]
        if isinstance(expected_spec, dict) or isinstance(actual_value, (int, float)):
            _assert_expected_number(actual_value, expected_spec, context)
        else:
            assert actual_value == expected_spec, (
                f"{context} actual={actual_value} expected={expected_spec}"
            )




def _nested_value(mapping, path):
    value = mapping
    for part in str(path).split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value

def _assert_canonical_contracts(idx, note, policy_trace, dispatch_state_trace):
    config_source = policy_trace.get('config_source')
    assert config_source == 'direct_tick_frame_v5_e2e', (
        f"step={idx} note={note} policy.config_source "
        f"actual={config_source} expected=direct_tick_frame_v5_e2e"
    )
    runtime_contract = policy_trace.get('runtime_input_contract')
    assert runtime_contract == 'direct_tick_frame_v5', (
        f"step={idx} note={note} policy.runtime_input_contract "
        f"actual={runtime_contract} expected=direct_tick_frame_v5"
    )


    dispatch_source = dispatch_state_trace.get('decision_source')
    assert dispatch_source == 'dispatch_command', (
        f"step={idx} note={note} dispatch_state.decision_source "
        f"actual={dispatch_source} expected=dispatch_command"
    )

    dispatch_contract = dispatch_state_trace.get('dispatch_state_contract')
    assert dispatch_contract == 'device_id_primary', (
        f"step={idx} note={note} dispatch_state.dispatch_state_contract "
        f"actual={dispatch_contract} expected=device_id_primary"
    )

    expected_action = policy_trace.get('surplus_dispatch_action')
    expected_device_id = policy_trace.get('surplus_dispatch_device_id')
    actual_action = dispatch_state_trace.get('device_dispatch_action')
    actual_device_id = dispatch_state_trace.get('device_dispatch_device_id')

    assert actual_action == expected_action, (
        f"step={idx} note={note} dispatch_state.device_dispatch_action "
        f"actual={actual_action} expected={expected_action}"
    )
    assert actual_device_id == expected_device_id, (
        f"step={idx} note={note} dispatch_state.device_dispatch_device_id "
        f"actual={actual_device_id} expected={expected_device_id}"
    )


def seed_previous_device_state(
    h,
    *,
    device_id='EV_CHARGER',
    mode,
    low_pv_cycles=0,
    hard_off_release_ready_cycles=0,
    hard_off_active=None,
):
    if hard_off_active is None:
        hard_off_active = mode == 'hard_off'

    policy_state = _entity(h, 'policy_state')
    state = {
        'device_id': device_id,
        'mode': mode,
        'low_pv_cycles': low_pv_cycles,
        'hard_off_release_ready_cycles': hard_off_release_ready_cycles,
        'hard_off_active': hard_off_active,
    }
    h.set_attrs(policy_state, {'previous_device_states': {device_id: state}})


def seed_previous_policy_trace(h, **attrs):
    h.set_attrs(_entity(h, 'policy_state'), attrs)
    h.set_attrs(_entity(h, 'policy_diagnostics'), attrs)


def seed_active_surplus_devices(
    h,
    *,
    active_device_ids=(),
    actuator_relay1=False,
    actuator_relay2=False,
    actuator_ev_enabled=False,
    actuator_ev_current_a=6,
    actuator_battery_setpoint_w=0,
    goal_profile=None,
    relay_states=None,
    ev_states=None,
):
    active_ids = tuple(active_device_ids or ())
    active_device_id_list = _configured_device_order(active_ids, h)

    seed = {}
    for key, value in (
        ('active_surplus_devices', ','.join(active_device_id_list)),
        ('actuator_relay1', actuator_relay1),
        ('actuator_relay2', actuator_relay2),
        ('actuator_ev_enabled', actuator_ev_enabled),
        ('actuator_ev_current_a', actuator_ev_current_a),
        ('actuator_battery_setpoint_w', actuator_battery_setpoint_w),
    ):
        entity_id = _optional_entity(h, key)
        if entity_id:
            seed[entity_id] = value
    if goal_profile is not None:
        seed[_entity(h, 'goal_profile')] = goal_profile
    for device_id, enabled in (relay_states or {}).items():
        seed[h.dev(device_id, 'enabled')] = enabled
    for device_id, state in (ev_states or {}).items():
        if not isinstance(state, dict):
            state = {'enabled': state}
        if 'enabled' in state:
            seed[h.dev(device_id, 'enabled')] = state['enabled']
        if 'current_a' in state:
            seed[h.dev(device_id, 'current_a')] = state['current_a']
    h.set_entities(seed)


def seed_battery_protect_runtime_state(
    h,
    *,
    guard_profile,
    soc,
    min_cell_voltage_v,
    actuator_battery_setpoint_w,
):
    h.set_entities({
        _entity(h, 'guard_profile'): guard_profile,
        _entity(h, 'soc'): soc,
        _entity(h, 'min_cell_voltage_v'): min_cell_voltage_v,
        _entity(h, 'actuator_battery_setpoint_w'): actuator_battery_setpoint_w,
    })


def run_scenario_steps(h, steps, *, validate=True):
    for idx, step in enumerate(steps):
        _assert_no_deprecated_e2e_fields(idx, step)
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        if not validate:
            continue

        # Legacy NET_ZERO direct intent keys remain temporarily allowed only as
        # a migration bridge. New raw runtime fixtures should use expect_derived.
        _assert_expected_derived(idx, step, h)

        policy_trace = h.getattrs(_entity(h, 'policy_diagnostics'))
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)
        _assert_canonical_contracts(idx, step['note'], policy_trace, dispatch_state_trace)

        for attr, expected in step.get('expect_policy', {}).items():
            actual = _nested_value(policy_trace, attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} policy.{attr} actual={actual} expected={expected}"
            )

        for device_id, expected_fields in step.get('expect_device_policies', {}).items():
            policy = _device_policy_by_id(policy_trace, device_id)
            assert policy is not None, (
                f"step={idx} note={step['note']} missing device_policy device_id={device_id}"
            )
            for field, expected in expected_fields.items():
                actual = policy.get(field)
                assert actual == expected, (
                    f"step={idx} note={step['note']} device_policy.{device_id}.{field} "
                    f"actual={actual} expected={expected}"
                )

        for attr, expected in step.get('expect_dispatch_state', {}).items():
            actual = dispatch_state_trace.get(attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} dispatch_state.{attr} actual={actual} expected={expected}"
            )

        if step.get('expect_writer_trace'):
            assert h.get(WRITER_TRACE) == 'ACTIVE', (
                f"step={idx} note={step['note']} expected writer trace entity to be ACTIVE"
            )
            writer_trace = h.getattrs(WRITER_TRACE)
            writer_contract = writer_trace.get('writer_policy_contract')
            if writer_contract is not None:
                assert writer_contract == 'device_policy_primary', (
                    f"step={idx} note={step['note']} writer.writer_policy_contract "
                    f"actual={writer_contract} expected=device_policy_primary"
                )
            for branch, expected_fields in step['expect_writer_trace'].items():
                actual_branch = _writer_trace_branch(writer_trace, branch)
                assert actual_branch is not None, (
                    f"step={idx} note={step['note']} missing writer branch={branch}"
                )
                for field, expected in expected_fields.items():
                    actual = actual_branch.get(field)
                    assert actual == expected, (
                        f"step={idx} note={step['note']} writer.{branch}.{field} "
                        f"actual={actual} expected={expected}"
                    )

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} actual={actual} expected={expected}"
            )
