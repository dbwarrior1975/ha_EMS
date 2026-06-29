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
        E['adjustable_surplus_load']: 'EV_CHARGER',
        E['adjustable_primary_load']: 'HOME_BATTERY',
        E['adjustable_surplus_activation']: 2500,
        E['adjustable_surplus_load_priority']: 4,
        E['ev_priority']: 3,
        E['actuator_ev_enabled']: False,
        E['actuator_ev_current_a']: 6,
        E['ev_current_step_a']: 1,
        E['ev_charger_phases']: 1,
        E['ev_max_absorb_w']: 6440,
        E['max_solar_charge_w']: 2000,
        E['current_battery_sp']: 0.0,
        E['pv_power_kw']: 4.0,
    })

    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
