import copy

import pytest
import yaml

from ems_adapter.config_loader import (
    compile_core_config_plan_from_grouped_config,
    load_grouped_ems_config,
)
from ems_adapter.direct_runtime import (
    RuntimePacketSchemaError,
    build_static_topology,
    parse_policy_config_cached,
    parse_tick_frame_v2,
    reset_direct_runtime_cache,
)
from ems_adapter import runtime_context
from ems_core.domain.models import NetZeroState, Profiles
from ems_core.guard.evaluator import evaluate_guard
from ems_core.integrations.haeo_net_zero_plan import compute_haeo_net_zero_plan
from ems_core.net_zero.derived_inputs import derive_net_zero_inputs
from ems_core.net_zero.engine import compute_net_zero_engine_outputs


NOW_TS = 1783134300.0


def _topology(project_root):
    config = load_grouped_ems_config(project_root / 'EMS_config.yaml')
    return build_static_topology(config)


def _policy_packet(*, revision=17):
    return {
        'schema_version': 2,
        'revision': revision,
        'profiles': {
            'control': 'AUTOMATIC',
            'goal': 'NET_ZERO',
            'forecast': 'NONE',
            'guard': 'NORMAL_LIMITS',
        },
        'config': {
            'deadband_w': 50,
            'ramp_w': 1000,
            'strict_limit_w': 8000,
            'default_sp_w': 100,
            'surplus_freeze_s': 300,
            'battery_heartbeat_timeout_s': 360,
            'haeo_stale_timeout_s': 900,
            'nz_battery_floor_default_w': 100,
            'nz_battery_floor_ev_active_w': 100,
            'adjustable_surplus_load': 'EV_CHARGER',
            'adjustable_primary_load': 'HOME_BATTERY',
            'adjustable_surplus_activation_w': 2300,
        },
        'devices': {
            'HOME_BATTERY': {
                'capabilities': {
                    'min_absorb_w': 0,
                    'max_absorb_w': 3800,
                    'max_produce_w': -4000,
                    'step_w': 50,
                    'uses_hard_off_lifecycle': False,
                },
                'policy': {
                    'priority': 3,
                    'default_min_absorb_w': 0,
                },
                'guard': {
                    'protect_soc': 1,
                    'protect_soc_recovery_margin': 1,
                    'protect_min_cell_voltage_v': 3.03,
                    'protect_min_absorb_w': 100,
                },
            },
            'EV_CHARGER': {
                'capabilities': {
                    'min_absorb_w': 1300,
                    'max_absorb_w': 6400,
                    'max_produce_w': 0,
                    'step_w': 400,
                    'uses_hard_off_lifecycle': True,
                },
                'policy': {
                    'priority': 4,
                    'surplus_allowed': False,
                    'force_on': False,
                    'low_pv_threshold_w': 1600,
                    'hard_off_low_pv_cycles': 100,
                    'hard_off_release_cycles': 100,
                },
                'adapter_config': {
                    'current_step_a': 2,
                    'phases': 1,
                    'voltage_v': 230,
                },
            },
            'RELAY1': {
                'capabilities': {
                    'min_absorb_w': 2600,
                    'max_absorb_w': 2600,
                    'max_produce_w': 0,
                    'step_w': 2600,
                    'uses_hard_off_lifecycle': False,
                },
                'policy': {
                    'priority': 1,
                    'surplus_allowed': True,
                    'force_on': False,
                },
            },
            'RELAY2': {
                'capabilities': {
                    'min_absorb_w': 5600,
                    'max_absorb_w': 5600,
                    'max_produce_w': 0,
                    'step_w': 5600,
                    'uses_hard_off_lifecycle': False,
                },
                'policy': {
                    'priority': 2,
                    'surplus_allowed': False,
                    'force_on': False,
                },
            },
        },
    }


def _measurements_packet():
    return {
        'schema_version': 2,
        'grid_power_w': 221.8,
        'quarter_energy_balance_kwh': 0.014,
        'pv_power_w': 489,
        'battery': {
            'soc': 74,
            'min_cell_voltage_v': 3.319,
            'heartbeat': -95.8,
            'heartbeat_age_s': 12.5,
            'target_w': -1800,
            'measured_power_w': -1794,
        },
        'ev': {
            'EV_CHARGER': {
                'enabled': False,
                'current_a': 6,
            },
        },
        'relays': {
            'RELAY1': {'enabled': False},
            'RELAY2': {'enabled': False},
        },
    }


