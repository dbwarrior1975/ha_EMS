from types import SimpleNamespace

import pytest


def _load_policy_module(project_root):
    path = project_root / 'ems_policy_engine.py'
    src = path.read_text(encoding='utf-8')

    filtered = []
    for line in src.splitlines():
        if line.startswith('from ems_adapter.ha_adapter import'):
            continue
        if line.startswith('from ems_adapter.runtime_context import'):
            continue
        filtered.append(line)
    src = '\n'.join(filtered)

    trigger_calls = []

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

    ns = {
        '__name__': 'policy_timer_test_module',
        '__file__': str(path),
        'time_trigger': _time_trigger,
        'state_trigger': _state_trigger,
        'get_bool': lambda *args, **kwargs: False,
        'get_float': lambda *args, **kwargs: 0.0,
        'get_int': lambda *args, **kwargs: 0,
        'get_str': lambda *args, **kwargs: '',
        'age_seconds': lambda *args, **kwargs: 0.0,
        'get_attr': lambda *args, **kwargs: kwargs.get('default'),
        'parse_input_datetime_ts': lambda *args, **kwargs: 0.0,
        'publish_sensor': lambda *args, **kwargs: None,
        '_GROUPED_CONFIG_DUAL_READ_STATUS': {},
        'config_trace_attrs': lambda: {},
        'read_runtime_context': lambda *args, **kwargs: (None, {}),
        '_TEST_TRIGGER_CALLS': trigger_calls,
    }
    code = compile(src, str(path), 'exec')
    exec(code, ns)
    return ns


@pytest.mark.unit
def test_policy_engine_uses_fixed_2_second_time_trigger(project_root):
    mod = _load_policy_module(project_root)

    time_triggers = [
        args[0]
        for kind, args, _kwargs in mod['_TEST_TRIGGER_CALLS']
        if kind == 'time' and args
    ]
    state_triggers = [
        args[0]
        for kind, args, _kwargs in mod['_TEST_TRIGGER_CALLS']
        if kind == 'state' and args
    ]

    assert 'period(now, 2s)' in time_triggers
    assert not state_triggers


@pytest.mark.unit
def test_policy_engine_source_has_no_raw_runtime_state_triggers(project_root):
    source = (project_root / 'ems_policy_engine.py').read_text(encoding='utf-8')

    assert 'sensor.average_active_power_2' not in source
    assert 'sensor.hourly_energy_balance' not in source
    assert 'sensor.pv_instant_power_2' not in source
    assert '@state_trigger' not in source


@pytest.mark.unit
def test_policy_engine_interval_elapsed_semantics(project_root):
    mod = _load_policy_module(project_root)
    state = mod['_POLICY_ENGINE_TIMER_STATE']

    state['last_run_ts'] = None
    assert mod['_policy_engine_interval_elapsed'](0.0, 5.0) is True

    state['last_run_ts'] = 0.0
    assert mod['_policy_engine_interval_elapsed'](2.0, 5.0) is False
    assert mod['_policy_engine_interval_elapsed'](4.0, 5.0) is False
    assert mod['_policy_engine_interval_elapsed'](6.0, 5.0) is True

    assert mod['_policy_engine_interval_elapsed'](2.0, 2.0) is True
    assert mod['_policy_engine_interval_elapsed'](4.0, 2.0) is True


@pytest.mark.unit
def test_policy_engine_run_and_skip_counters_update_only_on_matching_events(project_root):
    mod = _load_policy_module(project_root)
    state = mod['_POLICY_ENGINE_TIMER_STATE']
    state['last_run_ts'] = None
    state['ticks_seen'] = 0
    state['runs_seen'] = 0
    state['skipped_ticks'] = 0

    mod['_note_policy_tick'](0.0)
    mod['_note_policy_skip']()
    assert state['ticks_seen'] == 1
    assert state['skipped_ticks'] == 1
    assert state['runs_seen'] == 0
    assert state['last_run_ts'] is None

    mod['_note_policy_run'](6.0)
    assert state['runs_seen'] == 1
    assert state['last_run_ts'] == 6.0
    assert state['skipped_ticks'] == 1


@pytest.mark.unit
def test_policy_engine_interval_reads_core_config_value(project_root):
    mod = _load_policy_module(project_root)

    assert mod['_policy_engine_interval_seconds'](SimpleNamespace(policy_engine=None)) == 5.0
    assert mod['_policy_engine_interval_seconds'](
        SimpleNamespace(policy_engine=SimpleNamespace(interval_seconds=7))
    ) == 7.0


@pytest.mark.unit
def test_policy_engine_hash_boundary_ignores_timer_diagnostics(project_root):
    mod = _load_policy_module(project_root)
    attrs = {
        'device_policies': (
            {'device_id': 'HOME_BATTERY', 'target_w': 100, 'mode': 'net_zero'},
        ),
        'policy_engine_ticks_seen': 1,
        'policy_engine_last_tick_ts': 10.0,
    }

    first_hash = mod['_device_policies_hash'](attrs)
    attrs['policy_engine_ticks_seen'] = 99
    attrs['policy_engine_last_tick_ts'] = 1234.0
    second_hash = mod['_device_policies_hash'](attrs)

    assert first_hash == second_hash
