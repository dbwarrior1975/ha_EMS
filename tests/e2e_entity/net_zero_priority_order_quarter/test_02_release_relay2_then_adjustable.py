import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import run_steps


@pytest.mark.scenario
def test_02_release_relay2_then_adjustable(project_root):
    """Phase 2: from fully active state, release order begins RELAY2 -> ADJUSTABLE."""
    h = build_harness(project_root)

    # Seed end-of-phase-1 state so this phase is independent.
    h.set_entities({
        ENT['surplus_r1_active']: True,
        ENT['surplus_adjustable_active']: True,
        ENT['surplus_r2_active']: True,
        ENT['surplus_freeze_until']: 75.0,
        ENT['actuator_relay1']: True,
        ENT['actuator_relay2']: True,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 28,
    })

    steps = [
        {
            'at_s': 76,
            'note': 't76 all active remains stable with no eligible next target',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 450,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'No eligible next surplus target',
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
                ENT['actuator_ev_enabled']: True,
            },
        },
        {
            'at_s': 90,
            'note': 't90 surplus collapses so RELAY2 is released first',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY2',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_RELAY2',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 91,
            'note': 't91 RELAY2 release is visible and ADJUSTABLE gets released next',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_ADJUSTABLE',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 6,
            },
        },
    ]

    run_steps(h, steps)