def _state_packet():
    return {
        'schema_version': 2,
        'surplus': {
            'freeze_until': None,
            'active_device_ids': [],
            'previous_device_state': {
                'device_id': 'EV_CHARGER',
                'mode': '',
                'low_pv_cycles': 0,
                'hard_off_release_ready_cycles': 0,
                'hard_off_active': False,
            },
            'previous_device_states': {},
        },
        'haeo': {
            'battery_state_kw': 0,
            'ev_state_kw': 0,
            'battery_age_s': 10,
            'ev_age_s': 15,
        },
        'policy': {
            'haeo_nz_quarter_key': '',
            'haeo_nz_primary_device_id': '',
            'prev_force_on_device_ids': [],
        },
    }


def _parse(project_root, policy=None, measurements=None, state=None, *, now_ts=NOW_TS):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    runtime_cfg, cache_hit = parse_policy_config_cached(topology, policy or _policy_packet())
    frame = parse_tick_frame_v2(
        topology,
        runtime_cfg,
        measurements or _measurements_packet(),
        state or _state_packet(),
        now_ts,
    )
    return topology, runtime_cfg, frame, cache_hit


def _compute(project_root, policy=None, measurements=None, state=None, *, now_ts=NOW_TS):
    _top, cfg, frame, _cache_hit = _parse(
        project_root,
        policy=policy,
        measurements=measurements,
        state=state,
        now_ts=now_ts,
    )
    guard = evaluate_guard(cfg.profiles.guard, frame, cfg)
    profiles = Profiles(cfg.profiles.control, cfg.profiles.goal, cfg.profiles.forecast, guard.guard)
    haeo = frame.haeo_targets(profiles, cfg)
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=frame.quarter_energy_balance_kwh,
        grid_power_w=frame.grid_power_w,
        now_ts=now_ts,
    )
    nz = NetZeroState(
        rpnz_w=derived.rpnz_w,
        required_power_consumption_kw=derived.required_power_consumption_kw,
    )
    haeo_plan = compute_haeo_net_zero_plan(
        profiles,
        cfg,
        haeo,
        now_ts,
        previous_quarter_key=frame.previous_quarter_key,
        previous_primary_load='',
        previous_primary_device_id=frame.previous_primary_device_id,
    )
    previous_ev = frame.selected_previous_device_state(cfg.adjustable_surplus_load)
    adjustable_active = str(cfg.adjustable_surplus_load) in set(frame.active_surplus_device_ids)
    outputs = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        frame,
        haeo,
        nz,
        now_ts,
        freeze_until_ts=frame.surplus_freeze_until_ts,
        ev_burn_active=adjustable_active,
        adjustable_surplus_active=adjustable_active,
        pv_power_kw=frame.pv_power_w / 1000.0,
        ev_hard_off_active=bool(previous_ev['hard_off_active']),
        ev_low_pv_cycles=previous_ev['low_pv_cycles'],
        ev_hard_off_release_ready_cycles=previous_ev['hard_off_release_ready_cycles'],
        relay_device_states=frame.relay_states,
        previous_ev_device_states=frame.previous_ev_device_states,
        previous_force_on_device_ids=frame.previous_force_on_device_ids,
        haeo_nz_plan=haeo_plan,
    )
    return cfg, frame, guard, derived, outputs


@pytest.mark.unit
def test_static_topology_is_built_once_from_minimal_yaml(project_root):
    config = load_grouped_ems_config(project_root / 'EMS_config.yaml')
    plan = compile_core_config_plan_from_grouped_config(config)

    topology = plan.static_topology
    assert topology is not None
    assert topology.device_order == ('HOME_BATTERY', 'EV_CHARGER', 'RELAY1', 'RELAY2')
    assert topology.ev_device_ids == ('EV_CHARGER',)
    assert topology.relay_device_ids == ('RELAY1', 'RELAY2')
    assert topology.policy_config_entity_id == 'sensor.ems_policy_config_runtime'
    assert not hasattr(plan, 'runtime_packet_plan')


