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
    parse_tick_frame_v3,
    reset_direct_runtime_cache,
)
from ems_adapter import runtime_context
from ems_core.domain.models import HaeoTargets, NetZeroState, Profiles
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
        'schema_version': 3,
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
            'primary_device_id': 'HOME_BATTERY',
        },
        'devices': {
            'HOME_BATTERY': {
                'capabilities': {
                    'min_absorb_w': 0,
                    'max_absorb_w': 3800,
                    'max_produce_w': -4000,
                    'step_w': 50,
                    'uses_hard_off_lifecycle': False,
                    'supports_primary_regulation': True,
                    'supports_residual_regulation': True,
                },
                'policy': {
                    'priority': 3,
                    'surplus_allowed': True,
                    'surplus_dispatch_mode': 'max_absorb',
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
                    'supports_primary_regulation': True,
                    'supports_residual_regulation': False,
                },
                'policy': {
                    'priority': 4,
                    'surplus_allowed': False,
                    'surplus_dispatch_mode': 'max_absorb',
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
                    'supports_primary_regulation': False,
                    'supports_residual_regulation': False,
                },
                'policy': {
                    'priority': 1,
                    'surplus_allowed': True,
                    'surplus_dispatch_mode': 'fixed',
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
                    'supports_primary_regulation': False,
                    'supports_residual_regulation': False,
                },
                'policy': {
                    'priority': 2,
                    'surplus_allowed': False,
                    'surplus_dispatch_mode': 'fixed',
                    'force_on': False,
                },
            },
        },
    }


