from pathlib import Path

from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
from tests.e2e_entity.scenario_runner import run_scenario_steps


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    h.set_entities({
        E['primary_consuming_device_selector']: 'HOME_BATTERY',
        E['battery_protect_soc']: 1.0,
        E['battery_protect_soc_recovery_margin']: 1.0,
        E['battery_protect_min_cell_voltage_v']: 3.05,
        E['battery_protect_charge_floor_w']: 100.0,
    })
    return h


def run_steps(h, steps):
    run_scenario_steps(h, steps)
