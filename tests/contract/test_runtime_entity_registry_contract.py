import pytest

from tests.entity_ids import ENT


@pytest.mark.unit
def test_required_entities_exist():
    required_keys = {
        'control_profile',
        'goal_profile',
        'forecast_profile',
        'guard_profile',
        'policy_decision_trace',
        'device_policies',
        'active_surplus_devices',
        'previous_device_state',
        'surplus_next_target_pys',
        'surplus_next_threshold_pys',
        'surplus_release_candidate_pys',
        'surplus_explanation_pys',
        'actuator_writer_trace',
        'actuator_battery_setpoint_w',
        'actuator_ev_current_a',
        'actuator_ev_enabled',
        'actuator_relay1',
        'actuator_relay2',
    }
    assert required_keys.issubset(set(ENT))


@pytest.mark.unit
def test_entity_ids_are_unique():
    # Reuse is intentional only where actuator and current sensor target are same HA entity.
    duplicates = {}
    for key, value in ENT.items():
        duplicates.setdefault(value, []).append(key)

    allowed_shared_entities = {
        'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point': {'current_battery_sp', 'actuator_battery_setpoint_w'},
        'number.charger_current_level': {'charger_current', 'actuator_ev_current_a'},
        'switch.charger_control': {'charger_control', 'actuator_ev_enabled'},
        'switch.relay_1_2': {'relay1', 'actuator_relay1'},
        'switch.relay_2_2': {'relay2', 'actuator_relay2'},
    }

    actual_shared = {entity_id: set(keys) for entity_id, keys in duplicates.items() if len(keys) > 1}
    assert actual_shared == allowed_shared_entities


@pytest.mark.unit
def test_unit_conversion_contract():
    assert ENT['rpnz_w'].startswith('sensor.')
    assert ENT['required_power_consumption_kw'].startswith('sensor.')
    assert ENT['policy_decision_trace'].startswith('sensor.')
    assert ENT['actuator_battery_setpoint_w'].startswith('number.')
    assert ENT['actuator_ev_current_a'].startswith('number.')


@pytest.mark.unit
def test_unknown_state_defaults():
    assert ENT['surplus_policy_active_pys'].startswith('binary_sensor.')
    assert ENT['surplus_freeze_until'].startswith('input_datetime.')
    assert ENT['active_surplus_devices'].startswith('sensor.')
    assert ENT['previous_device_state'].startswith('sensor.')
    assert ENT['actuator_writer_trace'].startswith('sensor.')