@pytest.mark.unit
def test_policy_config_revision_cache_reuses_object_and_reparses_only_new_revision(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    first_packet = _policy_packet(revision=17)
    first, first_hit = parse_policy_config_cached(topology, first_packet)

    malformed_same_revision = {'schema_version': 2, 'revision': 17}
    second, second_hit = parse_policy_config_cached(topology, malformed_same_revision)

    changed = _policy_packet(revision=18)
    changed['config']['deadband_w'] = 125
    third, third_hit = parse_policy_config_cached(topology, changed)

    assert first_hit is False
    assert second_hit is True
    assert second is first
    assert third_hit is False
    assert third is not first
    assert third.revision == 18
    assert third.deadband_w == 125


@pytest.mark.unit
@pytest.mark.parametrize('value', (2300, 0.1))
def test_direct_parser_accepts_positive_adjustable_surplus_activation(project_root, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=180)
    packet['config']['adjustable_surplus_activation_w'] = value

    cfg, cache_hit = parse_policy_config_cached(topology, packet)

    assert cache_hit is False
    assert cfg.adjustable_surplus_activation == float(value)


@pytest.mark.unit
@pytest.mark.parametrize('value', (0, -1))
def test_direct_parser_rejects_non_positive_adjustable_surplus_activation(project_root, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=181)
    packet['config']['adjustable_surplus_activation_w'] = value

    with pytest.raises(
        RuntimePacketSchemaError,
        match=(
            r'RUNTIME_PACKET_INVALID: policy_config\.config\.adjustable_surplus_activation_w '
            r'must be greater than zero'
        ),
    ) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.adjustable_surplus_activation_w'


@pytest.mark.unit
def test_direct_parser_rejects_missing_adjustable_surplus_activation(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=182)
    del packet['config']['adjustable_surplus_activation_w']

    with pytest.raises(RuntimePacketSchemaError, match=r'adjustable_surplus_activation_w missing') as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.adjustable_surplus_activation_w'


@pytest.mark.unit
@pytest.mark.parametrize('value', ('unknown', None, True))
def test_direct_parser_rejects_non_numeric_adjustable_surplus_activation(project_root, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=183)
    packet['config']['adjustable_surplus_activation_w'] = value

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.adjustable_surplus_activation_w'

@pytest.mark.unit
@pytest.mark.parametrize('value', (True, False))
def test_direct_parser_accepts_explicit_hard_off_lifecycle_boolean(project_root, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=184)
    packet['devices']['EV_CHARGER']['capabilities']['uses_hard_off_lifecycle'] = value

    cfg, cache_hit = parse_policy_config_cached(topology, packet)

    assert cache_hit is False
    assert cfg.direct_policy_maps['device_capabilities_by_id']['EV_CHARGER']['uses_hard_off_lifecycle'] is value


@pytest.mark.unit
def test_direct_parser_rejects_missing_hard_off_lifecycle_capability(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=185)
    del packet['devices']['EV_CHARGER']['capabilities']['uses_hard_off_lifecycle']

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.devices.EV_CHARGER.capabilities.uses_hard_off_lifecycle'


@pytest.mark.unit
@pytest.mark.parametrize('value', ('true', 1, 0, None))
def test_direct_parser_rejects_non_boolean_hard_off_lifecycle_capability(project_root, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=186)
    packet['devices']['EV_CHARGER']['capabilities']['uses_hard_off_lifecycle'] = value

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.devices.EV_CHARGER.capabilities.uses_hard_off_lifecycle'


@pytest.mark.unit
def test_policy_config_rejects_relay_as_adjustable_surplus_load(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=18)
    packet['config']['adjustable_surplus_load'] = 'RELAY1'

    with pytest.raises(
        RuntimePacketSchemaError,
        match=(
            r'RUNTIME_PACKET_INVALID: policy_config\.config\.adjustable_surplus_load '
            r'must reference a BATTERY or EV_CHARGER device; RELAY1 has kind RELAY'
        ),
    ) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.adjustable_surplus_load'


@pytest.mark.unit
def test_direct_parser_preserves_float_measurement_signed_discharge_and_runtime_device_values(project_root):
    _top, cfg, frame, _cache_hit = _parse(project_root)

    assert frame.quarter_energy_balance_kwh == 0.014
    assert cfg.max_battery_discharge_w == -4000.0
    assert cfg.direct_policy_maps['device_adapter_by_id']['EV_CHARGER']['current_step_a'] == 2
    assert cfg.adjustable_surplus_load_priority == 4
    assert frame.ev_states['EV_CHARGER']['current_a'] == 6


@pytest.mark.unit
def test_direct_tick_frame_preserves_generic_device_owned_lifecycle_states(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    cfg, _cache_hit = parse_policy_config_cached(topology, _policy_packet(revision=187))
    state = _state_packet()
    state['surplus']['previous_device_states'] = {
        'EV_CHARGER': {
            'device_id': 'EV_CHARGER',
            'mode': 'hard_off',
            'low_pv_cycles': 50,
            'hard_off_release_ready_cycles': 7,
            'hard_off_active': True,
        },
        'EV_GARAGE': {
            'device_id': 'EV_GARAGE',
            'mode': 'restore_min',
            'low_pv_cycles': 3,
            'hard_off_release_ready_cycles': 0,
            'hard_off_active': False,
        },
    }

    frame = parse_tick_frame_v2(topology, cfg, _measurements_packet(), state, NOW_TS)

    assert frame.previous_device_states['EV_CHARGER']['low_pv_cycles'] == 50
    assert frame.previous_device_states['EV_GARAGE']['low_pv_cycles'] == 3
    assert frame.previous_ev_device_states == frame.previous_device_states


@pytest.mark.unit
def test_direct_parser_fails_closed_on_missing_required_measurement(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    cfg, _cache_hit = parse_policy_config_cached(topology, _policy_packet())
    measurements = _measurements_packet()
    del measurements['battery']['soc']

    with pytest.raises(RuntimePacketSchemaError, match=r'RUNTIME_PACKET_INVALID: measurements\.battery\.soc missing') as exc:
        parse_tick_frame_v2(topology, cfg, measurements, _state_packet(), NOW_TS)

    assert exc.value.path == 'measurements.battery.soc'


@pytest.mark.unit
def test_runtime_context_direct_path_reads_exactly_three_packets_and_reuses_config_revision(monkeypatch, project_root):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'EMS_config.yaml'))
    runtime_context._reset_runtime_context_config_cache()
    packets = {
        'sensor.ems_policy_config_runtime': _policy_packet(),
        'sensor.ems_measurements_runtime': _measurements_packet(),
        'sensor.ems_policy_state_runtime': _state_packet(),
    }
    reads = []

    def read_attrs(entity_id, default):
        reads.append(entity_id)
        return copy.deepcopy(packets.get(entity_id, default))

    def forbidden_reader(*_args, **_kwargs):
        raise AssertionError('direct v2 path must not issue scalar HA reads')

    first_cfg, first_entities = runtime_context.read_runtime_context(
        forbidden_reader,
        forbidden_reader,
        forbidden_reader,
        forbidden_reader,
        read_attrs,
    )
    first_metrics = runtime_context.runtime_context_metrics_attrs()
    first_reads = tuple(reads)

    reads.clear()
    second_cfg, second_entities = runtime_context.read_runtime_context(
        forbidden_reader,
        forbidden_reader,
        forbidden_reader,
        forbidden_reader,
        read_attrs,
    )
    second_metrics = runtime_context.runtime_context_metrics_attrs()

    assert first_reads == (
        'sensor.ems_policy_config_runtime',
        'sensor.ems_measurements_runtime',
        'sensor.ems_policy_state_runtime',
    )
    assert tuple(reads) == first_reads
    assert second_cfg is first_cfg
    assert first_entities['_direct_tick_frame'].quarter_energy_balance_kwh == 0.014
    assert second_entities['_direct_tick_frame'].policy_config_revision == 17
    assert first_metrics['policy_engine_runtime_packet_reads'] == 3
    assert second_metrics['policy_engine_runtime_policy_config_cache_hit'] is True
    assert second_metrics['policy_engine_dynamic_runtime_snapshot_ms'] == 0
    assert second_metrics['policy_engine_policy_context_view_ms'] == 0
    assert second_metrics['policy_engine_core_config_materialize_total_ms'] == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ('name', 'mutate', 'expected'),
    (
        (
            'positive_import',
            lambda p, m, s: m.update(grid_power_w=1500, quarter_energy_balance_kwh=0, pv_power_w=1000),
            {'battery_target_w': 100, 'dispatch_action': 'NOOP'},
        ),
        (
            'export_surplus_activation',
            lambda p, m, s: (
                p['devices']['EV_CHARGER']['policy'].update(surplus_allowed=True),
                m.update(grid_power_w=-3000, quarter_energy_balance_kwh=0, pv_power_w=5000),
            ),
            {'battery_target_w': 100, 'dispatch_action': 'ACTIVATE', 'dispatch_device_id': 'EV_CHARGER'},
        ),
        (
            'battery_guard_active',
            lambda p, m, s: m['battery'].update(soc=0.5, min_cell_voltage_v=3.0),
            {'guard': 'BATTERY_PROTECT', 'battery_target_w': 100, 'dispatch_action': 'CLEAR_ALL'},
        ),
        (
            'ev_force_on_binding',
            lambda p, m, s: p['devices']['EV_CHARGER']['policy'].update(force_on=True),
            {'ev_force_on': True},
        ),
        (
            'relay_force_on_binding',
            lambda p, m, s: p['devices']['RELAY1']['policy'].update(force_on=True),
            {'relay1_target_w': 2600, 'relay1_enabled': True},
        ),
        (
            'hard_off_state_transition',
            lambda p, m, s: (
                m.update(pv_power_w=500),
                s['surplus']['previous_device_state'].update(
                    mode='hard_off',
                    low_pv_cycles=100,
                    hard_off_release_ready_cycles=0,
                    hard_off_active=True,
                ),
            ),
            {'ev_policy_mode': 'hard_off', 'ev_hard_off_active': True, 'ev_low_pv_cycles': 101},
        ),
    ),
)
def test_direct_policy_golden_cases(project_root, name, mutate, expected):
    policy = _policy_packet(revision=100)
    measurements = _measurements_packet()
    state = _state_packet()
    mutate(policy, measurements, state)
    if name == 'hard_off_state_transition':
        state['surplus']['previous_device_states'] = {
            'EV_CHARGER': copy.deepcopy(state['surplus']['previous_device_state'])
        }

    _cfg, _frame, guard, _derived, outputs = _compute(
        project_root,
        policy=policy,
        measurements=measurements,
        state=state,
    )
    policies = {item.device_id: item for item in outputs.device_policies}

    if 'guard' in expected:
        assert guard.guard == expected['guard']
    if 'battery_target_w' in expected:
        assert outputs.battery_target_w == expected['battery_target_w']
    if 'dispatch_action' in expected:
        assert outputs.attrs['surplus_device_dispatch_action'] == expected['dispatch_action']
    if 'dispatch_device_id' in expected:
        assert outputs.attrs['surplus_device_dispatch_device_id'] == expected['dispatch_device_id']
    if 'ev_force_on' in expected:
        assert outputs.attrs['ev_force_on'] is expected['ev_force_on']
    if 'relay1_target_w' in expected:
        assert policies['RELAY1'].target_w == expected['relay1_target_w']
        assert policies['RELAY1'].enabled is expected['relay1_enabled']
    if 'ev_policy_mode' in expected:
        assert outputs.attrs['ev_policy_mode'] == expected['ev_policy_mode']
        assert outputs.attrs['ev_hard_off_active'] is expected['ev_hard_off_active']
        assert outputs.attrs['ev_low_pv_cycles'] == expected['ev_low_pv_cycles']


