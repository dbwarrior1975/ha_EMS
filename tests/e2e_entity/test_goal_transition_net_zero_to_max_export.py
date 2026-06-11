import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'
WRITER_TRACE = 'sensor.ems_actuator_writer_trace'


@pytest.mark.scenario
def test_goal_transition_net_zero_ev_burn_to_max_export_hard_off_and_clear_latches(project_root):
    """
    Scenario: NET_ZERO surplus EV burn is active, then goal changes to MAX_EXPORT.

    Current expected semantics:
    - NET_ZERO surplus policy becomes inactive when goal != NET_ZERO
    - surplus dispatch state loop clears active surplus states
    - MAX_EXPORT EV policy is 0 A with hard-off semantics
    - EV charger is disabled if it was already enabled
    - EV current selector is restored to hardware minimum while charger is off
    - relay actuators are released/off

    Harness semantics:
    1. `at_s` is explicit scenario time and should be preferred over implied step order.
    2. Each step may assert policy, dispatch state, and writer-visible state separately.
    3. Decision creation and visible actuator state are intentionally not treated as the same moment.
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    # EV starts already enabled so the transition can prove hard-off behaviour.
    h.set_entities({
        ENT['max_battery_discharge_w']: -4000,
        ENT['ramp_max_w']: 1000,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',        
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 4,
        ENT['ev_min_current_a']: 4,
        ENT['ev_max_current_a']: 28,
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
    })

    steps = [
        {
            'at_s': 0,
            'note': 't0 NET_ZERO activates relay1 first',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'restore_min',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
            },
        },
        {
            'at_s': 30,
            'note': 't30 NET_ZERO activates EV next',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_explanation': 'Raw RPC 6.000 kW >= ADJUSTABLE threshold 5.520 kW',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'restore_min',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_ADJUSTABLE',
                ENT['policy_relay1_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_relay1']: True,
            },
        },

        {
            'at_s': 44,
            'note': 't44 EV burn is already visible at max current while the activation freeze still blocks further surplus changes',
            'set': {
                ENT['required_power_consumption_kw']: 2.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_relay1_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'state_changed',
                    'written': True,
                },
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_relay1']: True,
            },
        },        
        {
            'at_s': 60,
            'note': 't60 EV burn is active at max current',
            'set': {
                ENT['required_power_consumption_kw']: 1.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'NET_ZERO',
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
                ENT['policy_relay1_command']: 1,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['surplus_adjustable_active']: True,
            },
        },
        {
            'at_s': 90,
            'note': 't90 goal changes to MAX_EXPORT; surplus states clear and EV drops to 0 current',
            'set': {
                ENT['goal_profile']: 'MAX_EXPORT',
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'CLEAR_ALL',
                ENT['policy_ev_current_a']: 28,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'already_matching',
                    'written': False,
                    'target_current_a': 28,
                },
                'relay1': {
                    'reason': 'state_changed',
                    'written': True,
                },
                'relay2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_battery_setpoint_w']: -200,  
            },
        },
        {
            'at_s': 120,
            'note': 't120 MAX_EXPORT remains stable: EV stays off and dispatch states remain clear',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'hard_off',
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'hard_off',
                    'written': True,
                    'target_current_a': 4,
                },
                'relay1': {
                    'reason': 'already_matching',
                    'written': False,
                },
                'relay2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_battery_setpoint_w']: -1200,  
            },
        },
        {
            'at_s': 150,
            'note': 't150 MAX_EXPORT remains stable: EV stays off and dispatch states remain clear',
            'set': {
                ENT['required_power_consumption_kw']: 7.0,
                ENT['rpnz_w']: 1000.0,
            },
            'expect_policy': {
                'goal': 'MAX_EXPORT',
                'surplus_dispatch_decision': 'CLEAR_ALL',
                'surplus_explanation': 'Policy inactive -> clear all surplus states',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'hard_off',
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'hard_off',
                    'written': False,
                    'target_current_a': 4,
                },
                'relay1': {
                    'reason': 'already_matching',
                    'written': False,
                },
                'relay2': {
                    'reason': 'already_matching',
                    'written': False,
                },
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_battery_setpoint_w']: -2200,  
            },
        },       
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        policy_trace = h.getattrs(ENT['policy_decision_trace'])
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)

        assert policy_trace['relay1_command'] == h.get(ENT['policy_relay1_command'])
        assert policy_trace['relay2_command'] == h.get(ENT['policy_relay2_command'])

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

        if step.get('expect_writer_trace'):
            assert h.get(WRITER_TRACE) == 'ACTIVE', (
                f"step={idx} note={step['note']} expected writer trace entity to be ACTIVE"
            )
            writer_trace = h.getattrs(WRITER_TRACE)
            for branch, expected_fields in step['expect_writer_trace'].items():
                actual_branch = writer_trace[branch]
                for field, expected in expected_fields.items():
                    actual = actual_branch.get(field)
                    assert actual == expected, (
                        f"step={idx} note={step['note']} writer.{branch}.{field} "
                        f"actual={actual} expected={expected}"
                    )

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} "
                f"actual={actual} expected={expected}"
            )
