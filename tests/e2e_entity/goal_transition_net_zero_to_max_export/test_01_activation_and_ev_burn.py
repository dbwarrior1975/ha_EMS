import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.goal_transition_net_zero_to_max_export.scenario_steps import build_harness, run_steps


@pytest.mark.scenario
def test_activation_and_ev_burn_window(project_root):
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 't0 NET_ZERO activates relay1 first',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'restore_min',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 200,
            },
        },
        {
            'at_s': 30,
            'note': 't30 NET_ZERO activates EV next',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_explanation': 'Raw RPC 6.000 kW >= ADJUSTABLE threshold 5.060 kW',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'restore_min',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_ADJUSTABLE',
                ENT['policy_relay1_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 400,
            },
        },
        {
            'at_s': 44,
            'note': 't44 EV burn visible while activation freeze blocks additional surplus changes',
            'set': {
                ENT['required_power_consumption_kw']: 2.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_relay1_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'state_changed',
                    'written': True,
                },
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 600,
            },
        },
        {
            'at_s': 60,
            'note': 't60 EV burn is active at max current',
            'set': {
                ENT['required_power_consumption_kw']: 1.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_relay1_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_battery_setpoint_w']: 800,
            },
        },
    ]

    run_steps(h, steps)
