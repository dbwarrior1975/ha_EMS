import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.system_degraded_safe_mode.scenario_steps import build_harness, run_steps

@pytest.mark.scenario
def test_soc_stale_enters_safe_mode(project_root):
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 1000,
            'note': 'stale battery inverter heartbeat enters degraded',
            'set': {
                ENT['required_power_consumption_kw']: 4.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'guard': 'DEGRADED',
                'dominant_limitation': 'SYSTEM_DEGRADED',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'skip'},
                'RELAY2': {'enabled': False, 'mode': 'skip'},
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 0.0,
            },
        },
    ]

    run_steps(h, steps)
