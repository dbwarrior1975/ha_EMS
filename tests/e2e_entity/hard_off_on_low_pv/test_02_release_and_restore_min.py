import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps


@pytest.mark.scenario
def test_02_release_and_restore_min(project_root):
    """Phase 2: release ADJUSTABLE and restore EV to minimum before hard-off."""
    pv_ent = ENT['pv_power_kw']
    h = build_harness(project_root)

    # Seed end-of-phase-1 state so phase 2 is independent from warmup chains.
    h.set_entities({
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 28,
        ENT['relay1']: True,
        ENT['surplus_r1_active']: True,
        ENT['surplus_r2_active']: False,
        ENT['surplus_adjustable_active']: True,
        ENT['pv_power_kw']: 3.0,
        ENT['ev_hard_off_pv_threshold_kw']: 1.6,
        ENT['ev_hard_off_low_pv_cycles']: 2,
    })
    h.set_attrs(ENT['policy_ev_current_a'], {
        'ev_policy_mode': 'burn',
        'ev_low_pv_cycles': 0,
        'ev_hard_off_release_ready_cycles': 0,
    })

    steps = [
        {
            'at_s': 90,
            'note': 't90 PV drops below threshold and RELEASE_ADJUSTABLE is decided; writer restores EV to minimum',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.4,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'RELEASE_ADJUSTABLE',
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'restore_min',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 1.4,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_ADJUSTABLE',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'restore_min_current',
                    'written': True,
                    'target_current_a': 4,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 4,
                ENT['surplus_adjustable_active']: False,
            },
        },
        {
            'at_s': 95,
            'note': 't95 first low-PV cycle after release -> restore min, no hard-off yet',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.1,
                pv_ent: 1.3,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'restore_min',
                'ev_low_pv_cycles': 1,
                'ev_hard_off_active': False,
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
                    'reason': 'already_released',
                    'written': False,
                    'target_current_a': None,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 4,
                ENT['surplus_adjustable_active']: False,
            },
        },
    ]

    run_steps(h, steps)
