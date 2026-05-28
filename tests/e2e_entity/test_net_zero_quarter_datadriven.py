import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_net_zero_one_quarter_datadriven(project_root):
    """
    One-quarter, 30-second-step, data-driven NET_ZERO scenario.

    Goal story:
    - start with AUTOMATIC/NET_ZERO and no active surplus loads
    - activate RELAY1 -> EV -> RELAY2 in priority order (3,2,1)
    - within the same quarter collapse surplus / RPNZ so release order becomes
      RELAY2 -> EV -> RELAY1
    - when EV is released, policy current becomes 0 on the following step and
      writer restores EV current to min current
    """

    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    # EV initial real shadow state: charger already on and able to restore current later
    h.set_entities({
        ENT['shadow_ev_enabled']: True,
        ENT['shadow_ev_current_a']: 4,
    })

    steps = [
        {
            'note': 't0 baseline, enough surplus to start with RELAY1',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
            },
        },
        {
            'note': 't30 RELAY1 is active, enough surplus for EV next',
            'set': {
                # EV threshold with defaults:
                # (28 - 4) * 230 / 1000 = 5.52 kW
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_EV',
                ENT['policy_relay1_command']: 1,
                ENT['shadow_relay1']: True,
            },
        },
        {
            'note': 't60 EV active, enough surplus for RELAY2 next',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY2',
                ENT['policy_ev_current_a']: 28,
                ENT['shadow_ev_current_a']: 28,
            },
        },
        {
            'note': 't90 surplus collapses, release lowest priority first -> RELAY2',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY2',
                # relay2 is still active entering this step; release is applied after the loop
                ENT['policy_relay2_command']: 1,
                ENT['shadow_relay2']: True,
            },
        },
        {
            'note': 't120 still no surplus, next release is EV; EV still active during this step',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_EV',
                # EV is still active entering this step; release applies after the loop
                ENT['policy_ev_current_a']: 28,
                ENT['shadow_ev_current_a']: 28,
            },
        },
        {
            'note': 't150 EV has been released; policy current goes to 0 and writer restores min current; RELAY1 gets released',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY1',
                ENT['policy_ev_current_a']: 0,
                ENT['shadow_ev_current_a']: 4,
            },
            'expect_trace': {
                ('sensor.ems_shadow_writer_trace', 'ev', 'reason'): 'restore_min_current',
                ('sensor.ems_shadow_writer_trace', 'ev', 'new_current_a'): 4,
            },
        },
        {
            'note': 't180 all loads released, relay1 shadow finally off, no further actions',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['shadow_relay1']: False,
            },
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step.get('note', f'step-{idx}'))

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step.get('note')} "
                f"entity={entity_id} actual={actual} expected={expected}"
            )

        for key_tuple, expected in step.get('expect_trace', {}).items():
            entity_id, branch, field = key_tuple
        
            trace_value = h.get(entity_id)
            assert trace_value == 'ACTIVE', (
                f"step={idx} note={step.get('note')} "
                f"trace entity {entity_id} value actual={trace_value} expected=ACTIVE"
            )
        
            trace_attrs = h.getattrs(entity_id)
            assert isinstance(trace_attrs, dict), f"step={idx} missing trace attrs for {entity_id}"
        
            actual = trace_attrs[branch][field]
            assert actual == expected, (
                f"step={idx} trace {branch}.{field} actual={actual} expected={expected}"
            )

    # Final sanity: history length == number of scenario steps
    assert len(h.history) == len(steps)