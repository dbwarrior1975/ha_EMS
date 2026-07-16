import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_ev_surplus_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_ev_surplus_load.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_previous_device_state
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_03_post_hard_off_recovery(project_root):
    """Phase 3: post-release/hard-off behavior and release-ready recovery ramp."""
    h = build_harness(project_root)
    E = h.ent

    # Seed phase-2 end state.
    seed_active_surplus_devices(
        h,
        active_device_ids=(),
        actuator_ev_enabled=False,
        actuator_ev_current_a=6,
        actuator_battery_setpoint_w=500,
    )
    h.set_entities({
        E['surplus_freeze_until']: 104.0,
        E['ev_hard_off_release_cycles']: 2,
    })
    seed_previous_device_state(h, mode='hard_off', low_pv_cycles=2)

    steps = [
        {
            'at_s': 240,
            'note': 't240 IF only RPC is abouve threshold but PV is below, remain in hard-off and do not count towards release-ready.',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-5.0,
                required_power_consumption_kw=1.45,
                at_s=240,
                pv_power_kw=0.0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-5.0,
                required_power_consumption_kw=1.45,
                at_s=240,
            ),
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False},
                'HOME_BATTERY': {'target_w': 1200},
            },
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 0,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'effective_primary_consuming_device_id': 'HOME_BATTERY',
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 1200,
            },
        },
        {
            'at_s': 270,
            'note': 't270 recovered PV starts the release counter even when RPC is zero; EV remains hard-off until the configured count is met',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=1.0,
                required_power_consumption_kw=0.0,
                at_s=270,
                pv_power_kw=1.7,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=1.0,
                required_power_consumption_kw=0.0,
                at_s=270,
            ),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 1200},
                'EV_CHARGER': {'enabled': False},
            },
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 1,
                'battery_min_floor_reason': 'not_applicable',
                'effective_primary_consuming_device_id': 'HOME_BATTERY',
                'primary_power_envelope_w': 1200.0,
            },
            'expect_values': {},
        },
        {
            'at_s': 275,
            'note': 't275 the second consecutive recovered-PV tick releases HARD_OFF; primary selection can now consider EV independently of RPC release gating.',
            'set': {
                **runtime_inputs_for_net_zero_intent(
                    E,
                    rpnz_w=100.0,
                    required_power_consumption_kw=1.385,
                    at_s=275,
                    pv_power_kw=1.7,
                ),
                E['ev_hard_off_low_pv_cycles']: 3,
            },
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=100.0,
                required_power_consumption_kw=1.385,
                at_s=275,
            ),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 1200},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 2,
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'surplus_freeze_until_ts': 104,
                'battery_min_floor_reason': 'primary_consuming_authority_hold',
                'effective_primary_consuming_device_id': 'EV_CHARGER',
                'primary_power_envelope_w': 2080.0,
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 1200,
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 9,
            },
        },
        {
            'at_s': 280,
            'note': 't280 EV is already released; primary authority continues while the release counter returns to its inactive value',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-10,
                required_power_consumption_kw=2.49,
                at_s=280,
                pv_power_kw=1.7,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-10,
                required_power_consumption_kw=2.49,
                at_s=280,
            ),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 1200},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_release_ready_cycles': 0,
                'battery_min_floor_reason': 'primary_consuming_authority_hold',
                'primary_power_envelope_w': 3070.0,
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 1200,
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 13,
            },
        },

        {
            'at_s': 285,
            'note': 't285 the shared controller ramps EV down to its physical minimum while EV remains the effective primary',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=-15,
                required_power_consumption_kw=-2.49,
                at_s=285,
                pv_power_kw=1.7,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-15,
                required_power_consumption_kw=-2.49,
                at_s=285,
            ),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 200},
                'EV_CHARGER': {'enabled': True, 'mode': 'burn', 'target_w': 1840},
            },
            'expect_policy': {
                'battery_min_floor_reason': 'ev_active_floor_override',
                'effective_primary_consuming_device_id': 'EV_CHARGER',
                'primary_consuming_skipped_by_id': {},
                'primary_power_envelope_w': 1990.0,
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 200,
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 8,
            },
        },

        {
            'at_s': 295,
            'note': 't295 EV remains available and ramps upward under primary authority',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=45,
                required_power_consumption_kw=2.49,
                at_s=295,
                pv_power_kw=1.7,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=45,
                required_power_consumption_kw=2.49,
                at_s=295,
            ),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 200},
                'EV_CHARGER': {'enabled': True, 'target_w': 2760},
            },
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'battery_min_floor_reason': 'primary_consuming_authority_hold',
                'primary_power_envelope_w': 2840.0,
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 200,
                E['actuator_ev_current_a']: 12,
            },
        }, 

        {
            'at_s': 300,
            'note': 't300 PV 5.5 kW',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=45,
                required_power_consumption_kw=2.65,
                at_s=300,
                pv_power_kw=3.7,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=45,
                required_power_consumption_kw=2.65,
                at_s=300,
            ),
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 200},
                'EV_CHARGER': {'enabled': True, 'target_w': 3680},
            },
            'expect_policy': {
                'device_lifecycle_states.EV_CHARGER.hard_off_active': False,
                'battery_min_floor_reason': 'primary_consuming_authority_hold',
                'primary_power_envelope_w': 3760.0,
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 200,
                E['actuator_ev_current_a']: 16,
            },
        },         
    ]

    run_steps(h, steps)
