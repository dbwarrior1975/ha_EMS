import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.optimizer_degraded_fallback.scenario_steps import build_harness, run_steps

@pytest.mark.scenario
def test_optimizer_stale_reactive_fallback(project_root):
    h = build_harness(project_root, goal_profile='NET_ZERO')
    E = h.ent
    h.set_stale(E['haeo_battery_active_power_fresh_source'], 1000.0)
    h.set_stale(E['haeo_ev_active_power_fresh_source'], 1000.0)

    steps = [
        {
            'at_s': 0,
            'note': 'stale forecast',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=0.0, at_s=0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=0.0, at_s=0),
            'expect_policy': {
                'configured_forecast': 'HAEO',
                'effective_forecast': 'NONE',
                'dominant_limitation': 'FORECAST_FALLBACK_LOCAL',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 0},
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 8,
                E['actuator_battery_setpoint_w']: 0,
            },
        },
    ]

    run_steps(h, steps)
