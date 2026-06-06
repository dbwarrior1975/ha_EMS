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

    steps = [
        {
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
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'])

        policy_trace = h.getattrs(ENT['policy_decision_trace'])

        for attr, expected in step.get('expect_policy', {}).items():
            actual = policy_trace.get(attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} policy.{attr} actual={actual} expected={expected}"
            )


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

    steps = [
        {
            'note': 'missing forecast payload',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['policy_battery_target_w']: 100,
            },
            'expect_same_as_entity': {
                ENT['policy_ev_current_a']: ENT['ev_max_current_a'],
            },
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'])

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} actual={actual} expected={expected}"
            )

        for lhs_entity, rhs_entity in step.get('expect_same_as_entity', {}).items():
            lhs_actual = h.get(lhs_entity)
            rhs_actual = h.get(rhs_entity)
            assert lhs_actual == rhs_actual, (
                f"step={idx} note={step['note']} entity={lhs_entity} actual={lhs_actual} "
                f"expected_same_as {rhs_entity}={rhs_actual}"
            )
