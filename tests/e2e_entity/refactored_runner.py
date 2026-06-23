DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'
WRITER_TRACE = 'sensor.ems_actuator_writer_trace'
_LEGACY_STEP_KEYS = (
    'expect_policy_values',
)
_LEGACY_POLICY_FIELDS = (
    'policy_source',
    'ev_policy_mode',
    'relay1_command',
    'relay2_command',
    'surplus_dispatch_decision',
)
_LEGACY_DISPATCH_FIELDS = (
    'adjustable_active',
    'relay1_active',
    'relay2_active',
)
_LEGACY_VALUE_ENTITY_IDS = (
    'sensor.ems_policy_battery_target_w_pyscript',
    'sensor.ems_policy_ev_current_a_pyscript',
    'sensor.ems_policy_relay1_command_pyscript',
    'sensor.ems_policy_relay2_command_pyscript',
    'sensor.ems_net_zero_surplus_dispatch_decision_pyscript',
    'input_boolean.ems_surplus_relay1_active',
    'input_boolean.ems_surplus_adjustable_active',
    'input_boolean.ems_surplus_relay2_active',
)
_LEGACY_WRITER_FIELDS = (
    'policy_source',
)
_LEGACY_WRITER_BRANCHES = (
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
        raise KeyError(f"missing runtime entity key={key} config={getattr(h, 'grouped_config_path', None)}")
    return entity_id


def _optional_entity(h, key):
    return _registry(h).get(key)


def _configured_device_order(active_ids, h=None):
    if h is not None:
        ordered = list(active_ids or ())
        index = {device_id: pos for pos, device_id in enumerate(ordered)}
        devices = (_registry(h).get('devices') or {})
        adjustable_surplus_load = h.get(_entity(h, 'adjustable_surplus_load'), '')
        adjustable_priority = h.get(_entity(h, 'adjustable_surplus_load_priority'), 0)

        def _priority(device_id):
            device = devices.get(device_id) or {}
            entity_id = device.get('priority')
            if entity_id:
                return h.get(entity_id, 0)
            if device_id == adjustable_surplus_load:
                return adjustable_priority
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


def _assert_no_legacy_e2e_fields(idx, step):
    note = step['note']
    for key in _LEGACY_STEP_KEYS:
        assert key not in step, (
            f"step={idx} note={note} forbidden_step_key={key} "
            f"use canonical device-policy/device-dispatch assertions instead"
        )

    for field in step.get('expect_policy', {}):
        assert field not in _LEGACY_POLICY_FIELDS, (
            f"step={idx} note={note} forbidden_policy_field={field} "
            f"use canonical policy trace fields instead"
        )

    for field in step.get('expect_dispatch_state', {}):
        assert field not in _LEGACY_DISPATCH_FIELDS, (
            f"step={idx} note={note} forbidden_dispatch_field={field} "
            f"use active_surplus_device_ids or device_dispatch_* instead"
        )

    for entity_id in step.get('expect_values', {}):
        assert entity_id not in _LEGACY_VALUE_ENTITY_IDS, (
            f"step={idx} note={note} forbidden_expect_value_entity={entity_id} "
            f"legacy policy/surplus mirror entities are not allowed in e2e asserts"
        )

    for branch, expected_fields in step.get('expect_writer_trace', {}).items():
        assert branch not in _LEGACY_WRITER_BRANCHES, (
            f"step={idx} note={note} forbidden_writer_branch={branch} "
            f"use device ids under writer_trace.devices instead"
        )
        for field in expected_fields:
            assert field not in _LEGACY_WRITER_FIELDS, (
                f"step={idx} note={note} forbidden_writer_field={branch}.{field} "
                f"writer policy_source is not allowed in e2e asserts"
            )


def _writer_trace_branch(writer_trace, branch):
    if branch == 'victron':
        return writer_trace.get('victron')
    devices = writer_trace.get('devices') or {}
    return devices.get(branch)


def _assert_canonical_contracts(idx, note, policy_trace, dispatch_state_trace):
    config_source = policy_trace.get('config_source')
    assert config_source == 'grouped_config', (
        f"step={idx} note={note} policy.config_source "
        f"actual={config_source} expected=grouped_config"
    )

    policy_contract = policy_trace.get('policy_output_contract')
    assert policy_contract == 'device_policy_primary', (
        f"step={idx} note={note} policy.policy_output_contract "
        f"actual={policy_contract} expected=device_policy_primary"
    )

    dispatch_source = dispatch_state_trace.get('decision_source')
    assert dispatch_source == 'device_trace', (
        f"step={idx} note={note} dispatch_state.decision_source "
        f"actual={dispatch_source} expected=device_trace"
    )

    dispatch_contract = dispatch_state_trace.get('dispatch_state_contract')
    assert dispatch_contract == 'device_id_primary', (
        f"step={idx} note={note} dispatch_state.dispatch_state_contract "
        f"actual={dispatch_contract} expected=device_id_primary"
    )

    expected_action = policy_trace.get('surplus_device_dispatch_action')
    expected_target = policy_trace.get('surplus_device_dispatch_target')
    expected_device_id = policy_trace.get('surplus_device_dispatch_device_id')

    actual_action = dispatch_state_trace.get('device_dispatch_action')
    actual_target = dispatch_state_trace.get('device_dispatch_target')
    actual_device_id = dispatch_state_trace.get('device_dispatch_device_id')

    assert actual_action == expected_action, (
        f"step={idx} note={note} dispatch_state.device_dispatch_action "
        f"actual={actual_action} expected={expected_action}"
    )
    assert actual_target == expected_target, (
        f"step={idx} note={note} dispatch_state.device_dispatch_target "
        f"actual={actual_target} expected={expected_target}"
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

    previous_device_state = _entity(h, 'previous_device_state')
    h.set_entities({previous_device_state: device_id})
    h.set_attrs(previous_device_state, {
        'device_id': device_id,
        'mode': mode,
        'low_pv_cycles': low_pv_cycles,
        'hard_off_release_ready_cycles': hard_off_release_ready_cycles,
        'hard_off_active': hard_off_active,
    })


def seed_previous_policy_trace(h, **attrs):
    h.set_attrs(_entity(h, 'policy_decision_trace'), attrs)


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


def run_refactored_steps(h, steps, *, validate=True):
    for idx, step in enumerate(steps):
        _assert_no_legacy_e2e_fields(idx, step)
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        if not validate:
            continue

        policy_trace = h.getattrs(_entity(h, 'policy_decision_trace'))
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)
        _assert_canonical_contracts(idx, step['note'], policy_trace, dispatch_state_trace)

        for attr, expected in step.get('expect_policy', {}).items():
            actual = policy_trace.get(attr)
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
