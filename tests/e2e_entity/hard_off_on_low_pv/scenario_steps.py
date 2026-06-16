from tests.entity_ids import ENT
from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
PV_THRESHOLD_KW = 1.6


def build_harness(project_root):
    pv_ent = ENT['pv_power_kw']
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, grouped_config_path=project_root / 'EMS_config.yaml')
    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['control_profile']: 'AUTOMATIC',
        ENT['guard_profile']: 'NORMAL_LIMITS',
        ENT['ev_force_current_a']: 0,
        ENT['ev_min_current_a']: 6,
        ENT['ev_max_current_a']: 28,
        ENT['ev_charger_phases']: 1,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 6,
        pv_ent: 3.5,
        ENT['surplus_freeze_s']: 15,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['adjustable_surplus_load_priority']: 2,
        ENT['relay1_priority']: 3,
        ENT['relay2_priority']: 1,
    })
    return h

def run_steps(h, steps):
    run_refactored_steps(h, steps)
