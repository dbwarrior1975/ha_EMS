from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['battery_protect_soc']: 1.0,
        ENT['battery_protect_soc_recovery_margin']: 1.0,
        ENT['battery_protect_min_cell_voltage_v']: 3.05,
        ENT['battery_protect_charge_floor_w']: 100.0,
    })
    return h


def run_steps(h, steps):
    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        policy_trace = h.getattrs(ENT['policy_decision_trace'])

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

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} "
                f"actual={actual} expected={expected}"
            )
