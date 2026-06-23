import pytest

from tests.e2e_entity.optimizer_degraded_fallback.scenario_steps import build_harness, run_steps

@pytest.mark.scenario
def test_forecast_missing_keeps_runtime_alive(project_root):
    h = build_harness(project_root, goal_profile='CHEAP_GRID_CHARGE')
    E = h.ent
    h.set_attrs(E['haeo_battery_power_active'], {'forecast': None})
    h.set_attrs(E['haeo_ev_battery_power_active'], {'forecast': None})
    h.set_stale(E['haeo_battery_active_power_fresh_source'], 1000.0)
    h.set_stale(E['haeo_ev_active_power_fresh_source'], 1000.0)

    steps = [
        {
            'at_s': 0,
            'note': 'missing forecast payload',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'configured_forecast': 'HAEO',
                'effective_forecast': 'NONE',
                'dominant_limitation': 'FORECAST_FALLBACK_LOCAL',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
                'HOME_BATTERY': {'target_w': 100},
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 100,
            },
        },
    ]

    run_steps(h, steps)
