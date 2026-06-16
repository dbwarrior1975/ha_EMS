import pytest

from ems_adapter.config_loader import build_core_config_from_grouped_config, load_grouped_ems_config


def _load_example(project_root):
    return load_grouped_ems_config(project_root / 'example_EMS_config.yaml')


def _core_entity_values():
    return {
        'input_select.ems_control_profile': 'AUTOMATIC',
        'input_select.ems_goal_profile': 'NET_ZERO',
        'input_select.ems_forecast_profile': 'NONE',
        'input_select.ems_guard_profile': 'NORMAL_LIMITS',
        'input_number.ems_deadband_w': 50,
        'input_number.ems_ramp_max_w': 1000,
        'input_number.ems_strict_limits_max_w': 4600,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_nz_battery_floor_default_w': 100,
        'input_number.ems_nz_battery_floor_ev_active_w': 0,
        'input_select.ems_adjustable_surplus_load': 'HOME_BATTERY',
        'input_select.ems_adjustable_primary_load': '',
        'input_number.ems_adjustable_surplus_activation_w': 0,
        'input_number.ems_default_activation_threshold_w': 0,
        'input_number.ems_home_battery_ev_primary_min_absorb_w': 0,
        'input_number.ems_ev_adjustable_activation_threshold_w': 0,
        'input_number.ems_home_battery_min_absorb_w': 0,
        'input_number.ems_max_battery_charge_w': 3700,
        'input_number.ems_max_battery_discharge_w': 4600,
        'input_number.ems_battery_protect_soc': 2,
        'input_number.ems_battery_protect_soc_recovery_margin': 1,
        'input_number.ems_battery_protect_min_cell_voltage_v': 3.03,
        'input_number.ems_battery_protect_charge_floor_w': 0,
        'sensor.haeo_battery_power_active': 'sensor.haeo_battery_power_active',
        'sensor.haeo_ev_battery_power_active': 'sensor.haeo_ev_battery_power_active',
        'sensor.battery_active_power': 'sensor.battery_active_power',
        'sensor.ev_akut_active_power': 'sensor.ev_akut_active_power',
        'input_datetime.ems_surplus_freeze_until': 'input_datetime.ems_surplus_freeze_until',
        'sensor.ems_policy_decision_trace_pyscript': 'sensor.ems_policy_decision_trace_pyscript',
        'sensor.ems_active_surplus_devices': 'sensor.ems_active_surplus_devices',
        'sensor.average_active_power_2': 'sensor.average_active_power_2',
        'sensor.hourly_energy_balance': 'sensor.hourly_energy_balance',
        'sensor.required_power_consumption': 'sensor.required_power_consumption',
        'sensor.ems_calculated_required_power_for_net_zero': 'sensor.ems_calculated_required_power_for_net_zero',
        'sensor.pv_instant_power_2': 'sensor.pv_instant_power_2',
        'sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc': 55,
        'sensor.victron_mqtt_b827eb48c929_battery_1_battery_min_cell_voltage': 3.2,
        'sensor.victron_mqtt_b827eb48c929_battery_1_battery_power': 0,
        'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point': 100,
        'number.charger_current_level': 4,
        'switch.charger_control': False,
        'input_number.ems_ev_min_power_w': 4140,
        'input_number.ems_ev_max_power_w': 11040,
        'input_number.ems_ev_power_step_w': 2760,
        'input_number.ems_surplus_ev_priority': 3,
        'input_number.ems_ev_hard_off_pv_threshold_kw': 1.6,
        'input_number.ems_ev_hard_off_low_pv_cycles': 2,
        'input_number.ems_ev_hard_off_release_cycles': 2,
        'switch.charger_control': False,
        'number.charger_current_level': 4,
        'input_number.ems_ev_min_current_a': 6,
        'input_number.ems_ev_max_current_a': 28,
        'input_number.ems_ev_current_step_a': 4,
        'input_number.ems_ev_charger_phases': 1,
        'input_number.ems_ev_voltage_v': 230,
        'input_number.ems_ev_force_current_a': 0,
        'input_number.ems_surplus_relay1_priority': 2,
        'input_number.ems_surplus_relay2_priority': 1,
        'input_boolean.ems_relay1_enabled_import_zero': True,
        'input_boolean.ems_relay2_enabled_import_zero': True,
        'input_boolean.ems_relay1_force_on': False,
        'input_boolean.ems_relay2_force_on': False,
        'switch.relay_1_2': False,
        'switch.relay_2_2': False,
        'input_number.ems_relay1_power_kw': 2.5,
        'input_number.ems_relay2_power_kw': 5.0,
    }


@pytest.mark.unit
def test_build_core_config_from_grouped_config_maps_top_level_sections(project_root):
    config = _load_example(project_root)

    core = build_core_config_from_grouped_config(config, _core_entity_values())

    assert core.profiles.control == 'AUTOMATIC'
    assert core.global_config.deadband_w == 50
    assert core.runtime.grid_power_w == 'sensor.average_active_power_2'
    assert core.state.surplus_freeze_until == 'input_datetime.ems_surplus_freeze_until'
    assert core.policy_outputs.decision_trace == 'sensor.ems_policy_decision_trace_pyscript'


@pytest.mark.unit
def test_build_core_config_from_grouped_config_maps_devices_with_kind_specific_fields(project_root):
    config = _load_example(project_root)

    core = build_core_config_from_grouped_config(config, _core_entity_values())

    assert core.home_battery.device_id == 'HOME_BATTERY'
    assert core.home_battery.kind == 'BATTERY'
    assert core.home_battery.capabilities.max_produce_w == 4600
    assert core.home_battery.guard.protect_min_absorb_w == 0
    assert core.home_battery.adapter.target_w == 100

    assert core.ev_charger.kind == 'EV_CHARGER'
    assert core.ev_charger.policy.low_pv_threshold_w == 1.6
    assert core.ev_charger.adapter.current_step_a == 4
    assert core.ev_charger.adapter.force_current_a == 0

    assert core.relay1.kind == 'RELAY'
    assert core.relay1.policy.force_on is False
    assert core.relay2.adapter.enabled is False


@pytest.mark.unit
def test_build_core_config_from_grouped_config_maps_optional_sections(project_root):
    config = _load_example(project_root)

    core = build_core_config_from_grouped_config(config, _core_entity_values())

    assert core.haeo is not None
    assert core.haeo.battery_power_active == 'sensor.haeo_battery_power_active'
    assert core.role_constraints.default['activation_threshold_w'] == 0
    assert core.role_constraints.by_role['EV_PRIMARY']['HOME_BATTERY']['min_absorb_w'] == 0
    assert core.role_constraints.by_role['HOME_BATTERY_PRIMARY']['EV_CHARGER']['activation_threshold_w'] == 0
