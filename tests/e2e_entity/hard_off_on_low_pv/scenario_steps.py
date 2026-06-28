from pathlib import Path

from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
PV_THRESHOLD_KW = 1.6


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    pv_ent = E['pv_power_kw']
    h.set_entities({
        E['goal_profile']: 'NET_ZERO',
        E['forecast_profile']: 'NONE',
        E['control_profile']: 'AUTOMATIC',
        E['guard_profile']: 'NORMAL_LIMITS',
        E['ev_force_on']: False,
        E['ev_min_current_a']: 6,
        E['ev_max_current_a']: 28,
        E['ev_charger_phases']: 1,
        E['actuator_ev_enabled']: True,
        E['actuator_ev_current_a']: 6,
        pv_ent: 3.5,
        E['surplus_freeze_s']: 15,
        E['adjustable_surplus_load']: 'EV_CHARGER',
        E['adjustable_primary_load']: 'HOME_BATTERY',
        E['adjustable_surplus_load_priority']: 2,
        E['relay1_priority']: 3,
        E['relay2_priority']: 1,
    })
    return h

def run_steps(h, steps):
    run_refactored_steps(h, steps)
