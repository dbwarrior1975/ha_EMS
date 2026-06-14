import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import run_steps


@pytest.mark.scenario
def test_03_release_relay1_then_restart(project_root):
    """Phase 3: final RELAY1 release and start of the next activation cycle."""
    h = build_harness(project_root)

    # Seed post-adjustable-release state so this phase is independent.
    h.set_entities({
        ENT['surplus_r1_active']: True,
        ENT['surplus_adjustable_active']: False,
        ENT['surplus_r2_active']: False,
        ENT['actuator_relay1']: True,
        ENT['actuator_relay2']: False,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 6,
    })

    steps = [
        {
            'at_s': 120,
            'note': 't120 RELAY1 becomes the final release decision',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY1',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 6,
            },
        },
        {
            'at_s': 121,
            'note': 't121 release visibility clears and policy idles below RELAY1 threshold',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.1,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 150,
            'note': 't150 next cycle starts and RELAY1 is activated again',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.1,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 165.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
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
                ENT['actuator_ev_enabled']: True,
            },
        },
    ]

    run_steps(h, steps)
