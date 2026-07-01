import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import run_steps

@pytest.mark.scenario
def test_01_ev_primary_ramp_and_adjustable_activation(project_root):
    """Phase 1: EV-primary ramp, ADJUSTABLE activation, and RELAY1 activation edge."""
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 PV 0.5 kW: no surplus yet; battery target stays 0 W and EV remains at minimum charge current.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=0, pv_power_kw=0.5),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': -700},
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: -700,
            },
        },
        {
            'at_s': 10,
            'note': 't10 PV 2.2 kW: EV ramps up while battery target remains near 0 W (RPC below threshold).',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=100.0, required_power_consumption_kw=2.1, at_s=10, pv_power_kw=1.7),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=100.0, required_power_consumption_kw=2.1, at_s=10),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 10,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 15,
            'note': 't15 PV 3.0 kW: EV-first path continues and battery target stays at 0 W.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=2, at_s=15, pv_power_kw=1.7),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=2, at_s=15),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': 3300,
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 14,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 20,
            'note': 't20 PV 3.0 kW: EV-first path continues and battery target stays at 0 W.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=550.0, required_power_consumption_kw=2, at_s=20, pv_power_kw=3.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=550.0, required_power_consumption_kw=2, at_s=20),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 18,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 30,
            'note': 't30 PV 2.0 kW: EV remains the primary sink and battery target stays at 0 W.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=530.0, required_power_consumption_kw=2.1, at_s=30, pv_power_kw=2.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=530.0, required_power_consumption_kw=2.1, at_s=30),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 22,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 45,
            'note': 't45 PV 4.0 kW: EV absorbs available surplus; battery target remains 0 W with floor override active.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=340.0, required_power_consumption_kw=0.1, at_s=45, pv_power_kw=4.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=340.0, required_power_consumption_kw=0.1, at_s=45),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 22,
                E['actuator_ev_enabled']: True,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 55,
            'note': 't55 PV 6.4 kW: EV keeps consuming surplus; battery target remains at 0 W.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=50.0, required_power_consumption_kw=0.9, at_s=55, pv_power_kw=6.4),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=50.0, required_power_consumption_kw=0.9, at_s=55),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 24,
                E['actuator_ev_enabled']: True,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 60,
            'note': 't60 PV 6.4 kW: EV current remains high and affects grid power as expected.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=50.0, required_power_consumption_kw=1.5, at_s=60, pv_power_kw=6.4),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=50.0, required_power_consumption_kw=1.5, at_s=60),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 27,
                E['actuator_ev_enabled']: True,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 70,
            'note': 't70 PV 8.0 kW: EV reaches high current; dispatch still waits for ADJUSTABLE activation.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=250.0, required_power_consumption_kw=1.0, at_s=70, pv_power_kw=8.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=250.0, required_power_consumption_kw=1.0, at_s=70),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'surplus_explanation': 'Waiting for HOME_BATTERY; raw RPC below threshold',
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 73,
            'note': 't73 PV 8.0 kW: RPC crosses ADJUSTABLE threshold and adjustable path activates.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=2.6, at_s=73, pv_power_kw=8.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=2.6, at_s=73),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'surplus_explanation': 'Raw RPC 2.600 kW >= HOME_BATTERY threshold 2.500 kW',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 80,
            'note': 't80 PV 8.0 kW: after activation, battery setpoint ramps with configured ramp limits.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=450.0, required_power_consumption_kw=-100.0, at_s=80, pv_power_kw=8.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=450.0, required_power_consumption_kw=-100.0, at_s=80),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 2500},
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'surplus_freeze_until_ts': 88.0,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 23,
                E['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 89,
            'note': 't89 PV 10.0 kW: RELAY1 activation occurs while EV remains prioritized.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=450.0, required_power_consumption_kw=2.4, at_s=89, pv_power_kw=10.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=450.0, required_power_consumption_kw=2.4, at_s=89),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 2500},
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',
                'surplus_freeze_until_ts': 104.0,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'surplus_explanation': 'Raw RPC 2.400 kW >= RELAY1 threshold 2.300 kW',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 27,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
        {
            'at_s': 90,
            'note': 't90 PV drops to 3kW: EV remains the primary sink and battery target stays at adjustable clamp level',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=100.0, required_power_consumption_kw=2.3, at_s=90, pv_power_kw=3.0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=100.0, required_power_consumption_kw=2.3, at_s=90),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 2500},
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY2',
                'surplus_freeze_until_ts': 104.0,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
            },
            'expect_values': {
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 2500,
            },
        },
    ]

    run_steps(h, steps)
