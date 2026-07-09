import pytest
import yaml
import time

from ems_adapter.config_loader import (
    build_core_config_from_grouped_config,
    build_core_config_from_grouped_reader,
    load_grouped_ems_config,
    validate_grouped_ems_config,
)
from ems_adapter import config_loader as config_loader_mod
from ems_adapter.device_read_model import build_device_configs
from ems_adapter import runtime_context as runtime_context_mod
from ems_adapter.runtime_context import read_runtime_context
from tests.e2e_entity.entity_registry import build_scenario_entity_registry
from tests.entity_ids import ENT
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
from tests.helpers import ev_w


@pytest.fixture(autouse=True)
def _enable_runtime_context_detailed_metrics_for_contract_tests():
    previous = runtime_context_mod.runtime_context_detailed_metrics_enabled()
    runtime_context_mod.set_runtime_context_detailed_metrics_enabled(True)
    try:
        yield
    finally:
        runtime_context_mod.set_runtime_context_detailed_metrics_enabled(previous)

def _write_grouped_config_with_override(project_root, tmp_path, dotted_path, value):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    node = config
    parts = dotted_path.split('.')
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value
    path = tmp_path / 'grouped_override.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path


def _write_grouped_config_with_overrides(project_root, tmp_path, overrides):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    for dotted_path, value in overrides.items():
        node = config
        parts = dotted_path.split('.')
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    path = tmp_path / 'grouped_overrides.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path


def _write_grouped_config_with_second_ev(project_root, tmp_path):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices']['EV_GARAGE'] = {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_regulation': True,
            'supports_residual_regulation': False,
            'uses_hard_off_lifecycle': True,
            'min_absorb_w': 'input_number.ems_ev_garage_min_power_w',
            'max_absorb_w': 'input_number.ems_ev_garage_max_power_w',
            'step_w': 'input_number.ems_ev_garage_power_step_w',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_ev_garage_priority',
            'surplus_allowed': 'input_boolean.ems_ev_garage_surplus_allowed',
            'surplus_dispatch_mode': 'max_absorb',
            'force_on': 'input_boolean.ems_ev_garage_force_on',
            'low_pv_threshold_w': 'input_number.ems_ev_garage_low_pv_threshold_w',
            'hard_off_low_pv_cycles': 'input_number.ems_ev_garage_low_pv_cycles',
            'hard_off_release_cycles': 'input_number.ems_ev_garage_release_cycles',
        },
        'adapter': {
            'enabled': 'switch.ev_garage_enabled',
            'current_a': 'number.ev_garage_current_a',
            'current_step_a': 'input_number.ems_ev_garage_current_step_a',
            'phases': 'input_number.ems_ev_garage_phases',
            'voltage_v': 'input_number.ems_ev_garage_voltage_v',
        },
    }
    path = tmp_path / 'grouped_two_ev.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path, config


def _write_grouped_config_without_ev(project_root, tmp_path):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices'] = {
        device_id: device
        for device_id, device in config['ems']['devices'].items()
        if device.get('kind') != 'EV_CHARGER'
    }
    role_constraints = config['ems'].get('role_constraints', {})
    if isinstance(role_constraints, dict):
        home_battery_primary = role_constraints.get('HOME_BATTERY_PRIMARY')
        if isinstance(home_battery_primary, dict):
            home_battery_primary.pop('EV_CHARGER', None)
    config['ems']['global_config']['primary_device_id'] = 'input_select.ems_adjustable_primary_load'
    path = tmp_path / 'grouped_no_ev.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path, config


def _stub_entity_readers():
    return (
        lambda _entity_id: False,
        lambda _entity_id, default=0.0: default,
        lambda _entity_id, default=0: default,
        lambda _entity_id, default='': default,
    )


def _mutable_entity_readers(values):
    return (
        lambda entity_id: bool(values.get(entity_id, False)),
        lambda entity_id, default=0.0: values.get(entity_id, default),
        lambda entity_id, default=0: values.get(entity_id, default),
        lambda entity_id, default='': values.get(entity_id, default),
    )


def _assert_dynamic_value_updates_on_static_cache_hit(project_root, monkeypatch, values, update_fn, extract_fn):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    read_bool, read_float, read_int, read_str = _mutable_entity_readers(values)

    first_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    update_fn(values)
    second_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert metrics['policy_engine_static_context_cache_hit'] is True
    assert extract_fn(first_cfg) != extract_fn(second_cfg)
    return first_cfg, second_cfg


