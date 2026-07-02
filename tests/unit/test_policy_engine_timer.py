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


def _install_minimal_policy_loop_stubs(mod, attrs=None):
    attrs = dict(attrs or {})
    attrs.setdefault('device_policies', ({'device_id': 'HOME_BATTERY', 'target_w': 100},))
    attrs.setdefault('surplus_device_dispatch_action', 'set_target')
    attrs.setdefault('surplus_device_dispatch_decision', 'apply')
    attrs.setdefault('surplus_device_dispatch_device_id', 'HOME_BATTERY')
    attrs.setdefault('surplus_device_dispatch_target', 100)
    attrs.setdefault('surplus_device_targets', ({'device_id': 'HOME_BATTERY', 'target_w': 100},))
    attrs.setdefault('surplus_freeze_until_ts', None)
    attrs.setdefault('surplus_state_clear_reason', '')
    attrs.setdefault('haeo_nz_quarter_key', '2026-07-02T10:00')
    attrs.setdefault('haeo_nz_primary_device_id', 'HOME_BATTERY')

    mod['read_profiles'] = lambda _entities: SimpleNamespace(
        control='AUTOMATIC',
        goal='NET_ZERO',
        forecast='NONE',
        guard='NORMAL_LIMITS',
    )
    mod['read_measurements'] = lambda *_args, **_kwargs: SimpleNamespace(
        quarter_energy_balance_kwh=0.0,
        grid_power_w=0.0,
        pv_power_w=0.0,
        relay_states={},
    )
    mod['evaluate_guard'] = lambda *_args, **_kwargs: SimpleNamespace(guard='NORMAL_LIMITS')
    mod['read_haeo'] = lambda *_args, **_kwargs: None
    mod['compute_haeo_net_zero_plan'] = lambda *_args, **_kwargs: None
    mod['_read_active_surplus_device_ids'] = lambda *_args, **_kwargs: ()
    mod['_read_previous_device_state'] = lambda *_args, **_kwargs: {
        'hard_off_active': False,
        'low_pv_cycles': 0,
        'hard_off_release_ready_cycles': 0,
    }
    mod['_read_previous_force_on_device_ids'] = lambda *_args, **_kwargs: ()
    mod['_read_adjustable_surplus_active'] = lambda *_args, **_kwargs: False
    mod['derive_net_zero_inputs'] = lambda **_kwargs: SimpleNamespace(
        rpnz_w=0.0,
        required_power_consumption_kw=0.0,
        required_power_w=0.0,
        input_quality='ok',
        input_warnings=(),
        remaining_quarter_s=900,
        remaining_quarter_min=15,
    )
    mod['compute_net_zero_engine_outputs'] = lambda *_args, **_kwargs: SimpleNamespace(
        attrs={'previous_device_state': {}, 'previous_ev_device_states': {}}
    )
    mod['net_zero_attrs'] = lambda *_args, **_kwargs: dict(attrs)
    mod['config_trace_attrs'] = lambda: {}
    mod['_selected_previous_device_state_for_outputs'] = lambda _outputs: {'mode': 'idle'}
    mod['_previous_device_state_attrs_from_outputs'] = lambda _outputs: {'mode': 'idle'}
    mod['_trace_state'] = lambda *_args, **_kwargs: 'trace'
    return attrs


def _minimal_entities():
    return {
        'surplus_freeze_until': 'input_datetime.freeze',
        'previous_device_state': 'sensor.previous_device_state',
        'device_policies': 'sensor.device_policies',
        'dispatch_command': 'sensor.dispatch_command',
        'policy_state': 'sensor.policy_state',
        'policy_diagnostics': 'sensor.policy_diagnostics',
    }


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
    assert mod['_policy_engine_diagnostics_interval_seconds'](SimpleNamespace(policy_engine=None)) == 30.0
    assert mod['_policy_engine_diagnostics_interval_seconds'](
        SimpleNamespace(policy_engine=SimpleNamespace(diagnostics_interval_seconds=45))
    ) == 45.0


