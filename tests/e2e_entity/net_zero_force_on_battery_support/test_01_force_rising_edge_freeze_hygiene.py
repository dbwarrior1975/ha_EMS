import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import build_harness
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import run_steps

@pytest.mark.scenario
def test_01_force_rising_edge_freeze_hygiene(project_root):
    """Phase 1: user force on RELAY2 creates freeze and blocks RELAY1 until expiry."""
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 baseline: no surplus loads active and nothing forced',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_device_id': 'RELAY2',
                'prev_force_on_device_ids': (),
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
            },
        },
        {
            'at_s': 30,
            'note': 't30 RPC is 3 kW, still below the 5 kW RELAY2 threshold',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=30),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=30),
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_device_id': 'RELAY2',
                'prev_force_on_device_ids': (),
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
            },
        },
        {
            'at_s': 60,
            'note': 't60 user forces RELAY2 on and RELAY1 must not react immediately',
            'set': {
                **runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=60),
                E['devices']['RELAY2']['force_on']: True,
            },
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=60),
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_device_id': 'RELAY1',
                'prev_force_on_device_ids': ('RELAY2',),
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
            },
            'expect_dispatch_state': {
                'freeze_until_ts': 75.0,
                'freeze_written': True,
            },
            'expect_writer_trace': {
                'RELAY1': {
                    'reason': 'already_matching',
                    'written': False,
                },
                'RELAY2': {
                    'reason': 'state_changed',
                    'written': True,
                },
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_relay2']: True,
            },
        },
        {
            'at_s': 74,
            'note': 't74 force freeze is still active and RELAY1 must remain off',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=74),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=74),
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_device_id': 'RELAY1',
                'prev_force_on_device_ids': ('RELAY2',),
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
            },
            'expect_writer_trace': {
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
                E['actuator_relay1']: False,
                E['actuator_relay2']: True,
            },
        },
        {
            'at_s': 90,
            'note': 't90 force freeze has expired and RELAY1 activation is decided, but actuator state remains unchanged this step',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=90),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=90),
            'expect_policy': {
                'surplus_freeze_until_ts': 105.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_device_id': 'RELAY1',
                'prev_force_on_device_ids': ('RELAY2',),
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
            },
            'expect_writer_trace': {
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
                E['actuator_relay1']: False,
                E['actuator_relay2']: True,
            },
        },
    ]

    run_steps(h, steps)
