import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'

# Control entities for adjustable-combo behavior in NET_ZERO.
NZ_BATTERY_FLOOR_DEFAULT_W = 'input_number.ems_nz_battery_floor_default_w'
NZ_BATTERY_FLOOR_EV_ACTIVE_W = 'input_number.ems_nz_battery_floor_ev_active_w'
ADJUSTABLE_SURPLUS_LOAD_PRIORITY = 'input_number.ems_adjustable_surplus_load_priority'
ADJUSTABLE_SURPLUS_LOAD = 'input_select.ems_adjustable_surplus_load'
ADJUSTABLE_SURPLUS_LOAD_EV = 'charger_current'
ADJUSTABLE_SURPLUS_LOAD_BATTERY = 'actuator_battery_setpoint_w'


@pytest.mark.scenario
def test_net_zero_adjustable_combo_ev_primary_spec(project_root):
    """
    Spec-style NET_ZERO story for EV-first charging semantics:
    - user sets adjustable combo: surplus=HOME_BATTERY, primary=EV_CHARGER
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
        ENT['adjustable_surplus_load']: 'HOME_BATTERY',
        ENT['adjustable_primary_load']: 'EV_CHARGER',
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
        ENT['max_solar_charge_w']: 2500,
        ENT['current_battery_sp']: 0.0,
        ENT['relay1_power_kw']: 2.3,
        ENT['pv_power_kw']: 1.3        
    })

    steps = [
         {
            'at_s': 0,
            'note': 't0 PV 0.5 kW: no surplus yet; battery target stays 0 W and EV remains at minimum charge current.',
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
                'ev_hard_off_active': False,
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'restore_min',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 4,     
                ENT['actuator_battery_setpoint_w']: 0,                           
            },
        },
         {
            'at_s': 10,
            'note': 't10 PV 1.5 kW: EV ramps up while battery target remains near 0 W (RPC below threshold).',
            'set': {
                ENT['required_power_consumption_kw']: 2.1,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: -2000.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'surplus_primary_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 8,     
                ENT['actuator_battery_setpoint_w']: 0,                           
            },
        },
        {
            'at_s': 15,
            'note': 't15 PV 3.0 kW: EV-first path continues and battery target stays at 0 W.',
            'set': {
                ENT['required_power_consumption_kw']: 2,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: -2200.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 12,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
                'primary_power_envelope_w': 2840,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 12,     
                ENT['actuator_battery_setpoint_w']: 0                               
            },
        },
        {
            'at_s': 20,
            'note': 't20 PV 3.0 kW: EV-first path continues and battery target stays at 0 W.',
            'set': {
                ENT['required_power_consumption_kw']: 2,
                ENT['rpnz_w']: 550.0,
                ENT['grid_power_w']: -2800.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 16,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 16,     
                ENT['actuator_battery_setpoint_w']: 0                               
            },
        },        
        {
            'at_s': 30,
            'note': 't30 PV 2.0 kW: EV remains the primary sink and battery target stays at 0 W.',
            'set': {
                ENT['required_power_consumption_kw']: 2.1,
                ENT['rpnz_w']: 530.0,
                ENT['grid_power_w']: -1120.0,
            },
            'expect_policy_values': {
                
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 19,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': None,
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 19,
                ENT['actuator_battery_setpoint_w']: 0                                     
            },
        },
        {
            'at_s': 45,
            'note': 't45 PV 4.0 kW: EV absorbs available surplus; battery target remains 0 W with floor override active.',
            'set': {
                ENT['required_power_consumption_kw']: 0.1,
                ENT['rpnz_w']: 340.0,
                ENT['grid_power_w']: -1843.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 23,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'battery_min_floor_w':0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 23,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_battery_setpoint_w']: 0                               
            },
        },
        {
            'at_s': 55,
            'note': 't55 PV 6.4 kW: EV keeps consuming surplus; battery target remains at 0 W.',
            'set': {
                ENT['required_power_consumption_kw']: 0.9,
                ENT['rpnz_w']: 50.0,
                ENT['grid_power_w']: -3140.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 27,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 27,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_battery_setpoint_w']: 0                    
            },
        },
        {
            'at_s': 60,
            'note': 't60 PV 6.4 kW: EV current remains high and affects grid power as expected.',
            'set': {
                ENT['required_power_consumption_kw']: 1.5,
                ENT['rpnz_w']: 50.0,
                ENT['grid_power_w']: -1840.0,

            },
            'expect_policy_values': {
                
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_battery_setpoint_w']: 0 
            },
        },                
        {
            'at_s': 70,
            'note': 't70 PV 8.0 kW: EV reaches high current; dispatch still waits for ADJUSTABLE activation.',
            'set': {
                ENT['required_power_consumption_kw']: 1.0,
                ENT['rpnz_w']: 250.0,
                ENT['grid_power_w']: -4140.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_next_target': 'ADJUSTABLE',                
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',           
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: None,                  
                 ENT['actuator_ev_enabled']: True, 
                ENT['actuator_ev_current_a']: 28,
            },
        },                       
        {
            'at_s': 73,
            'note': 't73 PV 8.0 kW: RPC crosses ADJUSTABLE threshold and adjustable path activates.',
            'set': {
                ENT['required_power_consumption_kw']: 2.6,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: -1500.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 88.0,
                'surplus_next_target': 'ADJUSTABLE',                
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
                'surplus_explanation': 'Raw RPC 2.600 kW >= ADJUSTABLE threshold 2.500 kW',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,                  
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 0                
            },
        },                
        {
            'at_s': 80,
            'note': 't80 PV 8.0 kW: after activation, battery setpoint ramps with configured ramp limits.',
            'set': {
                ENT['required_power_consumption_kw']: -100.0,
                ENT['rpnz_w']: 450.0,
                ENT['grid_power_w']: -40.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 2500,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1',                 
                'surplus_freeze_until_ts': 88.0,                
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,                
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 1000                
            },
        },               
        {
            'at_s': 89,
            'note': 't89 PV 10.0 kW: RELAY1 activation occurs while EV remains prioritized.',
            'set': {
                ENT['required_power_consumption_kw']: 2.4,
                ENT['rpnz_w']: 450.0,
                ENT['grid_power_w']: -40.0,

            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_battery_target_w']: 2500,
            },
            'expect_policy': {
                'surplus_next_target': 'RELAY1', 
                'surplus_freeze_until_ts': 104.0,                
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'surplus_explanation': 'Raw RPC 2.400 kW >= RELAY1 threshold 2.300 kW',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,                
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_battery_setpoint_w']: 2000                
            },
        },                      
        {
            'at_s': 90,
            'note': 't90 PV drops to 3kW: EV remains the primary sink and battery target stays at adjustable clamp level',
            'set': {
                ENT['required_power_consumption_kw']: 2.3,
                ENT['rpnz_w']: 100.0,
                ENT['grid_power_w']: 4040.0,
                ENT['pv_power_kw']: 3.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 24,
                ENT['policy_battery_target_w']: 2500,
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_policy_mode': 'burn',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                 ENT['surplus_adjustable_active']: True,                   
                ENT['actuator_ev_current_a']: 24,
                ENT['actuator_battery_setpoint_w']: 2500     
            },
        },
        {
            'at_s': 120,
            'note': 't120 PV 1.7 kW: EV priority remains active while battery charging continues.',
            'set': {
                ENT['required_power_consumption_kw']: -6.4,
                ENT['rpnz_w']: 10.0,
                ENT['grid_power_w']: 5290.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 20,
                ENT['policy_battery_target_w']: 2500,
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,   
                ENT['actuator_ev_current_a']: 20,
                ENT['actuator_battery_setpoint_w']: 2500                
            },
        },
        {
            'at_s': 135,
            'note': 't135 PV 1.7 kW: low RPNZ triggers RELEASE_RELAY1 and adjustable path remains active.',
            'set': {
                ENT['required_power_consumption_kw']: -3.4,
                ENT['rpnz_w']: -10.0,
                ENT['grid_power_w']: 3290.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY1',
                ENT['policy_ev_current_a']: 4,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_policy': {
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_low_pv_cycles': 0,
                'battery_to_ev_loop_risk': 0.0,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                   ENT['actuator_ev_current_a']: 4,    
                ENT['actuator_battery_setpoint_w']: 1500,                          
            },
        },        
        {
            'at_s': 150,
            'note': 't150 PV below threshold: RELEASE_ADJUSTABLE occurs and battery target ramps down per limits.',
            'set': {
                ENT['required_power_consumption_kw']: -4.0,
                ENT['rpnz_w']: -100.0,
                ENT['grid_power_w']: 2320.0,
                ENT['pv_power_kw']: 1.5,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_ADJUSTABLE',
                ENT['policy_ev_current_a']: 4,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'ev_low_pv_cycles': 1,
                'battery_to_ev_loop_risk': False,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: False,
                ENT['actuator_ev_current_a']: 4,
                 ENT['actuator_battery_setpoint_w']: 500,                                  
            },
        },
        {
            'at_s': 160,
            'note': 't160 PV 0.0 kW: EV enters HARD_OFF after low-PV persistence criteria are met.',
            'set': {
                ENT['required_power_consumption_kw']: 0.5,
                ENT['rpnz_w']: -80.0,
                ENT['grid_power_w']: -2020.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
                'ev_low_pv_cycles': 2,
                'battery_to_ev_loop_risk': False,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: False,
                ENT['actuator_battery_setpoint_w']: 500,                                   
            },
        },        
        {
            'at_s': 180,
            'note': 't180 PV 1.0 kW: hold state with EV disabled and battery setpoint held by gate logic.',
            'set': {
                ENT['required_power_consumption_kw']: 0.9,
                ENT['rpnz_w']: -50.0,
                ENT['grid_power_w']: -500.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['surplus_adjustable_active']: False,                
                ENT['actuator_ev_current_a']: 4,                
                ENT['actuator_battery_setpoint_w']: 500,                
            },
        },
        {
            'at_s': 210,
            'note': 't210 PV 1.0 kW with negative RPNZ: remain in hold path while waiting below ADJUSTABLE threshold.',
            'set': {
                ENT['required_power_consumption_kw']: 1.4,
                ENT['rpnz_w']: -40.0,
                ENT['grid_power_w']: -900.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',                
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 500,                                    
            },
        },
         {
            'at_s': 226,
            'note': 't226 PV 1.0 kW with negative RPNZ: EV remains hard-off and battery command stays held.',
            'set': {
                ENT['required_power_consumption_kw']: 1.9,
                ENT['rpnz_w']: -10.0,
                ENT['grid_power_w']: -1200.0,
                ENT['pv_power_kw']: 1.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'battery_min_floor_w': 0.0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,                 
                ENT['actuator_battery_setpoint_w']: 500,   
            },
        },       
        {
            'at_s': 240,
            'note': 't240 post-release: baseline floor semantics continue with hard-off still active.',
            'set': {
                ENT['required_power_consumption_kw']: 1.95,
                ENT['rpnz_w']: -5.0,
                ENT['grid_power_w']: -2300.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 500,
            },
            'expect_policy': {
                'ev_hard_off_active': True,
                'battery_min_floor_w': 0.0,
                'battery_min_floor_reason': 'activation_gate_hold',
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 500,                                   
            },
        },
        {
            'at_s': 270,
            'note': 't270 post-release: controller remains stable with NOOP dispatch.',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 1.0,
                ENT['grid_power_w']: -10.0,
                ENT['pv_power_kw']: 0.0,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_policy': {
                'ev_hard_off_active': True,                
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': None,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {},
        } ,
        {
            'at_s': 275,
            'note': 't275 PV 1.5 kW',
            'set': {
                ENT['required_power_consumption_kw']: 2.49,
                ENT['rpnz_w']: 2501.0,
                ENT['grid_power_w']: -1100.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 104, 
                'ev_hard_off_active': True,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': None,
            },
            'expect_dispatch_state': {
                    'decision': 'NOOP',
             
            },
            'expect_values': {
                  ENT['actuator_battery_setpoint_w']: 0,  
            },
        },

        {
            'at_s': 295,
            'note': 't295 PV 2.5 kW',
            'set': {
                ENT['required_power_consumption_kw']: 2.49,
                ENT['rpnz_w']: 2501,
                ENT['grid_power_w']: -1900.0,
                ENT['pv_power_kw']: 1.7,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_battery_target_w']: 0,
                ENT['policy_ev_current_a']: 8,
            },
            'expect_policy': {
                'ev_hard_off_active': False,
                'battery_min_floor_reason': 'ev_active_floor_override',
                'primary_power_envelope_w': 1920,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
             
            },
            'expect_values': {
                ENT['actuator_battery_setpoint_w']: 0,
            },
        }   
    ]

    for idx, step in enumerate(steps):
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
