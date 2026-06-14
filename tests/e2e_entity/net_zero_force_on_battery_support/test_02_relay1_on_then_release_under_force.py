import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import build_harness
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import run_steps


@pytest.mark.scenario
def test_02_relay1_on_then_release_under_force(project_root):
    """Phase 2: RELAY1 turns on under force regime and later gets released when RPNZ collapses."""
    h = build_harness(project_root)

    # Seed end-of-phase-1 state with force already active; avoid synthetic rising-edge freeze.
    h.set_entities({
        ENT['relay2_force_on']: True,
        ENT['surplus_r1_active']: True,
        ENT['surplus_r2_active']: False,
        ENT['actuator_relay1']: False,
        ENT['actuator_relay2']: True,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
        ENT['surplus_freeze_until']: 105.0,
    })
    h.set_attrs(ENT['policy_decision_trace'], {
        'prev_relay1_force_on': False,
        'prev_relay2_force_on': True,
    })

    steps = [
        {
            'at_s': 120,
            'note': 't120 RELAY1 activation is now visible and RELAY2 stays forced on',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': True,
            },
            'expect_policy_values': {
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
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
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
        },
        {
            'at_s': 150,
            'note': 't150 state is stable while RELAY1 and forced RELAY2 stay on',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': True,
            },
            'expect_policy_values': {
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
        },
        {
            'at_s': 180,
            'note': 't180 RPNZ collapse triggers RELAY1 release decision while RELAY2 stays forced on',
            'set': {
                ENT['required_power_consumption_kw']: -2.0,
                ENT['rpnz_w']: 0.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
                'surplus_next_target': 'ADJUSTABLE',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': True,
            },
            'expect_policy_values': {
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_RELAY1',
            },
            'expect_writer_trace': {
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
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
        },
        {
            'at_s': 210,
            'note': 't210 RELAY1 release is now visible at actuator level while RELAY2 remains user-forced',
            'set': {
                ENT['required_power_consumption_kw']: -2.0,
                ENT['rpnz_w']: -0.005,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
                'surplus_next_target': 'RELAY1',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': True,
            },
            'expect_policy_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
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
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
        },
    ]

    run_steps(h, steps)
