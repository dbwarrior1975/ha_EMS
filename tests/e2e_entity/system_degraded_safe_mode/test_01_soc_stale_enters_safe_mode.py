import pytest

from ems_adapter.entity_map import ENT
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
                'surplus_dispatch_decision': 'CLEAR_ALL',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'CLEAR_ALL',
                ENT['policy_relay1_command']: -1,
                ENT['policy_relay2_command']: -1,
                ENT['policy_ev_current_a']: -1,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_values': {
                ENT['policy_battery_target_w']: 0,
                ENT['policy_ev_current_a']: -1,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 0.0,
            },
        },
    ]

    run_steps(h, steps)
