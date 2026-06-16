from tests.entity_ids import ENT
from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, grouped_config_path=project_root / 'EMS_config.yaml')
    h.set_entities({
        ENT['control_profile']: 'HORIZON_BY_HAEO',
        ENT['goal_profile']: 'CHEAP_GRID_CHARGE',
        ENT['forecast_profile']: 'NONE',
        ENT['haeo_stale_timeout_s']: 300,
        ENT['haeo_battery_active_power_fresh_source']: 1.0,
        ENT['haeo_ev_active_power_fresh_source']: 1.0,
        ENT['ev_min_current_a']: 4,
        ENT['ev_current_step_a']: 4,
        ENT['actuator_battery_setpoint_w']: 0.0,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
    })
    h.set_attrs(ENT['haeo_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 1.5},
        ],
    })
    h.set_attrs(ENT['haeo_ev_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 3.7},
        ],
    })
    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
