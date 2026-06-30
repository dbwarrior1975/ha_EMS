import pytest

from tests.e2e_entity.goal_transition_net_zero_to_max_export.scenario_steps import build_harness, run_steps

@pytest.mark.scenario
def test_activation_and_ev_burn_window(project_root):
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 NET_ZERO activates relay1 first',
            'set': {
                E['required_power_consumption_kw']: 3.5,
                E['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_device_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_device_dispatch_action': 'ACTIVATE',
                'surplus_device_dispatch_target': 'RELAY1',
                'surplus_device_dispatch_device_id': 'RELAY1',
                'surplus_device_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_device_next_target': 'RELAY1',
                'surplus_device_next_device_id': 'RELAY1',
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
                E['actuator_battery_setpoint_w']: 200,
            },
        },
        {
            'at_s': 30,
            'note': 't30 NET_ZERO activates EV next',
            'set': {
                E['required_power_consumption_kw']: 6.0,
                E['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_device_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_device_dispatch_action': 'ACTIVATE',
                'surplus_device_dispatch_target': 'ADJUSTABLE',
                'surplus_device_dispatch_device_id': 'EV_CHARGER',
                'surplus_device_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Raw RPC 6.000 kW >= EV_CHARGER threshold 5.060 kW',
                'surplus_device_next_target': 'ADJUSTABLE',
                'surplus_device_next_device_id': 'EV_CHARGER',
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
                E['actuator_battery_setpoint_w']: 400,
            },
        },
        {
            'at_s': 44,
            'note': 't44 EV burn visible while activation freeze blocks additional surplus changes',
            'set': {
                E['required_power_consumption_kw']: 2.0,
                E['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_dispatch_action': 'NOOP',
                'surplus_device_dispatch_target': '',
                'surplus_device_dispatch_device_id': '',
                'surplus_device_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_device_next_target': 'RELAY2',
                'surplus_device_next_device_id': 'RELAY2',
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
                E['actuator_battery_setpoint_w']: 600,
            },
        },
        {
            'at_s': 60,
            'note': 't60 EV burn is active at max current',
            'set': {
                E['required_power_consumption_kw']: 1.0,
                E['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_dispatch_action': 'NOOP',
                'surplus_device_dispatch_target': '',
                'surplus_device_dispatch_device_id': '',
                'surplus_device_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_device_next_target': 'RELAY2',
                'surplus_device_next_device_id': 'RELAY2',
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
                E['actuator_battery_setpoint_w']: 800,
            },
        },
    ]

    run_steps(h, steps)