@pytest.mark.unit
def test_direct_policy_golden_quarter_end_large_rpnz(project_root):
    measurements = _measurements_packet()
    measurements.update(grid_power_w=200, quarter_energy_balance_kwh=0.05)

    _cfg, _frame, _guard, derived, outputs = _compute(
        project_root,
        measurements=measurements,
        now_ts=1783134890.0,
    )

    assert derived.rpnz_w == -6000
    assert derived.required_power_w == -3200
    assert outputs.battery_target_w == -2800
    assert outputs.attrs['discharge_limit_sign_mode'] == 'canonical_negative'
    assert outputs.attrs['configured_discharge_limit_w'] == -4000.0

@pytest.mark.unit
def test_runtime_packet_source_error_names_missing_measurements_entity(project_root):
    topology = _topology(project_root)
    packets = {
        topology.policy_config_entity_id: _policy_packet(),
        topology.policy_state_entity_id: _state_packet(),
    }

    def read_attrs(entity_id, default):
        return copy.deepcopy(packets.get(entity_id, default))

    with pytest.raises(
        RuntimePacketSchemaError,
        match=r'RUNTIME_PACKET_INVALID: measurements\.schema_version missing from source entity sensor\.ems_measurements_runtime',
    ) as exc:
        runtime_context.read_runtime_packets(read_attrs, topology)

    assert exc.value.path == 'measurements.schema_version'


