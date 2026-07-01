import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_previous_device_state
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_02_release_and_low_pv_hard_off_path(project_root):
    """Phase 2: release ADJUSTABLE and drive low-PV hard-off/discharge sequence."""
    h = build_harness(project_root)
    E = h.ent

    # Seed phase-1 end state.
    seed_active_surplus_devices(
        h,
        active_device_ids=('EV_CHARGER',),
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
        actuator_battery_setpoint_w=1000,
    )
    h.set_entities({
        E['surplus_freeze_until']: 88.0,
    })
    seed_previous_device_state(h, mode='burn')

    steps = [
        {
            'at_s': 120,
            'note': 't120 weak PV cannot cover the deficit, so EV stays pinned at burn current while battery support is held at the minimum floor.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=11.0, required_power_consumption_kw=-6.4, at_s=120, pv_power_kw=1.4),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=11.0, required_power_consumption_kw=-6.4, at_s=120),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 135,
            'note': 't135 deficit crosses critical balance and triggers RELEASE_ADJUSTABLE, forcing EV support off and flipping battery control into discharge.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-10.0, required_power_consumption_kw=-6.4, at_s=135, pv_power_kw=1.4),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-10.0, required_power_consumption_kw=-6.4, at_s=135),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': -900},
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'RPNZ <= 10 W release deadband -> release lowest-priority active target',
            },
            'expect_values': {},
        },
        {
            'at_s': 150,
            'note': 't150 PV is fully gone; EV remains off and battery control resets to baseline floor behavior while the system waits for a viable surplus path.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=120.0, required_power_consumption_kw=-4.0, at_s=150, pv_power_kw=0.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=120.0, required_power_consumption_kw=-4.0, at_s=150),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {},
        },
        {
            'at_s': 160,
            'note': 't160 with zero PV and negative balance pressure, hard-off protection is active and battery discharge ramps deeper to hold net-zero control.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-20.0, required_power_consumption_kw=-4.0, at_s=160, pv_power_kw=0.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-20.0, required_power_consumption_kw=-4.0, at_s=160),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -900},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {},
        },
        {
            'at_s': 180,
            'note': 't180 small PV recovery is still insufficient; low-PV stress persists, EV stays locked out, and battery discharge deepens further.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-50.0, required_power_consumption_kw=-0.5, at_s=180, pv_power_kw=1.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-50.0, required_power_consumption_kw=-0.5, at_s=180),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1100},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -1100,
            },
        },
        {
            'at_s': 210,
            'note': 't210 deficit intensifies again, no surplus path qualifies, and battery discharge is pushed toward a stronger defensive target.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-100.0, required_power_consumption_kw=-0.4, at_s=210, pv_power_kw=1.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-100.0, required_power_consumption_kw=-0.4, at_s=210),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1300},
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
                E['actuator_battery_setpoint_w']: -1300,
            },
        },
        {
            'at_s': 226,
            'note': 't226 prolonged low-PV stress reaches a trough, keeping EV unavailable while battery discharge is driven to its steepest support level in this segment.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-150.0, required_power_consumption_kw=0.0, at_s=226, pv_power_kw=1.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-150.0, required_power_consumption_kw=0.0, at_s=226),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1300},
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
                E['actuator_battery_setpoint_w']: -1300,
            },
        },
    ]

    run_steps(h, steps)
