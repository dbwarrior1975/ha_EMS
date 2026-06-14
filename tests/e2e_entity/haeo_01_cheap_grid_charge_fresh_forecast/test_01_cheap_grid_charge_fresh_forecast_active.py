import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.haeo_01_cheap_grid_charge_fresh_forecast.scenario_steps import build_harness, run_steps


@pytest.mark.scenario
def test_haeo_cheap_grid_charge_fresh_forecast_active(project_root):
    """
    Fresh HAEO forecast is configured through HORIZON_BY_HAEO and is used for
    CHEAP_GRID_CHARGE battery and EV targets without local fallback.
    """
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 'fresh HAEO forecast drives cheap-grid-charge targets',
            'set': {
                ENT['required_power_consumption_kw']: 1500.0,
                ENT['rpnz_w']: 100.0,
            },
            'expect_policy': {
                'control': 'HORIZON_BY_HAEO',
                'goal': 'CHEAP_GRID_CHARGE',
                'configured_forecast': 'HAEO',
                'effective_forecast': 'HAEO',
                'dominant_limitation': 'OPTIMIZATION_ACTIVE',
                'surplus_policy_active': False,
                'surplus_dispatch_decision': 'CLEAR_ALL',
            },
            'expect_policy_values': {
                ENT['policy_battery_target_w']: 1500,
                ENT['policy_ev_current_a']: 16,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['surplus_dispatch_decision_pys']: 'CLEAR_ALL',
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
                'adjustable_active': False,
                'relay1_active': False,
                'relay2_active': False,
            },
            'expect_writer_trace': {
                'victron.action': 'write',
                'ev.action': 'enable_and_set_current',
                'relay1.action': 'skip',
                'relay2.action': 'skip',
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 1000,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 16,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
    ]

    run_steps(h, steps)
