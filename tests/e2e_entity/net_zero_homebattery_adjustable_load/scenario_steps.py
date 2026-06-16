from tests.entity_ids import ENT
from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, grouped_config_path=project_root / 'EMS_config.yaml')

    h.set_entities({
        ENT['surplus_freeze_s']: 15,
        ENT['ramp_max_w']: 1000,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['adjustable_surplus_activation']: 2500,
        ENT['adjustable_surplus_load_priority']: 4,
        ENT['ev_priority']: 3,
        ENT['relay1_priority']: 2,
        ENT['relay2_priority']: 1,
        ENT['relay1_surplus_allowed']: True,
        ENT['relay2_surplus_allowed']: True,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 6,
        ENT['ev_current_step_a']: 1,
        ENT['ev_charger_phases']: 1,
        ENT['ev_max_current_a']: 28,
        ENT['max_solar_charge_w']: 2000,
        ENT['current_battery_sp']: 0.0,
    })

    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
