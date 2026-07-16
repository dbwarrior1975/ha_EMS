import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_homebattery_adjustable_load.scenario_steps import run_steps

@pytest.mark.scenario
def test_01_baseline_to_adjustable_activation(project_root):
    """Phase 1: baseline battery-support path and EV_CHARGER activation transition."""
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 baseline: NOOP, EV disabled at 4A min, battery target/setpoint 0W, and default floor semantics stay active',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 10,
            'note': 't10 moderate surplus: still NOOP with EV inactive; battery target/setpoint rises to 600W while floor semantics remain unchanged',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=100.0, required_power_consumption_kw=1.2, at_s=10),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=100.0, required_power_consumption_kw=1.2, at_s=10),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 600},
            },
            'expect_policy': {
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 600,
            },
        },
        {
            'at_s': 15,
            'note': 't15 increased load: NOOP continues, EV stays inactive, and battery target/setpoint climbs to 1400W',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=1.9, at_s=15),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=1.9, at_s=15),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 1600},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 1600,
            },
        },
        {
            'at_s': 20,
            'note': 't20 upper pre-threshold: still NOOP with EV_CHARGER as next target; EV remains inactive and battery target/setpoint reaches 2000W',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=550.0, required_power_consumption_kw=2, at_s=20),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=550.0, required_power_consumption_kw=2, at_s=20),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2000},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 30,
            'note': 't30 steady state: no activation transition; EV remains disabled at 4A and battery stays at 2000W target/setpoint',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=530.0, required_power_consumption_kw=2.1, at_s=30),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=530.0, required_power_consumption_kw=2.1, at_s=30),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2000},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 45,
            'note': 't45 low RPC sample: EV still inactive, NOOP decision, and battery path continues at 2000W without floor override mode',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=340.0, required_power_consumption_kw=0.5, at_s=45),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=340.0, required_power_consumption_kw=0.5, at_s=45),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2000},
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 6,
                E['actuator_ev_enabled']: False,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 55,
            'note': 't55 sustained condition: EV_CHARGER remains next target but not activated; EV stays off and battery target/setpoint remains 2000W',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=50.0, required_power_consumption_kw=0.5, at_s=55),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=50.0, required_power_consumption_kw=0.5, at_s=55),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2000},
            },
            'expect_policy': {
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 6,
                E['actuator_ev_enabled']: False,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 60,
            'note': 't60 altered grid signal: behavior still NOOP with EV inactive and battery held at 2000W, using not_applicable floor reason',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=50.0, required_power_consumption_kw=0.5, at_s=60),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=50.0, required_power_consumption_kw=0.5, at_s=60),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2000},
            },
            'expect_policy': {
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 6,
                E['actuator_ev_enabled']: False,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 70,
            'note': 't70 higher import/export swing: policy waits for EV_CHARGER threshold, no activation occurs, EV stays off, battery remains 2000W',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=250.0, required_power_consumption_kw=1.0, at_s=70),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=250.0, required_power_consumption_kw=1.0, at_s=70),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2000},
            },
            'expect_policy': {
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for EV_CHARGER; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 6,
                E['actuator_ev_enabled']: False,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 73,
            'note': 't73 trigger point: RPC crosses EV_CHARGER threshold and dispatch activates adjustable load',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=7.0, at_s=73),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=7.0, at_s=73),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 2000},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,
                'surplus_next_device_id': 'EV_CHARGER',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Raw RPC 7.000 kW >= EV_CHARGER threshold 5.060 kW',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 6,
                E['actuator_ev_enabled']: False,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 80,
            'note': 't80 post-trigger collapse: adjustable is released on negative RPC and relay path becomes next candidate',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=450.0, required_power_consumption_kw=-100.0, at_s=80),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=450.0, required_power_consumption_kw=-100.0, at_s=80),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 1000},
            },
            'expect_policy': {
                'surplus_next_device_id': 'RELAY1',
                'surplus_freeze_until_ts': 88.0,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 89,
            'note': 't89 post-trigger hold: relay path remains the next candidate while adjustable stays active',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=450.0, required_power_consumption_kw=2.4, at_s=89),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=450.0, required_power_consumption_kw=2.4, at_s=89),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 2000},
            },
            'expect_policy': {
                'surplus_next_device_id': 'RELAY1',
                'surplus_freeze_until_ts': 88.0,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 90,
            'note': 't90 PV has collapsed and EV is still burning hard; hard-off pressure is building while battery support is trimmed to 1.0 kW.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=100.0, required_power_consumption_kw=-5.0, at_s=90, pv_power_kw=3.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=100.0, required_power_consumption_kw=-5.0, at_s=90),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 1000},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,
                'surplus_next_device_id': 'RELAY1',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 1000,
            },
        },
    ]

    run_steps(h, steps)
