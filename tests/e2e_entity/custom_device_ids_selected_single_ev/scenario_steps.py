from pathlib import Path

from tests.e2e_entity.scenario_runner import run_scenario_steps
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(
        project_root=project_root,
        start_ts=0.0,
        step_s=30,
        scenario_dir=Path(__file__).parent,
    )
    E = h.ent

    h.set_entities({
        E['surplus_freeze_s']: 15,
        E['ramp_max_w']: 1000,
        E['adjustable_surplus_load']: 'EV_GARAGE',
        E['adjustable_primary_load']: 'HOME_BATTERY',
        E['adjustable_surplus_activation']: 2000,
        E['devices']['EV_GARAGE']['priority']: 4,
        E['current_battery_sp']: 0.0,
        'input_number.ems_ev_main_activation_threshold_w': 2000,
        'input_number.ems_ev_garage_activation_threshold_w': 2000,
        'input_number.ems_ev_main_min_power_w': 1380,
        'input_number.ems_ev_main_max_power_w': 3680,
        'input_number.ems_ev_main_power_step_w': 460,
        'input_number.ems_surplus_ev_main_priority': 2,
        'input_boolean.ems_ev_main_surplus_allowed': True,
        'input_number.ems_ev_main_low_pv_threshold_w': 1600,
        'input_number.ems_ev_main_low_pv_cycles': 2,
        'input_number.ems_ev_main_release_cycles': 2,
        'input_number.ems_ev_main_current_step_a': 2,
        'input_number.ems_ev_main_phases': 1,
        'input_number.ems_ev_main_voltage_v': 230,
        'switch.ev_main_enabled': False,
        'number.ev_main_current_a': 6,
        'input_number.ems_ev_garage_min_power_w': 1380,
        'input_number.ems_ev_garage_max_power_w': 3680,
        'input_number.ems_ev_garage_power_step_w': 460,
        'input_boolean.ems_ev_garage_surplus_allowed': True,
        'input_number.ems_ev_garage_low_pv_threshold_w': 1600,
        'input_number.ems_ev_garage_low_pv_cycles': 2,
        'input_number.ems_ev_garage_release_cycles': 2,
        'input_number.ems_ev_garage_current_step_a': 2,
        'input_number.ems_ev_garage_phases': 1,
        'input_number.ems_ev_garage_voltage_v': 230,
        'switch.ev_garage_enabled': False,
        'number.ev_garage_current_a': 6,
        'input_number.ems_surplus_relay_sauna_priority': 4,
        'input_boolean.ems_relay_sauna_enabled_import_zero': True,
        'input_boolean.ems_relay_sauna_force_on': False,
        'input_number.ems_relay_sauna_power_kw': 2.5,
        'input_number.ems_relay_sauna_nominal_absorb_w': 2500,
        'switch.relay_sauna_enabled': False,
        'input_number.ems_surplus_relay_boiler_priority': 1,
        'input_boolean.ems_relay_boiler_enabled_import_zero': True,
        'input_boolean.ems_relay_boiler_force_on': False,
        'input_number.ems_relay_boiler_power_kw': 5.0,
        'input_number.ems_relay_boiler_nominal_absorb_w': 5000,
        'switch.relay_boiler_enabled': False,
    })

    return h


def run_steps(h, steps):
    run_scenario_steps(h, steps)
