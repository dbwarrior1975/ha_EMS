import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_previous_device_state
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_03_post_hard_off_recovery(project_root):
    """Phase 3: post-release/hard-off behavior and release-ready recovery ramp."""
    h = build_harness(project_root)

    # Seed phase-2 end state.
    seed_active_surplus_devices(
        h,
        active_device_ids=(),
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
        actuator_battery_setpoint_w=500,
    )
    h.set_entities({
        ENT['surplus_freeze_until']: 104.0,
        ENT['ev_hard_off_release_cycles']: 2,
    })
    seed_previous_device_state(h, mode='hard_off', low_pv_cycles=2)

    steps = [
        {
            'at_s': 240,
            'note': 't240 IF only RPC is abouve threshold but PV is below, remain in hard-off and do not count towards release-ready.',
            'set': {
                ENT['required_power_consumption_kw']: 1.45,
                ENT['rpnz_w']: -5.0,
                ENT['grid_power_w']: -2300.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 500},
            },
            'expect_policy': {
                'ev_hard_off_release_ready_cycles': 0,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 270,
            'note': 't270 conter not count if only PV is over threshold; remain in hard-off',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 1.0,
                ENT['grid_power_w']: -10.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
                'EV_CHARGER': {'enabled': False},
            },
            'expect_policy': {
                'ev_hard_off_release_ready_cycles': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': None,
            },
            'expect_values': {},
        },
        {
            'at_s': 275,
            'note': 't275 PV 1.5 kW: When both RPC and PV are above threshold, count towards release-ready and remain in hard-off until release-ready cycles met.',
            'set': {
                ENT['required_power_consumption_kw']: 1.385,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: -1100.0,
                ENT['ev_hard_off_low_pv_cycles']: 3,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
                'EV_CHARGER': {'enabled': False},
            },
            'expect_policy': {
                'ev_hard_off_release_ready_cycles': 1,                
                'surplus_freeze_until_ts': 104,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': None,
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 280,
            'note': 't280 PV 2.5 kW',
            'set': {
                ENT['required_power_consumption_kw']: 2.49,
                ENT['rpnz_w']: -10,
                ENT['grid_power_w']: 1900.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_policy': {
                'ev_hard_off_release_ready_cycles': 2,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': 380,
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 0,
                ENT['actuator_ev_enabled']: True,
            },
        },

        {
            'at_s': 285,
            'note': 't285 PV 2.5 kW',
            'set': {
                ENT['required_power_consumption_kw']: -2.49,
                ENT['rpnz_w']: -15,
                ENT['grid_power_w']: 2900.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_policy': {
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': None,
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 0,
                ENT['actuator_ev_current_a']: 6,
            },
        },   

        {
            'at_s': 295,
            'note': 't295 PV 5.5 kW',
            'set': {
                ENT['required_power_consumption_kw']: 2.49,
                ENT['rpnz_w']: 45,
                ENT['grid_power_w']: -2900.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': 2380,
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 0,
                ENT['actuator_ev_current_a']: 10,
            },
        },              
    ]

    run_steps(h, steps)
