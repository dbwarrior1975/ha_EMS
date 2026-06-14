from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['control_profile']: 'HORIZON_BY_HAEO',
        ENT['goal_profile']: 'CHEAP_GRID_CHARGE',
        ENT['forecast_profile']: 'NONE',
        ENT['haeo_stale_timeout_s']: 300,
        ENT['haeo_battery_active_power_fresh_source']: 1.0,
        ENT['haeo_ev_active_power_fresh_source']: 1.0,
        ENT['ev_min_current_a']: 4,
        ENT['ev_current_step_a']: 4,
        ENT['actuator_battery_setpoint_w']: 0.0,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
    })
    h.set_attrs(ENT['haeo_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 1.5},
        ],
    })
    h.set_attrs(ENT['haeo_ev_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 3.7},
        ],
    })
    return h


def run_steps(h, steps):
    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        policy_trace = h.getattrs(ENT['policy_decision_trace'])
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)
        writer_trace = h.getattrs('sensor.ems_actuator_writer_trace')

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
                f"step={idx} note={step['note']} dispatch_state.{attr} actual={actual} expected={expected}"
            )

        for attr_path, expected in step.get('expect_writer_trace', {}).items():
            section, attr = attr_path.split('.', 1)
            actual = writer_trace.get(section, {}).get(attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} writer.{attr_path} actual={actual} expected={expected}"
            )

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} actual={actual} expected={expected}"
            )
