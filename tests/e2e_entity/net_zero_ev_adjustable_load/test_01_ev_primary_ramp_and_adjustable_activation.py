import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_ev_primary_ramp_and_adjustable_activation(project_root):
    """Phase 1: EV-primary ramp, ADJUSTABLE activation, and RELAY1 activation edge."""
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 't0 PV 0.5 kW: no surplus yet; battery target stays 0 W and EV remains at minimum charge current.',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: -10.0,
                ENT['grid_power_w']: -20.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 10,
            'note': 't10 PV 1.5 kW: EV ramps up while battery target remains near 0 W (RPC below threshold).',
            'set': {
                ENT['required_power_consumption_kw']: 2.1,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: -2000.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 8,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 15,
            'note': 't15 PV 3.0 kW: EV-first path continues and battery target stays at 0 W.',
            'set': {
                ENT['required_power_consumption_kw']: 2,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: -2200.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 12,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
                'primary_power_envelope_w': 2840,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 12,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 20,
            'note': 't20 PV 3.0 kW: EV-first path continues and battery target stays at 0 W.',
            'set': {
                ENT['required_power_consumption_kw']: 2,
                ENT['rpnz_w']: 550.0,
                ENT['grid_power_w']: -2800.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 16,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 16,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 30,
            'note': 't30 PV 2.0 kW: EV remains the primary sink and battery target stays at 0 W.',
            'set': {
                ENT['required_power_consumption_kw']: 2.1,
                ENT['rpnz_w']: 530.0,
                ENT['grid_power_w']: -1120.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 19,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 19,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 45,
            'note': 't45 PV 4.0 kW: EV absorbs available surplus; battery target remains 0 W with floor override active.',
            'set': {
                ENT['required_power_consumption_kw']: 0.1,
                ENT['rpnz_w']: 340.0,
                ENT['grid_power_w']: -1843.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 23,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 23,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 55,
            'note': 't55 PV 6.4 kW: EV keeps consuming surplus; battery target remains at 0 W.',
            'set': {
                ENT['required_power_consumption_kw']: 0.9,
                ENT['rpnz_w']: 50.0,
                ENT['grid_power_w']: -3140.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 27,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 27,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 60,
            'note': 't60 PV 6.4 kW: EV current remains high and affects grid power as expected.',
            'set': {
                ENT['required_power_consumption_kw']: 1.5,
                ENT['rpnz_w']: 50.0,
                ENT['grid_power_w']: -1840.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 70,
            'note': 't70 PV 8.0 kW: EV reaches high current; dispatch still waits for ADJUSTABLE activation.',
            'set': {
                ENT['required_power_consumption_kw']: 1.0,
                ENT['rpnz_w']: 250.0,
                ENT['grid_power_w']: -4140.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: None,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 73,
            'note': 't73 PV 8.0 kW: RPC crosses ADJUSTABLE threshold and adjustable path activates.',
            'set': {
                ENT['required_power_consumption_kw']: 2.6,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: -1500.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
                'surplus_explanation': 'Raw RPC 2.600 kW >= ADJUSTABLE threshold 2.500 kW',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 80,
            'note': 't80 PV 8.0 kW: after activation, battery setpoint ramps with configured ramp limits.',
            'set': {
                ENT['required_power_consumption_kw']: -100.0,
                ENT['rpnz_w']: 450.0,
                ENT['grid_power_w']: -40.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 2500,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'surplus_freeze_until_ts': 88.0,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 89,
            'note': 't89 PV 10.0 kW: RELAY1 activation occurs while EV remains prioritized.',
            'set': {
                ENT['required_power_consumption_kw']: 2.4,
                ENT['rpnz_w']: 450.0,
                ENT['grid_power_w']: -40.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 2500,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'surplus_freeze_until_ts': 104.0,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'surplus_explanation': 'Raw RPC 2.400 kW >= RELAY1 threshold 2.300 kW',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 90,
            'note': 't90 PV drops to 3kW: EV remains the primary sink and battery target stays at adjustable clamp level',
            'set': {
                ENT['required_power_consumption_kw']: 2.3,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: 4040.0,
                ENT['pv_power_kw']: 3.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 24,
                ENT['policy_battery_target_w']: 2500,
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_current_a']: 24,
                ENT['actuator_battery_setpoint_w']: 2500,
            },
        },
    ]

    run_steps(h, steps)
