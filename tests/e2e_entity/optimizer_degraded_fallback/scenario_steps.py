from pathlib import Path

from tests.e2e_entity.scenario_runner import run_scenario_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root, goal_profile):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    h.set_entities({
        E['control_profile']: 'HORIZON_BY_HAEO',
        E['goal_profile']: goal_profile,
        E['forecast_profile']: 'NONE',
        E['haeo_battery_active_power_fresh_source']: 0.0,
        E['haeo_ev_active_power_fresh_source']: 0.0,
        E['primary_device_id']: 'HOME_BATTERY',
    })
    return h


def run_steps(h, steps):
    run_scenario_steps(h, steps)
