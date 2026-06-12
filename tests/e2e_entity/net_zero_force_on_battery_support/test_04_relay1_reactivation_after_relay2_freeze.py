import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import build_harness
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import run_steps


@pytest.mark.scenario
def test_04_relay1_reactivation_after_relay2_freeze(project_root):
    """Phase 4: RELAY1 reactivates after RELAY2 freeze window and stabilizes."""
    h = build_harness(project_root)

    # Seed post-t284 state so phase is independent from previous phases.
    h.set_entities({
        ENT['relay2_force_on']: False,
        ENT['surplus_r1_active']: False,
        ENT['surplus_r2_active']: True,
        ENT['surplus_freeze_until']: 285.0,
        ENT['actuator_relay1']: False,
        ENT['actuator_relay2']: True,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 4,
    })

    steps = [
        {
            'at_s': 300,
            'note': 't300 RELAY2 is on and RELAY1 activation has already reached dispatch state state',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.215,
                ENT['grid_power_w']: -500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 315.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': False,
            },
            'expect_policy_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
                'freeze_until_ts': 315.0,
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
                ENT['surplus_r2_active']: True,
                ENT['surplus_r1_active']: True,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
        },
        {
            'at_s': 301,
            'note': 't301 RELAY1 command is already visible while freeze still blocks further surplus activation',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.215,
                ENT['grid_power_w']: -500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 315.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'ADJUSTABLE',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': False,
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
                ENT['surplus_r2_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
        },
        {
            'at_s': 330,
            'note': 't330 RELAY1 activation is now visible and both relays are stably on',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.115,
                ENT['grid_power_w']: 1500.0,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': False,
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
                    'reason': 'already_matching',
                    'written': False,
                },
                'relay2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
        },
    ]

    run_steps(h, steps)
