from tests.entity_ids import ENT
from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, grouped_config_path=project_root / 'EMS_config.yaml')
    h.set_entities({
        ENT['control_profile']: 'HORIZON_BY_HAEO',
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['haeo_stale_timeout_s']: 300,
        ENT['haeo_battery_active_power_fresh_source']: 1.0,
        ENT['haeo_ev_active_power_fresh_source']: 1.0,
        # Deliberately opposite to the expected HAEO plan. The future EMS-internal
        # HAEO NET_ZERO path should choose the combo from the forecast, not from
        # these config helpers.
        ENT['adjustable_primary_load']: 'EV_CHARGER',
        ENT['adjustable_surplus_load']: 'HOME_BATTERY',
        ENT['adjustable_surplus_activation']: 2500,
        ENT['adjustable_surplus_load_priority']: 3,
        ENT['ev_min_current_a']: 4,
        ENT['ev_current_step_a']: 4,
        ENT['current_battery_sp']: 2500.0,
        ENT['actuator_battery_setpoint_w']: 2500.0,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
        ENT['relay1_surplus_allowed']: False,
        ENT['relay2_surplus_allowed']: False,
        ENT['pv_power_kw']: 3.5,
    })
    seed_active_surplus_devices(h, active_device_ids=())
    h.set_attrs(ENT['haeo_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 3.0},
            {'time': 900, 'value': 1.0},
        ],
    })
    h.set_attrs(ENT['haeo_ev_battery_power_active'], {
        'forecast': [
            {'time': 0, 'value': 1.5},
            {'time': 900, 'value': 5.0},
        ],
    })
    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
