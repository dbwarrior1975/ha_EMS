import pytest

from ems_adapter.config_loader import (
    build_core_config_from_grouped_config,
    load_grouped_ems_config,
    validate_grouped_ems_config,
)
from ems_core.domain.constants import (
    CANONICAL_DIAGNOSTICS_OUTPUTS,
    CANONICAL_POLICY_OUTPUTS,
)


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
        'sensor.ems_previous_device_state': 'sensor.ems_previous_device_state',
        'sensor.ems_active_surplus_devices': 'sensor.ems_active_surplus_devices',
        'sensor.average_active_power_2': 'sensor.average_active_power_2',
        'sensor.hourly_energy_balance': 'sensor.hourly_energy_balance',
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
        'input_boolean.ems_ev_force_on': False,
        'input_number.ems_ev_hard_off_pv_threshold_kw': 1.6,
        'input_number.ems_ev_hard_off_low_pv_cycles': 2,
        'input_number.ems_ev_hard_off_release_cycles': 2,
        'switch.charger_control': False,
        'number.charger_current_level': 4,
        'input_number.ems_ev_current_step_a': 4,
        'input_number.ems_ev_charger_phases': 1,
        'input_number.ems_ev_voltage_v': 230,
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
    config['ems'].pop('policy_outputs', None)
    config['ems'].pop('diagnostics_outputs', None)

    core = build_core_config_from_grouped_config(config, _core_entity_values())

    assert core.profiles.control == 'AUTOMATIC'
    assert core.policy_engine.interval_seconds == 5.0
    assert core.policy_engine.diagnostics_interval_seconds == 30.0
    assert core.global_config.deadband_w == 50
    assert core.runtime.grid_power_w == 'sensor.average_active_power_2'
    assert core.runtime.quarter_energy_balance_kwh == 'sensor.hourly_energy_balance'
    assert core.state.surplus_freeze_until == 'input_datetime.ems_surplus_freeze_until'
    assert core.state.active_surplus_devices == 'sensor.ems_active_surplus_devices'
    assert core.state.previous_device_state == 'sensor.ems_previous_device_state'
    assert core.policy_outputs.device_policies == CANONICAL_POLICY_OUTPUTS['device_policies']
    assert core.policy_outputs.dispatch_command == CANONICAL_POLICY_OUTPUTS['dispatch_command']
    assert core.policy_outputs.policy_state == CANONICAL_POLICY_OUTPUTS['policy_state']
    assert core.diagnostics_outputs.policy_diagnostics == CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics']
    assert core.diagnostics_outputs.actuator_writer_trace == CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace']
    assert core.diagnostics_outputs.dispatch_state_applier_trace == CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace']


@pytest.mark.unit
def test_build_core_config_from_grouped_config_maps_devices_with_kind_specific_fields(project_root):
    config = _load_example(project_root)

    core = build_core_config_from_grouped_config(config, _core_entity_values())

    assert core.home_battery.device_id == 'HOME_BATTERY'
    assert core.home_battery.kind == 'BATTERY'
    assert core.home_battery.capabilities.max_produce_w == 4600
    assert core.home_battery.guard.protect_min_absorb_w == 0
    assert core.home_battery.adapter.target_w == 100

    ev_device = core.device_by_id('EV_CHARGER')
    relay1 = core.device_by_id('RELAY1')
    relay2 = core.device_by_id('RELAY2')

    assert ev_device is not None
    assert ev_device.kind == 'EV_CHARGER'
    assert ev_device.policy.force_on is False
    assert ev_device.policy.low_pv_threshold_w == 1.6
    assert ev_device.adapter.voltage_v == 230
    assert ev_device.adapter.current_step_a == 4
    assert ev_device.capabilities.min_absorb_w == 4140
    assert ev_device.capabilities.max_absorb_w == 11040

    assert relay1 is not None
    assert relay1.kind == 'RELAY'
    assert relay1.policy.force_on is False
    assert relay2 is not None
    assert relay2.adapter.enabled is False
    assert set(core.devices) == {'HOME_BATTERY', 'EV_CHARGER', 'RELAY1', 'RELAY2'}
    assert len(core.devices_by_kind('RELAY')) == 2
    assert {device.device_id for device in core.surplus_capable_devices()} == {'EV_CHARGER', 'RELAY1', 'RELAY2'}


