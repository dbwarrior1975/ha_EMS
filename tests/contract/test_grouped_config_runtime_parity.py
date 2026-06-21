import pytest
import yaml

from ems_adapter.config_loader import (
    build_ems_config_from_grouped_config,
    build_ems_config_from_grouped_reader,
    load_grouped_ems_config,
    validate_grouped_ems_config,
)
from ems_adapter.device_read_model import build_device_configs
from tests.entity_ids import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


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


@pytest.mark.unit
def test_grouped_config_builds_same_ems_config_and_device_configs_as_scalar_config_view(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    validation = validate_grouped_ems_config(grouped_config)
    assert validation.ok is True

    harness = QuarterScenarioHarness(project_root)
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
            ENT['ev_min_current_a']: 6,
            ENT['ev_max_current_a']: 20,
            ENT['ev_charger_phases']: 3,
            ENT['ev_force_current_a']: 0,
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
            ENT['relay1_power_kw']: 2.3,
            ENT['relay2_power_kw']: 4.8,
            ENT['surplus_freeze_s']: 45,
            ENT['ev_priority']: 5,
            ENT['relay1_priority']: 3,
            ENT['relay2_priority']: 1,
        }
    )

    scalar_config = harness.policy_mod['read_config']()
    grouped_config_view = build_ems_config_from_grouped_config(grouped_config, harness.store.values)

    assert grouped_config_view == scalar_config
    assert build_device_configs(grouped_config_view) == build_device_configs(scalar_config)


@pytest.mark.unit
def test_grouped_config_runtime_reader_matches_dict_scalar_view(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    validation = validate_grouped_ems_config(grouped_config)
    assert validation.ok is True

    harness = QuarterScenarioHarness(project_root)
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
            ENT['ev_min_current_a']: 7,
            ENT['ev_max_current_a']: 21,
            ENT['ev_charger_phases']: 1,
            ENT['ev_force_current_a']: 0,
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
            ENT['relay1_power_kw']: 2.1,
            ENT['relay2_power_kw']: 4.4,
            ENT['surplus_freeze_s']: 60,
            ENT['ev_priority']: 4,
            ENT['relay1_priority']: 2,
            ENT['relay2_priority']: 1,
        }
    )

    dict_view = build_ems_config_from_grouped_config(grouped_config, harness.store.values)
    reader_view = build_ems_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )

    assert reader_view == dict_view


@pytest.mark.unit
def test_policy_read_config_uses_grouped_config_as_default_source_when_available(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))

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
            ENT['ev_min_current_a']: 6,
            ENT['ev_max_current_a']: 22,
            ENT['ev_charger_phases']: 3,
            ENT['ev_force_current_a']: 0,
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
            ENT['relay1_power_kw']: 2.2,
            ENT['relay2_power_kw']: 4.6,
            ENT['surplus_freeze_s']: 55,
            ENT['ev_priority']: 5,
            ENT['relay1_priority']: 3,
            ENT['relay2_priority']: 1,
        }
    )

    scalar_config = harness.policy_mod['_read_scalar_config_view']()
    returned_config = harness.policy_mod['read_config']()
    status = harness.policy_mod['_GROUPED_CONFIG_DUAL_READ_STATUS']

    assert returned_config == scalar_config
    assert status['enabled'] is True
    assert status['ok'] is True
    assert status['source'] == 'grouped_config'
    assert status['reason'] == 'matched'


@pytest.mark.unit
def test_policy_loop_publishes_grouped_config_default_source_trace_attrs(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))

    harness = QuarterScenarioHarness(project_root)
    harness.step(note='dual-read trace')

    attrs = harness.getattrs(ENT['policy_decision_trace'])
    assert attrs['config_source'] == 'grouped_config'
    assert attrs['config_dual_read_enabled'] is True
    assert attrs['config_dual_read_ok'] is True
    assert attrs['config_dual_read_reason'] == 'matched'
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
    assert status['reason'] == 'matched'
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
            ENT['hourly_energy_balance']: -0.6,
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
    assert trace_attrs['config_dual_read_reason'] == 'matched'
    assert writer_attrs['victron']['policy_source'] == 'device_policy'
    assert writer_attrs['ev']['policy_source'] == 'device_policy'
    assert writer_attrs['relay1']['policy_source'] == 'device_policy'
    assert writer_attrs['relay2']['policy_source'] == 'device_policy'


@pytest.mark.unit
def test_policy_outputs_publish_device_policy_contract_and_payloads(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.step(note='policy output contract attrs')

    attrs = harness.getattrs(ENT['policy_decision_trace'])
    assert attrs['policy_output_contract'] == 'device_policy_primary'
    assert attrs['device_policies']
