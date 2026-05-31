import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_optimizer_stale_reactive_fallback(project_root):
    """Stale HAEO freshness forces local forecast fallback inside HORIZON_BY_HAEO."""
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['control_profile']: 'HORIZON_BY_HAEO',
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['haeo_battery_active_power_fresh_source']: 0.0,
        ENT['haeo_ev_active_power_fresh_source']: 0.0,
    })
    h.set_stale(ENT['haeo_battery_active_power_fresh_source'], 1000.0)
    h.set_stale(ENT['haeo_ev_active_power_fresh_source'], 1000.0)

    h.step(set_values={ENT['required_power_consumption_kw']: 0.0, ENT['rpnz_w']: 500}, note='stale forecast')
    attrs = h.getattrs(ENT['policy_decision_trace'])
    assert attrs['configured_forecast'] == 'HAEO'
    assert attrs['effective_forecast'] == 'NONE'
    assert attrs['dominant_limitation'] == 'FORECAST_FALLBACK_LOCAL'


@pytest.mark.scenario
def test_forecast_missing_keeps_runtime_alive(project_root):
    """Missing HAEO forecast payload falls back to local CHEAP_GRID_CHARGE policy."""
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['control_profile']: 'HORIZON_BY_HAEO',
        ENT['goal_profile']: 'CHEAP_GRID_CHARGE',
        ENT['forecast_profile']: 'NONE',
        ENT['haeo_battery_active_power_fresh_source']: 0.0,
        ENT['haeo_ev_active_power_fresh_source']: 0.0,
    })
    h.set_attrs(ENT['haeo_battery_power_active'], {'forecast': None})
    h.set_attrs(ENT['haeo_ev_battery_power_active'], {'forecast': None})
    h.set_stale(ENT['haeo_battery_active_power_fresh_source'], 1000.0)
    h.set_stale(ENT['haeo_ev_active_power_fresh_source'], 1000.0)

    h.step(set_values={ENT['required_power_consumption_kw']: 0.0, ENT['rpnz_w']: 0.0}, note='missing forecast payload')
    assert h.get(ENT['policy_battery_target_w']) == 100
    assert h.get(ENT['policy_ev_current_a']) == h.get(ENT['ev_max_current_a'])
