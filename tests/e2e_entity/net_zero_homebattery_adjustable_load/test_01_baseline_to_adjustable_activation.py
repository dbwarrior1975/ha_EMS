import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_baseline_to_adjustable_activation(project_root):
    """Phase 1: baseline battery-support path and ADJUSTABLE activation transition."""
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 't0 baseline: NOOP, EV disabled at 4A min, battery target/setpoint 0W, and default floor semantics stay active',
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
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 10,
            'note': 't10 moderate surplus: still NOOP with EV inactive; battery target/setpoint rises to 600W while floor semantics remain unchanged',
            'set': {
                ENT['required_power_consumption_kw']: 1.2,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: -1200.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 600,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 600,
            },
        },
        {
            'at_s': 15,
            'note': 't15 increased load: NOOP continues, EV stays inactive, and battery target/setpoint climbs to 1400W',
            'set': {
                ENT['required_power_consumption_kw']: 1.9,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: -1000.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 1400,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 1400,
            },
        },
        {
            'at_s': 20,
            'note': 't20 upper pre-threshold: still NOOP with ADJUSTABLE as next target; EV remains inactive and battery target/setpoint reaches 2000W',
            'set': {
                ENT['required_power_consumption_kw']: 2,
                ENT['rpnz_w']: 550.0,
                ENT['grid_power_w']: -2800.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 30,
            'note': 't30 steady state: no activation transition; EV remains disabled at 4A and battery stays at 2000W target/setpoint',
            'set': {
                ENT['required_power_consumption_kw']: 2.1,
                ENT['rpnz_w']: 530.0,
                ENT['grid_power_w']: -1120.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 45,
            'note': 't45 low RPC sample: EV still inactive, NOOP decision, and battery path continues at 2000W without floor override mode',
            'set': {
                ENT['required_power_consumption_kw']: 0.5,
                ENT['rpnz_w']: 340.0,
                ENT['grid_power_w']: -1843.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 55,
            'note': 't55 sustained condition: ADJUSTABLE remains next target but not activated; EV stays off and battery target/setpoint remains 2000W',
            'set': {
                ENT['required_power_consumption_kw']: 0.5,
                ENT['rpnz_w']: 50.0,
                ENT['grid_power_w']: -3140.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 60,
            'note': 't60 altered grid signal: behavior still NOOP with EV inactive and battery held at 2000W, using not_applicable floor reason',
            'set': {
                ENT['required_power_consumption_kw']: 0.5,
                ENT['rpnz_w']: 50.0,
                ENT['grid_power_w']: -1840.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 70,
            'note': 't70 higher import/export swing: policy waits for ADJUSTABLE threshold, no activation occurs, EV stays off, battery remains 2000W',
            'set': {
                ENT['required_power_consumption_kw']: 1.0,
                ENT['rpnz_w']: 250.0,
                ENT['grid_power_w']: -4140.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: None,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 73,
            'note': 't73 trigger point: RPC crosses ADJUSTABLE threshold and dispatch activates adjustable load',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: -1500.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 80,
            'note': 't80 post-trigger collapse: adjustable is released on negative RPC and relay path becomes next candidate',
            'set': {
                ENT['required_power_consumption_kw']: -100.0,
                ENT['rpnz_w']: 450.0,
                ENT['grid_power_w']: -40.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'surplus_freeze_until_ts': 88.0,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 89,
            'note': 't89 post-trigger hold: relay path remains the next candidate while adjustable stays active',
            'set': {
                ENT['required_power_consumption_kw']: 2.4,
                ENT['rpnz_w']: 450.0,
                ENT['grid_power_w']: -40.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'surplus_freeze_until_ts': 88.0,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 90,
            'note': 't90 PV has collapsed and EV is still burning hard; hard-off pressure is building while battery support is trimmed to 1.0 kW.',
            'set': {
                ENT['required_power_consumption_kw']: -5.0,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: 4040.0,
                ENT['pv_power_kw']: 3.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 1000,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 1000,
            },
        },
    ]

    run_steps(h, steps)
