import pytest

from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_previous_device_state
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_04_hard_off_persistence_and_relay_release(project_root):
    """Phase 4: hard-off persists and RELAY1 release path is applied."""
    h = build_harness(project_root)
    E = h.ent
    pv_ent = E['pv_power_kw']

    # Seed end-of-phase-3 state so phase 4 is independent from warmup chains.
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1',),
        actuator_relay1=True,
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        E['pv_power_kw']: 1.3,
        E['ev_hard_off_pv_threshold_kw']: 1.6,
        E['ev_hard_off_low_pv_cycles']: 2,
    })
    seed_previous_device_state(h, mode='hard_off', low_pv_cycles=2)

    steps = [
        {
            'at_s': 180,
            'note': 't180 low PV persists -> EV remains off',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
                pv_ent: 1.1,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_low_pv_cycles': 3,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.1,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
            },
            'expect_writer_trace': {
                'RELAY1': {
                    'reason': 'already_matching',
                    'written': False,
                }
            },
            'expect_values': {
                E['relay1']: True,
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
        {
            'at_s': 210,
            'note': 't210 PV recovers above threshold, but EV and relays remain off without a new surplus trigger',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
                'surplus_next_target': 'RELAY1',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
            },
            'expect_writer_trace': {
                'RELAY1': {
                    'reason': 'state_changed',
                    'written': True,
                }
            },
            'expect_values': {
                E['relay1']: False,
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
    ]

    run_steps(h, steps)
