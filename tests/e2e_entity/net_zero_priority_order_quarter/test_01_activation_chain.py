import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import run_steps

@pytest.mark.scenario
def test_01_activation_chain(project_root):
    """Phase 1: activation order RELAY1 -> EV_CHARGER -> RELAY2."""
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 intent: RPNZ=500 W, RPC=3.5 kW. Raw RPC crosses RELAY1 threshold so first activation decision targets RELAY1',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=3.5, at_s=0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=3.5, at_s=0),
            'expect_policy': {
                'surplus_device_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_device_next_target': 'RELAY1',
                'surplus_device_next_device_id': 'RELAY1',
                'surplus_freeze_until_ts': 15.0,
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
                E['actuator_ev_enabled']: False,
            },
        },
        {
            'at_s': 30,
            'note': 't30 RELAY1 is visible and EV becomes the next target once its threshold is reached',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=6.0, at_s=30),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=6.0, at_s=30),
            'expect_policy': {
                'surplus_device_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_device_next_target': 'ADJUSTABLE',
                'surplus_device_next_device_id': 'EV_CHARGER',
                'surplus_freeze_until_ts': 45.0,
                    'surplus_explanation': 'Raw RPC 6.000 kW >= EV_CHARGER threshold 5.060 kW',
                'surplus_next_target': 'ADJUSTABLE',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: False,
            },
        },
        {
            'at_s': 60,
            'note': 't60 EV burn is visible and RELAY2 becomes eligible as the third activation',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=6.0, at_s=60),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=6.0, at_s=60),
            'expect_policy': {
                'surplus_device_dispatch_decision': 'ACTIVATE_RELAY2',
                'surplus_device_next_target': 'RELAY2',
                'surplus_device_next_device_id': 'RELAY2',
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Raw RPC 6.000 kW >= RELAY2 threshold 5.000 kW',
                'surplus_next_target': 'RELAY2',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: False,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 61,
            'note': 't61 RELAY2 command is now visible and all three surplus targets are stably active',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=0.0, at_s=61),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=0.0, at_s=61),
            'expect_policy': {
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_next_target': 'NONE',
                'surplus_device_next_device_id': '',
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'NONE',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                E['actuator_ev_current_a']: 28,
            },
        },
    ]

    run_steps(h, steps)