@pytest.mark.unit
def test_policy_engine_fast_skip_uses_cached_interval(project_root):
    mod = _load_policy_module(project_root)
    state = mod['_POLICY_ENGINE_TIMER_STATE']

    state['last_run_ts'] = 100.0
    state['effective_interval_seconds'] = 5.0

    assert mod['_policy_engine_interval_elapsed_fast'](104.0) is False
    assert mod['_policy_engine_interval_elapsed_fast'](105.0) is True


@pytest.mark.unit
def test_policy_engine_tick_skip_does_not_read_runtime_context(project_root):
    mod = _load_policy_module(project_root)
    state = mod['_POLICY_ENGINE_TIMER_STATE']
    state['last_run_ts'] = 9999999999.0
    state['effective_interval_seconds'] = 30.0

    def _fail_read_runtime_context(*_args, **_kwargs):
        raise AssertionError('skip path must not read runtime context')

    mod['read_runtime_context'] = _fail_read_runtime_context
    mod['ems_policy_engine_tick']()

    assert state['skipped_ticks'] == 1


@pytest.mark.unit
def test_policy_engine_manual_run_updates_cached_intervals(project_root):
    mod = _load_policy_module(project_root)
    state = mod['_POLICY_ENGINE_TIMER_STATE']
    cfg = SimpleNamespace(policy_engine=SimpleNamespace(interval_seconds=8, diagnostics_interval_seconds=40))

    mod['read_runtime_context'] = lambda *_args, **_kwargs: (cfg, {})
    mod['run_policy_loop'] = lambda *_args, **_kwargs: None

    mod['ems_policy_engine_loop']('manual')

    assert state['effective_interval_seconds'] == 8.0
    assert state['effective_diagnostics_interval_seconds'] == 40.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ('trigger_reason', 'expected_reason'),
    [
        ('e2e', 'e2e'),
        ('manual', 'manual'),
    ],
)
def test_policy_engine_diagnostics_manual_and_e2e_force_publish(project_root, trigger_reason, expected_reason):
    mod = _load_policy_module(project_root)
    state = mod['_POLICY_ENGINE_TIMER_STATE']
    state['last_diagnostics_publish_ts'] = 100.0

    should_publish, reason = mod['_should_publish_policy_diagnostics'](
        101.0, trigger_reason, 30.0, False, False
    )

    assert should_publish is True
    assert reason == expected_reason


@pytest.mark.unit
def test_policy_engine_diagnostics_publish_decision_reasons(project_root):
    mod = _load_policy_module(project_root)
    state = mod['_POLICY_ENGINE_TIMER_STATE']

    state['last_diagnostics_publish_ts'] = None
    assert mod['_should_publish_policy_diagnostics'](100.0, 'timer', 30.0, False, False) == (True, 'startup')

    state['last_diagnostics_publish_ts'] = 100.0
    assert mod['_should_publish_policy_diagnostics'](110.0, 'timer', 30.0, False, False) == (False, 'throttled')
    assert mod['_should_publish_policy_diagnostics'](130.0, 'timer', 30.0, False, False) == (True, 'interval')
    assert mod['_should_publish_policy_diagnostics'](110.0, 'timer', 30.0, True, False) == (
        True,
        'canonical_changed',
    )
    assert mod['_should_publish_policy_diagnostics'](110.0, 'timer', 30.0, False, True) == (
        True,
        'warning_changed',
    )
    assert mod['_should_publish_policy_diagnostics'](130.0, 'timer', 30.0, True, False) == (
        True,
        'canonical_changed',
    )
    assert mod['_should_publish_policy_diagnostics'](130.0, 'timer', 30.0, False, True) == (
        True,
        'warning_changed',
    )


