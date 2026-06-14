import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import run_steps


@pytest.mark.scenario
def test_02_release_and_hard_off_hold(project_root):
    """Phase 2: relay/adjustable releases and EV hard-off hold behavior."""
    h = build_harness(project_root)

    h.set_entities({
        ENT['surplus_adjustable_active']: True,
        ENT['surplus_r1_active']: True,
        ENT['surplus_r2_active']: False,
        ENT['surplus_freeze_until']: 104.0,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 20,
        ENT['actuator_battery_setpoint_w']: 2500,
    })
    h.set_attrs(ENT['policy_ev_current_a'], {
        'ev_policy_mode': 'burn',
        'ev_low_pv_cycles': 0,
        'ev_hard_off_active': False,
        'ev_hard_off_release_ready_cycles': 0,
    })

    steps = [
        {
            'at_s': 135,
            'note': 't135 PV 1.7 kW: low RPNZ triggers RELEASE_RELAY1 and adjustable path remains active.',
            'set': {
                ENT['required_power_consumption_kw']: -3.4,
                ENT['rpnz_w']: -10.0,
                ENT['grid_power_w']: 3290.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY1',
                ENT['policy_ev_current_a']: 6,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_low_pv_cycles': 0,
                'battery_to_ev_loop_risk': 0.0,
            },
            'expect_dispatch_state': {'decision': 'RELEASE_RELAY1'},
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 1500,
            },
        },
        {
            'at_s': 150,
            'note': 't150 PV below threshold: RELEASE_ADJUSTABLE occurs and battery target ramps down per limits.',
            'set': {
                ENT['required_power_consumption_kw']: -4.0,
                ENT['rpnz_w']: -100.0,
                ENT['grid_power_w']: 2320.0,
                

                ENT['pv_power_kw']: 1.5,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_ADJUSTABLE',
                ENT['policy_ev_current_a']: 6,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_low_pv_cycles': 1,
                'battery_to_ev_loop_risk': False,
            },
            'expect_dispatch_state': {'decision': 'RELEASE_ADJUSTABLE'},
            'expect_values': {
                ENT['surplus_adjustable_active']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 160,
            'note': 't160 PV 0.0 kW: EV enters HARD_OFF after low-PV persistence criteria are met.',
            'set': {
                ENT['required_power_consumption_kw']: 0.5,
                ENT['rpnz_w']: -80.0,
                ENT['grid_power_w']: -2020.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
                'ev_low_pv_cycles': 2,
                'battery_to_ev_loop_risk': False,
            },
            'expect_dispatch_state': {'decision': 'NOOP'},
            'expect_values': {
                ENT['surplus_adjustable_active']: False,
                ENT['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 180,
            'note': 't180 PV 1.0 kW: hold state with EV disabled and battery setpoint held by gate logic.',
            'set': {
                ENT['required_power_consumption_kw']: 0.9,
                ENT['rpnz_w']: -50.0,
                ENT['grid_power_w']: -500.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_dispatch_state': {'decision': 'NOOP'},
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 210,
            'note': 't210 PV 1.0 kW with negative RPNZ: remain in hold path while waiting below ADJUSTABLE threshold.',
            'set': {
                ENT['required_power_consumption_kw']: 1.4,
                ENT['rpnz_w']: -40.0,
                ENT['grid_power_w']: -900.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,                
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_dispatch_state': {'decision': 'NOOP'},
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 226,
            'note': 't226 PV 1.0 kW with negative RPNZ: EV remains hard-off and battery command stays held.',
            'set': {
                ENT['required_power_consumption_kw']: 1.9,
                ENT['rpnz_w']: -10.0,
                ENT['grid_power_w']: -1200.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 0.0,
            },
            'expect_dispatch_state': {'decision': 'NOOP'},
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 240,
            'note': 't240 post-release: baseline floor semantics continue with hard-off still active.',
            'set': {
                ENT['required_power_consumption_kw']: 1.95,
                ENT['rpnz_w']: -5.0,
                ENT['grid_power_w']: -2300.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_dispatch_state': {'decision': 'NOOP'},
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 500,
            },
        },
    ]

    run_steps(h, steps)
