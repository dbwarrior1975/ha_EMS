from pathlib import Path

from tests.e2e_entity.scenario_runner import run_scenario_steps
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    h.set_entities({
        E['control_profile']: 'HORIZON_BY_HAEO',
        E['goal_profile']: 'NET_ZERO',
        E['forecast_profile']: 'NONE',
        E['haeo_stale_timeout_s']: 300,
        E['haeo_battery_active_power_fresh_source']: 1.0,
        E['haeo_ev_active_power_fresh_source']: 1.0,
        E['haeo_battery_power_active']: 3.0,
        E['haeo_ev_battery_power_active']: 1.5,
        # Deliberately opposite to the expected HAEO plan. The future EMS-internal
        # HAEO NET_ZERO path should choose the combo from the forecast, not from
        # these config helpers.
        E['primary_consuming_device_selector']: 'EV_CHARGER',
        E['devices']['HOME_BATTERY']['priority']: 3,
        E['ev_min_absorb_w']: 920,
        E['ev_current_step_a']: 4,
        E['current_battery_sp']: 2500.0,
        E['actuator_battery_setpoint_w']: 2500.0,
        E['actuator_ev_enabled']: False,
        E['actuator_ev_current_a']: 6,
        E['devices']['RELAY1']['surplus_allowed']: False,
        E['devices']['RELAY2']['surplus_allowed']: False,
        E['pv_power_w']: 3500.0,
    })
    seed_active_surplus_devices(h, active_device_ids=())
    return h


def run_steps(h, steps):
    run_scenario_steps(h, steps)
