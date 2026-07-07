import pytest

from ems_adapter.config_loader import runtime_alias_index, load_grouped_ems_config, validate_grouped_ems_config
from ems_adapter.runtime_context import build_runtime_entities_from_grouped_config


@pytest.mark.unit
def test_example_grouped_config_builds_expected_runtime_registry_for_profiles_globals_and_adapters(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    result = validate_grouped_ems_config(config)
    assert result.ok is True

    aliases = runtime_alias_index(config)
    runtime_entities = build_runtime_entities_from_grouped_config(config)

    expected_exact_matches = {
        'control_profile',
        'goal_profile',
        'forecast_profile',
        'guard_profile',
        'deadband_w',
        'ramp_max_w',
        'strict_limits_max_w',
        'max_battery_discharge_w',
        'max_solar_charge_w',
        'surplus_freeze_s',
        'haeo_stale_timeout_s',
        'nz_battery_floor_default_w',
        'nz_battery_floor_ev_active_w',
        'adjustable_primary_load',
        'battery_protect_soc',
        'battery_protect_soc_recovery_margin',
        'battery_protect_min_cell_voltage_v',
        'battery_protect_charge_floor_w',
        'soc',
        'min_cell_voltage_v',
        'battery_heartbeat',
        'current_battery_sp',
        'actuator_battery_setpoint_w',
        'charger_control',
        'actuator_ev_enabled',
        'charger_current',
        'actuator_ev_current_a',
        'ev_min_absorb_w',
        'ev_max_absorb_w',
        'ev_current_step_a',
        'ev_charger_phases',
        'ev_force_on',
        'actuator_relay1',
        'actuator_relay2',
    }

    for runtime_key in expected_exact_matches:
        assert aliases[runtime_key].value == runtime_entities[runtime_key], runtime_key


@pytest.mark.unit
def test_grouped_config_aliases_cover_runtime_alias_fields(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    aliases = runtime_alias_index(config)

    expected_ems_config_runtime_keys = {
        'deadband_w',
        'ramp_max_w',
        'strict_limits_max_w',
        'max_battery_discharge_w',
        'max_solar_charge_w',
        'battery_protect_soc',
        'battery_protect_soc_recovery_margin',
        'battery_protect_min_cell_voltage_v',
        'battery_protect_charge_floor_w',
        'ev_min_absorb_w',
        'ev_max_absorb_w',
        'ev_charger_phases',
        'ev_force_on',
        'ev_hard_off_pv_threshold_kw',
        'ev_hard_off_low_pv_cycles',
        'ev_hard_off_release_cycles',
        'ev_current_step_a',
        'nz_battery_floor_default_w',
        'nz_battery_floor_ev_active_w',
        'adjustable_primary_load',
        'haeo_stale_timeout_s',
        'surplus_freeze_s',
    }

    assert expected_ems_config_runtime_keys <= set(aliases)


@pytest.mark.unit
def test_example_grouped_config_exposes_explicit_unit_aliases(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    aliases = runtime_alias_index(config)

    assert aliases['ev_hard_off_pv_threshold_kw'].unit_transform == 'W_TO_KW'
    assert aliases['ev_hard_off_pv_threshold_kw'].config_path == 'ems.devices.EV_CHARGER.policy.low_pv_threshold_w'


@pytest.mark.unit
def test_grouped_config_rejects_unknown_fields_in_active_contract(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices']['EV_CHARGER']['adapter']['unexpected_field'] = 'input_number.foo'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert any(
        issue.path == 'ems.devices.EV_CHARGER.adapter.unexpected_field'
        and issue.message == 'Unknown config field: ems.devices.EV_CHARGER.adapter.unexpected_field'
        for issue in result.errors
    )
