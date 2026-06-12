import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import build_harness
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_force_rising_edge_freeze_hygiene(project_root):
    """Phase 1: user force on RELAY2 creates freeze and blocks RELAY1 until expiry."""
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 't0 baseline: no surplus loads active and nothing forced',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_target': 'RELAY2',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': False,
            },
            'expect_policy_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 30,
            'note': 't30 RPC is 3 kW, still below the 5 kW RELAY2 threshold',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_target': 'RELAY2',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': False,
            },
            'expect_policy_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 60,
            'note': 't60 user forces RELAY2 on and RELAY1 must not react immediately',
            'set': {
                ENT['relay2_force_on']: True,
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
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
                'freeze_until_ts': 75.0,
            },
            'expect_writer_trace': {
                'relay1': {
                    'reason': 'already_matching',
                    'written': False,
                },
                'relay2': {
                    'reason': 'state_changed',
                    'written': True,
                },
            },
            'expect_freeze_entity_present': True,
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
        },
        {
            'at_s': 74,
            'note': 't74 force freeze is still active and RELAY1 must remain off',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
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
                    'reason': 'already_matching',
                    'written': False,
                },
                'relay2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
        },
        {
            'at_s': 90,
            'note': 't90 force freeze has expired and RELAY1 activation is decided, but actuator state remains unchanged this step',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 105.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': True,
            },
            'expect_policy_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
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
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
        },
    ]

    run_steps(h, steps)
