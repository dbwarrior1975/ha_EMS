import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_activation_and_burn(project_root):
    """Phase 1: activate RELAY1, activate ADJUSTABLE, and confirm stable EV burn."""
    pv_ent = ENT['pv_power_kw']
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 't0 enough surplus -> activate relay1 first',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
                pv_ent: 3.5,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'restore_min',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 3.5,
                'ev_hard_off_pv_threshold_kw': 1.6,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['actuator_battery_setpoint_w']: 200,
            },
        },
        {
            'at_s': 30,
            'note': 't30 enough surplus -> activate EV next',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 2900,
                pv_ent: 3.2,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 45.0,
                'surplus_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_explanation': 'Raw RPC 6.000 kW >= ADJUSTABLE threshold 5.520 kW',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'restore_min',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 3.2,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_ADJUSTABLE',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_battery_setpoint_w']: 1200,
            },
        },
        {
            'at_s': 46,
            'note': 't46 freeze has expired and EV burn is now visible at max current',
            'set': {
                ENT['required_power_consumption_kw']: 4.5,
                ENT['rpnz_w']: 500,
                pv_ent: 3.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 45.0,
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 3.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'state_changed',
                    'written': True,
                    'target_current_a': 28,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['surplus_adjustable_active']: True,
            },
        },
        {
            'at_s': 60,
            'note': 't60 EV remains stably at max current after the freeze-expiry transition',
            'set': {
                ENT['required_power_consumption_kw']: 4.9,
                ENT['rpnz_w']: 500,
                pv_ent: 3.0,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 3.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'already_matching',
                    'written': False,
                    'target_current_a': 28,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['surplus_adjustable_active']: True,
            },
        },
    ]

    run_steps(h, steps)
