from tests.entity_ids import ENT
from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(
        project_root=project_root,
        start_ts=0.0,
        step_s=30,
        cfg_overrides={'surplus_freeze_s': 15},
        grouped_config_path=project_root / 'EMS_config.yaml',
    )

    h.set_entities({
        ENT['ramp_max_w']: 1000,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['surplus_freeze_s']: 15,
        ENT['relay2_priority']: 3,
        ENT['relay1_priority']: 2,
        ENT['ev_priority']: 1,
        ENT['relay2_force_on']: False,
        ENT['actuator_relay1']: False,
        ENT['actuator_relay2']: False,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
        ENT['grid_power_w']: 0.0,
        ENT['current_battery_sp']: 0.0,
        ENT['haeo_stale_timeout_s']: 300,
    })
    seed_active_surplus_devices(h, active_device_ids=())

    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
