from pathlib import Path

from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(
        project_root=project_root,
        start_ts=0.0,
        step_s=30,
        cfg_overrides={'surplus_freeze_s': 15},
        scenario_dir=Path(__file__).parent,
    )
    E = h.ent

    h.set_entities({
        E['ramp_max_w']: 1000,
        E['adjustable_surplus_load']: 'EV_CHARGER',
        E['adjustable_primary_load']: 'HOME_BATTERY',
        E['goal_profile']: 'NET_ZERO',
        E['forecast_profile']: 'NONE',
        E['surplus_freeze_s']: 15,
        E['relay2_priority']: 3,
        E['relay1_priority']: 2,
        E['ev_priority']: 1,
        E['relay2_force_on']: False,
        E['actuator_relay1']: False,
        E['actuator_relay2']: False,
        E['actuator_ev_enabled']: False,
        E['actuator_ev_current_a']: 6,
        E['grid_power_w']: 0.0,
        E['current_battery_sp']: 0.0,
        E['haeo_stale_timeout_s']: 300,
    })
    seed_active_surplus_devices(h, active_device_ids=())

    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
