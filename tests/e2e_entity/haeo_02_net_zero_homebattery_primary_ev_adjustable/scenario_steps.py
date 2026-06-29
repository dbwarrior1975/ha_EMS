from pathlib import Path

from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices
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
        # Deliberately opposite to the expected HAEO plan. The future EMS-internal
        # HAEO NET_ZERO path should choose the combo from the forecast, not from
        # these config helpers.
        E['adjustable_primary_load']: 'EV_CHARGER',
        E['adjustable_surplus_load']: 'HOME_BATTERY',
        E['adjustable_surplus_activation']: 2500,
        E['adjustable_surplus_load_priority']: 3,
        E['ev_min_absorb_w']: 920,
        E['ev_current_step_a']: 4,
        E['current_battery_sp']: 2500.0,
        E['actuator_battery_setpoint_w']: 2500.0,
        E['actuator_ev_enabled']: False,
        E['actuator_ev_current_a']: 6,
        E['devices']['RELAY1']['surplus_allowed']: False,
        E['devices']['RELAY2']['surplus_allowed']: False,
        E['pv_power_kw']: 3.5,
    })
    seed_active_surplus_devices(h, active_device_ids=())
    h.set_attrs(E['haeo_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 3.0},
            {'time': 900, 'value': 1.0},
        ],
    })
    h.set_attrs(E['haeo_ev_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 1.5},
            {'time': 900, 'value': 5.0},
        ],
    })
    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
