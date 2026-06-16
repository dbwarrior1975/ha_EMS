import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_previous_device_state
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_05_recovery_and_reactivation(project_root):
    """Phase 5: reactivation path from hard-off post-state to EV burn recovery."""
    pv_ent = ENT['pv_power_kw']
    h = build_harness(project_root)

    # Seed a hard-off post-state so this phase is independent from phases 1-4.
    seed_active_surplus_devices(
        h,
        active_device_ids=(),
        actuator_relay1=False,
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        ENT['pv_power_kw']: 1.9,
        ENT['ev_hard_off_pv_threshold_kw']: 1.6,
        ENT['ev_hard_off_low_pv_cycles']: 2,
    })
    seed_previous_device_state(h, mode='hard_off')

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
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'current_a': 0, 'enabled': False},
            },
            'expect_values': {
                ENT['relay1']: False,
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
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'current_a': 0, 'enabled': False},
            },
            'expect_writer_trace': {
                'relay1': {
                    'reason': 'state_changed',
                    'written': True,
                },
            },
            'expect_values': {
                ENT['relay1']: True,
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
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 5.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'current_a': 0, 'enabled': False},
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
                'surplus_explanation': 'Raw RPC 5.800 kW >= ADJUSTABLE threshold 5.060 kW',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 5.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'current_a': 28, 'enabled': True},
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