@pytest.mark.unit
def test_runtime_packet_sensor_example_pins_expected_entity_ids(project_root):
    source = (project_root / 'example_EMS_runtime_packet_sensors.yaml').read_text(encoding='utf-8')

    assert 'default_entity_id: sensor.ems_policy_config_runtime' in source
    assert 'default_entity_id: sensor.ems_measurements_runtime' in source
    assert 'default_entity_id: sensor.ems_policy_state_runtime' in source


@pytest.mark.unit
def test_runtime_packet_sensor_example_uses_template_strings_for_all_attributes(project_root):
    source = yaml.safe_load(
        (project_root / 'example_EMS_runtime_packet_sensors.yaml').read_text(encoding='utf-8')
    )

    sensors = source['template'][0]['sensor']
    assert len(sensors) == 3
    for sensor in sensors:
        attributes = sensor['attributes']
        non_template_values = {
            key: type(value).__name__
            for key, value in attributes.items()
            if not isinstance(value, str)
        }
        assert non_template_values == {}, (sensor['name'], non_template_values)


@pytest.mark.unit
def test_runtime_packet_sensor_example_guards_missing_haeo_entities(project_root):
    source = yaml.safe_load(
        (project_root / 'example_EMS_runtime_packet_sensors.yaml').read_text(encoding='utf-8')
    )

    sensors = source['template'][0]['sensor']
    state_sensor = next(sensor for sensor in sensors if sensor['name'] == 'EMS Policy State Runtime')
    haeo_template = state_sensor['attributes']['haeo']

    compact = ''.join(haeo_template.split())
    assert 'states.sensor.battery_active_power' in haeo_template
    assert 'states.sensor.ev_akut_active_power' in haeo_template
    assert "battery_fresh_entityisnotnoneandhas_value('sensor.battery_active_power')" in compact
    assert "ev_fresh_entityisnotnoneandhas_value('sensor.ev_akut_active_power')" in compact
    assert 'as_timestamp(battery_fresh_entity.last_updated,0)' in compact
    assert 'as_timestamp(ev_fresh_entity.last_updated,0)' in compact
    assert 'states.sensor.battery_active_power.last_updated' not in haeo_template
    assert 'states.sensor.ev_akut_active_power.last_updated' not in haeo_template



