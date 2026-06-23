import pytest
from types import SimpleNamespace


def _load_writer_module(project_root):
    path = project_root / 'ems_actuator_writers.py'
    src = path.read_text(encoding='utf-8')

    # Poista adapter-importit; injektoidaan korvikkeet testin namespaceen
    filtered = []
    for line in src.splitlines():
        if line.startswith('from ems_adapter.ha_adapter import'):
            continue
        filtered.append(line)
    src = '\n'.join(filtered)

    state = {}

    def _time_trigger(*args, **kwargs):
        def deco(fn):
            return fn
        return deco

    def _state_trigger(*args, **kwargs):
        def deco(fn):
            return fn
        return deco

    def get_bool(entity_id):
        return bool(state.get(entity_id, False))

    def get_float(entity_id, default=0.0):
        return float(state.get(entity_id, default))

    def get_int(entity_id, default=0):
        return int(state.get(entity_id, default))

    def get_str(entity_id, default=''):
        return str(state.get(entity_id, default))

    def set_boolean(entity_id, on):
        state[entity_id] = bool(on)

    def set_number(entity_id, value):
        state[entity_id] = value

    def publish_sensor(entity_id, value, attrs=None):
        state[entity_id] = {'value': value, 'attrs': attrs or {}}

    ENT = {
        'policy_battery_target_w': 'sensor.policy_battery',
        'actuator_battery_setpoint_w': 'input_number.test_actuator_battery_setpoint_w',
        'policy_ev_current_a': 'sensor.policy_ev',
        'actuator_ev_enabled': 'input_boolean.actuator_ev_enabled',
        'actuator_ev_current_a': 'input_number.test_actuator_ev_current_a',
        'policy_relay1_command': 'sensor.policy_relay1',
        'policy_relay2_command': 'sensor.policy_relay2',
        'actuator_relay1': 'input_boolean.actuator_relay1',
        'actuator_relay2': 'input_boolean.actuator_relay2',
    }

    ns = {
        '__name__': 'writer_test_module',
        '__file__': str(path),
        'time_trigger': _time_trigger,
        'state_trigger': _state_trigger,
        'get_bool': get_bool,
        'get_float': get_float,
        'get_int': get_int,
        'get_str': get_str,
        'set_boolean': set_boolean,
        'set_number': set_number,
        'publish_sensor': publish_sensor,
        'ENT': ENT,
        'read_runtime_entities': lambda *args, **kwargs: {},
    }
    _install_core_capabilities(ns)

    code = compile(src, str(path), 'exec')
    exec(code, ns)
    return ns, state, ENT


def _install_device_policies(mod, policies):
    def get_attr(entity_id, attr, default=None):
        if attr == 'device_policies':
            return tuple(policies)
        return default

    mod['get_attr'] = get_attr


def _install_core_capabilities(mod, **overrides):
    device_defaults = {
        'HOME_BATTERY': dict(can_absorb_w=True, can_produce_w=True, min_absorb_w=0, max_absorb_w=4000, max_produce_w=4000, step_w=50, priority=1),
        'EV_CHARGER': dict(can_absorb_w=True, can_produce_w=False, min_absorb_w=1380, max_absorb_w=6440, max_produce_w=0, step_w=460, priority=1),
        'RELAY1': dict(can_absorb_w=True, can_produce_w=False, min_absorb_w=2500, max_absorb_w=2500, max_produce_w=0, step_w=2500, priority=1),
        'RELAY2': dict(can_absorb_w=True, can_produce_w=False, min_absorb_w=5000, max_absorb_w=5000, max_produce_w=0, step_w=5000, priority=1),
    }
    for device_id, values in overrides.items():
        if device_id not in device_defaults:
            device_defaults[device_id] = dict(can_absorb_w=True, can_produce_w=False, min_absorb_w=0, max_absorb_w=0, max_produce_w=0, step_w=1, priority=1)
        device_defaults[device_id].update(values)

    def _device(device_id):
        kind = device_defaults[device_id].get('kind')
        if kind is None:
            kind = 'BATTERY' if device_id == 'HOME_BATTERY' else ('EV_CHARGER' if device_id == 'EV_CHARGER' else 'RELAY')
        cap_values = {key: value for key, value in device_defaults[device_id].items() if key != 'kind'}
        caps = SimpleNamespace(**cap_values)
        return SimpleNamespace(device_id=device_id, kind=kind, capabilities=caps, policy=SimpleNamespace(priority=device_defaults[device_id]['priority']))

    devices = {device_id: _device(device_id) for device_id in device_defaults}

    mod['read_core_config'] = lambda: SimpleNamespace(
        home_battery=devices['HOME_BATTERY'],
        ev_charger=devices['EV_CHARGER'],
        relay1=devices['RELAY1'],
        relay2=devices['RELAY2'],
        devices=devices,
        device_by_id=lambda device_id: devices.get(device_id),
    )


