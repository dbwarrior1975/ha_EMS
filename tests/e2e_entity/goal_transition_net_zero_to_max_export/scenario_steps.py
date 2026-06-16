from tests.entity_ids import ENT
from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, grouped_config_path=project_root / 'EMS_config.yaml')
    h.set_entities({
        ENT['max_battery_discharge_w']: -4000,
        ENT['ramp_max_w']: 1000,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 6,
        ENT['ev_min_current_a']: 6,
        ENT['ev_max_current_a']: 28,
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
    })
    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
