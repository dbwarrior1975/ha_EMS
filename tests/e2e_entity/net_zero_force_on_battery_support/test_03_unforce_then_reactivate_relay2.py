import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import build_harness
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_03_unforce_then_reactivate_relay2(project_root):
    """Phase 3: remove user force and re-activate RELAY2 through normal surplus path."""
    h = build_harness(project_root)

    # Seed post-t210 state so phase is independent from previous phases.
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY2',),
        actuator_relay1=False,
        actuator_relay2=True,
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        ENT['relay2_force_on']: True,
    })

    steps = [
        {
            'at_s': 240,
            'note': 't240 user removes RELAY2 force and the relay turns off at actuator level',
            'set': {
                ENT['relay2_force_on']: False,
                ENT['required_power_consumption_kw']: -3.0,
                ENT['rpnz_w']: -0.015,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
                'surplus_next_target': 'RELAY1',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': False,
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
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
            'at_s': 270,
            'note': 't270 RPC now triggers RELAY2 through ordinary surplus logic, but actuator state remains unchanged this step',
            'set': {
                ENT['required_power_consumption_kw']: 8.0,
                ENT['rpnz_w']: 0.015,
                ENT['grid_power_w']: -2500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 285.0,
                'surplus_explanation': 'Raw RPC 8.000 kW >= RELAY2 threshold 5.000 kW',
                'surplus_next_target': 'RELAY2',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': False,
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
            },
            'expect_dispatch_state': {

                'freeze_until_ts': 285.0,
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
            'expect_values': {
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 284,
            'note': 't284 RELAY2 freeze is still active and prevents RELAY1 activation',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.115,
                ENT['grid_power_w']: -500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 285.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'RELAY1',
                'prev_relay1_force_on': False,
                'prev_relay2_force_on': False,
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
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
            'expect_values': {
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
        },
    ]

    run_steps(h, steps)
