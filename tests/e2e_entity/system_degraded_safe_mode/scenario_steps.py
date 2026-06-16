from tests.entity_ids import ENT
from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=1000.0, step_s=30, grouped_config_path=project_root / 'EMS_config.yaml')
    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['soc']: 50.0,
        ENT['battery_heartbeat']: 0.0,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
    })
    h.set_stale(ENT['battery_heartbeat'], 1000.0)
    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
