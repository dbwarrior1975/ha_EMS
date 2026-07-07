import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.goal_transition_net_zero_to_max_export.scenario_steps import build_harness, run_steps

@pytest.mark.scenario
def test_activation_and_ev_burn_window(project_root):
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 NET_ZERO activates relay1 first',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=3.5, at_s=0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=3.5, at_s=0),
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_dispatch_action': 'ACTIVATE',
                'surplus_dispatch_device_id': 'RELAY1',
                'surplus_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'mode': 'restore_min'},
                'RELAY1': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 8,
                E['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 30,
            'note': 't30 NET_ZERO activates EV next',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=7.0, at_s=30),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=7.0, at_s=30),
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'ACTIVATE_EV_CHARGER',
                'surplus_dispatch_action': 'ACTIVATE',
                'surplus_dispatch_device_id': 'EV_CHARGER',
                'surplus_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Raw RPC 7.000 kW >= EV_CHARGER threshold 6.440 kW',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'mode': 'restore_min'},
                'RELAY1': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 8,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 44,
            'note': 't44 EV burn visible while activation freeze blocks additional surplus changes',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=2.0, at_s=44),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=2.0, at_s=44),
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'NOOP',
                'surplus_dispatch_action': 'NOOP',
                'surplus_dispatch_device_id': '',
                'surplus_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True, 'mode': 'burn'},
                'RELAY1': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'state_changed',
                    'written': True,
                },
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 3000,
            },
        },
        {
            'at_s': 60,
            'note': 't60 EV burn is active at max current',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=1.0, at_s=60),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=1.0, at_s=60),
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'NOOP',
                'surplus_dispatch_action': 'NOOP',
                'surplus_dispatch_device_id': '',
                'surplus_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True, 'mode': 'burn'},
                'RELAY1': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 3500,
            },
        },
    ]

    run_steps(h, steps)
