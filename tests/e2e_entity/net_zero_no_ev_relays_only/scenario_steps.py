from pathlib import Path

from tests.e2e_entity.scenario_runner import run_scenario_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(
        project_root=project_root,
        start_ts=0.0,
        step_s=30,
        scenario_dir=Path(__file__).parent,
    )
    E = h.ent

    h.set_entities({
        E['surplus_freeze_s']: 15,
        E['ramp_max_w']: 1000,
        E['primary_consuming_device_id']: '',
        E['devices']['HOME_BATTERY']['priority']: 4,
        E['devices']['RELAY1']['priority']: 2,
        E['devices']['RELAY2']['priority']: 1,
        E['devices']['RELAY1']['surplus_allowed']: True,
        E['devices']['RELAY2']['surplus_allowed']: True,
        E['max_solar_charge_w']: 2000,
        E['current_battery_sp']: 0.0,
    })

    return h


def run_steps(h, steps):
    run_scenario_steps(h, steps)
