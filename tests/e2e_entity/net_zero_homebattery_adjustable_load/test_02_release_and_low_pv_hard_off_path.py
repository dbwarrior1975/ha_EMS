import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_previous_device_state
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_02_release_and_low_pv_hard_off_path(project_root):
    """Phase 2: release ADJUSTABLE and drive low-PV hard-off/discharge sequence."""
    h = build_harness(project_root)

    # Seed phase-1 end state.
    seed_active_surplus_devices(
        h,
        active_device_ids=('EV_CHARGER',),
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
        actuator_battery_setpoint_w=1000,
    )
    h.set_entities({
        ENT['surplus_freeze_until']: 88.0,
    })
    seed_previous_device_state(h, mode='burn')

    steps = [
        {
            'at_s': 120,
            'note': 't120 weak PV cannot cover the deficit, so EV stays pinned at burn current while battery support is held at the minimum floor.',
            'set': {
                ENT['required_power_consumption_kw']: -6.4,
                ENT['rpnz_w']: 10.0,
                ENT['grid_power_w']: 6290.0,
                ENT['pv_power_kw']: 1.4,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 135,
            'note': 't135 deficit crosses critical balance and triggers RELEASE_ADJUSTABLE, forcing EV support off and flipping battery control into discharge.',
            'set': {
                ENT['required_power_consumption_kw']: -6.4,
                ENT['rpnz_w']: -10.0,
                ENT['grid_power_w']: 6290.0,
                ENT['pv_power_kw']: 1.4,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -900},
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {},
        },
        {
            'at_s': 150,
            'note': 't150 PV is fully gone; EV remains off and battery control resets to baseline floor behavior while the system waits for a viable surplus path.',
            'set': {
                ENT['required_power_consumption_kw']: -4.0,
                ENT['rpnz_w']: 120.0,
                ENT['grid_power_w']: 4320.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {},
        },
        {
            'at_s': 160,
            'note': 't160 with zero PV and negative balance pressure, hard-off protection is active and battery discharge ramps deeper to hold net-zero control.',
            'set': {
                ENT['required_power_consumption_kw']: -4.0,
                ENT['rpnz_w']: -20.0,
                ENT['grid_power_w']: 4320.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -900},
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {},
        },
        {
            'at_s': 180,
            'note': 't180 small PV recovery is still insufficient; low-PV stress persists, EV stays locked out, and battery discharge deepens further.',
            'set': {
                ENT['required_power_consumption_kw']: -0.5,
                ENT['rpnz_w']: -50.0,
                ENT['grid_power_w']: 500.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1200},
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: -1200,
            },
        },
        {
            'at_s': 210,
            'note': 't210 deficit intensifies again, no surplus path qualifies, and battery discharge is pushed toward a stronger defensive target.',
            'set': {
                ENT['required_power_consumption_kw']: -0.4,
                ENT['rpnz_w']: -100.0,
                ENT['grid_power_w']: 1200.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -1800},
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: -1800,
            },
        },
        {
            'at_s': 226,
            'note': 't226 prolonged low-PV stress reaches a trough, keeping EV unavailable while battery discharge is driven to its steepest support level in this segment.',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: -150.0,
                ENT['grid_power_w']: 700.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': -2200},
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: -2200,
            },
        },
    ]

    run_steps(h, steps)