@pytest.mark.unit
def test_runtime_packet_sensor_example_uses_production_source_entity_bindings(project_root):
    source = (project_root / 'example_EMS_runtime_packet_sensors.yaml').read_text(encoding='utf-8')

    expected = (
        'sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc',
        'sensor.victron_mqtt_b827eb48c929_battery_1_battery_min_cell_voltage',
        'sensor.victron_mqtt_b827eb48c929_battery_1_battery_power',
        'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point',
        'switch.charger_control',
        'number.charger_current_level',
        'switch.relay_1_2',
        'switch.relay_2_2',
        'sensor.ems_policy_state_pyscript',
        'sensor.haeo_battery_power_active',
        'sensor.haeo_ev_battery_power_active',
        'sensor.battery_active_power',
        'sensor.ev_akut_active_power',
    )
    for entity_id in expected:
        assert entity_id in source

    forbidden_placeholders = (
        "sensor.battery_soc'",
        "sensor.battery_min_cell_voltage'",
        "sensor.battery_heartbeat'",
        "sensor.current_battery_setpoint'",
        "sensor.battery_measured_power'",
        "switch.ev_charger'",
        "number.ev_charger_current'",
        "switch.relay1'",
        "switch.relay2'",
        "sensor.ems_policy_state'",
    )
    for entity_id in forbidden_placeholders:
        assert entity_id not in source