def _measurements_packet():
    return {
        'schema_version': 3,
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
        'schema_version': 3,
        'surplus': {
            'freeze_until': None,
            'active_device_ids': [],
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
    frame = parse_tick_frame_v3(
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
    ev_device_id = str((cfg.device_ids_by_kind('EV_CHARGER') or ('EV_CHARGER',))[0])
    adjustable_active = ev_device_id in set(frame.active_surplus_device_ids)
    outputs = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        frame,
        haeo,
        nz,
        now_ts,
        freeze_until_ts=frame.surplus_freeze_until_ts,
        pv_power_kw=frame.pv_power_w / 1000.0,
        relay_device_states=frame.relay_states,
        previous_device_states=frame.previous_device_states,
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

    malformed_same_revision = {'schema_version': 3, 'revision': 17}
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
    assert third.global_config.deadband_w == 125


@pytest.mark.unit
@pytest.mark.parametrize(
    ('field', 'value'),
    (
        ('adjustable_surplus_load', 'EV_CHARGER'),
        ('adjustable_surplus_activation_w', 2300),
    ),
)
def test_direct_parser_rejects_removed_legacy_surplus_config_fields(project_root, field, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=180)
    packet['config'][field] = value

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == f'policy_config.config.{field}'
    assert 'legacy field removed' in str(exc.value)


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
@pytest.mark.parametrize('field', ('supports_primary_regulation', 'supports_residual_regulation'))
@pytest.mark.parametrize('value', (True, False))
def test_direct_parser_accepts_explicit_regulation_capability_booleans(project_root, field, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=187)
    packet['devices']['EV_CHARGER']['capabilities'][field] = value

    cfg, cache_hit = parse_policy_config_cached(topology, packet)

    assert cache_hit is False
    assert cfg.direct_policy_maps['device_capabilities_by_id']['EV_CHARGER'][field] is value


@pytest.mark.unit
@pytest.mark.parametrize('field', ('supports_primary_regulation', 'supports_residual_regulation'))
def test_direct_parser_rejects_missing_regulation_capability(project_root, field):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=188)
    del packet['devices']['EV_CHARGER']['capabilities'][field]

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == f'policy_config.devices.EV_CHARGER.capabilities.{field}'


@pytest.mark.unit
@pytest.mark.parametrize('field', ('supports_primary_regulation', 'supports_residual_regulation'))
@pytest.mark.parametrize('value', ('true', 1, 0, None, 'unknown'))
def test_direct_parser_rejects_non_boolean_regulation_capability(project_root, field, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=189)
    packet['devices']['EV_CHARGER']['capabilities'][field] = value

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == f'policy_config.devices.EV_CHARGER.capabilities.{field}'


@pytest.mark.unit
def test_policy_config_rejects_removed_legacy_adjustable_surplus_alias(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=18)
    packet['config']['adjustable_surplus_load'] = 'RELAY1'

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.adjustable_surplus_load'


@pytest.mark.unit
def test_direct_runtime_v3_rejects_v2_policy_packet(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=189)
    packet['schema_version'] = 2

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.schema_version'
    assert 'must equal 3' in str(exc.value)


@pytest.mark.unit
def test_direct_runtime_v3_requires_primary_device_id_key(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=1891)
    packet['config'].pop('primary_device_id')
    packet['config']['adjustable_primary_load'] = 'HOME_BATTERY'

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.primary_device_id'


@pytest.mark.unit
def test_direct_parser_rejects_primary_without_primary_regulation_capability(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=190)
    packet['devices']['HOME_BATTERY']['capabilities']['supports_primary_regulation'] = False

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.primary_device_id'
    assert 'does not support primary regulation' in str(exc.value)


@pytest.mark.unit
def test_direct_parser_rejects_combination_without_residual_regulator(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=191)
    packet['devices']['HOME_BATTERY']['capabilities']['supports_residual_regulation'] = False
    packet['devices']['EV_CHARGER']['capabilities']['supports_residual_regulation'] = False

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.primary_device_id'
    assert 'no residual regulator capability' in str(exc.value)


@pytest.mark.unit
def test_direct_parser_primary_role_is_independent_of_removed_surplus_alias(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=192)
    packet['config']['primary_device_id'] = 'HOME_BATTERY'

    cfg, cache_hit = parse_policy_config_cached(topology, packet)

    assert cache_hit is False
    assert cfg.global_config.primary_device_id == 'HOME_BATTERY'
    assert not hasattr(cfg, 'adjustable_surplus_load')
    assert cfg.device_capabilities_by_id['HOME_BATTERY']['supports_primary_regulation'] is True


@pytest.mark.unit
def test_direct_parser_preserves_float_measurement_signed_discharge_and_runtime_device_values(project_root):
    _top, cfg, frame, _cache_hit = _parse(project_root)

    assert frame.quarter_energy_balance_kwh == 0.014
    assert cfg.v3_battery_capability('max_produce_w') == -4000.0
    assert cfg.direct_policy_maps['device_adapter_by_id']['EV_CHARGER']['current_step_a'] == 2
    assert cfg.device_policy_by_id['EV_CHARGER']['priority'] == 4
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

    frame = parse_tick_frame_v3(topology, cfg, _measurements_packet(), state, NOW_TS)

    assert frame.previous_device_states['EV_CHARGER']['low_pv_cycles'] == 50
    assert frame.previous_device_states['EV_GARAGE']['low_pv_cycles'] == 3


@pytest.mark.unit
def test_direct_parser_fails_closed_on_missing_required_measurement(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    cfg, _cache_hit = parse_policy_config_cached(topology, _policy_packet())
    measurements = _measurements_packet()
    del measurements['battery']['soc']

    with pytest.raises(RuntimePacketSchemaError, match=r'RUNTIME_PACKET_INVALID: measurements\.battery\.soc missing') as exc:
        parse_tick_frame_v3(topology, cfg, measurements, _state_packet(), NOW_TS)

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
    assert 'policy_engine_core_config_view_snapshot_ms' not in second_metrics
    assert 'policy_engine_policy_context_view_ms' not in second_metrics
    assert 'policy_engine_core_config_materialize_total_ms' not in second_metrics


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
                m.update(grid_power_w=-7000, quarter_energy_balance_kwh=0, pv_power_w=8000),
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
            {'ev_force_on_candidate': True},
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
                s['surplus']['previous_device_states'].update(
                    EV_CHARGER={
                        'device_id': 'EV_CHARGER',
                        'mode': 'hard_off',
                        'low_pv_cycles': 100,
                        'hard_off_release_ready_cycles': 0,
                        'hard_off_active': True,
                    }
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
        assert outputs.attrs['surplus_dispatch_action'] == expected['dispatch_action']
    if 'dispatch_device_id' in expected:
        assert outputs.attrs['surplus_dispatch_device_id'] == expected['dispatch_device_id']
    if 'ev_force_on_candidate' in expected:
        candidates = {item['device_id']: item for item in outputs.attrs['surplus_candidates']}
        assert candidates['EV_CHARGER']['force_on'] is expected['ev_force_on_candidate']
    if 'relay1_target_w' in expected:
        assert policies['RELAY1'].target_w == expected['relay1_target_w']
        assert policies['RELAY1'].enabled is expected['relay1_enabled']
    if 'ev_policy_mode' in expected:
        assert policies['EV_CHARGER'].mode == expected['ev_policy_mode']
        lifecycle = outputs.attrs['device_lifecycle_states']['EV_CHARGER']
        assert lifecycle['hard_off_active'] is expected['ev_hard_off_active']
        assert lifecycle['low_pv_cycles'] == expected['ev_low_pv_cycles']


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
    assert 'input_boolean.ems_surplus_adjustable_active' not in revision_template
    assert 'input_boolean.ems_ev_surplus_allowed' not in revision_template
    assert 'input_boolean.ems_ev_force_on' in revision_template


@pytest.mark.unit
def test_runtime_packet_templates_use_v3_primary_device_id_contract(project_root):
    for filename in ('template.yaml', 'example_EMS_runtime_packet_sensors.yaml'):
        source = yaml.safe_load((project_root / filename).read_text(encoding='utf-8'))
        sensors = source['template'][0]['sensor']
        policy_sensor = next(sensor for sensor in sensors if sensor['name'] == 'EMS Policy Config Runtime')
        config_template = policy_sensor['attributes']['config']

        assert policy_sensor['attributes']['schema_version'].strip() == '{{ 3 }}'
        assert "'primary_device_id':" in config_template
        assert "states('input_select.ems_adjustable_primary_load')" in config_template
        assert "'adjustable_primary_load':" not in config_template


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
    assert "states('input_select.ems_adjustable_surplus_load')" not in config_template
    assert "states('input_number.ems_adjustable_surplus_activation_w')" not in config_template
    assert "states('input_number.ems_max_battery_charge_w')" in devices_template
    assert "states('input_number.ems_max_battery_discharge_w')" in devices_template
    assert "states('input_number.ems_ev_current_step_a')" in devices_template
    assert "states('input_number.ems_ev_charger_phases')" in devices_template
    assert "states('input_number.ems_ev_voltage_v')" in devices_template
    assert "input_number.ems_ev_power_step_w" not in devices_template
    assert "input_boolean.ems_surplus_adjustable_active" not in devices_template
    battery_section = devices_template.split("'HOME_BATTERY': {", 1)[1].split("'EV_CHARGER': {", 1)[0]
    ev_section = devices_template.split("'EV_CHARGER': {", 1)[1].split("'RELAY1': {", 1)[0]
    assert "'surplus_allowed': true" in ' '.join(battery_section.split())
    assert "'surplus_allowed': true" in ' '.join(ev_section.split())
    assert "input_boolean.ems_ev_force_on" in devices_template
    assert "input_boolean.ems_relay1_force_on" in devices_template
    assert "input_boolean.ems_relay2_force_on" in devices_template


@pytest.mark.unit
def test_production_template_surplus_eligibility_is_independent_of_legacy_adjustable_selector(project_root):
    source = yaml.safe_load((project_root / 'template.yaml').read_text(encoding='utf-8'))
    sensors = source['template'][0]['sensor']
    policy_sensor = next(sensor for sensor in sensors if sensor['name'] == 'EMS Policy Config Runtime')
    devices_template = policy_sensor['attributes']['devices']

    battery_section = devices_template.split("'HOME_BATTERY': {", 1)[1].split("'EV_CHARGER': {", 1)[0]
    ev_section = devices_template.split("'EV_CHARGER': {", 1)[1].split("'RELAY1': {", 1)[0]

    assert "states('input_select.ems_adjustable_surplus_load')" not in battery_section
    assert "states('input_select.ems_adjustable_surplus_load')" not in ev_section
    assert "'surplus_allowed': true" in ' '.join(battery_section.split())
    assert "'surplus_allowed': true" in ' '.join(ev_section.split())


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
        parse_tick_frame_v3(topology, cfg, measurements, _state_packet(), NOW_TS)


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


@pytest.mark.unit
def test_direct_parser_accepts_device_owned_surplus_policy_values(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=193)
    packet['devices']['EV_CHARGER']['policy']['surplus_allowed'] = True
    packet['devices']['EV_CHARGER']['policy']['surplus_dispatch_mode'] = 'max_absorb'
    packet['devices']['RELAY1']['policy']['surplus_allowed'] = False

    cfg, _cache_hit = parse_policy_config_cached(topology, packet)

    assert cfg.device_policy_by_id['EV_CHARGER']['surplus_allowed'] is True
    assert 'activation_threshold_w' not in cfg.device_policy_by_id['EV_CHARGER']
    assert cfg.device_capabilities_by_id['EV_CHARGER']['max_absorb_w'] == 6400.0
    assert cfg.device_policy_by_id['EV_CHARGER']['surplus_dispatch_mode'] == 'max_absorb'
    assert cfg.device_policy_by_id['RELAY1']['surplus_allowed'] is False


@pytest.mark.unit
@pytest.mark.parametrize('value', (0, -1, 4400))
def test_direct_parser_rejects_removed_device_activation_threshold_field(project_root, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=194)
    packet['devices']['EV_CHARGER']['policy']['activation_threshold_w'] = value

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.devices.EV_CHARGER.policy.activation_threshold_w'
    assert 'field removed' in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize('value', ('true', 'false', 1, 0))
def test_direct_parser_rejects_non_boolean_surplus_allowed(project_root, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=195)
    packet['devices']['EV_CHARGER']['policy']['surplus_allowed'] = value

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.devices.EV_CHARGER.policy.surplus_allowed'


@pytest.mark.unit
def test_direct_parser_rejects_unknown_surplus_dispatch_mode(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=196)
    packet['devices']['EV_CHARGER']['policy']['surplus_dispatch_mode'] = 'stepped_magic'

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.devices.EV_CHARGER.policy.surplus_dispatch_mode'


@pytest.mark.unit
@pytest.mark.parametrize('field', ('surplus_allowed', 'surplus_dispatch_mode'))
def test_direct_parser_rejects_missing_device_owned_surplus_policy_field(project_root, field):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=197)
    del packet['devices']['EV_CHARGER']['policy'][field]

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == f'policy_config.devices.EV_CHARGER.policy.{field}'


@pytest.mark.unit
def test_direct_parser_blank_primary_preserves_valid_surplus_only_topology(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=198)
    packet['config']['primary_device_id'] = ''

    cfg, _cache_hit = parse_policy_config_cached(topology, packet)
    out = compute_net_zero_engine_outputs(
        cfg.profiles,
        cfg,
        parse_tick_frame_v3(topology, cfg, _measurements_packet(), _state_packet(), NOW_TS),
        HaeoTargets(
            effective_forecast='NONE',
            configured_forecast='NONE',
            fresh=False,
            battery_target_kw=0.0,
            ev_target_kw=0.0,
        ),
        NetZeroState(rpnz_w=0.0, required_power_consumption_kw=0.0),
        NOW_TS,
        freeze_until_ts=None,
    )

    assert out.attrs['primary_device_id'] == ''
    assert out.attrs['primary_surplus_combo_valid'] is True
    assert out.attrs['primary_surplus_combo_reason'] == 'surplus_only_topology'
    assert 'surplus_adjustable_device_id' not in out.attrs
    assert out.attrs['surplus_candidate_device_ids'] == ('HOME_BATTERY', 'RELAY1')


def _multi_battery_topology_and_policy(project_root):
    config = load_grouped_ems_config(project_root / 'EMS_config.yaml')
    devices = config['ems']['devices']
    first_battery = devices.pop('HOME_BATTERY')
    ordered_devices = {
        'BATTERY_30KWH': first_battery,
        'BATTERY_60KWH': {
            'kind': 'BATTERY',
            'capabilities': {
                'can_absorb_w': True,
                'can_produce_w': True,
                'supports_primary_regulation': True,
                'supports_residual_regulation': True,
            },
        },
    }
    ordered_devices.update(devices)
    config['ems']['devices'] = ordered_devices
    config['ems']['role_constraints']['default']['primary'] = 'BATTERY_30KWH'
    topology = build_static_topology(config)

    policy = _policy_packet(revision=91)
    first_policy = policy['devices'].pop('HOME_BATTERY')
    policy['devices'] = {
        'BATTERY_30KWH': first_policy,
        'BATTERY_60KWH': {
        'capabilities': {
            'min_absorb_w': 0,
            'max_absorb_w': 7200,
            'max_produce_w': -7600,
            'step_w': 100,
            'uses_hard_off_lifecycle': False,
            'supports_primary_regulation': True,
            'supports_residual_regulation': True,
        },
        'policy': {
            'priority': 2,
            'surplus_allowed': True,
            'surplus_dispatch_mode': 'max_absorb',
            'default_min_absorb_w': 0,
        },
            'guard': {
                'protect_soc': 5,
                'protect_soc_recovery_margin': 2,
                'protect_min_cell_voltage_v': 3.05,
                'protect_min_absorb_w': 200,
            },
        },
        **policy['devices'],
    }
    policy['config']['primary_device_id'] = 'BATTERY_30KWH'
    return topology, policy


@pytest.mark.unit
def test_direct_v3_multi_battery_requires_policy_config_entry_for_every_static_device(project_root):
    reset_direct_runtime_cache()
    topology, policy = _multi_battery_topology_and_policy(project_root)
    del policy['devices']['BATTERY_60KWH']

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, policy)

    assert exc.value.path == 'policy_config.devices.BATTERY_60KWH'
    assert exc.value.message == 'missing'


@pytest.mark.unit
def test_direct_v3_multi_battery_config_exposes_explicit_single_channel_owner(project_root):
    reset_direct_runtime_cache()
    topology, policy = _multi_battery_topology_and_policy(project_root)

    cfg, cache_hit = parse_policy_config_cached(topology, policy)

    assert cache_hit is False
    assert cfg.device_ids_by_kind('BATTERY') == ('BATTERY_30KWH', 'BATTERY_60KWH')
    assert cfg.v3_battery_device_id() == 'BATTERY_30KWH'
    assert cfg.unsupported_v3_battery_device_ids() == ('BATTERY_60KWH',)
    assert cfg.device_by_id('BATTERY_60KWH').capabilities.max_absorb_w == 7200
    assert cfg.device_by_id('BATTERY_60KWH').policy.priority == 2


@pytest.mark.unit
def test_direct_v3_multi_battery_policy_fails_closed_for_unwired_battery(project_root):
    reset_direct_runtime_cache()
    topology, policy = _multi_battery_topology_and_policy(project_root)
    cfg, _cache_hit = parse_policy_config_cached(topology, policy)
    frame = parse_tick_frame_v3(
        topology,
        cfg,
        _measurements_packet(),
        _state_packet(),
        NOW_TS,
    )
    guard = evaluate_guard(cfg.profiles.guard, frame, cfg)
    profiles = Profiles(cfg.profiles.control, cfg.profiles.goal, cfg.profiles.forecast, guard.guard)
    haeo = frame.haeo_targets(profiles, cfg)
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=frame.quarter_energy_balance_kwh,
        grid_power_w=frame.grid_power_w,
        now_ts=NOW_TS,
    )
    nz = NetZeroState(
        rpnz_w=derived.rpnz_w,
        required_power_consumption_kw=derived.required_power_consumption_kw,
    )
    haeo_plan = compute_haeo_net_zero_plan(
        profiles,
        cfg,
        haeo,
        NOW_TS,
        previous_quarter_key=frame.previous_quarter_key,
        previous_primary_load='',
        previous_primary_device_id=frame.previous_primary_device_id,
    )

    outputs = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        frame,
        haeo,
        nz,
        NOW_TS,
        freeze_until_ts=frame.surplus_freeze_until_ts,
        pv_power_kw=frame.pv_power_w / 1000.0,
        relay_device_states=frame.relay_states,
        previous_device_states=frame.previous_device_states,
        previous_force_on_device_ids=frame.previous_force_on_device_ids,
        haeo_nz_plan=haeo_plan,
    )
    policies = {policy.device_id: policy for policy in outputs.device_policies}

    owner = policies['BATTERY_30KWH']
    unwired = policies['BATTERY_60KWH']
    assert owner.reason == 'battery_policy'
    assert unwired.target_w == 0
    assert unwired.enabled is False
    assert unwired.reason == 'unsupported_v3_battery_channel'
    assert outputs.attrs['v3_battery_device_id'] == 'BATTERY_30KWH'
    assert outputs.attrs['v3_unsupported_battery_device_ids'] == ('BATTERY_60KWH',)