@pytest.mark.unit
def test_writer_relay_without_device_policy_does_not_use_legacy_command(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    state[ENT['actuator_relay1']] = True
    state[ENT['policy_relay1_command']] = 0

    result = mod['_write_relay_actuator'](ENT['policy_relay1_command'], ENT['actuator_relay1'], 'relay1')
    assert result['written'] is False
    assert state[ENT['actuator_relay1']] is True
    assert result['reason'] == 'missing_device_policy'
    assert result['policy_source'] == 'missing_device_policy'


@pytest.mark.unit
def test_writer_ev_without_device_policy_does_not_use_legacy_current_even_without_device_id(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    state[ENT['policy_ev_current_a']] = 12
    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 4

    result = mod['_write_ev_actuator'](device_id=None)

    assert result['written'] is False
    assert result['reason'] == 'missing_device_policy'
    assert result['policy_source'] == 'missing_device_policy'
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 4


@pytest.mark.unit
def test_writer_manual_battery_is_hands_off(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    state['input_select.ems_control_profile'] = 'MANUAL'
    state[ENT['policy_battery_target_w']] = 1500
    state[ENT['actuator_battery_setpoint_w']] = 250

    result = mod['_write_battery_actuator']()
    assert result['written'] is False
    assert result['reason'] == 'manual_skip'
    assert state[ENT['actuator_battery_setpoint_w']] == 250


@pytest.mark.unit
def test_writer_manual_safe_clamps_to_policy_target(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'HOME_BATTERY',
                'target_w': 0,
                'enabled': True,
                'mode': 'power',
            }
        ],
    )

    state['input_select.ems_control_profile'] = 'MANUAL_SAFE'
    state[ENT['policy_battery_target_w']] = 500
    state[ENT['actuator_battery_setpoint_w']] = -500

    result = mod['_write_battery_actuator']()
    assert result['written'] is True
    assert result['reason'] == 'manual_safe_clamp'
    assert result['policy_source'] == 'device_policy'
    assert state[ENT['actuator_battery_setpoint_w']] == 0


@pytest.mark.unit
def test_writer_battery_does_not_fallback_to_legacy_policy_target_without_device_policy(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 1
    state['input_number.ems_ramp_max_w'] = 1000
    state[ENT['policy_battery_target_w']] = 500
    state[ENT['actuator_battery_setpoint_w']] = 0

    result = mod['_write_battery_actuator']()

    assert result['written'] is False
    assert result['reason'] == 'missing_device_policy'
    assert result['policy_source'] == 'missing_device_policy'
    assert state[ENT['actuator_battery_setpoint_w']] == 0


@pytest.mark.unit
def test_writer_ev_does_not_fallback_to_legacy_current_without_device_policy(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    state[ENT['policy_ev_current_a']] = 16
    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 4

    result = mod['_write_ev_actuator']()

    assert result['written'] is False
    assert result['reason'] == 'missing_device_policy'
    assert result['policy_source'] == 'missing_device_policy'
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 4


@pytest.mark.unit
def test_writer_battery_can_read_device_policy_target(project_root):
    mod, state, ENT = _load_writer_module(project_root)
    _install_core_capabilities(mod, HOME_BATTERY={'can_absorb_w': True, 'can_produce_w': False})

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'HOME_BATTERY',
                'target_w': 500,
                'enabled': True,
                'mode': 'power',
            }
        ],
    )

    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 1
    state['input_number.ems_ramp_max_w'] = 1000
    state[ENT['policy_battery_target_w']] = 0
    state[ENT['actuator_battery_setpoint_w']] = 0

    result = mod['_write_battery_actuator']()

    assert result['written'] is True
    assert result['policy_source'] == 'device_policy'
    assert result['policy_target_w'] == 500
    assert state[ENT['actuator_battery_setpoint_w']] == 500


