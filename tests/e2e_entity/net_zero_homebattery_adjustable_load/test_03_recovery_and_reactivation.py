import pytest

from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_previous_device_state
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_03_recovery_and_reactivation(project_root):
    """Phase 3: post-hard-off recovery, ADJUSTABLE reactivation, and EV burn restore."""
    h = build_harness(project_root)
    E = h.ent

    # Seed end-of-phase-2 state so phase is independent.
    seed_active_surplus_devices(
        h,
        active_device_ids=(),
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
        actuator_battery_setpoint_w=-1200,
    )
    seed_previous_device_state(h, mode='hard_off', low_pv_cycles=3)

    steps = [
        {
            'at_s': 210,
            'note': 't210 deficit intensifies again, no surplus path qualifies, and battery discharge is pushed toward a stronger defensive target.',
            'set': {
                E['required_power_consumption_kw']: -0.4,
                E['rpnz_w']: -100.0,
                E['grid_power_w']: 1200.0,
                E['pv_power_kw']: 1.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1800},
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -1800,
            },
        },
        {
            'at_s': 226,
            'note': 't226 prolonged low-PV stress reaches a trough, keeping EV unavailable while battery discharge is driven to its steepest support level in this segment.',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: -150.0,
                E['grid_power_w']: 700.0,
                E['pv_power_kw']: 1.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -2200},
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -2200,
            },
        },
        {
            'at_s': 240,
            'note': 't240 balance flips back positive and control posture relaxes, returning battery targeting toward neutral floor behavior.',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 200.0,
                E['grid_power_w']: 300.0,
                E['pv_power_kw']: 0.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -1200,
            },
        },
        {
            'at_s': 270,
            'note': 't270 the system holds a stable wait state with EV still off, preserving margin until surplus conditions are clearly sustained.',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 380.0,
                E['grid_power_w']: -2100.0,
                E['pv_power_kw']: 2.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -200,
            },
        },
        {
            'at_s': 275,
            'note': 't275 strong PV surplus crosses activation threshold, dispatch switches to ACTIVATE_ADJUSTABLE, and recovery mode starts.',
            'set': {
                E['required_power_consumption_kw']: 2.6,
                E['rpnz_w']: 400.0,
                E['grid_power_w']: -6100.0,
                E['pv_power_kw']: 5.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 800},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 800,
            },
        },
        {
            'at_s': 280,
            'note': 't280 recovery is now established: EV burn current is restored, battery support rises, and freeze logic holds stability against rapid re-flapping.',
            'set': {
                E['required_power_consumption_kw']: 0.1,
                E['rpnz_w']: 400.0,
                E['grid_power_w']: -6100.0,
                E['pv_power_kw']: 5.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 1800},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 290.0,
                'surplus_next_target': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 1800,
            },
        },
    ]

    run_steps(h, steps)
