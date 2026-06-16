from tests.entity_ids import ENT
from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root, goal_profile):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, grouped_config_path=project_root / 'EMS_config.yaml')
    h.set_entities({
        ENT['control_profile']: 'HORIZON_BY_HAEO',
        ENT['goal_profile']: goal_profile,
        ENT['forecast_profile']: 'NONE',
        ENT['haeo_battery_active_power_fresh_source']: 0.0,
        ENT['haeo_ev_active_power_fresh_source']: 0.0,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
    })
    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
