import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_net_zero_user_forces_relay2_with_freeze_hygiene(project_root):
    """
    Quarter-step NET_ZERO scenario for user-forced RELAY2.

    Scenario intent:
    1. t0 no surplus latches are active
    2. priorities are RELAY2=3, RELAY1=2, EV=1
    3. t30 RPC rises, but stays below RELAY2 activation threshold so nothing triggers
    4. t60 user forces RELAY2 on; surplus freeze is set and RELAY1 must not react immediately
    5. t90 freeze is still active; RELAY1 remains off
    6. t120 freeze is over; RELAY1 may activate when RPC allows
    7. t150 state remains stable for one step
    8. t180 RPNZ collapse releases RELAY1 while forced RELAY2 stays on
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
            'note': 't30 rpc is 3kw which is still below relay2 threshold 5kw, so nothing triggers',
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
            'note': 't60 user forces relay2 on and relay1 must not react immediately',
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
            'at_s': 90,
            'note': 't90 freeze boundary: relay1 may start activating (forced relay2 stays on)',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_freeze_ts': 105.0,            
            'expect_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: True,
            },
            'expect_dispatch_decision': 'ACTIVATE_RELAY1',
            'expect_dispatch_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
            'expect_next_target': 'RELAY1',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
        },
        {
            'at_s': 120,
            'note': 't120 freeze is over and relay1 can activate with enough rpc',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
            },
             'expect_freeze_ts': 105.0,           
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for EV; raw RPC below threshold',
            'expect_next_target': 'EV',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': True,
        },
        {
            'at_s': 150,
            'note': 't150 state is stable while relay1 and forced relay2 stay on',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 500.0,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
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
            'note': 't180 rpnz collapse wont releases relay1  during freeze time',
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
            'note': 't210 rpnz collapse releases relay1after freeze tie while relay2 remains user-forced',
            'set': {
                ENT['required_power_consumption_kw']: -2.0,
                ENT['rpnz_w']: -0.005,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
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
            'note': 't240 user change relay2 user-forced to disabled and relay2 changes to off',
            'set': {
                ENT['relay2_force_on']: False,
                ENT['required_power_consumption_kw']: -3.0,
                ENT['rpnz_w']: -0.015,
                ENT['grid_power_w']: 2500.0,
            },
            'expect_values': {
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_freeze_ts': 105.0,
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for RELAY2; raw RPC below threshold',
            'expect_next_target': 'RELAY2',
            'expect_prev_relay1_force_on': False,
            'expect_prev_relay2_force_on': False,
        },

        
        {
            'at_s': 270,
            'note': 't270 RPC is now triggering RELAY2',
            'set': {
                ENT['required_power_consumption_kw']: 8.0,
                ENT['rpnz_w']: 0.015,
                ENT['grid_power_w']: -2500.0,
            },
             'expect_freeze_ts': 285.0,           
            'expect_values': {
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
            'at_s': 300,
            'note': 't300 freeze is over and also realy1 is triggered',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.215,
                ENT['grid_power_w']: -500.0,
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_r2_active']: True,
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
            'at_s': 330,
            'note': 't330 relay2 activation is now visible after latch update and freeze time preventes relay1',
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
