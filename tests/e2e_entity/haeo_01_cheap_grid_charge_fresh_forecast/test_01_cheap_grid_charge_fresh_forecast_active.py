import pytest

from tests.e2e_entity.haeo_01_cheap_grid_charge_fresh_forecast.scenario_steps import build_harness, run_steps

@pytest.mark.scenario
def test_haeo_cheap_grid_charge_fresh_forecast_active(project_root):
    """
    Fresh HAEO forecast is configured through HORIZON_BY_HAEO and is used for
    CHEAP_GRID_CHARGE battery and EV targets without local fallback.
    """
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 'fresh HAEO forecast drives cheap-grid-charge targets',
            'set': {
                E['required_power_consumption_kw']: 1500.0,
                E['rpnz_w']: 100.0,
            },
            'expect_policy': {
                'control': 'HORIZON_BY_HAEO',
                'goal': 'CHEAP_GRID_CHARGE',
                'configured_forecast': 'HAEO',
                'effective_forecast': 'HAEO',
                'dominant_limitation': 'OPTIMIZATION_ACTIVE',
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 1500},
                'EV_CHARGER': {'enabled': True},
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_writer_trace': {
                'victron': {'action': 'write'},
                'EV_CHARGER': {'action': 'enable_and_set_current'},
                'RELAY1': {'action': 'skip'},
                'RELAY2': {'action': 'skip'},
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 1000,
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 16,
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
            },
        },
    ]

    run_steps(h, steps)
