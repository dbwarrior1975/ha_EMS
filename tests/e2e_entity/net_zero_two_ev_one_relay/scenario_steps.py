from pathlib import Path

from tests.e2e_entity.refactored_runner import run_refactored_steps
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
        E['adjustable_surplus_load_priority']: 4,
        E['devices']['RELAY1']['priority']: 2,
        E['devices']['RELAY1']['surplus_allowed']: True,
        E['current_battery_sp']: 0.0,
        'input_number.ems_ev_garage_activation_threshold_w': 2000,
        'input_number.ems_ev_garage_min_power_w': 1380,
        'input_number.ems_ev_garage_max_power_w': 3680,
        'input_number.ems_ev_garage_power_step_w': 460,
        'input_number.ems_surplus_ev_garage_priority': 3,
        'input_boolean.ems_ev_garage_surplus_allowed': True,
        'input_number.ems_ev_garage_low_pv_threshold_w': 1600,
        'input_number.ems_ev_garage_low_pv_cycles': 2,
        'input_number.ems_ev_garage_release_cycles': 2,
        'input_number.ems_ev_garage_current_step_a': 2,
        'input_number.ems_ev_garage_phases': 1,
        'input_number.ems_ev_garage_voltage_v': 230,
        'switch.ev_garage_enabled': False,
        'number.ev_garage_current_a': 6,
        E['actuator_ev_enabled']: False,
        E['actuator_ev_current_a']: 6,
    })

    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
