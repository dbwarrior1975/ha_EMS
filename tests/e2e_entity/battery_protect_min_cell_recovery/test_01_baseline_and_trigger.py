import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.battery_protect_min_cell_recovery.scenario_steps import build_harness
from tests.e2e_entity.battery_protect_min_cell_recovery.scenario_steps import run_steps

@pytest.mark.scenario
def test_01_baseline_and_trigger(project_root):
    """Phase 1: normal baseline and SOC+min-cell trigger into BATTERY_PROTECT."""
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 normal baseline',
            'set': {
                **runtime_inputs_for_net_zero_intent(E, rpnz_w=-1.0, required_power_consumption_kw=0.0, at_s=0),
                E['guard_profile']: 'NORMAL_LIMITS',
                E['soc']: 10.0,
                E['min_cell_voltage_v']: 3.2,
            },
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-1.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
        {
            'at_s': 30,
            'note': 't30 SOC and min-cell both below thresholds -> battery protect',
            'set': {
                **runtime_inputs_for_net_zero_intent(E, rpnz_w=-1.0, required_power_consumption_kw=0.0, at_s=30),
                E['soc']: 0.0,
                E['min_cell_voltage_v']: 3.04,
            },
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-1.0, required_power_consumption_kw=0.0, at_s=30),
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: SOC and minimum cell voltage below thresholds',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
                E['actuator_battery_setpoint_w']: 100,
            },
        },

        {
            'at_s': 35,
            'note': 't30 SOC and min-cell both below thresholds -> battery protect',
            'set': {
                **runtime_inputs_for_net_zero_intent(E, rpnz_w=-1.0, required_power_consumption_kw=0.0, at_s=35),
                E['soc']: 0.0,
                E['min_cell_voltage_v']: 3.04,
            },
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-1.0, required_power_consumption_kw=0.0, at_s=35),
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: SOC and minimum cell voltage below thresholds',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
                E['actuator_battery_setpoint_w']: 100,
            },
        },

        {
            'at_s': 35,
            'note': 't30 SOC and min-cell both below thresholds -> battery protect',
            'set': {
                E['soc']: 0.0,
                E['min_cell_voltage_v']: 3.04,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: SOC and minimum cell voltage below thresholds',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
                E['actuator_battery_setpoint_w']: 100,
            },
        },       
    ]

    run_steps(h, steps)
