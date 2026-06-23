import pytest

from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_previous_device_state
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_02_release_and_restore_min(project_root):
    """Phase 2: release ADJUSTABLE and restore EV to minimum before hard-off."""
    h = build_harness(project_root)
    E = h.ent
    pv_ent = E['pv_power_kw']

    # Seed end-of-phase-1 state so phase 2 is independent from warmup chains.
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1', 'EV_CHARGER'),
        actuator_relay1=True,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
    )
    h.set_entities({
        E['pv_power_kw']: 3.0,
        E['ev_hard_off_pv_threshold_kw']: 1.6,
        E['ev_hard_off_low_pv_cycles']: 2,
    })
    seed_previous_device_state(h, mode='burn')

    steps = [
        {
            'at_s': 90,
            'note': 't90 PV drops below threshold and RELEASE_ADJUSTABLE is decided; writer restores EV to minimum',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
                pv_ent: 1.4,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
                'surplus_next_target': 'RELAY2',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 1.4,
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'already_matching',
                    'written': False,
                    'target_current_a': 28,
                },
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 95,
            'note': 't95 first low-PV cycle after release -> restore min, no hard-off yet',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.1,
                pv_ent: 1.3,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_low_pv_cycles': 1,
                'ev_hard_off_active': False,
                'pv_power_kw': 1.3,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'restore_min_current',
                    'written': True,
                    'target_current_a': 6,
                },
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 6,
            },
        },
    ]

    run_steps(h, steps)
