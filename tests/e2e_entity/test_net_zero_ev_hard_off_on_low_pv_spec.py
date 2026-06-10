import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'
WRITER_TRACE = 'sensor.ems_actuator_writer_trace'


@pytest.mark.scenario
def test_net_zero_ev_stays_at_min_first_then_hard_off_when_low_pv_persists_spec(project_root):
    """
    Spec test for desired NET_ZERO EV behaviour when solar production collapses.

    Intended semantics:
    1. EV surplus burn may end normally inside NET_ZERO.
    2. On the next step EV is restored to minimum current instead of turning off
       immediately. This keeps the current anti-flap / quarter-transition behaviour.
    3. If PV stays below a known practical threshold for long enough, EV should be
       hard-disabled because there is no real surplus left even for minimum current.


    Assumptions encoded here:
    1. low PV threshold is represented by a separate external sensor value
    2. threshold example is 1.6 kW
    3. persistence requirement is 2 x 30 s policy cycles ~= 60 s
    4. hard-off is only expected after EV has first gone through the existing
       restore-to-min path

    Harness semantics:
    1. `at_s` is explicit scenario time and should be preferred over implied step order.
    2. Each step may assert policy, dispatch state, and writer-visible state separately.
    3. Decision creation and visible actuator state are intentionally not treated as the same moment.
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    pv_ent = ENT['pv_power_kw']
    pv_threshold_kw = 1.6

    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['control_profile']: 'AUTOMATIC',
        ENT['guard_profile']: 'NORMAL_LIMITS',
        ENT['ev_force_current_a']: 0,
        ENT['ev_min_current_a']: 4,
        ENT['ev_max_current_a']: 28,
        ENT['ev_charger_phases']: 1,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 4,
        pv_ent: 3.5,
        ENT['surplus_freeze_s']: 15,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['adjustable_surplus_load_priority']: 2,
        ENT['relay1_priority']: 3,
        ENT['relay2_priority']: 1,           
    })

    steps = [
        {
            'at_s': 0,
            'note': 't0 enough surplus -> activate relay1 first',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
                pv_ent: 3.5,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'restore_min',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 3.5,
                'ev_hard_off_pv_threshold_kw': pv_threshold_kw,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['actuator_battery_setpoint_w']: 200,
            },
        },
        {
            'at_s': 30,
            'note': 't30 enough surplus -> activate EV next',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 2900,
                pv_ent: 3.2,
            },
            'expect_policy': {
                # This remains the last generated freeze timestamp even after the
                # freeze itself has already expired.
                'surplus_freeze_until_ts': 45.0,            
           
                'surplus_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_explanation': 'Raw RPC 6.000 kW >= ADJUSTABLE threshold 5.520 kW',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'restore_min',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 3.2,
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_ADJUSTABLE',
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: True,
                ENT['actuator_battery_setpoint_w']: 1200,
            },
        },
        {
            'at_s': 46,
            'note': 't46 freeze has expired and EV burn is now visible at max current',
            'set': {
                ENT['required_power_consumption_kw']: 4.5,
                ENT['rpnz_w']: 500,
                pv_ent: 3.0,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 45.0,            
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 3.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'state_changed',
                    'written': True,
                    'target_current_a': 28,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['surplus_adjustable_active']: True,
            },
        },
        {
            'at_s': 60,
            'note': 't60 EV remains stably at max current after the freeze-expiry transition',
            'set': {
                ENT['required_power_consumption_kw']: 4.9,
                ENT['rpnz_w']: 500,
                pv_ent: 3.0,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for RELAY2; raw RPC below threshold',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'burn',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 3.0,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'already_matching',
                    'written': False,
                    'target_current_a': 28,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['surplus_adjustable_active']: True,
            },
        },        
        {
            'at_s': 90,
            'note': 't90 PV drops below threshold and RELEASE_ADJUSTABLE is decided; writer restores EV to minimum',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.4,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'RELEASE_ADJUSTABLE',
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
                'surplus_next_target': 'RELAY2',
                'ev_policy_mode': 'restore_min',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 1.4,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_ADJUSTABLE',
            },

            'expect_writer_trace': {
                'ev': {
                    'reason': 'restore_min_current',
                    'written': True,
                    'target_current_a': 4,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 4,
                ENT['surplus_adjustable_active']: False,
            },
        },
        {
            'at_s': 95,
            'note': 't95 first low-PV cycle after release -> restore min, no hard-off yet',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.1,
                pv_ent: 1.3,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'restore_min',
                'ev_low_pv_cycles': 1,
                'ev_hard_off_active': False,
                'pv_power_kw': 1.3,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'already_released',
                    'written': False,
                    'target_current_a': None,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 4,
                ENT['surplus_adjustable_active']: False,
            },
        },        
        {
            'at_s': 120,
            'note': 't120 second consecutive low-PV cycle below threshold -> hard-off expected',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.1,
                pv_ent: 1.3,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 2,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.3,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'hard_off',
                    'written': True,
                    'target_current_a': 4,
                },
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
                ENT['surplus_adjustable_active']: False,
            },
        },
        {
            'at_s': 180,
            'note': 't180 low PV persists -> EV remains off',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.1,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'RELEASE_RELAY1',
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 3,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.1,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_RELAY1',
            },
            'expect_writer_trace': {
                'relay1': {
                    'reason': 'already_matching',
                    'written': False,
                }
            },
            'expect_values': {
                ENT['relay1']: True,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
            },
        },
        {
            'at_s': 210,
            'note': 't210 PV recovers above threshold, but EV and relays remain off without a new surplus trigger',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'relay1': {
                    'reason': 'state_changed',
                    'written': True,
                }
            },
            'expect_values': {
                ENT['relay1']: False,
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
            },
        }, 

        {
            'at_s': 224,
            'note': 't224 recovered PV and moderate RPC reactivate RELAY1 while EV remains hard-off',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.1,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 239.0,            
                'surplus_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['relay1']: False,
                ENT['surplus_r1_active']: True,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
            },
        }, 
        {
            'at_s': 238,
            'note': 't238 RELAY1 activation is now visible at actuator level while EV remains hard-off',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.1,
                pv_ent: 1.9,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 239.0,               
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 1.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_writer_trace': {
                'relay1': {
                    'reason': 'state_changed',
                    'written': True,
                },
            },
            'expect_values': {
                ENT['relay1']: True,
                ENT['surplus_r1_active']: True,
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
            },
        },
        {
            'at_s': 240,
            'note': 't240 recovered PV and RPC remain below the ADJUSTABLE activation threshold',
            'set': {
                ENT['required_power_consumption_kw']: 4.0,
                ENT['rpnz_w']: 0.15,
                pv_ent: 5.9,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'NOOP',
                'surplus_explanation': 'Waiting for ADJUSTABLE; raw RPC below threshold',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'hard_off',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': True,
                'pv_power_kw': 5.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: False,
                ENT['actuator_ev_current_a']: 4,
            },
        },

        {
            'at_s': 270,
            'note': 't270 recovered PV and RPC cross the ADJUSTABLE threshold so normal EV activation resumes',
            'set': {
                ENT['required_power_consumption_kw']: 5.8,
                ENT['rpnz_w']: 0.19,
                pv_ent: 5.9,
            },
            'expect_policy': {
                'surplus_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_explanation': 'Raw RPC 5.800 kW >= ADJUSTABLE threshold 5.520 kW',
                'surplus_next_target': 'ADJUSTABLE',
                'ev_policy_mode': 'burn',
                'ev_low_pv_cycles': 0,
                'ev_hard_off_active': False,
                'pv_power_kw': 5.9,
            },
            'expect_policy_values': {
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'state_changed',
                    'written': True,
                    'target_current_a': 28,
                },
            },
            'expect_values': {
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 28,
            },
        },        
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} threshold_kw={pv_threshold_kw} "
                f"entity={entity_id} actual={actual} expected={expected}"
            )

        policy_trace = h.getattrs(ENT['policy_decision_trace'])
        dispatch_state_trace = h.getattrs(DISPATCH_STATE_APPLIER_TRACE)

        assert policy_trace['goal'] == 'NET_ZERO'
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
