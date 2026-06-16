import pytest

from ems_adapter.config_loader import legacy_parity_index, load_grouped_ems_config, validate_grouped_ems_config
from ems_adapter.runtime_context import build_runtime_entities_from_grouped_config


@pytest.mark.unit
def test_example_grouped_config_builds_expected_runtime_registry_for_profiles_globals_and_adapters(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    result = validate_grouped_ems_config(config)
    assert result.ok is True

    aliases = legacy_parity_index(config)
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
        'adjustable_surplus_load',
        'adjustable_primary_load',
        'adjustable_surplus_activation',
        'adjustable_surplus_load_priority',
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
        'ev_min_current_a',
        'ev_max_current_a',
        'ev_current_step_a',
        'ev_charger_phases',
        'ev_force_current_a',
        'ev_priority',
        'relay1_power_kw',
        'relay1_priority',
        'relay1_surplus_allowed',
        'relay1_force_on',
        'relay1',
        'actuator_relay1',
        'relay2_priority',
        'relay2_surplus_allowed',
        'relay2_force_on',
        'relay2',
        'actuator_relay2',
        'relay2_power_kw',
        'required_power_consumption_kw',
        'rpnz_w',
        'pv_power_kw',
    }

    for legacy_key in expected_exact_matches:
        assert aliases[legacy_key].value == runtime_entities[legacy_key], legacy_key


@pytest.mark.unit
def test_grouped_config_aliases_cover_legacy_ems_config_fields(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    aliases = legacy_parity_index(config)

    expected_ems_config_legacy_keys = {
        'deadband_w',
        'ramp_max_w',
        'strict_limits_max_w',
        'max_battery_discharge_w',
        'max_solar_charge_w',
        'battery_protect_soc',
        'battery_protect_soc_recovery_margin',
        'battery_protect_min_cell_voltage_v',
        'battery_protect_charge_floor_w',
        'ev_min_current_a',
        'ev_max_current_a',
        'ev_charger_phases',
        'ev_force_current_a',
        'ev_hard_off_pv_threshold_kw',
        'ev_hard_off_low_pv_cycles',
        'ev_hard_off_release_cycles',
        'ev_current_step_a',
        'nz_battery_floor_default_w',
        'nz_battery_floor_ev_active_w',
        'adjustable_surplus_load',
        'adjustable_primary_load',
        'adjustable_surplus_activation',
        'adjustable_surplus_load_priority',
        'haeo_stale_timeout_s',
        'relay1_power_kw',
        'relay2_power_kw',
        'surplus_freeze_s',
        'ev_priority',
        'relay1_priority',
        'relay2_priority',
    }

    assert expected_ems_config_legacy_keys <= set(aliases)


@pytest.mark.unit
def test_example_grouped_config_exposes_explicit_unit_aliases(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    aliases = legacy_parity_index(config)

    assert aliases['required_power_consumption_kw'].unit_transform == 'W_TO_KW'
    assert aliases['pv_power_kw'].unit_transform == 'W_TO_KW'
    assert aliases['ev_hard_off_pv_threshold_kw'].unit_transform == 'W_TO_KW'
    assert aliases['ev_hard_off_pv_threshold_kw'].config_path == 'ems.devices.EV_CHARGER.policy.low_pv_threshold_w'
