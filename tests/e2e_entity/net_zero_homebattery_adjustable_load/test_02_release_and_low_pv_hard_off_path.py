import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import run_steps


@pytest.mark.scenario
def test_02_release_and_low_pv_hard_off_path(project_root):
    """Phase 2: release ADJUSTABLE and drive low-PV hard-off/discharge sequence."""
    h = build_harness(project_root)

    # Seed phase-1 end state.
    h.set_entities({
        ENT['surplus_adjustable_active']: True,
        ENT['surplus_r1_active']: False,
        ENT['surplus_r2_active']: False,
        ENT['surplus_freeze_until']: 88.0,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 28,
        ENT['actuator_battery_setpoint_w']: 1000,
    })
    h.set_attrs(ENT['policy_ev_current_a'], {
        'ev_policy_mode': 'burn',
        'ev_low_pv_cycles': 0,
        'ev_hard_off_active': False,
        'ev_hard_off_release_ready_cycles': 0,
    })

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
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 100,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
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
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_ADJUSTABLE',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -900,
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'surplus_next_target': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: False,
            },
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
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 100,
            },
            'expect_policy': {
                'ev_low_pv_cycles': 1,
                'ev_hard_off_active': False,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: False,
            },
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
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -900,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'ev_low_pv_cycles': 2,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: False,
            },
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
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -1200,
            },
            'expect_policy': {
                'ev_low_pv_cycles': 3,
                'ev_hard_off_active': True,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
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
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -1800,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: -1800,
            },
            'expect_battery_negative': True,
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
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -2200,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: -2200,
            },
            'expect_battery_negative': True,
        },
    ]

    run_steps(h, steps)
