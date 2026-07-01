import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import run_steps
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
            'note': 't135 PV 1.7 kW: low RPNZ triggers RELEASE_RELAY1 and adjustable path remains active.',
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
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_low_pv_cycles': 0,
                'battery_to_ev_loop_risk': 0.0,
            },
            'expect_values': {
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 1500,
            },
        },
        {
            'at_s': 150,
            'note': 't150 PV below threshold: RELEASE_ADJUSTABLE occurs and battery target ramps down per limits.',
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
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'battery_to_ev_loop_risk': False,
            },
            'expect_values': {
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 500,
            },
        },
        {
            'at_s': 160,
            'note': 't160 PV 0.0 kW: EV enters HARD_OFF after low-PV persistence criteria are met.',
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
                'HOME_BATTERY': {'target_w': 200},
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'battery_to_ev_loop_risk': False,
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 200,
            },
        },
        {
            'at_s': 180,
            'note': 't180 PV 1.0 kW: hold state with EV disabled and battery setpoint allow to discharge battery',
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
                'HOME_BATTERY': {'target_w': 200},
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 200,
            },
        },
        {
            'at_s': 210,
            'note': 't210 PV 1.0 kW with negative RPNZ: remain in hold path while waiting below ADJUSTABLE threshold.',
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
                'HOME_BATTERY': {'target_w': 200},
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for HOME_BATTERY; raw RPC below threshold',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 200,
            },
        },
        {
            'at_s': 226,
            'note': 't226 PV 1.0 kW with negative RPNZ: EV remains hard-off and battery command stays held.',
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
                'HOME_BATTERY': {'target_w': 200},
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for HOME_BATTERY; raw RPC below threshold',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 200,
            },
        },
        {
            'at_s': 240,
            'note': 't240 post-release: baseline floor semantics continue with hard-off still active.',
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
                'HOME_BATTERY': {'target_w': 200},
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 200,
            },
        },
    ]

    run_steps(h, steps)
