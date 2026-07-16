from pathlib import Path

from tests.e2e_entity.scenario_runner import run_scenario_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    h.set_entities({
        E['max_battery_discharge_w']: 4000,
        E['ramp_max_w']: 1000,
        E['primary_consuming_device_selector']: 'HOME_BATTERY',
        E['actuator_ev_enabled']: True,
        E['actuator_ev_current_a']: 6,
        E['ev_min_absorb_w']: 1380,
        E['ev_max_absorb_w']: 6440,
        E['goal_profile']: 'NET_ZERO',
        E['forecast_profile']: 'NONE',
    })
    return h


def run_steps(h, steps):
    run_scenario_steps(h, steps)
