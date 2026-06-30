import pytest
import yaml

from ems_adapter.config_loader import (
    build_core_config_from_grouped_config,
    build_core_config_from_grouped_reader,
    load_grouped_ems_config,
    validate_grouped_ems_config,
)
from ems_adapter.device_read_model import build_device_configs
from ems_adapter.runtime_context import build_runtime_entities_from_grouped_config, read_runtime_context
from tests.entity_ids import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
from tests.helpers import ev_w


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


def _write_grouped_config_with_second_ev(project_root, tmp_path):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices']['EV_GARAGE'] = {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'min_absorb_w': 'input_number.ems_ev_garage_min_power_w',
            'max_absorb_w': 'input_number.ems_ev_garage_max_power_w',
            'step_w': 'input_number.ems_ev_garage_power_step_w',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_ev_garage_priority',
            'surplus_allowed': 'input_boolean.ems_ev_garage_surplus_allowed',
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
    config['ems']['global_config']['adjustable_surplus_load'] = 'input_select.ems_adjustable_surplus_load'
    config['ems']['global_config']['adjustable_primary_load'] = 'input_select.ems_adjustable_primary_load'
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
            ENT['adjustable_surplus_load']: 'EV_CHARGER',
            ENT['adjustable_primary_load']: 'HOME_BATTERY',
            ENT['adjustable_surplus_activation']: 650,
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
            ENT['adjustable_surplus_load']: 'EV_CHARGER',
            ENT['adjustable_primary_load']: 'HOME_BATTERY',
            ENT['adjustable_surplus_activation']: 550,
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
def test_policy_read_config_uses_grouped_config_as_default_source_when_available(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')

    harness = QuarterScenarioHarness(project_root)
    harness.set_entities(
        {
            ENT['deadband_w']: 30,
            ENT['ramp_max_w']: 800,
            ENT['strict_limits_max_w']: 4300,
            ENT['max_battery_discharge_w']: 5100,
            ENT['max_solar_charge_w']: 4500,
            ENT['battery_protect_soc']: 6,
            ENT['battery_protect_soc_recovery_margin']: 2,
            ENT['battery_protect_min_cell_voltage_v']: 3.10,
            ENT['battery_protect_charge_floor_w']: 300,
            ENT['ev_min_absorb_w']: ev_w(6, phases=3),
            ENT['ev_max_absorb_w']: ev_w(22, phases=3),
            ENT['ev_charger_phases']: 3,
            ENT['ev_force_on']: False,
            ENT['ev_hard_off_pv_threshold_kw']: 1.3,
            ENT['ev_hard_off_low_pv_cycles']: 3,
            ENT['ev_hard_off_release_cycles']: 4,
            ENT['ev_current_step_a']: 2,
            ENT['nz_battery_floor_default_w']: 150,
            ENT['nz_battery_floor_ev_active_w']: 50,
            ENT['adjustable_surplus_load']: 'EV_CHARGER',
            ENT['adjustable_primary_load']: 'HOME_BATTERY',
            ENT['adjustable_surplus_activation']: 700,
            ENT['haeo_stale_timeout_s']: 210,
            ENT['devices']['RELAY1']['max_absorb_w']: 2200,
            ENT['devices']['RELAY2']['max_absorb_w']: 4600,
            ENT['surplus_freeze_s']: 55,
            ENT['devices']['EV_CHARGER']['priority']: 5,
            ENT['devices']['RELAY1']['priority']: 3,
            ENT['devices']['RELAY2']['priority']: 1,
        }
    )

    returned_config = harness.policy_mod['read_config']()
    status = harness.policy_mod['_GROUPED_CONFIG_DUAL_READ_STATUS']

    expected_core_config = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )
    assert set(returned_config.devices) == set(expected_core_config.devices)
    assert build_device_configs(returned_config) == build_device_configs(expected_core_config)
    assert status['enabled'] is True
    assert status['ok'] is True
    assert status['source'] == 'grouped_config'
    assert status['reason'] == 'loaded'


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
def test_policy_loop_publishes_grouped_config_default_source_trace_attrs(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))

    harness = QuarterScenarioHarness(project_root)
    harness.step(note='dual-read trace')

    attrs = harness.getattrs(ENT['policy_decision_trace'])
    assert attrs['config_source'] == 'grouped_config'
    assert attrs['config_dual_read_enabled'] is True
    assert attrs['config_dual_read_ok'] is True
    assert attrs['config_dual_read_reason'] == 'loaded'
    assert attrs['config_grouped_path'] == str(project_root / 'example_EMS_config.yaml')


