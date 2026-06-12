import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.battery_protect_min_cell_recovery.scenario_steps import build_harness
from tests.e2e_entity.battery_protect_min_cell_recovery.scenario_steps import run_steps


@pytest.mark.scenario
def test_02_recovery_gate_then_restore(project_root):
    """Phase 2: BATTERY_PROTECT persists until both recovery conditions are satisfied."""
    h = build_harness(project_root)

    # Seed a protect-state start so this phase is independent from phase 1.
    h.set_entities({
        ENT['guard_profile']: 'BATTERY_PROTECT',
        ENT['soc']: 0.0,
        ENT['min_cell_voltage_v']: 3.04,
        ENT['actuator_battery_setpoint_w']: 400,
    })

    steps = [
        {
            'at_s': 60,
            'note': 't60 only partial recovery -> stay in battery protect',
            'set': {
                ENT['guard_profile']: 'BATTERY_PROTECT',
                ENT['soc']: 1.0,
                ENT['min_cell_voltage_v']: 3.055,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect persists until SOC recovery margin and minimum cell voltage threshold are both satisfied',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 600,
            },
        },
        {
            'at_s': 90,
            'note': 't90 full recovery -> return to normal limits',
            'set': {
                ENT['guard_profile']: 'BATTERY_PROTECT',
                ENT['soc']: 2.0,
                ENT['min_cell_voltage_v']: 3.055,
            },
            'expect_policy': {
                'guard': 'NORMAL_LIMITS',
                'guard_reason': 'Guard recovered: SOC recovery margin reached and minimum cell voltage threshold restored',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 800,
            },
        },
    ]

    run_steps(h, steps)
