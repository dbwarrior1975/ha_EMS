import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.battery_protect_min_cell_recovery.scenario_steps import build_harness
from tests.e2e_entity.battery_protect_min_cell_recovery.scenario_steps import run_steps


@pytest.mark.scenario
def test_03_min_cell_retrigger_and_recovery(project_root):
    """Phase 3: min-cell-only trigger to BATTERY_PROTECT and explicit recovery to NORMAL_LIMITS."""
    h = build_harness(project_root)

    # Seed a normal-state start so this phase is independent from previous phases.
    h.set_entities({
        ENT['guard_profile']: 'NORMAL_LIMITS',
        ENT['soc']: 2.0,
        ENT['min_cell_voltage_v']: 3.06,
        ENT['actuator_battery_setpoint_w']: 800,
    })

    steps = [
        {
            'at_s': 120,
            'note': 't120 minimum cell voltage below threshold -> battery protect',
            'set': {
                ENT['soc']: 1.0,
                ENT['min_cell_voltage_v']: 3.045,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: minimum cell voltage below threshold',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 150,
            'note': 't150 recovery values restored while guard input is BATTERY_PROTECT -> recover to normal',
            'set': {
                ENT['guard_profile']: 'BATTERY_PROTECT',
                ENT['soc']: 2.0,
                ENT['min_cell_voltage_v']: 3.06,
            },
            'expect_policy': {
                'guard': 'NORMAL_LIMITS',
                'guard_reason': 'Guard recovered: SOC recovery margin reached and minimum cell voltage threshold restored',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 1200,
            },
        },
    ]

    run_steps(h, steps)
