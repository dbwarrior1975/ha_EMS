import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_previous_device_state
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_05_recovery_and_reactivation(project_root):
    """Phase 5: reactivation path from hard-off post-state to EV burn recovery."""
    h = build_harness(project_root)
    E = h.ent
    pv_ent = E['pv_power_w']

    # Seed a hard-off post-state so this phase is independent from phases 1-4.
    seed_active_surplus_devices(
        h,
        active_device_ids=(),
        actuator_relay1=False,
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        E['pv_power_w']: 1900.0,
        E['ev_hard_off_pv_threshold_kw']: 1.6,
        E['ev_hard_off_low_pv_cycles']: 2,
    })
    seed_previous_device_state(h, mode='hard_off')

    steps = [
        {
            'at_s': 224,
            'note': 't224 recovered PV and moderate RPC reactivate RELAY1 while EV remains hard-off',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=11.0,
                required_power_consumption_kw=3.0,
                at_s=224,
                pv_power_kw=1.9,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=11.0,
                required_power_consumption_kw=3.0,
                at_s=224,
            ),
            'expect_policy': {
                'surplus_freeze_until_ts': 239.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_device_id': 'RELAY1',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 2,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
        {
            'at_s': 238,
            'note': 't238 RELAY1 activation is now visible at actuator level while EV remains hard-off',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=11.0,
                required_power_consumption_kw=3.0,
                at_s=238,
                pv_power_kw=1.9,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=11.0,
                required_power_consumption_kw=3.0,
                at_s=238,
            ),
            'expect_policy': {
                'surplus_freeze_until_ts': 239.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_device_id': 'RELAY2',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 2,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
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
                E['actuator_relay1']: True,
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
        {
            'at_s': 240,
            'note': 't240 recovered PV and RPC remain below the EV_CHARGER activation threshold',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=15.0,
                required_power_consumption_kw=4.0,
                at_s=240,
                pv_power_kw=5.9,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=15.0,
                required_power_consumption_kw=4.0,
                at_s=240,
            ),
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_device_id': 'RELAY2',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 2,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
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
            'note': 't270 first consecutive recovery-ready cycle keeps EV hard-off',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=19.0,
                required_power_consumption_kw=7.0,
                at_s=270,
                pv_power_kw=5.9,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=19.0,
                required_power_consumption_kw=7.0,
                at_s=270,
            ),
            'expect_policy': {
                'surplus_explanation': 'Raw RPC 7.000 kW >= RELAY2 threshold 5.000 kW',
                'surplus_next_device_id': 'RELAY2',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 2,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 1,
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
            'at_s': 300,
            'note': 't300 second consecutive recovery-ready cycle releases hard-off and resumes EV activation',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=19.0,
                required_power_consumption_kw=7.0,
                at_s=300,
                pv_power_kw=5.9,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=19.0,
                required_power_consumption_kw=7.0,
                at_s=300,
            ),
            'expect_policy': {
                'surplus_explanation': 'Raw RPC 7.000 kW >= EV_CHARGER threshold 6.440 kW',
                'surplus_next_device_id': 'EV_CHARGER',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 0,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 2,
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
