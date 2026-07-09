from pathlib import Path

from tests.e2e_entity.scenario_runner import run_scenario_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    h.set_entities({
        E['control_profile']: 'HORIZON_BY_HAEO',
        E['goal_profile']: 'CHEAP_GRID_CHARGE',
        E['forecast_profile']: 'NONE',
        E['haeo_stale_timeout_s']: 300,
        E['haeo_battery_active_power_fresh_source']: 1.0,
        E['haeo_ev_active_power_fresh_source']: 1.0,
        E['haeo_battery_power_active']: 1.5,
        E['haeo_ev_battery_power_active']: 3.7,
        E['ev_min_absorb_w']: 920,
        E['ev_current_step_a']: 4,
        E['actuator_battery_setpoint_w']: 0.0,
        E['actuator_ev_enabled']: False,
        E['actuator_ev_current_a']: 6,
    })
    return h


def run_steps(h, steps):
    run_scenario_steps(h, steps)
