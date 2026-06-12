import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.goal_transition_net_zero_to_max_export.scenario_steps import build_harness, run_steps


@pytest.mark.scenario
def test_goal_switch_to_max_export_clears_surplus(project_root):
    h = build_harness(project_root)

    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['surplus_r1_active']: True,
        ENT['surplus_adjustable_active']: True,
        ENT['surplus_r2_active']: False,
        ENT['actuator_relay1']: True,
        ENT['actuator_relay2']: False,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 28,
        ENT['policy_relay1_command']: 1,
        ENT['policy_relay2_command']: 0,
        ENT['policy_ev_current_a']: 28,
        ENT['actuator_battery_setpoint_w']: 800,
    })

    steps = [
        {
            'at_s': 90,
            'note': 't90 goal changes to MAX_EXPORT; surplus states clear and EV target remains max current this cycle',
            'set': {
                ENT['goal_profile']: 'MAX_EXPORT',
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'CLEAR_ALL',
                ENT['policy_ev_current_a']: 28,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'already_matching',
                    'written': False,
                    'target_current_a': 28,
                },
                'relay1': {
                    'reason': 'state_changed',
                    'written': True,
                },
                'relay2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_battery_setpoint_w']: -200,
            },
        },
    ]

    run_steps(h, steps)
