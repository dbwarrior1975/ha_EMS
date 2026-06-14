from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'
WRITER_TRACE = 'sensor.ems_actuator_writer_trace'


def build_harness(project_root):
    h = QuarterScenarioHarness(
        project_root=project_root,
        start_ts=0.0,
        step_s=30,
        cfg_overrides={'surplus_freeze_s': 15},
    )

    h.set_entities({
        ENT['ramp_max_w']: 1000,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['surplus_freeze_s']: 15,
        ENT['relay2_priority']: 3,
        ENT['relay1_priority']: 2,
        ENT['ev_priority']: 1,
        ENT['relay2_force_on']: False,
        ENT['surplus_r1_active']: False,
        ENT['surplus_r2_active']: False,
        ENT['actuator_relay1']: False,
        ENT['actuator_relay2']: False,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
        ENT['grid_power_w']: 0.0,
        ENT['current_battery_sp']: 0.0,
        ENT['haeo_stale_timeout_s']: 300,
    })

    return h


def run_steps(h, steps):
    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

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

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} "
                f"actual={actual} expected={expected}"
            )

        if step.get('expect_freeze_entity_present'):
            freeze_raw = h.get(ENT['surplus_freeze_until'])
            assert freeze_raw not in (None, '', 'unknown', 'unavailable'), (
                f"step={idx} note={step['note']} expected freeze entity to be written"
            )
