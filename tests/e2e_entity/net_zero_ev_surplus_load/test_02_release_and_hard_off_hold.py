import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_ev_surplus_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_ev_surplus_load.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_previous_device_state
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_02_release_and_hard_off_hold(project_root):
    """Phase 2: relay/adjustable releases and EV hard-off hold behavior."""
    h = build_harness(project_root)
    E = h.ent

    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1', 'EV_CHARGER'),
        actuator_ev_enabled=True,
        actuator_ev_current_a=20,
        actuator_battery_setpoint_w=2500,
    )
    h.set_entities({
        E['surplus_freeze_until']: 104.0,
    })
    seed_previous_device_state(h, mode='burn')

    steps = [
        {
            'at_s': 135,
            'note': 't135 intent: RPNZ=-10 W, RPC=-3.4 kW, PV=1.7 kW. Producer authority remains active through sign crossing while release logic runs.',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-10.0,
                required_power_consumption_kw=-3.4,
                at_s=135,
                pv_power_kw=1.7,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-10.0,
                required_power_consumption_kw=-3.4,
                at_s=135,
            ),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 1500},
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'effective_primary_consuming_device_id': 'EV_CHARGER',
                'primary_consuming_requested_w_by_id.EV_CHARGER': 3600.0,
                'device_lifecycle_states.EV_CHARGER.low_pv_cycles': 0,
            },
            'expect_values': {
                E['actuator_ev_current_a']: 15,
                E['actuator_battery_setpoint_w']: 1500,
            },
        },
        {
            'at_s': 150,
            'note': 't150 PV below threshold: RELEASE_HOME_BATTERY occurs and producer authority ramps through the current target toward the signed remainder.',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-100.0,
                required_power_consumption_kw=-4.0,
                at_s=150,
                pv_power_kw=1.5,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-100.0,
                required_power_consumption_kw=-4.0,
                at_s=150,
            ),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 500},
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 10,
                E['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 160,
            'note': 't160 PV 0.0 kW: EV enters HARD_OFF; exact second-based feedback hands consuming authority to HOME_BATTERY at 300 W.',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-80.0,
                required_power_consumption_kw=-0.5,
                at_s=160,
                pv_power_kw=0.0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-80.0,
                required_power_consumption_kw=-0.5,
                at_s=160,
            ),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 300},
            },
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'effective_primary_consuming_device_id': 'HOME_BATTERY',
                'primary_consuming_skipped_by_id.EV_CHARGER': 'lifecycle_hard_off',
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 300,
            },
        },
        {
            'at_s': 180,
            'note': 't180 PV 1.0 kW: EV remains HARD_OFF and HOME_BATTERY becomes the explicit consuming fallback',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-50.0,
                required_power_consumption_kw=0.2,
                at_s=180,
                pv_power_kw=1.0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-50.0,
                required_power_consumption_kw=0.2,
                at_s=180,
            ),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 400},
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'effective_primary_consuming_device_id': 'HOME_BATTERY',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 400,
            },
        },
        {
            'at_s': 210,
            'note': 't210 PV 1.0 kW with negative RPNZ: battery fallback ramps under grid feedback while RELAY1 remains below threshold.',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-40.0,
                required_power_consumption_kw=1.4,
                at_s=210,
                pv_power_kw=1.0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-40.0,
                required_power_consumption_kw=1.4,
                at_s=210,
            ),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 1100},
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'effective_primary_consuming_device_id': 'HOME_BATTERY',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 1100,
            },
        },
        {
            'at_s': 226,
            'note': 't226 PV 1.0 kW with negative RPNZ: EV remains HARD_OFF and battery fallback continues ramping.',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-10.0,
                required_power_consumption_kw=1.9,
                at_s=226,
                pv_power_kw=1.0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-10.0,
                required_power_consumption_kw=1.9,
                at_s=226,
            ),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2100},
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'effective_primary_consuming_device_id': 'HOME_BATTERY',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 2100,
            },
        },
        {
            'at_s': 240,
            'note': 't240 post-release: battery fallback reaches its configured absorb ceiling while EV remains HARD_OFF.',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-5.0,
                required_power_consumption_kw=1.95,
                at_s=240,
                pv_power_kw=0.0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-5.0,
                required_power_consumption_kw=1.95,
                at_s=240,
            ),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2500},
            },
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'effective_primary_consuming_device_id': 'HOME_BATTERY',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 2500,
            },
        },
    ]

    run_steps(h, steps)
