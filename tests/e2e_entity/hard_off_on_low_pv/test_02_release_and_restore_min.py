import pytest

from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps
from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices
from tests.e2e_entity.scenario_runner import seed_previous_device_state


@pytest.mark.scenario
def test_02_release_and_restore_min(project_root):
    """Release newest EV by n-1 excess and restore it to minimum next tick."""
    h = build_harness(project_root)
    E = h.ent

    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1', 'EV_CHARGER'),
        actuator_relay1=True,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
    )
    h.set_entities({
        E['pv_power_w']: 3000.0,
        E['ev_hard_off_pv_threshold_kw']: 1.6,
        E['ev_hard_off_low_pv_cycles']: 2,
    })
    seed_previous_device_state(h, mode='burn')

    steps = [
        {
            'at_s': 90,
            'note': 't90 low PV begins and 6.2 kW excess releases newest EV step',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=0.0,
                required_power_consumption_kw=-6.2,
                at_s=90,
                pv_power_kw=1.4,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=0.0,
                required_power_consumption_kw=-6.2,
                at_s=90,
            ),
            'expect_policy': {
                'surplus_explanation': (
                    'N-1 excess 6200 W >= EV_CHARGER release threshold 4807 W '
                    '(5060 W - 253 W margin)'
                ),
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'EV_CHARGER',
                'surplus_release_mode': 'n_minus_one_incremental',
                'surplus_release_power_w': 5060,
                'surplus_release_margin_w': 253,
                'surplus_release_threshold_w': 4807,
                'surplus_freeze_until_ts': 105.0,
                'surplus_next_device_id': 'RELAY2',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 0,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'pv_power_kw': 1.4,
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'already_matching',
                    'written': False,
                    'target_current_a': 28,
                },
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 95,
            'note': 't95 first low-PV cycle after release restores EV minimum during settle freeze',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=11.0,
                required_power_consumption_kw=0.0,
                at_s=95,
                pv_power_kw=1.3,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=11.0,
                required_power_consumption_kw=0.0,
                at_s=95,
            ),
            'expect_policy': {
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_freeze_until_ts': 105.0,
                'surplus_next_device_id': 'EV_CHARGER',
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 1,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'pv_power_kw': 1.3,
            },
            'expect_device_policies': {
                'EV_CHARGER': {'mode': 'restore_min'},
            },
            'expect_writer_trace': {
                'EV_CHARGER': {
                    'reason': 'restore_min',
                    'written': True,
                    'target_current_a': 8,
                },
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 8,
            },
        },
    ]

    run_steps(h, steps)