@pytest.mark.unit
def test_runtime_packet_policy_config_revision_is_automatic_not_missing_helper(project_root):
    source = yaml.safe_load(
        (project_root / 'example_EMS_runtime_packet_sensors.yaml').read_text(encoding='utf-8')
    )
    sensors = source['template'][0]['sensor']
    policy_sensor = next(sensor for sensor in sensors if sensor['name'] == 'EMS Policy Config Runtime')
    revision_template = policy_sensor['attributes']['revision']

    assert 'input_number.ems_policy_config_revision' not in revision_template
    assert 'source.last_updated' in revision_template
    assert 'namespace(latest=0.0)' in revision_template
    assert 'input_select.ems_control_profile' in revision_template
    assert 'input_boolean.ems_surplus_adjustable_active' in revision_template
    assert 'input_boolean.ems_ev_surplus_allowed' not in revision_template
    assert 'input_boolean.ems_ev_force_on' in revision_template


@pytest.mark.unit
def test_runtime_packet_policy_config_uses_runtime_helpers_instead_of_hardcoded_device_policy(project_root):
    source = yaml.safe_load(
        (project_root / 'example_EMS_runtime_packet_sensors.yaml').read_text(encoding='utf-8')
    )
    sensors = source['template'][0]['sensor']
    policy_sensor = next(sensor for sensor in sensors if sensor['name'] == 'EMS Policy Config Runtime')
    config_template = policy_sensor['attributes']['config']
    devices_template = policy_sensor['attributes']['devices']

    assert "states('input_number.ems_deadband_w')" in config_template
    assert "states('input_select.ems_adjustable_surplus_load')" in config_template
    assert "states('input_number.ems_max_battery_charge_w')" in devices_template
    assert "states('input_number.ems_max_battery_discharge_w')" in devices_template
    assert "states('input_number.ems_ev_current_step_a')" in devices_template
    assert "states('input_number.ems_ev_charger_phases')" in devices_template
    assert "states('input_number.ems_ev_voltage_v')" in devices_template
    assert "input_number.ems_ev_power_step_w" not in devices_template
    assert "input_boolean.ems_surplus_adjustable_active" in devices_template
    assert "input_boolean.ems_ev_force_on" in devices_template
    assert "input_boolean.ems_relay1_force_on" in devices_template
    assert "input_boolean.ems_relay2_force_on" in devices_template


@pytest.mark.unit
def test_direct_parser_requires_and_preserves_heartbeat_age(project_root):
    _top, _cfg, frame, _cache_hit = _parse(project_root)
    assert frame.battery_heartbeat_age_s == 12.5

    reset_direct_runtime_cache()
    topology = _topology(project_root)
    cfg, _cache_hit = parse_policy_config_cached(topology, _policy_packet())
    measurements = _measurements_packet()
    del measurements['battery']['heartbeat_age_s']

    with pytest.raises(
        RuntimePacketSchemaError,
        match=r'RUNTIME_PACKET_INVALID: measurements\.battery\.heartbeat_age_s missing',
    ):
        parse_tick_frame_v2(topology, cfg, measurements, _state_packet(), NOW_TS)


@pytest.mark.unit
def test_runtime_packet_measurements_do_not_mask_missing_required_sources_with_zero_or_false(project_root):
    source = yaml.safe_load(
        (project_root / 'example_EMS_runtime_packet_sensors.yaml').read_text(encoding='utf-8')
    )
    sensors = source['template'][0]['sensor']
    measurement_sensor = next(sensor for sensor in sensors if sensor['name'] == 'EMS Measurements Runtime')

    battery_template = measurement_sensor['attributes']['battery']
    ev_template = measurement_sensor['attributes']['ev']
    relay_template = measurement_sensor['attributes']['relays']
    battery_compact = ''.join(battery_template.split())
    ev_compact = ''.join(ev_template.split())
    relay_compact = ''.join(relay_template.split())

    assert "states('sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc')" in battery_compact
    assert "|float(0)" not in battery_compact
    assert "elsestates('switch.charger_control')" in ev_compact
    assert "elsestates('switch.relay_1_2')" in relay_compact
    assert "elsestates('switch.relay_2_2')" in relay_compact