@pytest.mark.unit
def test_policy_warning_signature_ignores_volatile_and_explanation_fields(project_root):
    mod = _load_policy_module(project_root)
    attrs = {
        'net_zero_input_quality': 'ok',
        'net_zero_input_warnings': ('missing_pv',),
        'dominant_limitation': 'battery',
        'surplus_explanation': 'first explanation',
        'policy_engine_run_duration_ms': 1,
    }

    first = mod['_policy_warning_signature'](attrs)
    attrs['dominant_limitation'] = 'grid'
    attrs['surplus_explanation'] = 'changed explanation'
    attrs['policy_engine_run_duration_ms'] = 999
    second = mod['_policy_warning_signature'](attrs)
    attrs['net_zero_input_warnings'] = ('missing_pv', 'missing_grid')
    third = mod['_policy_warning_signature'](attrs)

    assert first == second
    assert third != first


@pytest.mark.unit
def test_throttled_diagnostics_does_not_prevent_canonical_publish(project_root):
    mod = _load_policy_module(project_root)
    _install_minimal_policy_loop_stubs(mod)
    state = mod['_POLICY_ENGINE_TIMER_STATE']
    cfg = SimpleNamespace(policy_engine=SimpleNamespace(interval_seconds=5, diagnostics_interval_seconds=30))
    entities = _minimal_entities()
    published = []

    mod['publish_sensor'] = lambda entity, value, attrs=None: published.append((entity, value, attrs))

    mod['run_policy_loop'](100.0, cfg, entities, 'timer')
    published.clear()
    mod['run_policy_loop'](110.0, cfg, entities, 'timer')

    published_entities = [entity for entity, _value, _attrs in published]
    assert entities['device_policies'] in published_entities
    assert entities['dispatch_command'] in published_entities
    assert entities['policy_state'] in published_entities
    assert entities['policy_diagnostics'] not in published_entities
    assert state['last_diagnostics_publish_ts'] == 100.0


@pytest.mark.unit
def test_canonical_changed_forces_diagnostics_publish_before_interval(project_root):
    mod = _load_policy_module(project_root)
    _install_minimal_policy_loop_stubs(mod)
    cfg = SimpleNamespace(policy_engine=SimpleNamespace(interval_seconds=5, diagnostics_interval_seconds=30))
    entities = _minimal_entities()
    published = []

    mod['publish_sensor'] = lambda entity, value, attrs=None: published.append((entity, value, attrs))

    mod['run_policy_loop'](100.0, cfg, entities, 'timer')
    _install_minimal_policy_loop_stubs(
        mod,
        attrs={'device_policies': ({'device_id': 'HOME_BATTERY', 'target_w': 200},)},
    )
    published.clear()
    mod['run_policy_loop'](110.0, cfg, entities, 'timer')

    diagnostics = [item for item in published if item[0] == entities['policy_diagnostics']]
    assert len(diagnostics) == 1
    assert diagnostics[0][2]['policy_engine_diagnostics_publish_reason'] == 'canonical_changed'


@pytest.mark.unit
def test_timing_fields_are_diagnostics_only(project_root):
    mod = _load_policy_module(project_root)
    _install_minimal_policy_loop_stubs(mod)
    cfg = SimpleNamespace(policy_engine=SimpleNamespace(interval_seconds=5, diagnostics_interval_seconds=30))
    entities = _minimal_entities()
    published = []

    mod['publish_sensor'] = lambda entity, value, attrs=None: published.append((entity, value, attrs))

    mod['run_policy_loop'](100.0, cfg, entities, 'timer')

    canonical_attrs = [
        attrs
        for entity, _value, attrs in published
        if entity in (entities['device_policies'], entities['dispatch_command'], entities['policy_state'])
    ]
    diagnostics_attrs = [attrs for entity, _value, attrs in published if entity == entities['policy_diagnostics']][0]

    for attrs in canonical_attrs:
        assert 'policy_engine_run_duration_ms' not in attrs
        assert 'policy_engine_publish_ms' not in attrs
        assert 'policy_engine_published_policy_diagnostics' not in attrs
    assert 'policy_engine_run_duration_ms' in diagnostics_attrs
    assert 'policy_engine_publish_ms' in diagnostics_attrs
    assert diagnostics_attrs['policy_engine_published_policy_diagnostics'] is True


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


