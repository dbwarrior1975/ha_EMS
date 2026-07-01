from copy import deepcopy

import pytest

from ems_adapter.config_loader import load_grouped_ems_config
from ems_adapter.runtime_context import build_runtime_entities_from_grouped_config
from tests.entity_ids import ENT


@pytest.mark.unit
def test_required_entities_exist():
    required_keys = {
        'control_profile',
        'goal_profile',
        'forecast_profile',
        'guard_profile',
        'device_policies',
        'dispatch_command',
        'policy_state',
        'policy_diagnostics',
        'active_surplus_devices',
        'previous_device_state',
        'actuator_writer_trace',
        'dispatch_state_applier_trace',
        'actuator_battery_setpoint_w',
        'actuator_ev_current_a',
        'actuator_ev_enabled',
        'actuator_relay1',
        'actuator_relay2',
        'devices',
        'relay_device_ids',
        'ev_device_ids',
    }
    assert required_keys.issubset(set(ENT))


@pytest.mark.unit
def test_runtime_registry_exposes_current_ev_watt_and_actuator_keys():
    assert ENT['ev_min_absorb_w'].startswith('input_number.')
    assert ENT['ev_max_absorb_w'].startswith('input_number.')
    assert ENT['actuator_ev_current_a'].startswith('number.')
    assert ENT['actuator_ev_enabled'].startswith('switch.')


@pytest.mark.unit
def test_entity_ids_are_unique():
    # Reuse is intentional only where actuator and current sensor target are same HA entity.
    duplicates = {}
    for key, value in ENT.items():
        if not isinstance(value, str):
            continue
        duplicates.setdefault(value, []).append(key)

    allowed_shared_entities = {
        'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point': {
            'current_battery_sp',
            'actuator_battery_setpoint_w',
        },
        'number.charger_current_level': {'charger_current', 'actuator_ev_current_a'},
        'switch.charger_control': {'charger_control', 'actuator_ev_enabled'},
    }

    actual_shared = {
        entity_id: set(keys)
        for entity_id, keys in duplicates.items()
        if len(keys) > 1
    }
    assert actual_shared == allowed_shared_entities


@pytest.mark.unit
def test_unit_conversion_contract():
    assert ENT['rpnz_w'].startswith('sensor.')
    assert ENT['required_power_consumption_kw'].startswith('sensor.')
    assert ENT['policy_diagnostics'].startswith('sensor.')
    assert ENT['dispatch_command'].startswith('sensor.')
    assert ENT['policy_state'].startswith('sensor.')
    assert ENT['actuator_battery_setpoint_w'].startswith('number.')
    assert ENT['actuator_ev_current_a'].startswith('number.')


@pytest.mark.unit
def test_unknown_state_defaults():
    assert ENT['surplus_freeze_until'].startswith('input_datetime.')
    assert ENT['active_surplus_devices'].startswith('sensor.')
    assert ENT['previous_device_state'].startswith('sensor.')
    assert ENT['dispatch_command'].startswith('sensor.')
    assert ENT['policy_state'].startswith('sensor.')
    assert ENT['policy_diagnostics'].startswith('sensor.')
    assert ENT['actuator_writer_trace'].startswith('sensor.')
    assert ENT['dispatch_state_applier_trace'].startswith('sensor.')


def _with_extra_relay_and_ev(config):
    config = deepcopy(config)
    devices = config['ems']['devices']
    devices['RELAY3'] = {
        'kind': 'RELAY',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
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
    devices['EV_GARAGE'] = {
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
            'low_pv_threshold_w': 'input_number.ems_ev_garage_hard_off_pv_threshold_w',
            'hard_off_low_pv_cycles': 'input_number.ems_ev_garage_hard_off_low_pv_cycles',
            'hard_off_release_cycles': 'input_number.ems_ev_garage_hard_off_release_cycles',
        },
        'adapter': {
            'enabled': 'switch.ev_garage_control',
            'current_a': 'number.ev_garage_current_level',
            'current_step_a': 'input_number.ems_ev_garage_current_step_a',
            'phases': 'input_number.ems_ev_garage_phases',
            'voltage_v': 'input_number.ems_ev_garage_voltage_v',
        },
    }
    return config


def test_runtime_entity_registry_exposes_extra_relay_and_ev_without_top_level_alias(project_root):
    config = _with_extra_relay_and_ev(
        load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    )

    entities = build_runtime_entities_from_grouped_config(config)

    assert entities['relay_device_ids'] == ('RELAY1', 'RELAY2', 'RELAY3')
    assert entities['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert 'actuator_relay3' not in entities
    assert 'relay3' not in entities

    relay3 = entities['devices']['RELAY3']
    assert relay3 == {
        'device_id': 'RELAY3',
        'kind': 'RELAY',
        'enabled': 'switch.relay_3_2',
        'surplus_allowed': 'input_boolean.ems_relay3_enabled_import_zero',
        'force_on': 'input_boolean.ems_relay3_force_on',
        'priority': 'input_number.ems_surplus_relay3_priority',
        'max_absorb_w': 'input_number.ems_relay3_power_kw',
    }

    ev_garage = entities['devices']['EV_GARAGE']
    assert ev_garage == {
        'device_id': 'EV_GARAGE',
        'kind': 'EV_CHARGER',
        'enabled': 'switch.ev_garage_control',
        'current_a': 'number.ev_garage_current_level',
        'current_step_a': 'input_number.ems_ev_garage_current_step_a',
        'phases': 'input_number.ems_ev_garage_phases',
        'voltage_v': 'input_number.ems_ev_garage_voltage_v',
        'min_absorb_w': 'input_number.ems_ev_garage_min_power_w',
        'max_absorb_w': 'input_number.ems_ev_garage_max_power_w',
        'surplus_allowed': 'input_boolean.ems_ev_garage_surplus_allowed',
        'force_on': 'input_boolean.ems_ev_garage_force_on',
        'priority': 'input_number.ems_surplus_ev_garage_priority',
    }


def test_runtime_entity_registry_keeps_explicit_empty_device_id_lists(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    devices = config['ems']['devices']
    config['ems']['devices'] = {
        device_id: device
        for device_id, device in devices.items()
        if device.get('kind') not in {'RELAY', 'EV_CHARGER'}
    }

    entities = build_runtime_entities_from_grouped_config(config)

    assert entities['relay_device_ids'] == ()
    assert entities['ev_device_ids'] == ()
    assert entities['devices'] == {
        'HOME_BATTERY': {
            'device_id': 'HOME_BATTERY',
            'kind': 'BATTERY',
            'target_w': 'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point',
            'measured_power_w': 'sensor.victron_mqtt_b827eb48c929_battery_1_battery_power',
        }
    }


def test_runtime_entity_registry_exposes_derived_ev_debug_fields_for_numeric_config(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    ev = config['ems']['devices']['EV_CHARGER']
    ev['capabilities']['min_absorb_w'] = 1380
    ev['capabilities']['max_absorb_w'] = 3680
    ev['adapter']['current_step_a'] = 2
    ev['adapter']['phases'] = 1
    ev['adapter']['voltage_v'] = 230
    ev['adapter']['current_a'] = 10

    entities = build_runtime_entities_from_grouped_config(config)
    ev_entry = entities['devices']['EV_CHARGER']

    assert ev_entry['ev_per_amp_w'] == 230.0
    assert ev_entry['ev_derived_min_current_a'] == 6
    assert ev_entry['ev_derived_max_current_a'] == 16
    assert ev_entry['ev_derived_step_w'] == 460.0
    assert ev_entry['ev_current_power_w'] == 2300.0