@pytest.mark.unit
def test_grouped_config_default_source_marks_production_ready(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))

    harness = QuarterScenarioHarness(project_root)
    harness.step(note='strict grouped production preflight')

    attrs = harness.getattrs(ENT['policy_decision_trace'])
    assert attrs['config_source'] == 'grouped_config'
    assert attrs['config_dual_read_ok'] is True
    assert attrs['config_grouped_production_ready'] is True
    assert attrs['config_grouped_production_ready_reason'] == 'ready'


@pytest.mark.unit
def test_policy_loop_requires_grouped_config_path_to_exist(project_root, monkeypatch):
    missing_path = project_root / 'missing_grouped_config.yaml'
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(missing_path))

    harness = QuarterScenarioHarness(project_root)
    with pytest.raises(FileNotFoundError):
        harness.step(note='invalid grouped path')

    status = harness.policy_mod['_GROUPED_CONFIG_DUAL_READ_STATUS']
    assert status['source'] == 'grouped_config'
    assert status['ok'] is False
    assert status['reason'] == 'FileNotFoundError'
    assert status['path'] == str(missing_path)


@pytest.mark.unit
def test_read_runtime_context_validation_error_lists_failing_paths(project_root, tmp_path, monkeypatch):
    grouped_path = _write_grouped_config_with_override(
        project_root,
        tmp_path,
        'ems.state.previous_device_state',
        None,
    )
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    with pytest.raises(ValueError, match='ems.state.previous_device_state: must be a non-empty entity id string'):
        read_runtime_context(read_bool, read_float, read_int, read_str)


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
def test_grouped_config_dual_read_accepts_grouped_specific_entity_ids(project_root, tmp_path, monkeypatch):
    grouped_path = _write_grouped_config_with_override(
        project_root,
        tmp_path,
        'ems.global_config.deadband_w',
        'input_number.grouped_deadband_w',
    )
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))

    harness = QuarterScenarioHarness(project_root)
    harness.set_entities(
        {
            ENT['deadband_w']: 30,
            'input_number.grouped_deadband_w': 35,
        }
    )

    returned_config = harness.policy_mod['read_config']()
    status = harness.policy_mod['_GROUPED_CONFIG_DUAL_READ_STATUS']

    assert returned_config.deadband_w == 35
    assert status['source'] == 'grouped_config'
    assert status['ok'] is True
    assert status['reason'] == 'loaded'
    assert status['mismatches'] == ()
    harness.step(note='parity mismatch trace')
    attrs = harness.getattrs(ENT['policy_decision_trace'])
    assert attrs['config_grouped_production_ready'] is True
    assert attrs['config_grouped_production_ready_reason'] == 'ready'


