from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'
WRITER_TRACE = 'sensor.ems_actuator_writer_trace'
PV_THRESHOLD_KW = 1.6


def build_harness(project_root):
    pv_ent = ENT['pv_power_kw']
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['control_profile']: 'AUTOMATIC',
        ENT['guard_profile']: 'NORMAL_LIMITS',
        ENT['ev_force_current_a']: 0,
        ENT['ev_min_current_a']: 4,
        ENT['ev_max_current_a']: 28,
        ENT['ev_charger_phases']: 1,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 4,
        pv_ent: 3.5,
        ENT['surplus_freeze_s']: 15,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['adjustable_surplus_load_priority']: 2,
        ENT['relay1_priority']: 3,
        ENT['relay2_priority']: 1,
    })
    return h


def run_steps(h, steps, validate=True):
    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        if not validate:
            continue

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} threshold_kw={PV_THRESHOLD_KW} "
                f"entity={entity_id} actual={actual} expected={expected}"
            )

        policy_trace = h.getattrs(ENT['policy_decision_trace'])
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)

        assert policy_trace['goal'] == 'NET_ZERO'
        assert policy_trace['relay1_command'] == h.get(ENT['policy_relay1_command'])
        assert policy_trace['relay2_command'] == h.get(ENT['policy_relay2_command'])

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

        if step.get('expect_writer_trace'):
            assert h.get(WRITER_TRACE) == 'ACTIVE', (
                f"step={idx} note={step['note']} expected writer trace entity to be ACTIVE"
            )
            writer_trace = h.getattrs(WRITER_TRACE)
            for branch, expected_fields in step['expect_writer_trace'].items():
                actual_branch = writer_trace[branch]
                for field, expected in expected_fields.items():
                    actual = actual_branch.get(field)
                    assert actual == expected, (
                        f"step={idx} note={step['note']} writer.{branch}.{field} "
                        f"actual={actual} expected={expected}"
                    )
