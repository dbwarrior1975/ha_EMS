from pathlib import Path

from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    h.set_entities({
        E['max_battery_discharge_w']: -4000,
        E['ramp_max_w']: 1000,
        E['adjustable_surplus_load']: 'EV_CHARGER',
        E['adjustable_primary_load']: 'HOME_BATTERY',
        E['actuator_ev_enabled']: True,
        E['actuator_ev_current_a']: 6,
        E['ev_min_current_a']: 6,
        E['ev_max_current_a']: 28,
        E['goal_profile']: 'NET_ZERO',
        E['forecast_profile']: 'NONE',
    })
    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
