import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_goal_transition_net_zero_ev_burn_to_max_export_min_current_and_clear_latches(project_root):
    """
    Scenario: NET_ZERO surplus EV burn is active, then goal changes to MAX_EXPORT.

    Current expected semantics:
    - NET_ZERO surplus policy becomes inactive when goal != NET_ZERO
    - surplus latch loop clears active surplus latches
    - MAX_EXPORT EV policy is ev_min_current_a, not EV off
    - EV charger remains enabled if it was already enabled
    - EV actuator current is reduced from max current to min current
    - relay actuators are released/off

    If product semantics later change so MAX_EXPORT means EV OFF, this test should
    be updated together with ems_core.net_zero.load_projection.ev_strategy_current_a().
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    # EV starts already enabled so we can distinguish "set current to min" from
    # "turn charger on" behaviour after the goal transition.
    h.set_entities({
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 4,
        ENT['ev_min_current_a']: 4,
        ENT['ev_max_current_a']: 28,
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
    })

    steps = [
        {
            'note': 't0 NET_ZERO activates relay1 first',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['surplus_r1_active']: True,
            },
        },
        {
            'note': 't30 NET_ZERO activates EV next',
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
        },
        {
            'note': 't60 EV burn is active at max current',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['surplus_ev_active']: True,
            },
        },
        {
            'note': 't90 goal changes to MAX_EXPORT; surplus latches clear and EV drops to 0 current',
            'set': {
                ENT['goal_profile']: 'MAX_EXPORT',
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'CLEAR_ALL',
                ENT['surplus_r1_active']: False,
                ENT['surplus_ev_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 0,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_trace': {
                ('sensor.ems_actuator_writer_trace', 'ev', 'new_current_a'): 0,
            },
        },
        {
            'note': 't120 MAX_EXPORT remains stable: EV stays off and latches remain clear',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['goal_profile']: 'MAX_EXPORT',
                ENT['surplus_r1_active']: False,
                ENT['surplus_ev_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'])

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} "
                f"actual={actual} expected={expected}"
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
