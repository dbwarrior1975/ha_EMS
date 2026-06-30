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
    trigger_calls = []
    calls = []

    def _time_trigger(*args, **kwargs):
        trigger_calls.append(('time', args, kwargs))
        def deco(fn):
            return fn
        return deco

    def _state_trigger(*args, **kwargs):
        trigger_calls.append(('state', args, kwargs))
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
        calls.append(('set_boolean', entity_id, bool(on)))
        state[entity_id] = bool(on)

    def set_number(entity_id, value):
        calls.append(('set_number', entity_id, value))
        state[entity_id] = value

    def publish_sensor(entity_id, value, attrs=None):
        state[entity_id] = {'value': value, 'attrs': attrs or {}}

    ENT = {
        'actuator_battery_setpoint_w': 'input_number.test_actuator_battery_setpoint_w',
        'actuator_ev_enabled': 'input_boolean.actuator_ev_enabled',
        'actuator_ev_current_a': 'input_number.test_actuator_ev_current_a',
        'actuator_relay1': 'input_boolean.actuator_relay1',
        'actuator_relay2': 'input_boolean.actuator_relay2',
        'device_policies': 'sensor.ems_device_policies_pyscript',
        'policy_decision_trace': 'sensor.ems_policy_decision_trace_pyscript',
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
        '_TEST_TRIGGER_CALLS': trigger_calls,
        '_TEST_CALLS': calls,
    }
    _install_core_capabilities(ns)

    code = compile(src, str(path), 'exec')
    exec(code, ns)
    return ns, state, ENT


def _install_device_policies(mod, policies):
    ent = mod.get('ENT', {})
    _install_device_policies_by_entity(
        mod,
        {
            ent.get('device_policies', 'sensor.ems_device_policies_pyscript'): tuple(policies),
            ent.get('policy_decision_trace', 'sensor.ems_policy_decision_trace_pyscript'): tuple(policies),
        },
    )


def _install_device_policies_by_entity(mod, mapping):
    def get_attr(entity_id, attr, default=None):
        if attr == 'device_policies':
            return tuple(mapping.get(entity_id, ()))
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
def test_writer_ev_without_device_policy_skips_without_writing_even_without_device_id(project_root):
    mod, state, ENT = _load_writer_module(project_root)

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
    state[ENT['actuator_battery_setpoint_w']] = -500

    result = mod['_write_battery_actuator']()
    assert result['written'] is True
    assert result['reason'] == 'manual_safe_clamp'
    assert result['policy_source'] == 'device_policy'
    assert state[ENT['actuator_battery_setpoint_w']] == 0


@pytest.mark.unit
def test_writer_ev_without_device_policy_skips_without_writing(project_root):
    mod, state, ENT = _load_writer_module(project_root)

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

    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 4
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

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
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

    result = mod['_write_ev_actuator']()

    assert result['written'] is True
    assert result['reason'] == 'capability_blocked_absorb'
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 6


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

    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 4
    state['input_number.ems_ev_current_step_a'] = 4
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

    result = mod['_write_ev_actuator']()

    assert result['written'] is True
    assert result['policy_source'] == 'device_policy'
    assert result['target_current_a'] == 24
    assert state[ENT['actuator_ev_current_a']] == 24


@pytest.mark.unit
def test_writer_ev_exact_max_target_w_maps_to_supported_max_current(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'EV_CHARGER',
                'target_w': 6440,
                'enabled': True,
                'mode': 'burn',
            }
        ],
    )

    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 6
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

    result = mod['_write_ev_actuator']()

    assert result['written'] is True
    assert result['policy_target_w'] == 6440
    assert result['target_current_a'] == 28
    assert state[ENT['actuator_ev_enabled']] is True
    assert state[ENT['actuator_ev_current_a']] == 28


