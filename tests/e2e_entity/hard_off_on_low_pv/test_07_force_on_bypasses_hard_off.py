import pytest

from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices
from tests.e2e_entity.scenario_runner import seed_previous_device_state


@pytest.mark.scenario
def test_force_on_bypasses_active_hard_off_without_clearing_lifecycle_state(project_root):
    """User FORCE_ON must drive EV output even while low-PV HARD_OFF remains latched."""
    h = build_harness(project_root)
    E = h.ent

    seed_active_surplus_devices(
        h,
        active_device_ids=(),
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        E['ev_hard_off_pv_threshold_kw']: 1.6,
        E['ev_hard_off_low_pv_cycles']: 2,
        E['ev_hard_off_release_cycles']: 2,
    })
    seed_previous_device_state(h, mode='hard_off', low_pv_cycles=36)

    h.step(
        at_s=0,
        note='explicit EV FORCE_ON while low-PV HARD_OFF remains latched',
        set_values={
            **runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=12.0,
                required_power_consumption_kw=0.526,
                at_s=0,
                pv_power_kw=1.402,
            ),
            E['ev_force_on']: True,
            E['actuator_ev_enabled']: False,
            E['actuator_ev_current_a']: 6,
        },
    )

    policy_trace = h.getattrs(E['policy_diagnostics'])
    candidates = {item['device_id']: item for item in policy_trace['surplus_candidates']}
    policies = {item['device_id']: item for item in policy_trace['device_policies']}
    writer_trace = h.getattrs(E['actuator_writer_trace'])

    assert candidates['EV_CHARGER']['force_on'] is True
    assert candidates['EV_CHARGER']['activation_allowed'] is True
    assert policy_trace['feedback_protection_active'] is False
    assert policy_trace['device_lifecycle_states']['EV_CHARGER']['hard_off_active'] is True
    assert policy_trace['device_lifecycle_states']['EV_CHARGER']['hard_off_release_ready_cycles'] == 0
    assert policies['EV_CHARGER']['target_w'] > 0
    assert policies['EV_CHARGER']['enabled'] is True
    assert policies['EV_CHARGER']['mode'] == 'burn'
    assert policies['EV_CHARGER']['reason'] == 'ev_force_on'
    assert writer_trace['devices']['EV_CHARGER']['action'] == 'enable_and_set_current'
    assert h.get(E['actuator_ev_enabled']) is True
    assert h.get(E['actuator_ev_current_a']) > 6

    h.step(
        at_s=30,
        note='FORCE_ON removed -> still-latched HARD_OFF immediately regains authority',
        set_values={
            **runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=12.0,
                required_power_consumption_kw=0.526,
                at_s=30,
                pv_power_kw=1.402,
            ),
            E['ev_force_on']: False,
        },
    )

    released_policy_trace = h.getattrs(E['policy_diagnostics'])
    released_policies = {
        item['device_id']: item for item in released_policy_trace['device_policies']
    }
    released_writer_trace = h.getattrs(E['actuator_writer_trace'])

    assert released_policy_trace['device_lifecycle_states']['EV_CHARGER']['hard_off_active'] is True
    assert released_policy_trace['force_on_active_device_ids'] == ()
    assert released_policy_trace['force_on_hard_off_bypass_device_ids'] == ()
    assert released_policies['EV_CHARGER']['target_w'] == 0
    assert released_policies['EV_CHARGER']['enabled'] is False
    assert released_policies['EV_CHARGER']['mode'] == 'hard_off'
    assert released_policies['EV_CHARGER']['reason'] == 'ev_lifecycle_hard_off'
    assert released_writer_trace['devices']['EV_CHARGER']['action'] == 'hard_off'
    assert h.get(E['actuator_ev_enabled']) is False

