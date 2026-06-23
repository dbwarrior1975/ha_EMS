from pathlib import Path

from tests.e2e_entity.refactored_runner import run_refactored_steps
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
        E['ev_min_current_a']: 4,
        E['ev_current_step_a']: 4,
        E['actuator_battery_setpoint_w']: 0.0,
        E['actuator_ev_enabled']: False,
        E['actuator_ev_current_a']: 6,
    })
    h.set_attrs(E['haeo_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 1.5},
        ],
    })
    h.set_attrs(E['haeo_ev_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 3.7},
        ],
    })
    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
