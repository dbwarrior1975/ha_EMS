import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.optimizer_degraded_fallback.scenario_steps import build_harness, run_steps


@pytest.mark.scenario
def test_optimizer_stale_reactive_fallback(project_root):
    h = build_harness(project_root, goal_profile='NET_ZERO')
    h.set_stale(ENT['haeo_battery_active_power_fresh_source'], 1000.0)
    h.set_stale(ENT['haeo_ev_active_power_fresh_source'], 1000.0)

    steps = [
        {
            'at_s': 0,
            'note': 'stale forecast',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'configured_forecast': 'HAEO',
                'effective_forecast': 'NONE',
                'dominant_limitation': 'FORECAST_FALLBACK_LOCAL',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'CLEAR_ALL',
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 200,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 200,
            },
        },
    ]

    run_steps(h, steps)
