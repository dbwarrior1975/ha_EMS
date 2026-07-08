from pathlib import Path

from tests.e2e_entity.scenario_runner import run_scenario_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
PV_THRESHOLD_KW = 1.6


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    pv_ent = E['pv_power_w']
    h.set_entities({
        E['goal_profile']: 'NET_ZERO',
        E['forecast_profile']: 'NONE',
        E['control_profile']: 'AUTOMATIC',
        E['guard_profile']: 'NORMAL_LIMITS',
        E['ev_force_on']: False,
        E['ev_min_absorb_w']: 1380,
        E['ev_max_absorb_w']: 6440,
        E['ev_charger_phases']: 1,
        E['actuator_ev_enabled']: True,
        E['actuator_ev_current_a']: 6,
        pv_ent: 3500.0,
        E['surplus_freeze_s']: 15,
        E['primary_device_id']: 'HOME_BATTERY',
        E['devices']['EV_CHARGER']['priority']: 2,
        E['devices']['RELAY1']['priority']: 3,
        E['devices']['RELAY2']['priority']: 1,
    })
    return h

def run_steps(h, steps):
    run_scenario_steps(h, steps)