@pytest.mark.unit
def test_grouped_config_builds_same_core_config_and_device_configs_as_runtime_view(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    validation = validate_grouped_ems_config(grouped_config)
    assert validation.ok is True

    grouped_config_path = project_root / 'example_EMS_config.yaml'
    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_config_path)
    harness.set_entities(
        {
            ENT['deadband_w']: 25,
            ENT['ramp_max_w']: 750,
            ENT['strict_limits_max_w']: 4100,
            ENT['max_battery_discharge_w']: 5200,
            ENT['max_solar_charge_w']: 4300,
            ENT['battery_protect_soc']: 7,
            ENT['battery_protect_soc_recovery_margin']: 2,
            ENT['battery_protect_min_cell_voltage_v']: 3.12,
            ENT['battery_protect_charge_floor_w']: 350,
            ENT['ev_min_absorb_w']: ev_w(6, phases=3),
            ENT['ev_max_absorb_w']: ev_w(20, phases=3),
            ENT['ev_charger_phases']: 3,
            ENT['ev_force_on']: False,
            ENT['ev_hard_off_pv_threshold_kw']: 1.4,
            ENT['ev_hard_off_low_pv_cycles']: 3,
            ENT['ev_hard_off_release_cycles']: 4,
            ENT['ev_current_step_a']: 2,
            ENT['nz_battery_floor_default_w']: 125,
            ENT['nz_battery_floor_ev_active_w']: 75,
            ENT['primary_device_id']: 'HOME_BATTERY',
            ENT['haeo_stale_timeout_s']: 240,
            ENT['devices']['RELAY1']['max_absorb_w']: 2300,
            ENT['devices']['RELAY2']['max_absorb_w']: 4800,
            ENT['surplus_freeze_s']: 45,
            ENT['devices']['EV_CHARGER']['priority']: 5,
            ENT['devices']['RELAY1']['priority']: 3,
            ENT['devices']['RELAY2']['priority']: 1,
        }
    )

    core_config = harness.policy_mod['read_config']()
    grouped_config_view = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )

    assert set(grouped_config_view.devices) == set(core_config.devices)
    assert build_device_configs(grouped_config_view) == build_device_configs(core_config)


@pytest.mark.unit
def test_grouped_config_runtime_reader_matches_dict_core_view(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    validation = validate_grouped_ems_config(grouped_config)
    assert validation.ok is True

    grouped_config_path = project_root / 'example_EMS_config.yaml'
    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_config_path)
    harness.set_entities(
        {
            ENT['deadband_w']: 20,
            ENT['ramp_max_w']: 900,
            ENT['strict_limits_max_w']: 4200,
            ENT['max_battery_discharge_w']: 5000,
            ENT['max_solar_charge_w']: 4400,
            ENT['battery_protect_soc']: 8,
            ENT['battery_protect_soc_recovery_margin']: 3,
            ENT['battery_protect_min_cell_voltage_v']: 3.11,
            ENT['battery_protect_charge_floor_w']: 250,
            ENT['ev_min_absorb_w']: ev_w(7),
            ENT['ev_max_absorb_w']: ev_w(21),
            ENT['ev_charger_phases']: 1,
            ENT['ev_force_on']: False,
            ENT['ev_hard_off_pv_threshold_kw']: 1.5,
            ENT['ev_hard_off_low_pv_cycles']: 4,
            ENT['ev_hard_off_release_cycles']: 5,
            ENT['ev_current_step_a']: 1,
            ENT['nz_battery_floor_default_w']: 175,
            ENT['nz_battery_floor_ev_active_w']: 25,
            ENT['primary_device_id']: 'HOME_BATTERY',
            ENT['haeo_stale_timeout_s']: 180,
            ENT['devices']['RELAY1']['max_absorb_w']: 2100,
            ENT['devices']['RELAY2']['max_absorb_w']: 4400,
            ENT['surplus_freeze_s']: 60,
            ENT['devices']['EV_CHARGER']['priority']: 4,
            ENT['devices']['RELAY1']['priority']: 2,
            ENT['devices']['RELAY2']['priority']: 1,
        }
    )

    dict_view = build_core_config_from_grouped_config(grouped_config, harness.store.values)
    reader_view = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )
    core_view = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )
    runtime_core_view = harness.policy_mod['read_config']()

    assert reader_view == dict_view
    assert set(runtime_core_view.devices) == set(core_view.devices)
    assert build_device_configs(runtime_core_view) == build_device_configs(core_view)


