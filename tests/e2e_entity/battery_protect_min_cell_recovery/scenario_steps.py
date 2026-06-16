from tests.entity_ids import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
from tests.e2e_entity.refactored_runner import run_refactored_steps


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, grouped_config_path=project_root / 'EMS_config.yaml')
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
    run_refactored_steps(h, steps)
