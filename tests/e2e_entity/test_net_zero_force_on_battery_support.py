import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_net_zero_user_forces_relay2_with_freeze_hygiene(project_root):
    """
    Absolute-time NET_ZERO scenario for user-forced RELAY2.

    Scenario intent:
    1. T0/T30 stay below RELAY2 threshold with no surplus activations.
    2. T60 user forces RELAY2 on, which creates a force-triggered surplus freeze.
    3. T74 proves the force freeze still blocks RELAY1 activation just before expiry.
    4. T90 shows RELAY1 activation decision can be created after the force freeze expires.
    5. T120/T150 show RELAY1 visibly on while RELAY2 remains user-forced.
    6. T180/T210 show RPNZ collapse triggers RELAY1 release and the release becomes visible.
    7. T240 removes user force so RELAY2 returns to ordinary surplus eligibility.
    8. T270/T284 show RELAY2 reactivation and the new freeze that blocks RELAY1 again.
    9. T300/T301/T330 show RELAY1 reactivation after that freeze and the resulting stable state.
    """
    h = QuarterScenarioHarness(
        project_root=project_root,
        start_ts=0.0,
        step_s=30,
        cfg_overrides={'surplus_freeze_s': 15},
    )

    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['surplus_freeze_s']: 15,
        ENT['relay2_priority']: 3,
        ENT['relay1_priority']: 2,
        ENT['ev_priority']: 1,
        ENT['relay2_force_on']: False,
        ENT['surplus_r1_active']: False,
        ENT['surplus_r2_active']: False,
        ENT['surplus_ev_active']: False,
        ENT['actuator_relay1']: False,
        ENT['actuator_relay2']: False,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 4,
        ENT['grid_power_w']: 0.0,
        ENT['current_battery_sp']: 0.0,
        ENT['haeo_stale_timeout_s']: 300,
    })

    steps = [
        {
            'at_s': 0,
            'note': 't0 baseline: no surplus loads active and nothing forced',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['surplus_ev_active']: False,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for RELAY2; raw RPC below threshold',
            'expect_next_target': 'RELAY2',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        },
        {
            'at_s': 30,
            'note': 't30 RPC is 3 kW, still below the 5 kW RELAY2 threshold',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['surplus_ev_active']: False,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for RELAY2; raw RPC below threshold',
            'expect_next_target': 'RELAY2',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        },
        {
            'at_s': 60,
            'note': 't60 user forces RELAY2 on and RELAY1 must not react immediately',
            'set': {
                ENT['relay2_force_on']: True,
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
            'expect_freeze_ts': 75.0,
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Freeze active -> wait for measurements to settle',
            'expect_next_target': 'RELAY1',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
            'expect_freeze_entity_present': True,
        },
        {
            'at_s': 74,
            'note': 't74 force freeze is still active and RELAY1 must remain off',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
            'expect_freeze_ts': 75.0,
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Freeze active -> wait for measurements to settle',
            'expect_next_target': 'RELAY1',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
        },
        {
            'at_s': 90,
            'note': 't90 force freeze has expired and RELAY1 activation decision is created',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
            'expect_freeze_ts': 105.0,
            'expect_dispatch_decision': 'ACTIVATE_RELAY1',
            'expect_dispatch_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
            'expect_next_target': 'RELAY1',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
        },
        {
            'at_s': 120,
            'note': 't120 RELAY1 activation is now visible and RELAY2 stays forced on',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for EV; raw RPC below threshold',
            'expect_next_target': 'EV',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
        },
        {
            'at_s': 150,
            'note': 't150 state is stable while RELAY1 and forced RELAY2 stay on',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for EV; raw RPC below threshold',
            'expect_next_target': 'EV',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
        },
        {
            'at_s': 180,
            'note': 't180 RPNZ collapse triggers RELAY1 release decision while RELAY2 stays forced on',
            'set': {
                ENT['required_power_consumption_kw']: -2.0,
                ENT['rpnz_w']: 0.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
            'expect_dispatch_decision': 'RELEASE_RELAY1',
            'expect_dispatch_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            'expect_next_target': 'EV',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
        },

        {
            'at_s': 210,
            'note': 't210 RELAY1 release is now visible while RELAY2 remains user-forced',
            'set': {
                ENT['required_power_consumption_kw']: -2.0,
                ENT['rpnz_w']: -0.005,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for RELAY1; raw RPC below threshold',
            'expect_next_target': 'RELAY1',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
        },
        
        {
            'at_s': 240,
            'note': 't240 user removes RELAY2 force and RELAY2 turns off',
            'set': {
                ENT['relay2_force_on']: False,
                ENT['required_power_consumption_kw']: -3.0,
                ENT['rpnz_w']: -0.015,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for RELAY2; raw RPC below threshold',
            'expect_next_target': 'RELAY2',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        },

        
        {
            'at_s': 270,
            'note': 't270 RPC now triggers RELAY2 through ordinary surplus logic',
            'set': {
                ENT['required_power_consumption_kw']: 8.0,
                ENT['rpnz_w']: 0.015,
                ENT['grid_power_w']: -2500.0,
            },
             'expect_freeze_ts': 285.0,           
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: True,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_dispatch_decision': 'ACTIVATE_RELAY2',
            'expect_dispatch_explanation': 'Raw RPC 8.000 kW >= RELAY2 threshold 5.000 kW',
            'expect_next_target': 'RELAY2',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        },
        {
            'at_s': 284,
            'note': 't284 RELAY2 freeze is still active and prevents RELAY1 activation',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.115,
                ENT['grid_power_w']: -500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_r2_active']: True,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
            'expect_freeze_ts': 285.0,
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Freeze active -> wait for measurements to settle',
            'expect_next_target': 'RELAY1',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        },

        
        {
            'at_s': 300,
            'note': 't300 RELAY2 is on and RELAY1 activation has already reached latch state',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.215,
                ENT['grid_power_w']: -500.0,
            },
            'expect_values': {
                ENT['surplus_r2_active']: True,
                ENT['surplus_r1_active']: True,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
                     
             'expect_freeze_ts': 315.0,            
            'expect_dispatch_decision': 'ACTIVATE_RELAY1',
            'expect_dispatch_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
            'expect_next_target': 'RELAY1',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        },
        {
            'at_s': 301,
            'note': 't301 RELAY1 command is already visible while freeze still blocks further surplus activation',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.215,
                ENT['grid_power_w']: -500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
            'expect_freeze_ts': 315.0,
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Freeze active -> wait for measurements to settle',
            'expect_next_target': 'EV',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        },
        {
            'at_s': 330,
            'note': 't330 RELAY1 activation is now visible and both relays are stably on',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.115,
                ENT['grid_power_w']: 1500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for EV; raw RPC below threshold',
            'expect_next_target': 'EV',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        }        
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} "
                f"actual={actual} expected={expected}"
            )

        if 'expect_freeze_ts' in step:
            decision_trace = h.getattrs(ENT['policy_decision_trace'])
            actual_freeze = decision_trace.get('surplus_freeze_until_ts')
            assert actual_freeze == step['expect_freeze_ts'], (
                f"step={idx} note={step['note']} freeze_until_ts={actual_freeze} expected={step['expect_freeze_ts']}"
            )

        if step.get('expect_freeze_entity_present'):
            freeze_raw = h.get(ENT['surplus_freeze_until'])
            assert freeze_raw not in (None, '', 'unknown', 'unavailable'), (
                f"step={idx} note={step['note']} expected freeze entity to be written"
            )

        if 'expect_dispatch' in step or 'expect_dispatch_decision' in step or 'expect_dispatch_explanation' in step:
            trace = h.getattrs('sensor.ems_surplus_latch_trace')
            decision_trace = h.getattrs(ENT['policy_decision_trace'])

            if 'expect_dispatch_decision' in step:
                assert trace['decision'] == step['expect_dispatch_decision'], (
                    f"step={idx} note={step['note']} decision={trace['decision']} expected={step['expect_dispatch_decision']}"
                )
            elif 'expect_dispatch' in step:
                # Backward-compatible: treat expect_dispatch as decision only.
                assert trace['decision'] == step['expect_dispatch'], (
                    f"step={idx} note={step['note']} decision={trace['decision']} expected={step['expect_dispatch']}"
                )

            if 'expect_dispatch_explanation' in step:
                assert decision_trace['surplus_explanation'] == step['expect_dispatch_explanation'], (
                    f"step={idx} note={step['note']} surplus_explanation={decision_trace['surplus_explanation']} "
                    f"expected={step['expect_dispatch_explanation']}"
                )
            elif 'expect_dispatch' in step:
                # Legacy behavior: expect_dispatch is explanation text.
                assert decision_trace['surplus_explanation'] == step['expect_dispatch'], (
                    f"step={idx} note={step['note']} surplus_explanation={decision_trace['surplus_explanation']} "
                    f"expected={step['expect_dispatch']}"
                )

        policy_trace = h.getattrs(ENT['policy_decision_trace'])
        assert policy_trace['goal'] == 'NET_ZERO'
        assert policy_trace['relay1_command'] == h.get(ENT['policy_relay1_command'])
        assert policy_trace['relay2_command'] == h.get(ENT['policy_relay2_command'])

        if 'expect_next_target' in step:
            assert policy_trace['surplus_next_target'] == step['expect_next_target'], (
                f"step={idx} note={step['note']} surplus_next_target={policy_trace['surplus_next_target']} "
                f"expected={step['expect_next_target']}"
            )

        if 'expect_prev_relay1_force_on' in step:
            assert policy_trace['prev_relay1_force_on'] == step['expect_prev_relay1_force_on'], (
                f"step={idx} note={step['note']} prev_relay1_force_on={policy_trace['prev_relay1_force_on']} "
                f"expected={step['expect_prev_relay1_force_on']}"
            )

        if 'expect_prev_relay2_force_on' in step:
            assert policy_trace['prev_relay2_force_on'] == step['expect_prev_relay2_force_on'], (
                f"step={idx} note={step['note']} prev_relay2_force_on={policy_trace['prev_relay2_force_on']} "
                f"expected={step['expect_prev_relay2_force_on']}"
            )
