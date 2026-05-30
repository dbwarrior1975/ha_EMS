import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_net_zero_ev_stays_at_min_first_then_hard_off_when_low_pv_persists_spec(project_root):
    """
    Spec test for desired NET_ZERO EV behaviour when solar production collapses.

    Intended semantics:
    1. EV surplus burn may end normally inside NET_ZERO.
    2. On the next step EV is restored to minimum current instead of turning off
       immediately. This keeps the current anti-flap / quarter-transition behaviour.
    3. If PV stays below a known practical threshold for long enough, EV should be
       hard-disabled because there is no real surplus left even for minimum current.

    This test is intentionally written as a target spec. It is expected to fail until
    production code learns a dedicated NET_ZERO hard-off policy.

    Assumptions encoded here:
    1. low PV threshold is represented by a separate external sensor value
    2. threshold example is 1.6 kW
    3. persistence requirement is 2 x 30 s policy cycles ~= 60 s
    4. hard-off is only expected after EV has first gone through the existing
       restore-to-min path
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    pv_ent = ENT['pv_power_kw']
    pv_threshold_kw = 1.6

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
    })

    steps = [
        {
            'note': 't0 enough surplus -> activate relay1 first',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
                pv_ent: 3.5,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['surplus_r1_active']: True,
            },
        },
        {
            'note': 't30 enough surplus -> activate EV next',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
                pv_ent: 3.2,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_EV',
                ENT['surplus_ev_active']: True,
            },
        },
        {
            'note': 't60 EV is actively burning at max current',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
                pv_ent: 3.0,
            },
            'expect_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['surplus_ev_active']: True,
            },
        },
        {
            'note': 't90 PV drops below threshold, EV burn is released but EV remains at min first',
            'set': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.4,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_EV',
            },
        },
        {
            'note': 't120 first low-PV cycle after release -> restore min, no hard-off yet',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.3,
            },
            'expect_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 4,
            },
            'expect_trace': {
                ('sensor.ems_actuator_writer_trace', 'ev', 'reason'): 'restore_min_current',
                ('sensor.ems_actuator_writer_trace', 'ev', 'new_current_a'): 4,
            },
        },
        {
            'note': 't150 second consecutive low-PV cycle below threshold -> hard-off expected',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.2,
            },
            'expect_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 0,
            },
            'expect_trace': {
                ('sensor.ems_actuator_writer_trace', 'ev', 'reason'): 'hard_off',
                ('sensor.ems_actuator_writer_trace', 'ev', 'new_current_a'): 0,
            },
        },
        {
            'note': 't180 low PV persists -> EV remains off',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.1,
            },
            'expect_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 0,
            },
        },
        {
            'note': 't210 notlow PV persists anymore -> EV still remains off',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.9,
            },
            'expect_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 0,
            },
        }, 

        {
            'note': 't240 required power conumption is close to trigger EV charger normally way',
            'set': {
                ENT['required_power_consumption_kw']: 4.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 5.9,
            },
            'expect_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 0,
            },
        },

        {
            'note': 't270 required power conumption is triggering EV charger normally way',
            'set': {
                ENT['required_power_consumption_kw']: 5.8,
                ENT['rpnz_w']: 0.0,
                pv_ent: 5.9,
            },
            'expect_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
            },
        },        
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'])

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} threshold_kw={pv_threshold_kw} "
                f"entity={entity_id} actual={actual} expected={expected}"
            )

        for key_tuple, expected in step.get('expect_trace', {}).items():
            entity_id, branch, field = key_tuple
            trace_state = h.get(entity_id)
            assert trace_state == 'ACTIVE', (
                f"step={idx} note={step['note']} trace entity {entity_id} "
                f"actual={trace_state} expected=ACTIVE"
            )
            attrs = h.getattrs(entity_id)
            actual = attrs[branch][field]
            assert actual == expected, (
                f"step={idx} note={step['note']} trace={entity_id}.{branch}.{field} "
                f"actual={actual} expected={expected}"
            )
