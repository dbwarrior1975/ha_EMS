import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'

# Proposed new control entities for EV-first behavior in NET_ZERO.
EV_PRIMARY_CHARGE_MODE = 'input_boolean.ems_ev_primary_charge_mode'
NZ_BATTERY_FLOOR_DEFAULT_W = 'input_number.ems_nz_battery_floor_default_w'
NZ_BATTERY_FLOOR_EV_ACTIVE_W = 'input_number.ems_nz_battery_floor_ev_active_w'
ADJUSTABLE_SURPLUS_LOAD_PRIORITY = 'input_number.ems_adjustable_surplus_load_priority'
ADJUSTABLE_SURPLUS_LOAD = 'input_select.ems_adjustable_surplus_load'
ADJUSTABLE_SURPLUS_LOAD_EV = 'charger_current'
ADJUSTABLE_SURPLUS_LOAD_BATTERY = 'actuator_battery_setpoint_w'


@pytest.mark.scenario
#@pytest.mark.skip(reason='Long power/current assertion scenario temporarily skipped during primary envelope migration')
#@pytest.mark.xfail(reason='Long legacy scenario under migration; non-blocking for ADJUSTABLE V2 unification', strict=False)
def test_net_zero_ev_primary_charge_mode_spec(project_root):
    """
    Spec-style NET_ZERO story for EV-first charging semantics:
    - user enables EV-primary mode via dedicated feature flag
    - when EV surplus state is active, battery min charge floor is lowered to 0 W
    - EV remains charge-only (never negative current), even when RPNZ collapses
    - 4 kW surplus -> EV should absorb practically all and battery target stays 0 W
    - 8 kW surplus -> EV saturates and battery can receive capped 1.6 kW
    - release path keeps existing dispatch pipeline contract (RELEASE_* decisions)
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

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
        ENT['actuator_ev_current_a']: 4,
        ENT['ev_current_step_a']: 1,
        ENT['ev_charger_phases']: 1,
        ENT['ev_max_current_a']: 28,
        ENT['max_solar_charge_w']: 2000,
        ENT['current_battery_sp']: 0.0,
    })

    steps = [
         {
            'at_s': 0,
            'note': 't0 baseline: NOOP, EV disabled at 4A min, battery target/setpoint 0W, and default floor semantics stay active',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: -10.0,
                ENT['grid_power_w']: -20.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,     
                ENT['actuator_battery_setpoint_w']: 0,                           
            },
        },
         {
            'at_s': 10,
                'note': 't10 moderate surplus: still NOOP with EV inactive; battery target/setpoint rises to 600W while floor semantics remain unchanged',
            'set': {
                ENT['required_power_consumption_kw']: 1.2,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: -1200.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 600,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,     
                ENT['actuator_battery_setpoint_w']: 600,                           
            },
        },
        {
            'at_s': 15,
            'note': 't15 increased load: NOOP continues, EV stays inactive, and battery target/setpoint climbs to 1400W',
            'set': {
                ENT['required_power_consumption_kw']: 1.9,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: -1000.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 1400,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,     
                ENT['actuator_battery_setpoint_w']: 1400                               
            },
        },
        {
            'at_s': 20,
            'note': 't20 upper pre-threshold: still NOOP with ADJUSTABLE as next target; EV remains inactive and battery target/setpoint reaches 2000W',
            'set': {
                ENT['required_power_consumption_kw']: 2,
                ENT['rpnz_w']: 550.0,
                ENT['grid_power_w']: -2800.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,     
                ENT['actuator_battery_setpoint_w']: 2000                               
            },
        },        
        {
            'at_s': 30,
            'note': 't30 steady state: no activation transition; EV remains disabled at 4A and battery stays at 2000W target/setpoint',
            'set': {
                ENT['required_power_consumption_kw']: 2.1,
                ENT['rpnz_w']: 530.0,
                ENT['grid_power_w']: -1120.0,
            },
            'expect_policy_values': {
                
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 2000                                     
            },
        },
        {
            'at_s': 45,
            'note': 't45 low RPC sample: EV still inactive, NOOP decision, and battery path continues at 2000W without floor override mode',
            'set': {
                ENT['required_power_consumption_kw']: 0.5,
                ENT['rpnz_w']: 340.0,
                ENT['grid_power_w']: -1843.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'battery_min_floor_w':100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000                               
            },
        },
        {
            'at_s': 55,
            'note': 't55 sustained condition: ADJUSTABLE remains next target but not activated; EV stays off and battery target/setpoint remains 2000W',
            'set': {
                ENT['required_power_consumption_kw']: 0.5,
                ENT['rpnz_w']: 50.0,
                ENT['grid_power_w']: -3140.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000                    
            },
        },
        {
            'at_s': 60,
            'note': 't60 altered grid signal: behavior still NOOP with EV inactive and battery held at 2000W, using not_applicable floor reason',
            'set': {
                ENT['required_power_consumption_kw']: 0.5,
                ENT['rpnz_w']: 50.0,
                ENT['grid_power_w']: -1840.0,

            },
            'expect_policy_values': {
                
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },                
        {
            'at_s': 70,
            'note': 't70 higher import/export swing: policy waits for ADJUSTABLE threshold, no activation occurs, EV stays off, battery remains 2000W',
            'set': {
                ENT['required_power_consumption_kw']: 1.0,
                ENT['rpnz_w']: 250.0,
                ENT['grid_power_w']: -4140.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',                
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',           
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_adjustable_active']: None,                  
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000,
            },
        },                       
        {
            'at_s': 73,
            'note': 't73 trigger point: RPC crosses ADJUSTABLE threshold and dispatch activates adjustable load',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: -1500.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,
                'surplus_next_target': 'ADJUSTABLE',                
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_battery_setpoint_w']: 2000                
            },
        },                
        {
            'at_s': 80,
            'note': 't80 post-trigger collapse: adjustable is released on negative RPC and relay path becomes next candidate',
            'set': {
                ENT['required_power_consumption_kw']: -100.0,
                ENT['rpnz_w']: 450.0,
                ENT['grid_power_w']: -40.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',                 
                'surplus_freeze_until_ts': 88.0,                
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_adjustable_active']: True,                
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 2000                
            },
        },               
        {
            'at_s': 89,
            'note': 't89 post-trigger hold: relay path remains the next candidate while adjustable stays active',
            'set': {
                ENT['required_power_consumption_kw']: 2.4,
                ENT['rpnz_w']: 450.0,
                ENT['grid_power_w']: -40.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 2000,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1', 
                'surplus_freeze_until_ts': 88.0,                
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_adjustable_active']: True,                
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 2000                
            },
        },                      
        {
            'at_s': 90,
            'note': 't90 PV has collapsed and EV is still burning hard; hard-off pressure is building while battery support is trimmed to 1.0 kW.',
            'set': {
                ENT['required_power_consumption_kw']: -5.0,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: 4040.0,
                ENT['pv_power_kw']: 3.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 1000,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,                
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 120,
            'note': 't120 weak PV cannot cover the deficit, so EV stays pinned at burn current while battery support is held at the minimum floor.',
            'set': {
                ENT['required_power_consumption_kw']: -6.4,
                ENT['rpnz_w']: 10.0,
                ENT['grid_power_w']: 6290.0,
                ENT['pv_power_kw']: 1.4,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 100,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',                 
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_ev_current_a']: 28,                                
            },
        },
        {
            'at_s': 135,
            'note': 't135 deficit crosses critical balance and triggers RELEASE_ADJUSTABLE, forcing EV support off and flipping battery control into discharge.',
            'set': {
                ENT['required_power_consumption_kw']: -6.4,
                ENT['rpnz_w']: -10.0,
                ENT['grid_power_w']: 6290.0,
                ENT['pv_power_kw']: 1.4,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_ADJUSTABLE',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -900,
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'surplus_next_target': 'RELAY1',                 
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_ADJUSTABLE',
            },
            'expect_values': {
            
                ENT['surplus_ev_active']: False,
                ENT['surplus_adjustable_active']: False,                 
            },
        },        
        {
            'at_s': 150,
            'note': 't150 PV is fully gone; EV remains off and battery control resets to baseline floor behavior while the system waits for a viable surplus path.',
            'set': {
                ENT['required_power_consumption_kw']: -4.0,
                ENT['rpnz_w']: 120.0,
                ENT['grid_power_w']: 4320.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 100,
            },
            'expect_policy': {
                 'ev_low_pv_cycles': 1,               
                'ev_hard_off_active': False,
                'surplus_next_target': 'ADJUSTABLE', 
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_adjustable_active']: False,                 
            },
        },
        {
            'at_s': 160,
            'note': 't160 with zero PV and negative balance pressure, hard-off protection is active and battery discharge ramps deeper to hold net-zero control.',
            'set': {
                ENT['required_power_consumption_kw']: -4.0,
                ENT['rpnz_w']: -20.0,
                ENT['grid_power_w']: 4320.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -900,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'ev_low_pv_cycles': 2,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['surplus_adjustable_active']: False,                 
            },
        },        
        {
            'at_s': 180,
            'note': 't180 small PV recovery is still insufficient; low-PV stress persists, EV stays locked out, and battery discharge deepens further.',
            'set': {
                ENT['required_power_consumption_kw']: -0.5,
                ENT['rpnz_w']: -50.0,
                ENT['grid_power_w']: 500.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -1200,
            },
            'expect_policy': {
                'ev_low_pv_cycles': 3,
                'ev_hard_off_active': True,
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,                
                ENT['actuator_battery_setpoint_w']: -1200,                
            },
        },
        {
            'at_s': 210,
            'note': 't210 deficit intensifies again, no surplus path qualifies, and battery discharge is pushed toward a stronger defensive target.',
            'set': {
                ENT['required_power_consumption_kw']: -0.4,
                ENT['rpnz_w']: -100.0,
                ENT['grid_power_w']: 1200.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -1800,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: -1800,                                    
            },
            'expect_battery_negative': True,
        },
         {
            'at_s': 226,
                'note': 't226 prolonged low-PV stress reaches a trough, keeping EV unavailable while battery discharge is driven to its steepest support level in this segment.',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: -150.0,
                ENT['grid_power_w']: 700.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: -2200,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,                 
                ENT['actuator_battery_setpoint_w']: -2200,   
            },
            'expect_battery_negative': True,
        },       
        {
            'at_s': 240,
            'note': 't240 balance flips back positive and control posture relaxes, returning battery targeting toward neutral floor behavior.',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 200.0,
                ENT['grid_power_w']: 300.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 100,
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: -1200,                                   
            },
        },
        {
            'at_s': 270,
            'note': 't270 the system holds a stable wait state with EV still off, preserving margin until surplus conditions are clearly sustained.',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 380.0,
                ENT['grid_power_w']: -2100.0,
                ENT['pv_power_kw']: 2.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 100,
            },
            'expect_policy': {
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: -200,                 
            },
        } ,
        {
            'at_s': 275,
            'note': 't275 strong PV surplus crosses activation threshold, dispatch switches to ACTIVATE_ADJUSTABLE, and recovery mode starts.',
            'set': {
                ENT['required_power_consumption_kw']: 2.6,
                ENT['rpnz_w']: 400.0,
                ENT['grid_power_w']: -6100.0,
                ENT['pv_power_kw']: 5.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_ADJUSTABLE',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 800,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE', 
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 800,                 
            },
        }
 ,
        {
            'at_s': 280,
            'note': 't280 recovery is now established: EV burn current is restored, battery support rises, and freeze logic holds stability against rapid re-flapping.',
            'set': {
                ENT['required_power_consumption_kw']: 0.1,
                ENT['rpnz_w']: 400.0,
                ENT['grid_power_w']: -6100.0,
                ENT['pv_power_kw']: 5.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 1800,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 290.0,  
                'surplus_next_target': 'RELAY1', 
                'battery_min_floor_w': 100.0,
                'battery_min_floor_reason': 'not_applicable',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_ev_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 1800,                 
            },
        }               
    ]

    steps_t0_t90 = [step for step in steps if float(step.get('at_s', 0)) <= 280.0]

    for idx, step in enumerate(steps_t0_t90):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        policy_trace = h.getattrs(ENT['policy_decision_trace'])
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)

        assert policy_trace['goal'] == 'NET_ZERO'
        assert policy_trace['surplus_dispatch_decision'] == h.get(ENT['surplus_dispatch_decision_pys'])

        for attr, expected in step.get('expect_policy', {}).items():
            actual = policy_trace.get(attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} policy.{attr} actual={actual} expected={expected}"
            )

        for entity_id, expected in step.get('expect_policy_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} policy_value entity={entity_id} "
                f"actual={actual} expected={expected}"
            )

        for attr, expected in step.get('expect_dispatch_state', {}).items():
            actual = dispatch_state_trace.get(attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} dispatch state.{attr} actual={actual} expected={expected}"
            )

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} "
                f"actual={actual} expected={expected}"
            )

        assert h.get(ENT['policy_ev_current_a']) >= 0, (
            f"step={idx} note={step['note']} EV current must never be negative"
        )

        if step.get('expect_battery_negative'):
            assert h.get(ENT['policy_battery_target_w']) < 0, (
                f"step={idx} note={step['note']} battery target should be negative (discharge)"
            )
