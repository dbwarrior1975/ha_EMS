from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'


def build_harness(project_root, goal_profile):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['control_profile']: 'HORIZON_BY_HAEO',
        ENT['goal_profile']: goal_profile,
        ENT['forecast_profile']: 'NONE',
        ENT['haeo_battery_active_power_fresh_source']: 0.0,
        ENT['haeo_ev_active_power_fresh_source']: 0.0,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
    })
    return h


def run_steps(h, steps):
    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        policy_trace = h.getattrs(ENT['policy_decision_trace'])
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)

        for attr, expected in step.get('expect_policy', {}).items():
            actual = policy_trace.get(attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} policy.{attr} actual={actual} expected={expected}"
            )

        for entity_id, expected in step.get('expect_policy_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} policy_value entity={entity_id} "
                f"actual={actual} expected={expected}"
            )

        for attr, expected in step.get('expect_dispatch_state', {}).items():
            actual = dispatch_state_trace.get(attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} dispatch state.{attr} actual={actual} expected={expected}"
            )

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
