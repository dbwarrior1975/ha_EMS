import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps


@pytest.mark.scenario
def test_04_hard_off_persistence_and_relay_release(project_root):
    """Phase 4: hard-off persists and RELAY1 release path is applied."""
    pv_ent = ENT['pv_power_kw']
    h = build_harness(project_root)

    # Seed end-of-phase-3 state so phase 4 is independent from warmup chains.
    h.set_entities({
        ENT['actuator_ev_enabled']: False,
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
        'ev_policy_mode': 'hard_off',
        'ev_low_pv_cycles': 2,
        'ev_hard_off_release_ready_cycles': 0,
    })

    steps = [
        {
            'at_s': 180,
            'note': 't180 low PV persists -> EV remains off',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.1,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'RELEASE_RELAY1',
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 3,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.1,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_RELAY1',
            },
            'expect_writer_trace': {
                'relay1': {
                    'reason': 'already_matching',
                    'written': False,
                }
            },
            'expect_values': {
                ENT['relay1']: True,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
            },
        },
        {
            'at_s': 210,
            'note': 't210 PV recovers above threshold, but EV and relays remain off without a new surplus trigger',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
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
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'relay1': {
                    'reason': 'state_changed',
                    'written': True,
                }
            },
            'expect_values': {
                ENT['relay1']: False,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
            },
        },
    ]

    run_steps(h, steps)
