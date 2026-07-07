import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.goal_transition_net_zero_to_max_export.scenario_steps import build_harness, run_steps
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_max_export_hard_off_stability(project_root):
    h = build_harness(project_root)
    E = h.ent

    seed_active_surplus_devices(
        h,
        goal_profile='MAX_EXPORT',
        active_device_ids=(),
        actuator_relay1=False,
        actuator_relay2=False,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
        actuator_battery_setpoint_w=-200,
    )

    steps = [
        {
            'at_s': 120,
            'note': 't120 MAX_EXPORT keeps surplus clear and transitions EV policy to hard_off',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=120),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=120),
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_dispatch_action': 'CLEAR_ALL',
                'surplus_dispatch_device_id': '',
                'surplus_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'mode': 'hard_off'},
                'RELAY1': {'enabled': False},
                'RELAY2': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'hard_off',
                    'written': True,
                    'target_current_a': 8,
                },
                'RELAY1': {
                    'reason': 'already_matching',
                    'written': False,
                },
                'RELAY2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
                E['actuator_battery_setpoint_w']: -1200,
            },
        },
        {
            'at_s': 150,
            'note': 't150 MAX_EXPORT remains stable with EV hard_off and clear dispatch state',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=1000.0, required_power_consumption_kw=7.0, at_s=150),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=1000.0, required_power_consumption_kw=7.0, at_s=150),
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_dispatch_action': 'CLEAR_ALL',
                'surplus_dispatch_device_id': '',
                'surplus_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'mode': 'hard_off'},
                'RELAY1': {'enabled': False},
                'RELAY2': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'hard_off',
                    'written': False,
                    'target_current_a': 8,
                },
                'RELAY1': {
                    'reason': 'already_matching',
                    'written': False,
                },
                'RELAY2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
                E['actuator_battery_setpoint_w']: -2200,
            },
        },
    ]

    run_steps(h, steps)
