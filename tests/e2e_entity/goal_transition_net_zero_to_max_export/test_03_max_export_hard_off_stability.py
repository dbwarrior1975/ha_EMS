import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.goal_transition_net_zero_to_max_export.scenario_steps import build_harness, run_steps


@pytest.mark.scenario
def test_max_export_hard_off_stability(project_root):
    h = build_harness(project_root)

    h.set_entities({
        ENT['goal_profile']: 'MAX_EXPORT',
        ENT['surplus_r1_active']: False,
        ENT['surplus_adjustable_active']: False,
        ENT['surplus_r2_active']: False,
        ENT['actuator_relay1']: False,
        ENT['actuator_relay2']: False,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 28,
        ENT['policy_relay1_command']: 0,
        ENT['policy_relay2_command']: 0,
        ENT['policy_ev_current_a']: 28,
        ENT['actuator_battery_setpoint_w']: -200,
    })

    steps = [
        {
            'at_s': 120,
            'note': 't120 MAX_EXPORT keeps surplus clear and transitions EV policy to hard_off',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'hard_off',
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'hard_off',
                    'written': True,
                    'target_current_a': 4,
                },
                'relay1': {
                    'reason': 'already_matching',
                    'written': False,
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
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_battery_setpoint_w']: -1200,
            },
        },
        {
            'at_s': 150,
            'note': 't150 MAX_EXPORT remains stable with EV hard_off and clear dispatch state',
            'set': {
                ENT['required_power_consumption_kw']: 7.0,
                ENT['rpnz_w']: 1000.0,
            },
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'hard_off',
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'hard_off',
                    'written': False,
                    'target_current_a': 4,
                },
                'relay1': {
                    'reason': 'already_matching',
                    'written': False,
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
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_battery_setpoint_w']: -2200,
            },
        },
    ]

    run_steps(h, steps)
