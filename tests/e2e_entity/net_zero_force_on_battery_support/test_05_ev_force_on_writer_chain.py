import pytest

from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import build_harness
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent


@pytest.mark.scenario
def test_ev_force_on_survives_low_pv_discharging_battery_through_writer(project_root):
    """FORCE_ON must reach DevicePolicy and the EV actuator when HARD_OFF is inactive."""
    h = build_harness(project_root)
    E = h.ent

    h.step(
        at_s=0,
        note='EV FORCE_ON under low PV and negative battery setpoint',
        set_values={
            **runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-10.0,
                required_power_consumption_kw=0.0,
                at_s=0,
            ),
            E['pv_power_w']: 0.0,
            E['current_battery_sp']: -1200.0,
            E['devices']['EV_CHARGER']['force_on']: True,
            E['actuator_ev_enabled']: False,
            E['actuator_ev_current_a']: 6,
        },
    )

    policy_trace = h.getattrs(E['policy_diagnostics'])
    candidates = {
        item['device_id']: item
        for item in policy_trace['surplus_candidates']
    }
    policies = {
        item['device_id']: item
        for item in policy_trace['device_policies']
    }
    writer_trace = h.getattrs(E['actuator_writer_trace'])

    assert candidates['EV_CHARGER']['force_on'] is True
    assert policy_trace['feedback_protection_active'] is False
    assert policy_trace['activation_block_reason'] == ''
    assert 'battery_to_ev_loop_risk' not in policy_trace
    assert policy_trace['device_lifecycle_states']['EV_CHARGER']['hard_off_active'] is False
    assert policies['EV_CHARGER']['target_w'] > 0
    assert policies['EV_CHARGER']['enabled'] is True
    assert writer_trace['devices']['EV_CHARGER']['action'] == 'enable_and_set_current'
    assert h.get(E['actuator_ev_enabled']) is True
    assert h.get(E['actuator_ev_current_a']) > 6
