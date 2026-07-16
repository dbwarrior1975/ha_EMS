import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_previous_device_state
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_03_recovery_and_reactivation(project_root):
    """Phase 3: post-hard-off recovery, EV_CHARGER reactivation, and EV burn restore."""
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
            'note': 't210 no surplus path qualifies; producer authority updates from the seeded signed target using measured grid feedback.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-100.0, required_power_consumption_kw=-0.4, at_s=210, pv_power_kw=1.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-100.0, required_power_consumption_kw=-0.4, at_s=210),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1400},
            },
            'expect_policy': {
                'surplus_next_device_id': 'RELAY1',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
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
            'note': 't226 prolonged low-PV stress reaches a trough, keeping EV unavailable while producer authority follows measured grid feedback.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-150.0, required_power_consumption_kw=0.0, at_s=226, pv_power_kw=1.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-150.0, required_power_consumption_kw=0.0, at_s=226),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1400},
            },
            'expect_policy': {
                'surplus_next_device_id': 'RELAY1',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
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
            'note': 't240 balance flips back positive and control posture relaxes, ending producer authority while preserving the current canonical target.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=200.0, required_power_consumption_kw=0.0, at_s=240, pv_power_kw=0.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=200.0, required_power_consumption_kw=0.0, at_s=240),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1400},
            },
            'expect_policy': {
                'surplus_next_device_id': 'RELAY1',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
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
            'note': 't270 the system holds a stable wait state with EV still off, holding the canonical target until surplus conditions are clearly sustained.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=380.0, required_power_consumption_kw=0.0, at_s=270, pv_power_kw=2.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=380.0, required_power_consumption_kw=0.0, at_s=270),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1400},
            },
            'expect_policy': {
                'surplus_next_device_id': 'RELAY1',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
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
            'note': 't275 the second recovered-PV tick releases HARD_OFF; RPC independently causes an ACTIVATE_EV_CHARGER dispatch.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=400.0, required_power_consumption_kw=7.0, at_s=275, pv_power_kw=5.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=400.0, required_power_consumption_kw=7.0, at_s=275),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'mode': 'restore_min'},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_freeze_until_ts': 290.0,
                'surplus_explanation': 'Raw RPC 7.000 kW >= EV_CHARGER threshold 5.060 kW',
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 2,
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -400,
            },
        },
        {
            'at_s': 280,
            'note': 't280 the dispatch-applier state makes EV active; lifecycle is already released and freeze holds further surplus changes.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=400.0, required_power_consumption_kw=0.1, at_s=280, pv_power_kw=5.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=400.0, required_power_consumption_kw=0.1, at_s=280),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True, 'target_w': 6440},
                'HOME_BATTERY': {'target_w': -400},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 290.0,
                'surplus_next_device_id': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 0,
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: -400,
            },
        },
        {
            'at_s': 285,
            'note': 't285 EV remains active while HOME_BATTERY takes positive primary authority and freeze remains in force.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=400.0, required_power_consumption_kw=7.0, at_s=285, pv_power_kw=5.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=400.0, required_power_consumption_kw=7.0, at_s=285),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True, 'target_w': 6440},
                'HOME_BATTERY': {'target_w': 600},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 290.0,
                'surplus_next_device_id': 'RELAY1',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 0,
            },
        },
        {
            'at_s': 290,
            'note': 't290 EV stays active and the next eligible relay receives its independent surplus activation command.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=400.0, required_power_consumption_kw=7.0, at_s=290, pv_power_kw=5.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=400.0, required_power_consumption_kw=7.0, at_s=290),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True, 'target_w': 6440},
                'HOME_BATTERY': {'target_w': 1600},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 305.0,
                'surplus_next_device_id': 'RELAY1',
                'surplus_explanation': 'Raw RPC 7.000 kW >= RELAY1 threshold 2.500 kW',
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 0,
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
            },
        },
    ]

    run_steps(h, steps)
