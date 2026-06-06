import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


WRITER_TRACE = 'sensor.ems_actuator_writer_trace'


@pytest.mark.scenario
def test_soc_stale_enters_safe_mode(project_root):
    """Stale Victron heartbeat pushes guard into DEGRADED and clamps policy outputs."""
    h = QuarterScenarioHarness(project_root=project_root, start_ts=1000.0, step_s=30)
    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['soc']: 50.0,
        ENT['victron_heartbeat']: 0.0,
    })
    h.set_stale(ENT['victron_heartbeat'], 1000.0)

    steps = [
        {
            'note': 'stale victron enters degraded',
            'set': {
                ENT['required_power_consumption_kw']: 4.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'guard': 'DEGRADED',
                'dominant_limitation': 'SYSTEM_DEGRADED',
            },
            'expect_values': {
                ENT['policy_battery_target_w']: 0,
                ENT['policy_ev_current_a']: -1,
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

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} actual={actual} expected={expected}"
            )


@pytest.mark.scenario
def test_writer_freeze_in_system_degraded(project_root):
    """In DEGRADED the latch state clears, but writers skip existing EV/relay actuators."""
    h = QuarterScenarioHarness(project_root=project_root, start_ts=1000.0, step_s=30)
    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['soc']: 50.0,
        ENT['victron_heartbeat']: 0.0,
        ENT['surplus_ev_active']: True,
        ENT['surplus_r1_active']: True,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 16,
        ENT['actuator_relay1']: True,
    })
    h.set_stale(ENT['victron_heartbeat'], 1000.0)

    steps = [
        {
            'note': 'degraded clears latches and skips ev',
            'set': {
                ENT['required_power_consumption_kw']: 4.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_r1_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 16,
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'policy_skip',
                },
                'relay1': {
                    'reason': 'policy_skip',
                },
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
