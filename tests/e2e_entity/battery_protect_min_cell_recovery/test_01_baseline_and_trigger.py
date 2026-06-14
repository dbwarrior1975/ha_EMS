import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.battery_protect_min_cell_recovery.scenario_steps import build_harness
from tests.e2e_entity.battery_protect_min_cell_recovery.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_baseline_and_trigger(project_root):
    """Phase 1: normal baseline and SOC+min-cell trigger into BATTERY_PROTECT."""
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 't0 normal baseline',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: -1.0,
                ENT['grid_power_w']: 200.0,                
                ENT['guard_profile']: 'NORMAL_LIMITS',
                ENT['soc']: 10.0,
                ENT['min_cell_voltage_v']: 3.2,
            },
            'expect_policy_values': {
                ENT['policy_decision_trace']: 'AUTOMATIC/NET_ZERO/NORMAL_LIMITS/NONE',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: -100,
            },
        },
        {
            'at_s': 30,
            'note': 't30 SOC and min-cell both below thresholds -> battery protect',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: -1.0,
                ENT['grid_power_w']: 200.0,    
                ENT['soc']: 0.0,
                ENT['min_cell_voltage_v']: 3.04,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: SOC and minimum cell voltage below thresholds',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 100,
            },
        },

        {
            'at_s': 35,
            'note': 't30 SOC and min-cell both below thresholds -> battery protect',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: -1.0,
                ENT['grid_power_w']: 200.0,                    
                ENT['soc']: 0.0,
                ENT['min_cell_voltage_v']: 3.04,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: SOC and minimum cell voltage below thresholds',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 100,
            },
        },

        {
            'at_s': 35,
            'note': 't30 SOC and min-cell both below thresholds -> battery protect',
            'set': {
                ENT['soc']: 0.0,
                ENT['min_cell_voltage_v']: 3.04,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: SOC and minimum cell voltage below thresholds',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 100,
            },
        },       
    ]

    run_steps(h, steps)
