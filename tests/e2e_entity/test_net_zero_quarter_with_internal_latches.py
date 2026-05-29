import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_net_zero_quarter_with_internal_latches(project_root):
    """
    Data-driven 30s-step quarter scenario for the *current* production chain:

        ems_net_zero_shadow.py
            -> ems_surplus_latches.py
            -> ems_actuator_writers.py

    Goal story:
    - start AUTOMATIC + NET_ZERO with no surplus loads active
    - internal latch loop converts ACTIVATE_* and RELEASE_* dispatches to active booleans
    - next steps consume those booleans so allocator state advances without external automations
    - EV is restored to min current when its surplus burn is released
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    # EV starts already enabled so restore-to-min has a realistic path later
    h.set_entities({
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 4,
    })

    steps = [
        {
            'note': 't0 activate relay1 and create freeze/latch',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['surplus_r1_active']: True,
            },
            'expect_trace': {
                ('sensor.ems_surplus_latch_trace', 'decision'): 'ACTIVATE_RELAY1',
                ('sensor.ems_surplus_latch_trace', 'relay1_active'): True,
            },
            'expect_freeze_present': True,
        },
        {
            'note': 't30 relay1 active -> activate ev',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_EV',
                ENT['surplus_ev_active']: True,
                ENT['policy_relay1_command']: 1,
                ENT['actuator_relay1']: True,
            },
            'expect_trace': {
                ('sensor.ems_surplus_latch_trace', 'decision'): 'ACTIVATE_EV',
                ('sensor.ems_surplus_latch_trace', 'ev_active'): True,
            },
        },
        {
            'note': 't60 relay1 + ev active -> activate relay2',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY2',
                ENT['surplus_r2_active']: True,
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_ev_current_a']: 28,
            },
            'expect_trace': {
                ('sensor.ems_surplus_latch_trace', 'decision'): 'ACTIVATE_RELAY2',
                ('sensor.ems_surplus_latch_trace', 'relay2_active'): True,
            },
        },
        {
            'note': 't90 collapse surplus -> release relay2 first',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY2',
                ENT['surplus_r2_active']: False,
            },
            'expect_trace': {
                ('sensor.ems_surplus_latch_trace', 'decision'): 'RELEASE_RELAY2',
                ('sensor.ems_surplus_latch_trace', 'relay2_active'): False,
            },
        },
        {
            'note': 't120 next release is ev; latch becomes false',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_EV',
                ENT['surplus_ev_active']: False,
            },
            'expect_trace': {
                ('sensor.ems_surplus_latch_trace', 'decision'): 'RELEASE_EV',
                ('sensor.ems_surplus_latch_trace', 'ev_active'): False,
            },
        },
        {
            'note': 't150 ev no longer active -> policy current 0, writer restores min current, relay1 gets released',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY1',
                ENT['surplus_r1_active']: False,
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_current_a']: 4,
            },
            'expect_trace': {
                ('sensor.ems_surplus_latch_trace', 'decision'): 'RELEASE_RELAY1',
                ('sensor.ems_surplus_latch_trace', 'relay1_active'): False,
                ('sensor.ems_actuator_writer_trace', 'ev', 'reason'): 'restore_min_current',
                ('sensor.ems_actuator_writer_trace', 'ev', 'new_current_a'): 4,
            },
        },
        {
            'note': 't180 all latches false and outputs quiet',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_ev_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step.get('note', f'step-{idx}'))

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step.get('note')} entity={entity_id} actual={actual} expected={expected}"
            )

        if step.get('expect_freeze_present'):
            freeze_raw = h.get(ENT['surplus_freeze_until'])
            assert freeze_raw not in (None, '', 'unknown', 'unavailable'), (
                f"step={idx} note={step.get('note')} expected freeze_until to be written"
            )

        for key_tuple, expected in step.get('expect_trace', {}).items():
            if len(key_tuple) == 2:
                entity_id, field = key_tuple
                trace_value = h.get(entity_id)
                assert trace_value not in (None, ''), f'step={idx} note={step.get("note")} missing trace value for {entity_id}'
                attrs = h.getattrs(entity_id)
                actual = attrs[field]
            else:
                entity_id, branch, field = key_tuple
                trace_value = h.get(entity_id)
                assert trace_value == 'ACTIVE' or entity_id.endswith('latch_trace'), (
                    f'step={idx} note={step.get("note")} unexpected trace state for {entity_id}: {trace_value}'
                )
                attrs = h.getattrs(entity_id)
                actual = attrs[branch][field]

            assert actual == expected, (
                f"step={idx} note={step.get('note')} trace={key_tuple} actual={actual} expected={expected}"
            )

    assert len(h.history) == len(steps)
