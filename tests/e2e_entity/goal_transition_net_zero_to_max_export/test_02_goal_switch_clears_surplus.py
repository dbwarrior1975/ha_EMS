import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.goal_transition_net_zero_to_max_export.scenario_steps import build_harness, run_steps
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_goal_switch_to_max_export_clears_surplus(project_root):
    h = build_harness(project_root)
    E = h.ent

    seed_active_surplus_devices(
        h,
        goal_profile='NET_ZERO',
        active_device_ids=('RELAY1', 'EV_CHARGER'),
        actuator_relay1=True,
        actuator_relay2=False,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
        actuator_battery_setpoint_w=800,
    )

    steps = [
        {
            'at_s': 90,
            'note': 't90 goal changes to MAX_EXPORT; surplus states clear and EV target remains max current this cycle',
            'set': {
                **runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=6.0, at_s=90),
                E['goal_profile']: 'MAX_EXPORT',
            },
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=6.0, at_s=90),
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_device_dispatch_decision': 'CLEAR_ALL',
                'surplus_device_dispatch_action': 'CLEAR_ALL',
                'surplus_device_dispatch_target': '',
                'surplus_device_dispatch_device_id': '',
                'surplus_device_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_device_next_target': 'RELAY2',
                'surplus_device_next_device_id': 'RELAY2',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True, 'mode': 'burn'},
                'RELAY1': {'enabled': False},
                'RELAY2': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'already_matching',
                    'written': False,
                    'target_current_a': 28,
                },
                'RELAY1': {
                    'reason': 'state_changed',
                    'written': True,
                },
                'RELAY2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
                E['actuator_battery_setpoint_w']: -200,
            },
        },
    ]

    run_steps(h, steps)
