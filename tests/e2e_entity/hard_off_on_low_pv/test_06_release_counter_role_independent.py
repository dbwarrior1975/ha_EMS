import pytest

from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import build_harness
from tests.e2e_entity.hard_off_on_low_pv.scenario_steps import run_steps
from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices
from tests.e2e_entity.scenario_runner import seed_previous_device_state


@pytest.mark.scenario
def test_hard_off_release_counter_applies_when_ev_is_surplus_adjustable(project_root):
    """HOME_BATTERY primary / EV adjustable must not bypass release cycles."""
    h = build_harness(project_root)
    E = h.ent

    seed_active_surplus_devices(
        h,
        active_device_ids=(),
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
    )
    h.set_entities({
        E['ev_hard_off_release_cycles']: 3,
        E['ev_hard_off_pv_threshold_kw']: 1.6,
    })
    seed_previous_device_state(h, mode='hard_off')

    def recovery_inputs(at_s, rpc_kw):
        return runtime_inputs_for_net_zero_intent(
            E,
            rpnz_w=25.0,
            required_power_consumption_kw=rpc_kw,
            at_s=at_s,
            pv_power_kw=5.9,
        )

    def recovery_derived(at_s, rpc_kw):
        return expect_derived_for_net_zero_intent(
            rpnz_w=25.0,
            required_power_consumption_kw=rpc_kw,
            at_s=at_s,
        )

    steps = [
        {
            'at_s': 100,
            'note': 'recovery cycle 1 increments counter but EV stays hard-off',
            'set': recovery_inputs(100, 7.0),
            'expect_derived': recovery_derived(100, 7.0),
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 1,
            },
            'expect_device_policies': {'EV_CHARGER': {'enabled': False}},
        },
        {
            'at_s': 130,
            'note': 'recovery cycle 2 still does not release when three cycles are required',
            'set': recovery_inputs(130, 7.0),
            'expect_derived': recovery_derived(130, 7.0),
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 2,
            },
            'expect_device_policies': {'EV_CHARGER': {'enabled': False}},
        },
        {
            'at_s': 160,
            'note': 'PV dropping below the lifecycle threshold resets the release counter',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=25.0,
                required_power_consumption_kw=4.0,
                at_s=160,
                pv_power_kw=1.0,
            ),
            'expect_derived': recovery_derived(160, 4.0),
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 0,
            },
            'expect_device_policies': {'EV_CHARGER': {'enabled': False}},
        },
        {
            'at_s': 190,
            'note': 'recovery restarts at cycle 1 after reset',
            'set': recovery_inputs(190, 7.0),
            'expect_derived': recovery_derived(190, 7.0),
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 1,
            },
            'expect_device_policies': {'EV_CHARGER': {'enabled': False}},
        },
        {
            'at_s': 220,
            'note': 'recovery cycle 2 remains hard-off',
            'set': recovery_inputs(220, 7.0),
            'expect_derived': recovery_derived(220, 7.0),
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': True,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 2,
            },
            'expect_device_policies': {'EV_CHARGER': {'enabled': False}},
        },
        {
            'at_s': 250,
            'note': 'the third consecutive PV-recovery cycle releases HARD_OFF; activation remains a separate dispatch step',
            'set': recovery_inputs(250, 7.0),
            'expect_derived': recovery_derived(250, 7.0),
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 3,
                'surplus_next_device_id': 'EV_CHARGER',
                'surplus_dispatch_action': 'ACTIVATE',
                'surplus_explanation': 'Raw RPC 7.000 kW >= EV_CHARGER threshold 5.060 kW',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'mode': 'restore_min'},
            },
        },
    ]

    run_steps(h, steps)
