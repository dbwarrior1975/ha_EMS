import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_previous_device_state
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

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
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-100.0, required_power_consumption_kw=-0.4, at_s=210, pv_power_kw=1.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-100.0, required_power_consumption_kw=-0.4, at_s=210),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1400},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -1400,
            },
        },
        {
            'at_s': 226,
            'note': 't226 prolonged low-PV stress reaches a trough, keeping EV unavailable while battery discharge is driven to its steepest support level in this segment.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-150.0, required_power_consumption_kw=0.0, at_s=226, pv_power_kw=1.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-150.0, required_power_consumption_kw=0.0, at_s=226),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1400},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -1400,
            },
        },
        {
            'at_s': 240,
            'note': 't240 balance flips back positive and control posture relaxes, returning battery targeting toward neutral floor behavior.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=200.0, required_power_consumption_kw=0.0, at_s=240, pv_power_kw=0.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=200.0, required_power_consumption_kw=0.0, at_s=240),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1400},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -1400,
            },
        },
        {
            'at_s': 270,
            'note': 't270 the system holds a stable wait state with EV still off, preserving margin until surplus conditions are clearly sustained.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=380.0, required_power_consumption_kw=0.0, at_s=270, pv_power_kw=2.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=380.0, required_power_consumption_kw=0.0, at_s=270),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1400},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -1400,
            },
        },
        {
            'at_s': 275,
            'note': 't275 strong PV surplus crosses activation threshold, dispatch switches to ACTIVATE_ADJUSTABLE, and recovery mode starts.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=400.0, required_power_consumption_kw=2.6, at_s=275, pv_power_kw=5.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=400.0, required_power_consumption_kw=2.6, at_s=275),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_freeze_until_ts': 290.0,
                'surplus_explanation': 'Raw RPC 2.600 kW >= EV_CHARGER threshold 2.500 kW',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -400,
            },
        },
        {
            'at_s': 280,
            'note': 't280 recovery is now established: EV burn current is restored, battery support rises, and freeze logic holds stability against rapid re-flapping.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=400.0, required_power_consumption_kw=0.1, at_s=280, pv_power_kw=5.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=400.0, required_power_consumption_kw=0.1, at_s=280),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 290.0,
                'surplus_next_target': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 100,
            },
        },
    ]

    run_steps(h, steps)
