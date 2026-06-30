import pytest

from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_previous_device_state
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_03_low_pv_to_hard_off(project_root):
    """Phase 3: second low-PV cycle triggers EV hard-off."""
    h = build_harness(project_root)
    E = h.ent
    pv_ent = E['pv_power_kw']

    # Seed end-of-phase-2 state so phase 3 is independent from warmup chains.
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1',),
        actuator_relay1=True,
        actuator_ev_enabled=True,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        E['pv_power_kw']: 1.3,
        E['ev_hard_off_pv_threshold_kw']: 1.6,
        E['ev_hard_off_low_pv_cycles']: 2,
    })
    seed_previous_device_state(h, mode='restore_min', low_pv_cycles=1)

    steps = [
        {
            'at_s': 120,
            'note': 't120 second consecutive low-PV cycle below threshold -> hard-off expected',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 11.0,
                pv_ent: 1.3,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_low_pv_cycles': 2,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.3,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'hard_off',
                    'written': True,
                    'target_current_a': 8,
                },
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
    ]

    run_steps(h, steps)
