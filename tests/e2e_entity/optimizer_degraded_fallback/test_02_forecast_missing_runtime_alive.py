import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.optimizer_degraded_fallback.scenario_steps import build_harness, run_steps


@pytest.mark.scenario
def test_forecast_missing_keeps_runtime_alive(project_root):
    h = build_harness(project_root, goal_profile='CHEAP_GRID_CHARGE')
    h.set_attrs(ENT['haeo_battery_power_active'], {'forecast': None})
    h.set_attrs(ENT['haeo_ev_battery_power_active'], {'forecast': None})
    h.set_stale(ENT['haeo_battery_active_power_fresh_source'], 1000.0)
    h.set_stale(ENT['haeo_ev_active_power_fresh_source'], 1000.0)

    steps = [
        {
            'at_s': 0,
            'note': 'missing forecast payload',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
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
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 100,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_values': {
                ENT['policy_battery_target_w']: 100,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 100,
            },
            'expect_same_as_entity': {
                ENT['policy_ev_current_a']: ENT['ev_max_current_a'],
            },
        },
    ]

    run_steps(h, steps)
