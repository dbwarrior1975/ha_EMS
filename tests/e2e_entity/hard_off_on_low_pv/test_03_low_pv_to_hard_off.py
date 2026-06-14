import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps


@pytest.mark.scenario
def test_03_low_pv_to_hard_off(project_root):
    """Phase 3: second low-PV cycle triggers EV hard-off."""
    pv_ent = ENT['pv_power_kw']
    h = build_harness(project_root)

    # Seed end-of-phase-2 state so phase 3 is independent from warmup chains.
    h.set_entities({
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 6,
        ENT['relay1']: True,
        ENT['surplus_r1_active']: True,
        ENT['surplus_r2_active']: False,
        ENT['surplus_adjustable_active']: False,
        ENT['pv_power_kw']: 1.3,
        ENT['ev_hard_off_pv_threshold_kw']: 1.6,
        ENT['ev_hard_off_low_pv_cycles']: 2,
    })
    h.set_attrs(ENT['policy_ev_current_a'], {
        'ev_policy_mode': 'restore_min',
        'ev_low_pv_cycles': 1,
        'ev_hard_off_release_ready_cycles': 0,
    })

    steps = [
        {
            'at_s': 120,
            'note': 't120 second consecutive low-PV cycle below threshold -> hard-off expected',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.1,
                pv_ent: 1.3,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 2,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.3,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'hard_off',
                    'written': True,
                    'target_current_a': 6,
                },
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['surplus_adjustable_active']: False,
            },
        },
    ]

    run_steps(h, steps)
