import pytest


def _load_writer_module(project_root):
    path = project_root / 'ems_shadow_writers.py'
    src = path.read_text(encoding='utf-8')

    # Poista adapter-importit; injektoidaan korvikkeet testin namespaceen
    filtered = []
    for line in src.splitlines():
        if line.startswith('from ems_adapter.entity_map import'):
            continue
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
        'shadow_victron_setpoint_w': 'input_number.shadow_victron',
        'policy_ev_current_a': 'sensor.policy_ev',
        'shadow_ev_enabled': 'input_boolean.shadow_ev_enabled',
        'shadow_ev_current_a': 'input_number.shadow_ev_current',
        'policy_relay1_command': 'sensor.policy_relay1',
        'policy_relay2_command': 'sensor.policy_relay2',
        'shadow_relay1': 'input_boolean.shadow_relay1',
        'shadow_relay2': 'input_boolean.shadow_relay2',
    }

    ns = {
        '__name__': 'writer_test_module',
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
    }

    exec(src, ns)
    return ns, state, ENT


@pytest.mark.unit
def test_writer_relay_release_turns_shadow_off(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    # policy says relay should be off; shadow currently on
    state[ENT['shadow_relay1']] = True
    state[ENT['policy_relay1_command']] = 0

    result = mod['_write_relay_shadow'](ENT['policy_relay1_command'], ENT['shadow_relay1'], 'relay1')
    assert result['written'] is True
    assert state[ENT['shadow_relay1']] is False
    assert result['reason'] == 'state_changed'


@pytest.mark.unit
def test_writer_manual_battery_is_hands_off(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    state['input_select.ems_control_profile'] = 'MANUAL'
    state[ENT['policy_battery_target_w']] = 1500
    state[ENT['shadow_victron_setpoint_w']] = 250

    result = mod['_write_victron_shadow']()
    assert result['written'] is False
    assert result['reason'] == 'manual_skip'
    assert state[ENT['shadow_victron_setpoint_w']] == 250


@pytest.mark.unit
def test_writer_manual_safe_clamps_to_policy_target(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    state['input_select.ems_control_profile'] = 'MANUAL_SAFE'
    state[ENT['policy_battery_target_w']] = 0
    state[ENT['shadow_victron_setpoint_w']] = -500

    result = mod['_write_victron_shadow']()
    assert result['written'] is True
    assert result['reason'] == 'manual_safe_clamp'
    assert state[ENT['shadow_victron_setpoint_w']] == 0
    
    
@pytest.mark.unit
def test_writer_loop_restores_ev_to_min_current_when_policy_current_is_zero(project_root):
    mod, state, ENT = _load_writer_module(project_root)

    # Neutraloi muut writer-haarat, jotta testin fokus pysyy EV:ssä
    state['input_select.ems_control_profile'] = 'AUTOMATIC'
    state['input_number.ems_deadband_w'] = 100
    state['input_number.ems_ramp_max_w'] = 500

    state[ENT['policy_battery_target_w']] = 0
    state[ENT['shadow_victron_setpoint_w']] = 0

    state[ENT['policy_relay1_command']] = -1
    state[ENT['policy_relay2_command']] = -1
    state[ENT['shadow_relay1']] = False
    state[ENT['shadow_relay2']] = False

    # EV on päällä ja current on yli minimin
    state[ENT['shadow_ev_enabled']] = True
    state[ENT['shadow_ev_current_a']] = 16

    # Policy kertoo, että aktiivinen EV-burn on päättynyt -> strategy 0
    state[ENT['policy_ev_current_a']] = 0
    state['input_number.ems_ev_min_current_a'] = 4

    # Ajetaan koko writer-loop, ei vain _write_ev_shadow()
    mod['ems_shadow_writers_loop']()

    # EV-current pitää palautua minimiin
    assert state[ENT['shadow_ev_current_a']] == 4

    # Writer trace pitää kertoa mitä tapahtui
    trace = state['sensor.ems_shadow_writer_trace']
    assert trace['value'] == 'ACTIVE'
    assert trace['attrs']['ev']['written'] is True
    assert trace['attrs']['ev']['reason'] == 'restore_min_current'
    assert trace['attrs']['ev']['new_current_a'] == 4
