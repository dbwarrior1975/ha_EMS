import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps


@pytest.mark.scenario
def test_05_recovery_and_reactivation(project_root):
    """Phase 5: reactivation path from hard-off post-state to EV burn recovery."""
    pv_ent = ENT['pv_power_kw']
    h = build_harness(project_root)

    # Seed a hard-off post-state so this phase is independent from phases 1-4.
    h.set_entities({
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
        ENT['relay1']: False,
        ENT['surplus_r1_active']: False,
        ENT['surplus_r2_active']: False,
        ENT['surplus_adjustable_active']: False,
        ENT['pv_power_kw']: 1.9,
        ENT['ev_hard_off_pv_threshold_kw']: 1.6,
        ENT['ev_hard_off_low_pv_cycles']: 2,
    })
    h.set_attrs(ENT['policy_ev_current_a'], {
        'ev_policy_mode': 'hard_off',
        'ev_low_pv_cycles': 0,
        'ev_hard_off_release_ready_cycles': 0,
    })

    steps = [
        {
            'at_s': 224,
            'note': 't224 recovered PV and moderate RPC reactivate RELAY1 while EV remains hard-off',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.1,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 239.0,
                'surplus_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['relay1']: False,
                ENT['surplus_r1_active']: True,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
            },
        },
        {
            'at_s': 238,
            'note': 't238 RELAY1 activation is now visible at actuator level while EV remains hard-off',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.1,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 239.0,
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'relay1': {
                    'reason': 'state_changed',
                    'written': True,
                },
            },
            'expect_values': {
                ENT['relay1']: True,
                ENT['surplus_r1_active']: True,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
            },
        },
        {
            'at_s': 240,
            'note': 't240 recovered PV and RPC remain below the ADJUSTABLE activation threshold',
            'set': {
                ENT['required_power_consumption_kw']: 4.0,
                ENT['rpnz_w']: 0.15,
                pv_ent: 5.9,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 5.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
            },
        },
        {
            'at_s': 270,
            'note': 't270 recovered PV and RPC cross the ADJUSTABLE threshold so normal EV activation resumes',
            'set': {
                ENT['required_power_consumption_kw']: 5.8,
                ENT['rpnz_w']: 0.19,
                pv_ent: 5.9,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_explanation': 'Raw RPC 5.800 kW >= ADJUSTABLE threshold 5.060 kW',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'burn',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 5.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
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
            },
        },
    ]

    run_steps(h, steps)
