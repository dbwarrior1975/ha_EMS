import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_net_zero_priority_order_one_quarter(project_root):
    """
    Quarter story:
    - RELAY1 (priority 3) activates first
    - EV (priority 2) activates second when its threshold is reached
    - RELAY2 (priority 1) activates third
    - when surplus collapses, release order is RELAY2 -> EV -> RELAY1
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    # Keep EV already enabled so later EV activation is visible on current level
    h.set_entities({
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 4,
    })

    steps = [
        {
            'note': 't0 activate RELAY1',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect': {ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1'},
        },
        {
            'note': 't30 activate EV',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_EV',
                ENT['policy_relay1_command']: 1,
                ENT['actuator_relay1']: True,
            },
        },
        {
            'note': 't60 activate RELAY2',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY2',
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'note': 't90 release RELAY2 first',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect': {ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY2'},
        },
        {
            'note': 't120 release EV second',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect': {ENT['surplus_dispatch_decision_pys']: 'RELEASE_EV'},
        },
        {
            'note': 't150 release RELAY1 last',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY1',
                ENT['policy_ev_current_a']: 0,
            },
        },
        {
            'note': 't180 final quiet step',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect': {
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
    ]

    observed_dispatches = []
    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'])
        for entity_id, expected in step['expect'].items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f'step={idx} note={step["note"]} entity={entity_id} actual={actual} expected={expected}'
            )
        observed_dispatches.append(h.get(ENT['surplus_dispatch_decision_pys']))

    assert observed_dispatches[:6] == [
        'ACTIVATE_RELAY1',
        'ACTIVATE_EV',
        'ACTIVATE_RELAY2',
        'RELEASE_RELAY2',
        'RELEASE_EV',
        'RELEASE_RELAY1',
    ]