@pytest.mark.unit
def test_dispatch_command_hash_stable_for_repeated_clear_all_with_only_now_ts_change(project_root):
    mod = _load_policy_module(project_root)
    attrs_100 = {
        'surplus_device_dispatch_action': 'CLEAR_ALL',
        'surplus_device_dispatch_decision': 'CLEAR_ALL',
        'surplus_device_dispatch_device_id': '',
        'surplus_device_dispatch_target': '',
        'surplus_device_targets': (),
        'surplus_freeze_until_ts': 100.0,
        'surplus_state_clear_reason': '',
    }
    attrs_105 = dict(attrs_100, surplus_freeze_until_ts=105.0)

    first = mod['_dispatch_command_attrs'](attrs_100)
    second = mod['_dispatch_command_attrs'](attrs_105)

    assert first['dispatch_command_hash'] == second['dispatch_command_hash']
    assert first['surplus_freeze_until_ts'] is None
    assert second['surplus_freeze_until_ts'] is None


@pytest.mark.unit
def test_dispatch_command_hash_keeps_activate_freeze_until_ts(project_root):
    mod = _load_policy_module(project_root)
    attrs_130 = {
        'surplus_device_dispatch_action': 'ACTIVATE',
        'surplus_device_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
        'surplus_device_dispatch_device_id': 'EV_CHARGER',
        'surplus_device_dispatch_target': 'ADJUSTABLE',
        'surplus_device_targets': ({'device_id': 'EV_CHARGER', 'enabled': True},),
        'surplus_freeze_until_ts': 130.0,
        'surplus_state_clear_reason': '',
    }
    attrs_135 = dict(attrs_130, surplus_freeze_until_ts=135.0)

    first = mod['_dispatch_command_attrs'](attrs_130)
    second = mod['_dispatch_command_attrs'](attrs_135)

    assert first['dispatch_command_hash'] != second['dispatch_command_hash']
    assert first['surplus_freeze_until_ts'] == 130.0
    assert second['surplus_freeze_until_ts'] == 135.0


@pytest.mark.unit
def test_policy_diagnostics_throttled_for_repeated_policy_inactive_clear_all(project_root):
    mod = _load_policy_module(project_root)
    state = mod['_POLICY_ENGINE_TIMER_STATE']
    cfg = SimpleNamespace(policy_engine=SimpleNamespace(interval_seconds=5, diagnostics_interval_seconds=30))
    entities = _minimal_entities()
    published = []

    mod['publish_sensor'] = lambda entity, value, attrs=None: published.append((entity, value, attrs))
    _install_minimal_policy_loop_stubs(
        mod,
        attrs={
            'surplus_device_dispatch_action': 'CLEAR_ALL',
            'surplus_device_dispatch_decision': 'CLEAR_ALL',
            'surplus_device_dispatch_device_id': '',
            'surplus_device_dispatch_target': '',
            'surplus_device_targets': (),
            'surplus_freeze_until_ts': 100.0,
            'surplus_state_clear_reason': '',
        },
    )

    mod['run_policy_loop'](100.0, cfg, entities, 'timer')
    first_dispatch = [item for item in published if item[0] == entities['dispatch_command']][0]
    assert first_dispatch[2]['surplus_freeze_until_ts'] is None

    published.clear()
    _install_minimal_policy_loop_stubs(
        mod,
        attrs={
            'surplus_device_dispatch_action': 'CLEAR_ALL',
            'surplus_device_dispatch_decision': 'CLEAR_ALL',
            'surplus_device_dispatch_device_id': '',
            'surplus_device_dispatch_target': '',
            'surplus_device_targets': (),
            'surplus_freeze_until_ts': 105.0,
            'surplus_state_clear_reason': '',
        },
    )
    mod['run_policy_loop'](105.0, cfg, entities, 'timer')

    dispatches = [item for item in published if item[0] == entities['dispatch_command']]
    diagnostics = [item for item in published if item[0] == entities['policy_diagnostics']]

    assert len(dispatches) == 1
    assert dispatches[0][2]['surplus_freeze_until_ts'] is None
    assert dispatches[0][1] == first_dispatch[1]
    assert diagnostics == []
    assert state['last_diagnostics_publish_ts'] == 100.0
