from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    h.set_entities({
        ENT['surplus_freeze_s']: 15,
        ENT['ramp_max_w']: 1000,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['adjustable_surplus_activation']: 2500,
        ENT['adjustable_surplus_load_priority']: 4,
        ENT['ev_priority']: 3,
        ENT['relay1_priority']: 2,
        ENT['relay2_priority']: 1,
        ENT['relay1_surplus_allowed']: True,
        ENT['relay2_surplus_allowed']: True,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
        ENT['ev_current_step_a']: 1,
        ENT['ev_charger_phases']: 1,
        ENT['ev_max_current_a']: 28,
        ENT['max_solar_charge_w']: 2000,
        ENT['current_battery_sp']: 0.0,
    })

    return h


def run_steps(h, steps):
    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        policy_trace = h.getattrs(ENT['policy_decision_trace'])
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)

        assert policy_trace['goal'] == 'NET_ZERO'
        assert policy_trace['surplus_dispatch_decision'] == h.get(ENT['surplus_dispatch_decision_pys'])

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

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} "
                f"actual={actual} expected={expected}"
            )

        assert h.get(ENT['policy_ev_current_a']) >= 0, (
            f"step={idx} note={step['note']} EV current must never be negative"
        )

        if step.get('expect_battery_negative'):
            assert h.get(ENT['policy_battery_target_w']) < 0, (
                f"step={idx} note={step['note']} battery target should be negative (discharge)"
            )
