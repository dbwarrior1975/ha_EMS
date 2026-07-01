import pytest

from tests.e2e_entity.haeo_02_net_zero_homebattery_primary_ev_adjustable.scenario_steps import (
    build_harness,
    run_steps,
)
from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent

@pytest.mark.xfail(reason='Future EMS-internal HAEO combo semantics are not implemented yet')
@pytest.mark.scenario
def test_haeo_net_zero_internal_plan_homebattery_primary_ev_adjustable(project_root):
    """
    Future EMS-internal HAEO NET_ZERO semantics:
    battery forecast is larger than EV forecast, so HOME_BATTERY becomes
    primary and EV_CHARGER becomes adjustable surplus for this quarter.
    """
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 'quarter start: internal HAEO plan selects HOME_BATTERY primary and EV adjustable',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=6000.0,
                required_power_consumption_kw=4.5,
                at_s=0,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=6000.0,
                required_power_consumption_kw=4.5,
                at_s=0,
            ),
            'expect_policy': {
                'control': 'HORIZON_BY_HAEO',
                'goal': 'NET_ZERO',
                'configured_forecast': 'HAEO',
                'effective_forecast': 'HAEO',
                'dominant_limitation': 'OPTIMIZATION_ACTIVE',
                'explanation': 'HAEO net zero plan active',
                'haeo_nz_plan_active': True,
                'surplus_device_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_device_next_target': 'ADJUSTABLE',
                'surplus_device_next_device_id': 'EV_CHARGER',
                'primary_surplus_combo_source': 'HAEO_NET_ZERO_PLAN',
                'haeo_nz_combo_changed': True,
                'haeo_nz_primary_device_id': 'HOME_BATTERY',
                'haeo_nz_adjustable_device_id': 'EV_CHARGER',
                'haeo_nz_device_limits_w': {'HOME_BATTERY': 3000, 'EV_CHARGER': 1500},
                'haeo_nz_battery_limit_w': 3000,
                'haeo_nz_ev_limit_w': 1500,
                'adjustable_primary_load': 'HOME_BATTERY',
                'adjustable_surplus_load': 'EV_CHARGER',
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('EV_CHARGER',),
            },
            'expect_writer_trace': {
                'victron': {'action': 'write'},
                'EV_CHARGER': {
                    'action': 'skip',
                    'reason': 'already_released',
                },
                'RELAY1': {'action': 'skip'},
                'RELAY2': {'action': 'skip'},
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 3000,
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
            },
        },
        {
            'at_s': 30,
            'note': 'next policy cycle: EV adjustable state is active and EV current is capped by HAEO limit',
            'set': runtime_inputs_for_net_zero_intent(
                E,
                rpnz_w=6000.0,
                required_power_consumption_kw=4.5,
                at_s=30,
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=6000.0,
                required_power_consumption_kw=4.5,
                at_s=30,
            ),
            'expect_policy': {
                'control': 'HORIZON_BY_HAEO',
                'goal': 'NET_ZERO',
                'configured_forecast': 'HAEO',
                'effective_forecast': 'HAEO',
                'dominant_limitation': 'OPTIMIZATION_ACTIVE',
                'explanation': 'HAEO net zero plan active',
                'haeo_nz_plan_active': True,
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_next_target': 'NONE',
                'surplus_device_next_device_id': '',
                'primary_surplus_combo_source': 'HAEO_NET_ZERO_PLAN',
                'haeo_nz_combo_changed': False,
                'haeo_nz_primary_device_id': 'HOME_BATTERY',
                'haeo_nz_adjustable_device_id': 'EV_CHARGER',
                'haeo_nz_device_limits_w': {'HOME_BATTERY': 3000, 'EV_CHARGER': 1500},
                'haeo_nz_battery_limit_w': 3000,
                'haeo_nz_ev_limit_w': 1500,
                'adjustable_primary_load': 'HOME_BATTERY',
                'adjustable_surplus_load': 'EV_CHARGER',
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('EV_CHARGER',),
            },
            'expect_writer_trace': {
                'victron': {'action': 'skip'},
                'EV_CHARGER': {
                    'action': 'enable_and_set_current',
                    'policy_current_a': 8,
                    'target_current_a': 8,
                },
                'RELAY1': {'action': 'skip'},
                'RELAY2': {'action': 'skip'},
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 3000,
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 8,
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
            },
        },
        {
            'at_s': 900,
            'note': 'new quarter: HAEO flips priority to EV primary and old adjustable state must be cleared',
            'set': {
                **runtime_inputs_for_net_zero_intent(
                    E,
                    rpnz_w=7000.0,
                    required_power_consumption_kw=6.0,
                    at_s=900,
                ),
                E['battery_heartbeat']: 0.0,
                E['haeo_battery_active_power_fresh_source']: 2.0,
                E['haeo_ev_active_power_fresh_source']: 2.0,
            },
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=7000.0,
                required_power_consumption_kw=6.0,
                at_s=900,
            ),
            'expect_policy': {
                'control': 'HORIZON_BY_HAEO',
                'goal': 'NET_ZERO',
                'configured_forecast': 'HAEO',
                'effective_forecast': 'HAEO',
                'dominant_limitation': 'OPTIMIZATION_ACTIVE',
                'explanation': 'HAEO net zero plan active',
                'haeo_nz_plan_active': True,
                'surplus_device_dispatch_decision': 'CLEAR_ALL',
                'surplus_device_next_target': 'NONE',
                'surplus_device_next_device_id': '',
                'primary_surplus_combo_source': 'HAEO_NET_ZERO_PLAN',
                'haeo_nz_combo_changed': True,
                'haeo_nz_primary_device_id': 'EV_CHARGER',
                'haeo_nz_adjustable_device_id': 'HOME_BATTERY',
                'haeo_nz_device_limits_w': {'HOME_BATTERY': 1000, 'EV_CHARGER': 5000},
                'haeo_nz_battery_limit_w': 1000,
                'haeo_nz_ev_limit_w': 5000,
                'adjustable_primary_load': 'EV_CHARGER',
                'adjustable_surplus_load': 'HOME_BATTERY',
                'surplus_freeze_until_ts': 930.0,
                'surplus_state_clear_reason': 'HAEO_COMBO_CHANGED',
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
        },
    ]

    run_steps(h, steps)