@pytest.mark.unit
def test_grouped_config_resolution_prefers_explicit_path_over_env_and_scenario(tmp_path, monkeypatch):
    explicit_path = tmp_path / 'explicit.yaml'
    env_path = tmp_path / 'env.yaml'
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    (scenario_dir / 'EMS_config.yaml').write_text('scenario: true\n', encoding='utf-8')
    explicit_path.write_text('explicit: true\n', encoding='utf-8')
    env_path.write_text('env: true\n', encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(env_path))

    resolved = QuarterScenarioHarness._resolve_grouped_config_path(
        project_root=tmp_path,
        grouped_config_path=explicit_path,
        scenario_dir=scenario_dir,
    )

    assert resolved == explicit_path


@pytest.mark.unit
def test_grouped_config_resolution_prefers_scenario_config_over_root_fallbacks(tmp_path, monkeypatch):
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    scenario_path = scenario_dir / 'EMS_config.yaml'
    scenario_path.write_text('scenario: true\n', encoding='utf-8')
    (tmp_path / 'example_EMS_config.yaml').write_text('root_example: true\n', encoding='utf-8')
    (tmp_path / 'EMS_config.yaml').write_text('root_ems: true\n', encoding='utf-8')
    monkeypatch.delenv('EMS_GROUPED_CONFIG_PATH', raising=False)

    resolved = QuarterScenarioHarness._resolve_grouped_config_path(
        project_root=tmp_path,
        scenario_dir=scenario_dir,
    )

    assert resolved == scenario_path


@pytest.mark.unit
def test_grouped_config_resolution_prefers_scenario_config_over_env(tmp_path, monkeypatch):
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    scenario_path = scenario_dir / 'EMS_config.yaml'
    env_path = tmp_path / 'env.yaml'
    scenario_path.write_text('scenario: true\n', encoding='utf-8')
    env_path.write_text('env: true\n', encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(env_path))

    resolved = QuarterScenarioHarness._resolve_grouped_config_path(
        project_root=tmp_path,
        scenario_dir=scenario_dir,
    )

    assert resolved == scenario_path


@pytest.mark.unit
def test_grouped_config_resolution_fails_when_scenario_dir_has_no_ems_config(tmp_path, monkeypatch):
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    (scenario_dir / 'example_EMS_config.yaml').write_text('scenario_example: true\n', encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(tmp_path / 'env.yaml'))

    with pytest.raises(FileNotFoundError) as exc:
        QuarterScenarioHarness._resolve_grouped_config_path(
            project_root=tmp_path,
            scenario_dir=scenario_dir,
        )

    assert str(scenario_dir) in str(exc.value)
    assert 'EMS_config.yaml' in str(exc.value)


@pytest.mark.unit
def test_grouped_config_resolution_prefers_root_example_before_root_ems(tmp_path, monkeypatch):
    root_example = tmp_path / 'example_EMS_config.yaml'
    root_ems = tmp_path / 'EMS_config.yaml'
    root_example.write_text('root_example: true\n', encoding='utf-8')
    root_ems.write_text('root_ems: true\n', encoding='utf-8')
    monkeypatch.delenv('EMS_GROUPED_CONFIG_PATH', raising=False)

    resolved = QuarterScenarioHarness._resolve_grouped_config_path(project_root=tmp_path)

    assert resolved == root_example


@pytest.mark.unit
def test_all_e2e_scenario_dirs_define_ems_config(project_root):
    scenario_root = project_root / 'tests' / 'e2e_entity'
    scenario_dirs = sorted(
        path for path in scenario_root.iterdir()
        if path.is_dir() and not path.name.startswith('__')
    )

    missing = [
        path.name
        for path in scenario_dirs
        if not (path / 'EMS_config.yaml').exists()
    ]

    assert missing == []