@pytest.mark.unit
def test_writer_relay_device_policy_can_turn_off_actuator(project_root):
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

    state[ENT['actuator_relay1']] = True

    result = mod['_write_relay_actuator'](
        '',
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
        '',
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

    state[ENT['actuator_relay1']] = True

    result = mod['_write_relay_actuator'](
        '',
        ENT['actuator_relay1'],
        'relay1',
        device_id='RELAY1',
    )

    assert result['written'] is False
    assert result['reason'] == 'policy_skip'
    assert result['policy_source'] == 'device_policy'
    assert state[ENT['actuator_relay1']] is True


@pytest.mark.unit
def test_writer_loop_uses_device_policies_across_all_devices(project_root):
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
    state['input_number.ems_ev_min_power_w'] = 1380
    state['input_number.ems_ev_max_power_w'] = 6440
    state['input_number.ems_ev_current_step_a'] = 2
    state['input_number.ems_ev_charger_phases'] = 1
    state[ENT['actuator_battery_setpoint_w']] = 0
    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 6
    state[ENT['actuator_relay1']] = False
    state[ENT['actuator_relay2']] = True

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
            'current_step_a': 'input_number.ems_ev_current_step_a',
            'phases': 'input_number.ems_ev_charger_phases',
            'voltage_v': 'input_number.ems_ev_voltage_v',
            'min_absorb_w': 1380,
            'max_absorb_w': 6440,
        },
        'GARAGE_EV': {
            'kind': 'EV_CHARGER',
            'enabled': 'switch.garage_ev_enabled',
            'current_a': 'number.garage_ev_current_a',
            'current_step_a': 'input_number.garage_ev_current_step_a',
            'phases': 'input_number.garage_ev_phases',
            'voltage_v': 'input_number.garage_ev_voltage_v',
            'min_absorb_w': 1380,
            'max_absorb_w': 3680,
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
    state['input_number.garage_ev_current_step_a'] = 2
    state['input_number.garage_ev_phases'] = 1
    state['input_number.ems_ev_current_step_a'] = 2
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230
    state['input_number.garage_ev_voltage_v'] = 230
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
def test_writer_loop_disables_ev_and_restores_min_current_when_target_w_is_zero(project_root):
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

    state[ENT['actuator_battery_setpoint_w']] = 0

    state[ENT['actuator_relay1']] = False
    state[ENT['actuator_relay2']] = False

    # EV on päällä ja current on yli minimin
    state[ENT['actuator_ev_enabled']] = True
    state[ENT['actuator_ev_current_a']] = 16

    # Policy kertoo, että aktiivinen EV-burn on päättynyt -> target_w 0
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

    # Ajetaan koko writer-loop, ei vain _write_ev_actuator()
    mod['ems_actuator_writers_loop']()

    # EV-current pitää palautua minimiin ja laturi sammuttaa
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 6

    # Writer trace pitää kertoa mitä tapahtui
    trace = state['sensor.ems_actuator_writer_trace']
    assert trace['value'] == 'ACTIVE'
    assert trace['attrs']['devices']['EV_CHARGER']['written'] is True
    assert trace['attrs']['devices']['EV_CHARGER']['reason'] == 'target_zero_disable'
    assert trace['attrs']['devices']['EV_CHARGER']['target_current_a'] == 6


@pytest.mark.unit
def test_writer_restore_min_keeps_enabled_charger_alive(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'EV_CHARGER',
                'target_w': 0,
                'enabled': True,
                'mode': 'restore_min',
            }
        ],
    )

    state[ENT['actuator_ev_enabled']] = True
    state[ENT['actuator_ev_current_a']] = 16
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

    result = mod['_write_ev_actuator']()

    assert result['reason'] in {'restore_min', 'restore_min_current'}
    assert result['target_current_a'] == 6
    assert result['enabled_changed'] is False
    assert result['current_changed'] is True
    assert state[ENT['actuator_ev_enabled']] is True
    assert state[ENT['actuator_ev_current_a']] == 6


@pytest.mark.unit
def test_writer_restore_min_does_not_start_disabled_charger(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {
                'device_id': 'EV_CHARGER',
                'target_w': 0,
                'enabled': True,
                'mode': 'restore_min',
            }
        ],
    )

    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 16
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

    result = mod['_write_ev_actuator']()

    assert result['reason'] in {'restore_min', 'restore_min_current'}
    assert result['target_current_a'] == 6
    assert result['enabled_changed'] is False
    assert result['current_changed'] is True
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 6


