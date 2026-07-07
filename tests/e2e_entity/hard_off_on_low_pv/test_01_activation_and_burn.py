import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps

@pytest.mark.scenario
def test_01_activation_and_burn(project_root):
    """Phase 1: activate RELAY1, activate EV_CHARGER, and confirm stable EV burn."""
    h = build_harness(project_root)
    E = h.ent
    pv_ent = E['pv_power_w']

    steps = [
        {
            'at_s': 0,
            'note': 't0 enough surplus -> activate relay1 first',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=500,
                required_power_consumption_kw=3.5,
                at_s=0,
                pv_power_kw=3.5,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=500,
                required_power_consumption_kw=3.5,
                at_s=0,
            ),
            'expect_policy': {
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_device_id': 'RELAY1',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 0,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'pv_power_kw': 3.5,
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 30,
            'note': 't30 enough surplus -> activate EV next',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=2900,
                required_power_consumption_kw=7.0,
                at_s=30,
                pv_power_kw=3.2,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=2900,
                required_power_consumption_kw=7.0,
                at_s=30,
            ),
            'expect_policy': {
                'surplus_freeze_until_ts': 45.0,
                'surplus_explanation': 'Raw RPC 7.000 kW >= EV_CHARGER threshold 6.440 kW',
                'surplus_next_device_id': 'EV_CHARGER',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 0,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'pv_power_kw': 3.2,
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 46,
            'note': 't46 freeze has expired and EV burn is now visible at max current',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=500,
                required_power_consumption_kw=4.5,
                at_s=46,
                pv_power_kw=3.0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=500,
                required_power_consumption_kw=4.5,
                at_s=46,
            ),
            'expect_policy': {
                'surplus_freeze_until_ts': 45.0,
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_device_id': 'RELAY2',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 0,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'pv_power_kw': 3.0,
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
        {
            'at_s': 60,
            'note': 't60 EV remains stably at max current after the freeze-expiry transition',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=500,
                required_power_consumption_kw=4.9,
                at_s=60,
                pv_power_kw=3.0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=500,
                required_power_consumption_kw=4.9,
                at_s=60,
            ),
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_device_id': 'RELAY2',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 0,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'pv_power_kw': 3.0,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
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
    ]

    run_steps(h, steps)