@pytest.mark.unit
def test_writer_battery_clamps_disallowed_discharge_to_zero(project_root):
    mod, state, ENT = _load_writer_module(project_root)
    _install_core_capabilities(mod, HOME_BATTERY={'can_absorb_w': True, 'can_produce_w': False})

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'HOME_BATTERY',
                'target_w': -1200,
                'enabled': True,
                'mode': 'power',
            }
        ],
    )

    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 1
    state['input_number.ems_ramp_max_w'] = 5000
    state[ENT['actuator_battery_setpoint_w']] = -800

    result = mod['_write_battery_actuator']()

    assert result['written'] is True
    assert result['reason'] == 'capability_blocked_produce'
    assert state[ENT['actuator_battery_setpoint_w']] == 0


@pytest.mark.unit
def test_writer_ev_can_convert_device_policy_target_w_to_current(project_root):
    mod, state, ENT = _load_writer_module(project_root)
    _install_core_capabilities(mod)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'EV_CHARGER',
                'target_w': 3680,
                'enabled': True,
                'mode': 'burn',
            }
        ],
    )

    state[ENT['policy_ev_current_a']] = -1
    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 4
    state['input_number.ems_ev_min_current_a'] = 4
    state['input_number.ems_ev_max_current_a'] = 32
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1

    result = mod['_write_ev_actuator']()

    assert result['written'] is True
    assert result['policy_source'] == 'device_policy'
    assert result['target_current_a'] == 16
    assert state[ENT['actuator_ev_enabled']] is True
    assert state[ENT['actuator_ev_current_a']] == 16


@pytest.mark.unit
def test_writer_ev_hard_offs_when_absorb_is_disallowed(project_root):
    mod, state, ENT = _load_writer_module(project_root)
    _install_core_capabilities(mod, EV_CHARGER={'can_absorb_w': False})

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'EV_CHARGER',
                'target_w': 3680,
                'enabled': True,
                'mode': 'burn',
            }
        ],
    )

    state[ENT['actuator_ev_enabled']] = True
    state[ENT['actuator_ev_current_a']] = 16
    state['input_number.ems_ev_min_current_a'] = 4
    state['input_number.ems_ev_max_current_a'] = 32
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1

    result = mod['_write_ev_actuator']()

    assert result['written'] is True
    assert result['reason'] == 'capability_blocked_absorb'
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 4


@pytest.mark.unit
def test_writer_ev_uses_target_w_even_if_policy_payload_has_only_watt_contract(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'EV_CHARGER',
                'target_w': 5520,
                'enabled': True,
                'mode': 'burn',
            }
        ],
    )

    state[ENT['policy_ev_current_a']] = -1
    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 4
    state['input_number.ems_ev_min_current_a'] = 6
    state['input_number.ems_ev_max_current_a'] = 28
    state['input_number.ems_ev_current_step_a'] = 4
    state['input_number.ems_ev_charger_phases'] = 1

    result = mod['_write_ev_actuator']()

    assert result['written'] is True
    assert result['policy_source'] == 'device_policy'
    assert result['target_current_a'] == 22
    assert state[ENT['actuator_ev_current_a']] == 22


@pytest.mark.unit
def test_writer_relay_device_policy_overrides_legacy_command(project_root):
    mod, state, ENT = _load_writer_module(project_root)
    _install_core_capabilities(mod)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'RELAY1',
                'target_w': 0,
                'enabled': False,
                'mode': 'relay',
            }
        ],
    )

    state[ENT['policy_relay1_command']] = 1
    state[ENT['actuator_relay1']] = True

    result = mod['_write_relay_actuator'](
        ENT['policy_relay1_command'],
        ENT['actuator_relay1'],
        'relay1',
        device_id='RELAY1',
    )

    assert result['written'] is True
    assert result['policy_source'] == 'device_policy'
    assert state[ENT['actuator_relay1']] is False


