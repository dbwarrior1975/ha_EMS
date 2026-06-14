import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.haeo_02_net_zero_homebattery_primary_ev_adjustable.scenario_steps import (
    build_harness,
    run_steps,
)


@pytest.mark.scenario
def test_haeo_net_zero_internal_plan_homebattery_primary_ev_adjustable(project_root):
    """
    Future EMS-internal HAEO NET_ZERO semantics:
    battery forecast is larger than EV forecast, so HOME_BATTERY becomes
    primary and EV_CHARGER becomes adjustable surplus for this quarter.
    """
    h = build_harness(project_root)

    steps = [
        {
            'at_s': 0,
            'note': 'quarter start: internal HAEO plan selects HOME_BATTERY primary and EV adjustable',
            'set': {
                ENT['required_power_consumption_kw']: 4.5,
                ENT['rpnz_w']: 6000.0,
                ENT['grid_power_w']: 0.0,
            },
            'expect_policy': {
                'control': 'HORIZON_BY_HAEO',
                'goal': 'NET_ZERO',
                'configured_forecast': 'HAEO',
                'effective_forecast': 'HAEO',
                'dominant_limitation': 'OPTIMIZATION_ACTIVE',
                'explanation': 'HAEO net zero plan active',
                'haeo_nz_plan_active': True,
                'primary_surplus_combo_source': 'HAEO_NET_ZERO_PLAN',
                'haeo_nz_combo_changed': True,
                'haeo_nz_primary_load': 'HOME_BATTERY',
                'haeo_nz_adjustable_surplus_load': 'EV_CHARGER',
                'haeo_nz_battery_limit_w': 3000,
                'haeo_nz_ev_limit_w': 1500,
                'haeo_nz_ev_limit_a': 8,
                'adjustable_primary_load': 'HOME_BATTERY',
                'adjustable_surplus_load': 'EV_CHARGER',
                'surplus_policy_active': True,
                'surplus_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'ev_policy_mode': 'restore_min',
            },
            'expect_policy_values': {
                ENT['policy_battery_target_w']: 3000,
                ENT['policy_ev_current_a']: 0,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_ADJUSTABLE',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
                'adjustable_active': True,
                'relay1_active': False,
                'relay2_active': False,
            },
            'expect_writer_trace': {
                'victron.action': 'write',
                'ev.action': 'skip',
                'ev.reason': 'already_released',
                'relay1.action': 'skip',
                'relay2.action': 'skip',
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 3000,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 30,
            'note': 'next policy cycle: EV adjustable state is active and EV current is capped by HAEO limit',
            'set': {
                ENT['required_power_consumption_kw']: 4.5,
                ENT['rpnz_w']: 6000.0,
                ENT['grid_power_w']: 0.0,
            },
            'expect_policy': {
                'control': 'HORIZON_BY_HAEO',
                'goal': 'NET_ZERO',
                'configured_forecast': 'HAEO',
                'effective_forecast': 'HAEO',
                'dominant_limitation': 'OPTIMIZATION_ACTIVE',
                'explanation': 'HAEO net zero plan active',
                'haeo_nz_plan_active': True,
                'primary_surplus_combo_source': 'HAEO_NET_ZERO_PLAN',
                'haeo_nz_combo_changed': False,
                'haeo_nz_primary_load': 'HOME_BATTERY',
                'haeo_nz_adjustable_surplus_load': 'EV_CHARGER',
                'haeo_nz_battery_limit_w': 3000,
                'haeo_nz_ev_limit_w': 1500,
                'haeo_nz_ev_limit_a': 8,
                'adjustable_primary_load': 'HOME_BATTERY',
                'adjustable_surplus_load': 'EV_CHARGER',
                'surplus_policy_active': True,
                'surplus_dispatch_decision': 'NOOP',
                'ev_policy_mode': 'burn',
            },
            'expect_policy_values': {
                ENT['policy_battery_target_w']: 3000,
                ENT['policy_ev_current_a']: 8,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
                'adjustable_active': True,
                'relay1_active': False,
                'relay2_active': False,
            },
            'expect_writer_trace': {
                'victron.action': 'skip',
                'ev.action': 'enable_and_set_current',
                'relay1.action': 'skip',
                'relay2.action': 'skip',
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 3000,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 8,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 900,
            'note': 'new quarter: HAEO flips priority to EV primary and old adjustable state must be cleared',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 7000.0,
                ENT['grid_power_w']: 0.0,
                ENT['battery_heartbeat']: 0.0,
                ENT['haeo_battery_active_power_fresh_source']: 2.0,
                ENT['haeo_ev_active_power_fresh_source']: 2.0,
            },
            'expect_policy': {
                'control': 'HORIZON_BY_HAEO',
                'goal': 'NET_ZERO',
                'configured_forecast': 'HAEO',
                'effective_forecast': 'HAEO',
                'dominant_limitation': 'OPTIMIZATION_ACTIVE',
                'explanation': 'HAEO net zero plan active',
                'haeo_nz_plan_active': True,
                'primary_surplus_combo_source': 'HAEO_NET_ZERO_PLAN',
                'haeo_nz_combo_changed': True,
                'haeo_nz_primary_load': 'EV_CHARGER',
                'haeo_nz_adjustable_surplus_load': 'HOME_BATTERY',
                'haeo_nz_battery_limit_w': 1000,
                'haeo_nz_ev_limit_w': 5000,
                'haeo_nz_ev_limit_a': 20,
                'adjustable_primary_load': 'EV_CHARGER',
                'adjustable_surplus_load': 'HOME_BATTERY',
                'surplus_policy_active': True,
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_freeze_until_ts': 930.0,
                'surplus_state_clear_reason': 'HAEO_COMBO_CHANGED',
                'ev_policy_mode': 'restore_min',
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['surplus_dispatch_decision_pys']: 'CLEAR_ALL',
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
                'adjustable_active': False,
                'relay1_active': False,
                'relay2_active': False,
            },
        },
    ]

    run_steps(h, steps)
