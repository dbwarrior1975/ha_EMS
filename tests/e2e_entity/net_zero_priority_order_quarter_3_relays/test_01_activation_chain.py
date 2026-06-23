import pytest

from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import run_steps

@pytest.mark.scenario
def test_01_activation_chain(project_root):
    """Phase 1: activation order RELAY1 -> EV_CHARGER -> RELAY2 -> RELAY3."""
    h = build_harness(project_root)
    E = h.ent
    relay3_enabled = h.dev('RELAY3', 'enabled')

    steps = [
        {
            'at_s': 0,
            'note': 't0 raw RPC crosses RELAY1 threshold so first activation decision targets RELAY1',
            'set': {
                E['required_power_consumption_kw']: 3.5,
                E['rpnz_w']: 500,
            },
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
                'RELAY3': {'enabled': False, 'mode': 'relay'},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
                relay3_enabled: False,
                E['actuator_ev_enabled']: False,
            },
        },
        {
            'at_s': 30,
            'note': 't30 RELAY1 is visible and EV becomes the next target once its threshold is reached',
            'set': {
                E['required_power_consumption_kw']: 6.0,
                E['rpnz_w']: 500,
            },
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
                'RELAY3': {'enabled': False, 'mode': 'relay'},
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
            'set': {
                E['required_power_consumption_kw']: 6.0,
                E['rpnz_w']: 500,
            },
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
                'RELAY3': {'enabled': False, 'mode': 'relay'},
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
            'note': 't61 RELAY2 command is now visible and RELAY3 is the remaining target',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_next_target': 'RELAY3',
                'surplus_device_next_device_id': 'RELAY3',
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'RELAY3',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'RELAY3': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                relay3_enabled: False,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 75,
            'note': 't75 RELAY3 becomes eligible as the fourth activation',
            'set': {
                E['required_power_consumption_kw']: 8.0,
                E['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_device_dispatch_decision': 'ACTIVATE_RELAY3',
                'surplus_device_next_target': 'RELAY3',
                'surplus_device_next_device_id': 'RELAY3',
                'surplus_freeze_until_ts': 90.0,
                'surplus_explanation': 'Raw RPC 8.000 kW >= RELAY3 threshold 7.500 kW',
                'surplus_next_target': 'RELAY3',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'RELAY3': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                relay3_enabled: False,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 76,
            'note': 't76 RELAY3 command is visible and all four surplus targets are active',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_next_target': 'NONE',
                'surplus_device_next_device_id': '',
                'surplus_freeze_until_ts': 90.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'NONE',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'RELAY3': {'enabled': True, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                relay3_enabled: True,
                E['actuator_ev_current_a']: 28,
            },
        },
    ]

    run_steps(h, steps)