@pytest.mark.unit
def test_writer_relay_turns_off_when_absorb_is_disallowed(project_root):
    mod, state, ENT = _load_writer_module(project_root)
    _install_core_capabilities(mod, RELAY1={'can_absorb_w': False})

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'RELAY1',
                'target_w': 2500,
                'enabled': True,
                'mode': 'relay',
            }
        ],
    )

    state[ENT['actuator_relay1']] = True

    result = mod['_write_relay_actuator'](
        ENT['policy_relay1_command'],
        ENT['actuator_relay1'],
        'relay1',
        device_id='RELAY1',
    )

    assert result['written'] is True
    assert result['reason'] == 'capability_blocked_absorb'
    assert state[ENT['actuator_relay1']] is False


@pytest.mark.unit
def test_writer_relay_device_policy_skip_preserves_actuator_state(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'RELAY1',
                'target_w': 0,
                'enabled': False,
                'mode': 'skip',
            }
        ],
    )

    state[ENT['policy_relay1_command']] = 0
    state[ENT['actuator_relay1']] = True

    result = mod['_write_relay_actuator'](
        ENT['policy_relay1_command'],
        ENT['actuator_relay1'],
        'relay1',
        device_id='RELAY1',
    )

    assert result['written'] is False
    assert result['reason'] == 'policy_skip'
    assert result['policy_source'] == 'device_policy'
    assert state[ENT['actuator_relay1']] is True


@pytest.mark.unit
def test_writer_relay_does_not_fallback_to_legacy_command_with_device_id(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    state[ENT['policy_relay1_command']] = 1
    state[ENT['actuator_relay1']] = False

    result = mod['_write_relay_actuator'](
        ENT['policy_relay1_command'],
        ENT['actuator_relay1'],
        'relay1',
        device_id='RELAY1',
    )

    assert result['written'] is False
    assert result['reason'] == 'missing_device_policy'
    assert result['policy_source'] == 'missing_device_policy'
    assert state[ENT['actuator_relay1']] is False


@pytest.mark.unit
def test_writer_loop_uses_device_policies_when_legacy_policy_sensors_conflict(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'HOME_BATTERY',
                'target_w': 500,
                'enabled': True,
                'mode': 'power',
            },
                {
                    'device_id': 'EV_CHARGER',
                    'target_w': 2760,
                    'enabled': True,
                    'mode': 'burn',
                },
            {
                'device_id': 'RELAY1',
                'target_w': 0,
                'enabled': True,
                'mode': 'relay',
            },
            {
                'device_id': 'RELAY2',
                'target_w': 0,
                'enabled': False,
                'mode': 'relay',
            },
        ],
    )

    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 1
    state['input_number.ems_ramp_max_w'] = 1000
    state['input_number.ems_ev_min_current_a'] = 6
    state['input_number.ems_ev_max_current_a'] = 28
    state['input_number.ems_ev_current_step_a'] = 2
    state['input_number.ems_ev_charger_phases'] = 1
    state[ENT['actuator_battery_setpoint_w']] = 0
    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 6
    state[ENT['actuator_relay1']] = False
    state[ENT['actuator_relay2']] = True

    state[ENT['policy_battery_target_w']] = -2000
    state[ENT['policy_ev_current_a']] = -1
    state[ENT['policy_relay1_command']] = 0
    state[ENT['policy_relay2_command']] = 1

    result = mod['ems_actuator_writers_loop']()
    writer_trace = state['sensor.ems_actuator_writer_trace']

    assert result['victron']['policy_source'] == 'device_policy'
    assert result['devices']['EV_CHARGER']['policy_source'] == 'device_policy'
    assert result['devices']['RELAY1']['policy_source'] == 'device_policy'
    assert result['devices']['RELAY2']['policy_source'] == 'device_policy'
    assert state[ENT['actuator_battery_setpoint_w']] == 500
    assert state[ENT['actuator_ev_enabled']] is True
    assert state[ENT['actuator_ev_current_a']] == 12
    assert state[ENT['actuator_relay1']] is True
    assert state[ENT['actuator_relay2']] is False
    assert writer_trace['attrs']['writer_policy_contract'] == 'device_policy_primary'
    

