from pathlib import Path

from tests.e2e_entity.refactored_runner import run_refactored_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


def build_harness(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30, scenario_dir=Path(__file__).parent)
    E = h.ent
    relay3 = E['devices']['RELAY3']

    h.set_entities({
        E['surplus_freeze_s']: 15,
        E['adjustable_surplus_load']: 'EV_CHARGER',
        E['adjustable_primary_load']: 'HOME_BATTERY',
        E['adjustable_surplus_load_priority']: 3,
        E['actuator_ev_enabled']: False,
        E['actuator_ev_current_a']: 6,
        E['ev_max_absorb_w']: 6440,
        E['devices']['RELAY1']['priority']: 4,
        E['devices']['RELAY2']['priority']: 2,
        relay3['priority']: 1,
        E['devices']['RELAY1']['surplus_allowed']: True,
        E['devices']['RELAY2']['surplus_allowed']: True,
        relay3['surplus_allowed']: True,
        relay3['force_on']: False,
        relay3['enabled']: False,
        relay3['max_absorb_w']: 7500,
    })
    seed_active_surplus_devices(h, active_device_ids=(), relay_states={'RELAY3': False})

    return h


def run_steps(h, steps):
    run_refactored_steps(h, steps)
