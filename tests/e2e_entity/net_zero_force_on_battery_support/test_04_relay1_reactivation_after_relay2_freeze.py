import pytest

from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import build_harness
from tests.e2e_entity.net_zero_force_on_battery_support.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_04_relay1_reactivation_after_relay2_freeze(project_root):
    """Phase 4: RELAY1 reactivates after RELAY2 freeze window and stabilizes."""
    h = build_harness(project_root)
    E = h.ent

    # Seed post-t284 state so phase is independent from previous phases.
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY2',),
        actuator_relay1=False,
        actuator_relay2=True,
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        E['devices']['RELAY2']['force_on']: False,
        E['surplus_freeze_until']: 285.0,
    })

    steps = [
        {
            'at_s': 300,
            'note': 't300 RELAY2 is on and RELAY1 activation has already reached dispatch state state',
            'set': {
                E['required_power_consumption_kw']: 3.0,
                E['rpnz_w']: 0.215,
                E['grid_power_w']: -500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 315.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'prev_force_on_device_ids': (),
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
            },
            'expect_dispatch_state': {

                'freeze_until_ts': 315.0,
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
            'at_s': 301,
            'note': 't301 RELAY1 command is already visible while freeze still blocks further surplus activation',
            'set': {
                E['required_power_consumption_kw']: 3.0,
                E['rpnz_w']: 0.215,
                E['grid_power_w']: -500.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 315.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'ADJUSTABLE',
                'prev_force_on_device_ids': (),
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
            },
            'expect_writer_trace': {
                'RELAY1': {
                    'reason': 'state_changed',
                    'written': True,
                },
                'RELAY2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
            },
        },
        {
            'at_s': 330,
            'note': 't330 RELAY1 activation is now visible and both relays are stably on',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.115,
                E['grid_power_w']: 1500.0,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'prev_force_on_device_ids': (),
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
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
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
            },
        },
    ]

    run_steps(h, steps)