@pytest.mark.unit
def test_policy_loop_requires_grouped_config_path_to_exist(project_root, monkeypatch):
    missing_path = project_root / 'missing_grouped_config.yaml'
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(missing_path))

    harness = QuarterScenarioHarness(project_root)
    with pytest.raises(FileNotFoundError):
        harness.step(note='invalid grouped path')

    status = harness.policy_mod['_GROUPED_CONFIG_STATUS']
    assert status['source'] == 'grouped_config'
    assert status['ok'] is False
    assert status['reason'] == 'FileNotFoundError'
    assert status['path'] == str(missing_path)


@pytest.mark.unit
def test_harness_builds_scenario_entity_registry_from_scenario_yaml(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'

    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    assert harness.grouped_config_path == scenario_dir / 'EMS_config.yaml'
    assert harness.grouped_config is not None
    assert harness.ent['devices']['RELAY3']['enabled'] == 'switch.relay_3_2'
    assert harness.dev('RELAY3', 'enabled') == 'switch.relay_3_2'
    assert harness.dev('RELAY3', 'enabled') == 'switch.relay_3_2'
    assert harness.policy_mod['ENT'] is harness.ent


@pytest.mark.unit
def test_scenario_harness_registry_is_isolated_from_root_ent(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'

    assert 'RELAY3' not in ((ENT.get('devices') or {}))

    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    assert harness.grouped_config_path == scenario_dir / 'EMS_config.yaml'
    assert 'RELAY3' in harness.ent['devices']
    assert harness.dev('RELAY3', 'enabled') == 'switch.relay_3_2'


@pytest.mark.unit
def test_seed_active_surplus_devices_uses_harness_registry_for_scenario_only_relay(project_root):
    from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'
    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    harness.set_entities({
        harness.ent['devices']['RELAY1']['priority']: 4,
        harness.ent['devices']['EV_CHARGER']['priority']: 3,
        harness.ent['devices']['RELAY2']['priority']: 2,
        harness.dev('RELAY3', 'priority'): 1,
    })

    seed_active_surplus_devices(
        harness,
        active_device_ids=('RELAY3', 'RELAY1', 'EV_CHARGER', 'RELAY2'),
        relay_states={'RELAY3': True},
    )

    assert harness.get(harness.dev('RELAY3', 'enabled')) is True
    assert harness.get(harness.ent['active_surplus_devices']) == 'RELAY1,EV_CHARGER,RELAY2,RELAY3'


@pytest.mark.unit
def test_harness_device_entity_error_includes_scenario_config_path(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'
    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    with pytest.raises(KeyError) as exc:
        harness.device_entity('RELAY3', 'missing_field')

    message = str(exc.value)
    assert 'device_id=RELAY3' in message
    assert 'field=missing_field' in message
    assert str(scenario_dir / 'EMS_config.yaml') in message


@pytest.mark.unit
def test_grouped_config_two_ev_candidate_pool_uses_canonical_device_id_routing(project_root, tmp_path, monkeypatch):
    grouped_path, grouped_config = _write_grouped_config_with_second_ev(project_root, tmp_path)
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))

    entities = build_scenario_entity_registry(grouped_config)
    assert entities['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert entities['devices']['EV_GARAGE']['enabled'] == 'switch.ev_garage_enabled'
    assert entities['devices']['EV_GARAGE']['current_a'] == 'number.ev_garage_current_a'

    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_path)
    harness.set_entities(
        {
            ENT['primary_device_id']: 'HOME_BATTERY',
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=4000,
                required_power_consumption_kw=4.0,
                at_s=harness.now,
            ),
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
            'input_number.ems_ev_garage_min_power_w': 1380,
            'input_number.ems_ev_garage_max_power_w': 3680,
            'input_number.ems_ev_garage_power_step_w': 460,
            'input_number.ems_surplus_ev_garage_priority': 4,
            'input_boolean.ems_ev_garage_surplus_allowed': True,
            'input_number.ems_ev_garage_low_pv_threshold_w': 1600,
            'input_number.ems_ev_garage_low_pv_cycles': 2,
            'input_number.ems_ev_garage_release_cycles': 2,
            'input_number.ems_ev_garage_current_step_a': 2,
            'input_number.ems_ev_garage_phases': 1,
            'input_number.ems_ev_garage_voltage_v': 230,
            'input_boolean.ems_ev_garage_force_on': False,
            'switch.ev_garage_enabled': False,
            'number.ev_garage_current_a': 6,
        }
    )

    harness.step(note='activate first surplus device')
    harness.step(note='activate higher-priority garage ev')
    snap = harness.step(note='generic two-ev pool writes garage ev')
    trace_attrs = snap['attrs'][ENT['policy_diagnostics']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']
    policies = {item['device_id']: item for item in trace_attrs['device_policies']}

    assert set(harness.policy_mod['read_config']().devices) >= {'EV_CHARGER', 'EV_GARAGE'}
    assert trace_attrs['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert {'EV_CHARGER', 'EV_GARAGE'} <= set(trace_attrs['surplus_candidate_device_ids'])
    assert policies['EV_GARAGE']['enabled'] is True
    assert policies['EV_GARAGE']['target_w'] == 3680
    assert policies['EV_CHARGER']['enabled'] is False
    assert policies['EV_CHARGER']['target_w'] == 0
    assert trace_attrs['previous_device_states']['EV_GARAGE']['mode'] == policies['EV_GARAGE']['mode']
    assert writer_attrs['devices']['EV_CHARGER']['policy_source'] == 'canonical'
    assert writer_attrs['devices']['EV_GARAGE']['policy_source'] == 'canonical'
    assert writer_attrs['devices']['EV_GARAGE']['target_current_a'] == 16
    assert snap['values']['switch.ev_garage_enabled'] is True
    assert snap['values']['number.ev_garage_current_a'] == 16


@pytest.mark.unit
def test_zero_ev_config_runs_policy_without_ev_policy(project_root, tmp_path, monkeypatch):
    grouped_path, grouped_config = _write_grouped_config_without_ev(project_root, tmp_path)
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))

    entities = build_scenario_entity_registry(grouped_config)
    assert entities['ev_device_ids'] == ()

    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_path)
    harness.set_entities(
        {
            ENT['primary_device_id']: '',
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=2400,
                required_power_consumption_kw=2.4,
                at_s=harness.now,
                pv_power_kw=3.5,
            ),
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        }
    )

    snap = harness.step(note='grouped config no ev policy run')
    trace_attrs = snap['attrs'][ENT['policy_diagnostics']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']
    policies = {item['device_id']: item for item in trace_attrs['device_policies']}

    assert trace_attrs['ev_device_ids'] == ()
    assert 'EV_CHARGER' not in policies
    assert set(policies) == {'HOME_BATTERY', 'RELAY1', 'RELAY2'}
    assert 'EV_CHARGER' not in writer_attrs['devices']
    assert set(writer_attrs['devices']) == {'RELAY1', 'RELAY2'}


@pytest.mark.unit
def test_canonical_tuple_key_is_stable_for_semantically_equal_payloads(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    stable_key = harness.policy_mod['_stable_key']

    left = {
        'device_policies': (
            {'device_id': 'RELAY1', 'enabled': True, 'targets': ('a', 'b')},
            {'device_id': 'RELAY2', 'enabled': False, 'meta': {'priority': 2, 'mode': 'off'}},
        ),
        'flags': {'alpha', 'beta'},
    }
    right = {
        'flags': {'beta', 'alpha'},
        'device_policies': [
            {'targets': ['a', 'b'], 'enabled': True, 'device_id': 'RELAY1'},
            {'meta': {'mode': 'off', 'priority': 2}, 'enabled': False, 'device_id': 'RELAY2'},
        ],
    }
    changed = {
        'device_policies': [
            {'targets': ['a', 'b'], 'enabled': True, 'device_id': 'RELAY1'},
            {'meta': {'mode': 'off', 'priority': 2}, 'enabled': True, 'device_id': 'RELAY2'},
        ],
        'flags': {'beta', 'alpha'},
    }

    assert stable_key(left) == stable_key(right)
    assert stable_key(left) != stable_key(changed)


@pytest.mark.unit
def test_device_policies_sensor_uses_monotonic_version_and_only_advances_on_change(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    device_policies_entity = ENT['device_policies']

    harness.set_entities(
        {
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=2200,
                required_power_consumption_kw=2.2,
                at_s=harness.now,
            ),
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        }
    )
    harness._run_policy_loop()
    first_state = harness.get(device_policies_entity)
    first_attrs = harness.getattrs(device_policies_entity)

    harness._run_policy_loop()
    second_state = harness.get(device_policies_entity)
    second_attrs = harness.getattrs(device_policies_entity)

    harness.set_entities({ENT['control_profile']: 'MANUAL'})
    harness._run_policy_loop()
    third_state = harness.get(device_policies_entity)
    third_attrs = harness.getattrs(device_policies_entity)

    assert first_state == first_attrs['device_policies_version']
    assert first_attrs['device_policies_state_kind'] == 'monotonic_version'
    assert second_state == first_state
    assert second_attrs['device_policies'] == first_attrs['device_policies']
    assert third_state == third_attrs['device_policies_version']
    assert third_state > second_state
    assert third_attrs['device_policies'] != second_attrs['device_policies']


@pytest.mark.unit
def test_dispatch_command_sensor_uses_monotonic_version_and_carries_dispatch_attrs(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    dispatch_entity = ENT['dispatch_command']

    harness.set_entities(
        {
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=2200,
                required_power_consumption_kw=2.2,
                at_s=harness.now,
            ),
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        }
    )
    harness._run_policy_loop()
    first_state = harness.get(dispatch_entity)
    first_attrs = harness.getattrs(dispatch_entity)

    harness._run_policy_loop()
    second_state = harness.get(dispatch_entity)
    second_attrs = harness.getattrs(dispatch_entity)

    harness.set_entities(
        {
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=3000,
                required_power_consumption_kw=2.4,
                at_s=harness.now,
            ),
        }
    )
    harness._run_policy_loop()
    third_state = harness.get(dispatch_entity)
    third_attrs = harness.getattrs(dispatch_entity)

    assert first_state == first_attrs['dispatch_command_version']
    assert first_attrs['dispatch_command_state_kind'] == 'monotonic_version'
    assert second_state == first_state
    # The changed measurements do not alter the dispatch command in this scenario.
    assert third_state == second_state
    assert third_attrs == second_attrs
    assert 'surplus_dispatch_action' in third_attrs
    assert 'surplus_dispatch_device_id' in third_attrs
    assert 'surplus_dispatch_contract' in third_attrs
    assert 'surplus_candidates' not in third_attrs
    assert 'surplus_freeze_until_ts' in third_attrs


@pytest.mark.unit
def test_policy_state_sensor_uses_monotonic_version_and_carries_previous_state_fields(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    policy_state_entity = ENT['policy_state']

    harness._run_policy_loop()
    first_state = harness.get(policy_state_entity)
    first_attrs = harness.getattrs(policy_state_entity)
    harness._run_policy_loop()
    second_state = harness.get(policy_state_entity)
    second_attrs = harness.getattrs(policy_state_entity)
    harness.set_entities({ENT['devices']['RELAY1']['force_on']: True})
    harness._run_policy_loop()
    third_state = harness.get(policy_state_entity)
    third_attrs = harness.getattrs(policy_state_entity)

    assert first_state == first_attrs['policy_state_version']
    assert first_attrs['policy_state_state_kind'] == 'monotonic_version'
    assert second_state == first_state
    assert third_state == third_attrs['policy_state_version']
    assert third_state > second_state
    assert 'haeo_nz_quarter_key' in second_attrs
    assert 'haeo_nz_primary_device_id' in second_attrs
    assert 'prev_force_on_device_ids' in second_attrs


@pytest.mark.unit
def test_policy_state_helpers_prefer_canonical_sensor_over_trace(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    harness.set_attrs(
        ENT['policy_state'],
        {
            'haeo_nz_quarter_key': 'canonical-quarter',
            'haeo_nz_primary_device_id': 'HOME_BATTERY',
            'prev_force_on_device_ids': ('RELAY2',),
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'haeo_nz_quarter_key': 'trace-quarter',
            'haeo_nz_primary_device_id': 'EV_CHARGER',
            'prev_force_on_device_ids': ('RELAY1',),
        },
    )

    assert harness.policy_mod['_policy_state_attr'](harness.ent, 'haeo_nz_quarter_key', '') == 'canonical-quarter'
    assert harness.policy_mod['_policy_state_attr'](harness.ent, 'haeo_nz_primary_device_id', '') == 'HOME_BATTERY'
    assert harness.policy_mod['_read_previous_force_on_device_ids'](harness.ent) == ('RELAY2',)
