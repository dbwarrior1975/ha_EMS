import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_net_zero_ev_release_restores_min_current_in_quarter(project_root):
    """
    Focused quarter scenario for the observed EV release path:
    - EV gets activated to high current during NET_ZERO burn
    - later EV is released
    - on the following step policy current becomes 0
    - writer loop restores EV actuator current to min current
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    h.set_entities({
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 4,
    })

    steps = [
        {
            'note': 't0 activate relay1',
            'set': {ENT['required_power_consumption_kw']: 3.5, ENT['rpnz_w']: 500},
            'expect': {ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1'},
        },
        {
            'note': 't30 activate ev',
            'set': {ENT['required_power_consumption_kw']: 6.0, ENT['rpnz_w']: 500},
            'expect': {ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_EV'},
        },
        {
            'note': 't60 ev is actively burning at max current',
            'set': {ENT['required_power_consumption_kw']: 6.0, ENT['rpnz_w']: 500},
            'expect': {
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'note': 't90 release EV once lower-priority load already gone',
            'set': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect': {ENT['surplus_dispatch_decision_pys']: 'RELEASE_EV'},
        },
        {
            'note': 't120 EV no longer active -> policy drops to 0 -> writer restores min current',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect': {
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_current_a']: 4,
            },
            'trace': {
                ('sensor.ems_actuator_writer_trace', 'ev', 'reason'): 'restore_min_current',
                ('sensor.ems_actuator_writer_trace', 'ev', 'new_current_a'): 4,
            },
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'])
        for entity_id, expected in step['expect'].items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f'step={idx} note={step["note"]} entity={entity_id} actual={actual} expected={expected}'
            )
        for key_tuple, expected in step.get('trace', {}).items():
            entity_id, branch, field = key_tuple
            assert h.get(entity_id) == 'ACTIVE'
            actual = h.getattrs(entity_id)[branch][field]
            assert actual == expected, (
                f'step={idx} trace {branch}.{field} actual={actual} expected={expected}'
            )