@pytest.mark.unit
def test_grouped_config_source_runs_full_policy_dispatch_writer_chain(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))

    harness = QuarterScenarioHarness(project_root)
    snap = harness.step(
        {
            ENT['grid_power_w']: -2600,
            ENT['quarter_energy_balance']: -0.6,
            ENT['rpnz_w']: 1800,
            ENT['required_power_consumption_kw']: 1.8,
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        },
        note='grouped source e2e',
    )

    trace_attrs = snap['attrs'][ENT['policy_decision_trace']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']

    assert trace_attrs['config_source'] == 'grouped_config'
    assert trace_attrs['config_dual_read_enabled'] is True
    assert trace_attrs['config_dual_read_ok'] is True
    assert trace_attrs['config_dual_read_reason'] == 'loaded'
    assert writer_attrs['writer_trace_canonical_contract'] == 'devices'
    assert writer_attrs['victron']['policy_source'] == 'device_policy'
    assert writer_attrs['devices']['EV_CHARGER']['policy_source'] == 'device_policy'
    assert writer_attrs['devices']['RELAY1']['policy_source'] == 'device_policy'
    assert writer_attrs['devices']['RELAY2']['policy_source'] == 'device_policy'


@pytest.mark.unit
def test_grouped_config_two_ev_boundary_targets_selected_ev(project_root, tmp_path, monkeypatch):
    grouped_path, grouped_config = _write_grouped_config_with_second_ev(project_root, tmp_path)
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))

    entities = build_runtime_entities_from_grouped_config(grouped_config)
    assert entities['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert entities['devices']['EV_GARAGE']['enabled'] == 'switch.ev_garage_enabled'
    assert entities['devices']['EV_GARAGE']['current_a'] == 'number.ev_garage_current_a'

    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_path)
    harness.set_entities(
        {
            ENT['adjustable_surplus_load']: 'EV_GARAGE',
            ENT['adjustable_primary_load']: 'HOME_BATTERY',
            ENT['adjustable_surplus_activation']: 2000,
            ENT['grid_power_w']: -3200,
            ENT['quarter_energy_balance']: -0.8,
            ENT['rpnz_w']: 3200,
            ENT['required_power_consumption_kw']: 3.2,
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
    harness.step(note='activate selected garage ev')
    snap = harness.step(note='selected garage ev writes')
    trace_attrs = snap['attrs'][ENT['policy_decision_trace']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']
    policies = {item['device_id']: item for item in trace_attrs['device_policies']}

    assert set(harness.policy_mod['read_config']().devices) >= {'EV_CHARGER', 'EV_GARAGE'}
    assert trace_attrs['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert trace_attrs['selected_ev_device_id'] == 'EV_GARAGE'
    assert policies['EV_GARAGE']['enabled'] is True
    assert policies['EV_GARAGE']['target_w'] == 3680
    assert policies['EV_CHARGER']['enabled'] is False
    assert policies['EV_CHARGER']['target_w'] == 0
    assert trace_attrs['previous_ev_device_states']['EV_GARAGE']['mode'] == trace_attrs['ev_policy_mode']
    assert writer_attrs['devices']['EV_CHARGER']['policy_source'] == 'device_policy'
    assert writer_attrs['devices']['EV_GARAGE']['policy_source'] == 'device_policy'
    assert writer_attrs['devices']['EV_GARAGE']['target_current_a'] == 16
    assert snap['values']['switch.ev_garage_enabled'] is True
    assert snap['values']['number.ev_garage_current_a'] == 16


@pytest.mark.unit
def test_zero_ev_config_runs_policy_without_ev_policy(project_root, tmp_path, monkeypatch):
    grouped_path, grouped_config = _write_grouped_config_without_ev(project_root, tmp_path)
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))

    entities = build_runtime_entities_from_grouped_config(grouped_config)
    assert entities['ev_device_ids'] == ()

    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_path)
    harness.set_entities(
        {
            ENT['adjustable_surplus_load']: 'HOME_BATTERY',
            ENT['adjustable_primary_load']: '',
            ENT['adjustable_surplus_activation']: 2000,
            ENT['grid_power_w']: -2400,
            ENT['quarter_energy_balance']: -0.5,
            ENT['rpnz_w']: 2400,
            ENT['required_power_consumption_kw']: 2.4,
            ENT['pv_power_kw']: 3.5,
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        }
    )

    snap = harness.step(note='grouped config no ev policy run')
    trace_attrs = snap['attrs'][ENT['policy_decision_trace']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']
    policies = {item['device_id']: item for item in trace_attrs['device_policies']}

    assert trace_attrs['ev_device_ids'] == ()
    assert trace_attrs['selected_ev_device_id'] == ''
    assert trace_attrs['ev_policy_mode'] == 'skip'
    assert trace_attrs['ev_target_w'] == 0
    assert 'EV_CHARGER' not in policies
    assert set(policies) == {'HOME_BATTERY', 'RELAY1', 'RELAY2'}
    assert 'EV_CHARGER' not in writer_attrs['devices']
    assert set(writer_attrs['devices']) == {'RELAY1', 'RELAY2'}


@pytest.mark.unit
def test_policy_outputs_publish_device_policy_contract_and_payloads(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    harness.step(note='policy output contract attrs')

    attrs = harness.getattrs(ENT['policy_decision_trace'])
    assert attrs['policy_output_contract'] == 'device_policy_primary'
    assert attrs['device_policies']