@pytest.mark.unit
def test_writer_loop_writes_third_relay_from_device_registry(project_root):
    mod, state, ENT = _load_writer_module(project_root)
    _install_core_capabilities(
        mod,
        RELAY3={'max_absorb_w': 7500, 'min_absorb_w': 7500, 'step_w': 7500, 'priority': 4},
    )

    ENT['devices'] = {
        'RELAY3': {
            'enabled': 'switch.relay_3_2',
        },
    }
    _install_device_policies(
        mod,
        [
            {
                'device_id': 'HOME_BATTERY',
                'target_w': 0,
                'enabled': True,
                'mode': 'power',
            },
            {
                'device_id': 'EV_CHARGER',
                'target_w': 0,
                'enabled': True,
                'mode': 'release',
            },
            {
                'device_id': 'RELAY1',
                'target_w': 0,
                'enabled': False,
                'mode': 'skip',
            },
            {
                'device_id': 'RELAY2',
                'target_w': 0,
                'enabled': False,
                'mode': 'skip',
            },
            {
                'device_id': 'RELAY3',
                'target_w': 7500,
                'enabled': True,
                'mode': 'relay',
            },
        ],
    )

    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 100
    state['input_number.ems_ramp_max_w'] = 500
    state[ENT['actuator_battery_setpoint_w']] = 0
    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 6
    state[ENT['actuator_relay1']] = False
    state[ENT['actuator_relay2']] = False
    state['switch.relay_3_2'] = False

    result = mod['ems_actuator_writers_loop']()
    writer_trace = state['sensor.ems_actuator_writer_trace']

    assert result['devices']['RELAY3']['written'] is True
    assert result['devices']['RELAY3']['action'] == 'turn_on'
    assert state['switch.relay_3_2'] is True
    assert writer_trace['attrs']['devices']['RELAY3']['policy_source'] == 'device_policy'


@pytest.mark.unit
def test_writer_loop_targets_selected_second_ev_and_keeps_inactive_ev_off(project_root):
    mod, state, ENT = _load_writer_module(project_root)
    _install_core_capabilities(
        mod,
        GARAGE_EV={
            'kind': 'EV_CHARGER',
            'can_absorb_w': True,
            'can_produce_w': False,
            'min_absorb_w': 1380,
            'max_absorb_w': 3680,
            'step_w': 460,
            'max_produce_w': 0,
            'priority': 4,
        },
    )

    ENT['devices'] = {
        'EV_CHARGER': {
            'kind': 'EV_CHARGER',
            'enabled': ENT['actuator_ev_enabled'],
            'current_a': ENT['actuator_ev_current_a'],
            'current_min_a': 'input_number.ems_ev_min_current_a',
            'current_max_a': 'input_number.ems_ev_max_current_a',
            'current_step_a': 'input_number.ems_ev_current_step_a',
            'phases': 'input_number.ems_ev_charger_phases',
        },
        'GARAGE_EV': {
            'kind': 'EV_CHARGER',
            'enabled': 'switch.garage_ev_enabled',
            'current_a': 'number.garage_ev_current_a',
            'current_min_a': 'input_number.garage_ev_min_current_a',
            'current_max_a': 'input_number.garage_ev_max_current_a',
            'current_step_a': 'input_number.garage_ev_current_step_a',
            'phases': 'input_number.garage_ev_phases',
        },
    }
    _install_device_policies(
        mod,
        [
            {
                'device_id': 'HOME_BATTERY',
                'target_w': 0,
                'enabled': True,
                'mode': 'power',
            },
            {
                'device_id': 'EV_CHARGER',
                'target_w': 0,
                'enabled': False,
                'mode': 'restore_min',
                'reason': 'inactive_ev_policy',
            },
            {
                'device_id': 'GARAGE_EV',
                'target_w': 3680,
                'enabled': True,
                'mode': 'burn',
            },
            {
                'device_id': 'RELAY1',
                'target_w': 0,
                'enabled': False,
                'mode': 'skip',
            },
            {
                'device_id': 'RELAY2',
                'target_w': 0,
                'enabled': False,
                'mode': 'skip',
            },
        ],
    )

    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 100
    state['input_number.ems_ramp_max_w'] = 500
    state[ENT['actuator_battery_setpoint_w']] = 0
    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 6
    state['switch.garage_ev_enabled'] = False
    state['number.garage_ev_current_a'] = 6
    state['input_number.garage_ev_min_current_a'] = 6
    state['input_number.garage_ev_max_current_a'] = 16
    state['input_number.garage_ev_current_step_a'] = 2
    state['input_number.garage_ev_phases'] = 1
    state[ENT['actuator_relay1']] = False
    state[ENT['actuator_relay2']] = False

    result = mod['ems_actuator_writers_loop']()
    writer_trace = state['sensor.ems_actuator_writer_trace']

    assert result['devices']['EV_CHARGER']['policy_source'] == 'device_policy'
    assert result['devices']['GARAGE_EV']['policy_source'] == 'device_policy'
    assert result['devices']['GARAGE_EV']['action'] == 'enable_and_set_current'
    assert result['devices']['GARAGE_EV']['target_current_a'] == 16
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 6
    assert state['switch.garage_ev_enabled'] is True
    assert state['number.garage_ev_current_a'] == 16
    assert writer_trace['attrs']['devices']['EV_CHARGER']['policy_source'] == 'device_policy'
    assert writer_trace['attrs']['devices']['GARAGE_EV']['target_current_a'] == 16

    
