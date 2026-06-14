import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_activation_chain(project_root):
    """Phase 1: activation order RELAY1 -> ADJUSTABLE(EV) -> RELAY2."""
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 't0 raw RPC crosses RELAY1 threshold so first activation decision targets RELAY1',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 15.0,
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_enabled']: False,
            },
        },
        {
            'at_s': 30,
            'note': 't30 RELAY1 is visible and EV becomes the next target once its threshold is reached',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 45.0,
                'surplus_explanation': 'Raw RPC 6.000 kW >= ADJUSTABLE threshold 5.060 kW',
                'surplus_next_target': 'ADJUSTABLE',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_ADJUSTABLE',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 60,
            'note': 't60 EV burn is visible and RELAY2 becomes eligible as the third activation',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Raw RPC 6.000 kW >= RELAY2 threshold 5.000 kW',
                'surplus_next_target': 'RELAY2',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY2',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY2',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 61,
            'note': 't61 RELAY2 command is now visible and all three surplus targets are stably active',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'NONE',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
            },
        },
    ]

    run_steps(h, steps)
