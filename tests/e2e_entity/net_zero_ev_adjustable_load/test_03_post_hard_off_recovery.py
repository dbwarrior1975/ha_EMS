import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import run_steps


@pytest.mark.scenario
def test_03_post_hard_off_recovery(project_root):
    """Phase 3: post-release/hard-off behavior and release-ready recovery ramp."""
    h = build_harness(project_root)

    # Seed phase-2 end state.
    h.set_entities({
        ENT['surplus_adjustable_active']: False,
        ENT['surplus_r1_active']: False,
        ENT['surplus_r2_active']: False,
        ENT['surplus_freeze_until']: 104.0,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 4,
        ENT['actuator_battery_setpoint_w']: 500,
    })
    h.set_attrs(ENT['policy_ev_current_a'], {
        'ev_policy_mode': 'hard_off',
        'ev_low_pv_cycles': 2,
        'ev_hard_off_active': True,
        'ev_hard_off_release_ready_cycles': 0,
    })

    steps = [
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
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 270,
            'note': 't270 post-release: controller remains stable with NOOP dispatch.',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 1.0,
                ENT['grid_power_w']: -10.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': None,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {},
        },
        {
            'at_s': 275,
            'note': 't275 PV 1.5 kW',
            'set': {
                ENT['required_power_consumption_kw']: 2.49,
                ENT['rpnz_w']: 2501.0,
                ENT['grid_power_w']: -1100.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 104,
                'ev_hard_off_active': True,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': None,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 295,
            'note': 't295 PV 2.5 kW',
            'set': {
                ENT['required_power_consumption_kw']: 2.49,
                ENT['rpnz_w']: 2501,
                ENT['grid_power_w']: -1900.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
                ENT['policy_ev_current_a']: 8,
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': 1920,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 0,
            },
        },
    ]

    run_steps(h, steps)