@pytest.mark.unit
def test_writer_loop_restores_ev_to_min_current_when_policy_current_is_zero(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'HOME_BATTERY',
                'target_w': 0,
                'enabled': True,
                'mode': 'power',
            },
            {
                'device_id': 'EV_CHARGER',
                'target_w': 0,
                'enabled': True,
                'mode': 'release',
            },
            {
                'device_id': 'RELAY1',
                'target_w': 0,
                'enabled': False,
                'mode': 'skip',
            },
            {
                'device_id': 'RELAY2',
                'target_w': 0,
                'enabled': False,
                'mode': 'skip',
            },
        ],
    )

    # Neutraloi muut writer-haarat, jotta testin fokus pysyy EV:ssä
    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 100
    state['input_number.ems_ramp_max_w'] = 500

    state[ENT['policy_battery_target_w']] = 0
    state[ENT['actuator_battery_setpoint_w']] = 0

    state[ENT['policy_relay1_command']] = -1
    state[ENT['policy_relay2_command']] = -1
    state[ENT['actuator_relay1']] = False
    state[ENT['actuator_relay2']] = False

    # EV on päällä ja current on yli minimin
    state[ENT['actuator_ev_enabled']] = True
    state[ENT['actuator_ev_current_a']] = 16

    # Policy kertoo, että aktiivinen EV-burn on päättynyt -> strategy 0
    state[ENT['policy_ev_current_a']] = 0
    state['input_number.ems_ev_min_current_a'] = 4

    # Ajetaan koko writer-loop, ei vain _write_ev_actuator()
    mod['ems_actuator_writers_loop']()

    # EV-current pitää palautua minimiin
    assert state[ENT['actuator_ev_current_a']] == 4

    # Writer trace pitää kertoa mitä tapahtui
    trace = state['sensor.ems_actuator_writer_trace']
    assert trace['value'] == 'ACTIVE'
    assert trace['attrs']['devices']['EV_CHARGER']['written'] is True
    assert trace['attrs']['devices']['EV_CHARGER']['reason'] == 'restore_min_current'
    assert trace['attrs']['devices']['EV_CHARGER']['target_current_a'] == 4


@pytest.mark.unit
def test_writer_hard_off_disables_ev_and_sets_current_zero(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'EV_CHARGER',
                'target_w': 0,
                'enabled': False,
                'mode': 'hard_off',
            }
        ],
    )

    state[ENT['actuator_ev_enabled']] = True
    state[ENT['actuator_ev_current_a']] = 16
    state[ENT['policy_ev_current_a']] = 0
    state['input_number.ems_ev_min_current_a'] = 4

    result = mod['_write_ev_actuator']()
    assert result['written'] is True
    assert result['reason'] == 'hard_off'
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 4
