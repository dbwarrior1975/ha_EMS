import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.goal_transition_net_zero_to_max_export.scenario_steps import build_harness, run_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_max_export_hard_off_stability(project_root):
    h = build_harness(project_root)

    seed_active_surplus_devices(
        h,
        goal_profile='MAX_EXPORT',
        active_device_ids=(),
        actuator_relay1=False,
        actuator_relay2=False,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
        actuator_battery_setpoint_w=-200,
    )

    steps = [
        {
            'at_s': 120,
            'note': 't120 MAX_EXPORT keeps surplus clear and transitions EV policy to hard_off',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_device_dispatch_decision': 'CLEAR_ALL',
                'surplus_device_dispatch_action': 'CLEAR_ALL',
                'surplus_device_dispatch_target': '',
                'surplus_device_dispatch_device_id': '',
                'surplus_device_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_device_next_target': 'RELAY1',
                'surplus_device_next_device_id': 'RELAY1',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'mode': 'hard_off', 'current_a': 0},
                'RELAY1': {'enabled': False},
                'RELAY2': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'hard_off',
                    'written': True,
                    'target_current_a': 6,
                },
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
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_battery_setpoint_w']: -1200,
            },
        },
        {
            'at_s': 150,
            'note': 't150 MAX_EXPORT remains stable with EV hard_off and clear dispatch state',
            'set': {
                ENT['required_power_consumption_kw']: 7.0,
                ENT['rpnz_w']: 1000.0,
            },
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_device_dispatch_decision': 'CLEAR_ALL',
                'surplus_device_dispatch_action': 'CLEAR_ALL',
                'surplus_device_dispatch_target': '',
                'surplus_device_dispatch_device_id': '',
                'surplus_device_dispatch_contract': 'device_id_primary',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_device_next_target': 'RELAY1',
                'surplus_device_next_device_id': 'RELAY1',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'mode': 'hard_off', 'current_a': 0},
                'RELAY1': {'enabled': False},
                'RELAY2': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'hard_off',
                    'written': False,
                    'target_current_a': 6,
                },
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
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_battery_setpoint_w']: -2200,
            },
        },
    ]

    run_steps(h, steps)
