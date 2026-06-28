import pytest

from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_previous_device_state
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_05_recovery_and_reactivation(project_root):
    """Phase 5: reactivation path from hard-off post-state to EV burn recovery."""
    h = build_harness(project_root)
    E = h.ent
    pv_ent = E['pv_power_kw']

    # Seed a hard-off post-state so this phase is independent from phases 1-4.
    seed_active_surplus_devices(
        h,
        active_device_ids=(),
        actuator_relay1=False,
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        E['pv_power_kw']: 1.9,
        E['ev_hard_off_pv_threshold_kw']: 1.6,
        E['ev_hard_off_low_pv_cycles']: 2,
    })
    seed_previous_device_state(h, mode='hard_off')

    steps = [
        {
            'at_s': 224,
            'note': 't224 recovered PV and moderate RPC reactivate RELAY1 while EV remains hard-off',
            'set': {
                E['required_power_consumption_kw']: 3.0,
                E['rpnz_w']: 0.1,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 239.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
            },
            'expect_values': {
                E['relay1']: False,
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
        {
            'at_s': 238,
            'note': 't238 RELAY1 activation is now visible at actuator level while EV remains hard-off',
            'set': {
                E['required_power_consumption_kw']: 3.0,
                E['rpnz_w']: 0.1,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 239.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'ADJUSTABLE',
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
                },
            },
            'expect_values': {
                E['relay1']: True,
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
        {
            'at_s': 240,
            'note': 't240 recovered PV and RPC remain below the ADJUSTABLE activation threshold',
            'set': {
                E['required_power_consumption_kw']: 4.0,
                E['rpnz_w']: 0.15,
                pv_ent: 5.9,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 5.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
        {
            'at_s': 270,
            'note': 't270 recovered PV and RPC cross the ADJUSTABLE threshold so normal EV activation resumes',
            'set': {
                E['required_power_consumption_kw']: 5.8,
                E['rpnz_w']: 0.19,
                pv_ent: 5.9,
            },
            'expect_policy': {
                'surplus_explanation': 'Raw RPC 5.800 kW >= EV_CHARGER threshold 5.060 kW',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 5.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'state_changed',
                    'written': True,
                    'target_current_a': 28,
                },
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
            },
        },
    ]

    run_steps(h, steps)