@pytest.mark.unit
def test_writer_hard_off_disables_ev_and_sets_current_to_derived_min(project_root):
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
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

    result = mod['_write_ev_actuator']()
    assert result['written'] is True
    assert result['reason'] == 'hard_off'
    assert state[ENT['actuator_ev_enabled']] is False
    assert state[ENT['actuator_ev_current_a']] == 6


@pytest.mark.unit
def test_writer_state_trigger_uses_device_policies_not_policy_trace(project_root):
    mod, _state, _ENT = _load_writer_module(project_root)

    state_triggers = [
        args[0]
        for kind, args, _kwargs in mod['_TEST_TRIGGER_CALLS']
        if kind == 'state' and args
    ]

    assert any('sensor.ems_device_policies_pyscript' in trigger for trigger in state_triggers)
    assert all('sensor.ems_policy_decision_trace_pyscript' not in trigger for trigger in state_triggers)
    assert any('input_select.ems_control_profile' in trigger for trigger in state_triggers)


@pytest.mark.unit
def test_writer_uses_canonical_device_policies_before_trace_fallback(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies_by_entity(
        mod,
        {
            ENT['device_policies']: (
                {'device_id': 'RELAY1', 'target_w': 2500, 'enabled': True, 'mode': 'relay'},
            ),
            ENT['policy_decision_trace']: (
                {'device_id': 'RELAY1', 'target_w': 0, 'enabled': False, 'mode': 'relay'},
            ),
        },
    )

    state[ENT['actuator_relay1']] = False

    result = mod['_write_relay_actuator']('', ENT['actuator_relay1'], 'relay1', device_id='RELAY1')

    assert result['written'] is True
    assert state[ENT['actuator_relay1']] is True


@pytest.mark.unit
def test_writer_can_still_use_trace_fallback_when_canonical_missing(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies_by_entity(
        mod,
        {
            ENT['policy_decision_trace']: (
                {'device_id': 'RELAY1', 'target_w': 2500, 'enabled': True, 'mode': 'relay'},
            ),
        },
    )

    state[ENT['actuator_relay1']] = False

    result = mod['_write_relay_actuator']('', ENT['actuator_relay1'], 'relay1', device_id='RELAY1')

    assert result['written'] is True
    assert state[ENT['actuator_relay1']] is True


@pytest.mark.unit
def test_writer_repeated_identical_relay_policy_does_not_repeat_service_call(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {'device_id': 'RELAY1', 'target_w': 2500, 'enabled': True, 'mode': 'relay'},
        ],
    )

    state[ENT['actuator_relay1']] = False

    mod['_write_relay_actuator']('', ENT['actuator_relay1'], 'relay1', device_id='RELAY1')
    mod['_write_relay_actuator']('', ENT['actuator_relay1'], 'relay1', device_id='RELAY1')

    assert mod['_TEST_CALLS'] == [('set_boolean', ENT['actuator_relay1'], True)]


@pytest.mark.unit
def test_writer_repeated_identical_ev_current_policy_does_not_repeat_service_call(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {'device_id': 'EV_CHARGER', 'target_w': 3680, 'enabled': True, 'mode': 'burn'},
        ],
    )

    state[ENT['actuator_ev_enabled']] = False
    state[ENT['actuator_ev_current_a']] = 6
    state['input_number.ems_ev_current_step_a'] = 1
    state['input_number.ems_ev_charger_phases'] = 1
    state['input_number.ems_ev_voltage_v'] = 230

    mod['_write_ev_actuator']()
    mod['_write_ev_actuator']()

    assert mod['_TEST_CALLS'] == [
        ('set_boolean', ENT['actuator_ev_enabled'], True),
        ('set_number', ENT['actuator_ev_current_a'], 16),
    ]


@pytest.mark.unit
def test_writer_repeated_identical_battery_policy_respects_deadband_without_repeat_write(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    _install_device_policies(
        mod,
        [
            {'device_id': 'HOME_BATTERY', 'target_w': 500, 'enabled': True, 'mode': 'power'},
        ],
    )

    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 50
    state['input_number.ems_ramp_max_w'] = 1000
    state[ENT['actuator_battery_setpoint_w']] = 0

    mod['_write_battery_actuator']()
    mod['_write_battery_actuator']()

    assert mod['_TEST_CALLS'] == [
        ('set_number', ENT['actuator_battery_setpoint_w'], 500),
    ]