@pytest.mark.unit
def test_build_core_config_from_grouped_config_keeps_extra_devices_in_registry(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['RELAY3'] = {
        'kind': 'RELAY',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'uses_hard_off_lifecycle': False,
            'min_absorb_w': 'input_number.ems_relay3_power_kw',
            'max_absorb_w': 'input_number.ems_relay3_power_kw',
            'step_w': 'input_number.ems_relay3_power_kw',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_relay3_priority',
            'surplus_allowed': 'input_boolean.ems_relay3_enabled_import_zero',
            'force_on': 'input_boolean.ems_relay3_force_on',
        },
        'adapter': {
            'enabled': 'switch.relay_3_2',
        },
    }
    values = _core_entity_values()
    values.update(
        {
            'input_number.ems_relay3_power_kw': 7.5,
            'input_number.ems_surplus_relay3_priority': 4,
            'input_boolean.ems_relay3_enabled_import_zero': True,
            'input_boolean.ems_relay3_force_on': False,
            'switch.relay_3_2': False,
        }
    )

    core = build_core_config_from_grouped_config(config, values)

    assert 'RELAY3' in core.devices
    assert core.devices['RELAY3'].kind == 'RELAY'
    assert core.devices['RELAY3'].capabilities.max_absorb_w == 7.5
    assert len(core.devices_by_kind('RELAY')) == 3


@pytest.mark.unit
def test_build_core_config_from_grouped_config_maps_optional_sections(project_root):
    config = _load_example(project_root)

    core = build_core_config_from_grouped_config(config, _core_entity_values())

    assert core.haeo is not None
    assert core.haeo.battery_power_active == 'sensor.haeo_battery_power_active'
    assert core.role_constraints.default['activation_threshold_w'] == 0
    assert core.role_constraints.by_role['EV_PRIMARY']['HOME_BATTERY']['min_absorb_w'] == 0
    assert core.role_constraints.by_role['HOME_BATTERY_PRIMARY']['EV_CHARGER']['activation_threshold_w'] == 0


@pytest.mark.unit
def test_build_core_config_from_grouped_config_does_not_expose_ev_scalar_mirrors(project_root):
    config = _load_example(project_root)

    core = build_core_config_from_grouped_config(config, _core_entity_values())

    for attr_name in (
        'ev_charger_phases',
        'ev_voltage_v',
        'ev_force_on',
        'ev_hard_off_pv_threshold_kw',
        'ev_hard_off_low_pv_cycles',
        'ev_hard_off_release_cycles',
        'ev_current_step_a',
        'ev_priority',
    ):
        assert not hasattr(core, attr_name)


@pytest.mark.unit
def test_build_core_config_from_grouped_config_uses_canonical_outputs_without_yaml_sections(project_root):
    config = _load_example(project_root)
    config['ems'].pop('policy_outputs', None)
    config['ems'].pop('diagnostics_outputs', None)

    core = build_core_config_from_grouped_config(config, _core_entity_values())

    assert core.policy_outputs.device_policies == CANONICAL_POLICY_OUTPUTS['device_policies']
    assert core.policy_outputs.dispatch_command == CANONICAL_POLICY_OUTPUTS['dispatch_command']
    assert core.policy_outputs.policy_state == CANONICAL_POLICY_OUTPUTS['policy_state']
    assert core.diagnostics_outputs.policy_diagnostics == CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics']
    assert core.diagnostics_outputs.actuator_writer_trace == CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace']
    assert core.diagnostics_outputs.dispatch_state_applier_trace == CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace']


@pytest.mark.unit
def test_validate_grouped_config_rejects_output_sections_as_user_config(project_root):
    config = _load_example(project_root)
    config['ems']['policy_outputs'] = dict(CANONICAL_POLICY_OUTPUTS)
    config['ems']['diagnostics_outputs'] = dict(CANONICAL_DIAGNOSTICS_OUTPUTS)

    result = validate_grouped_ems_config(config)
    paths = {issue.path for issue in result.errors}

    assert result.ok is False
    assert 'ems.policy_outputs' in paths
    assert 'ems.diagnostics_outputs' in paths
