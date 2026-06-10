import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_STATE_APPLIER_TRACE = 'sensor.ems_dispatch_state_applier_trace'
WRITER_TRACE = 'sensor.ems_actuator_writer_trace'


@pytest.mark.scenario
def test_net_zero_priority_order_one_quarter(project_root):
    """
    Absolute-time NET_ZERO priority story:
    - RELAY1 (priority 3) activates first
    - EV (priority 2) activates second when its threshold is reached
    - RELAY2 (priority 1) activates third
    - when surplus collapses, release order is RELAY2 -> EV -> RELAY1
    - decision, dispatch state visibility, and actuator visibility are separated when useful
    - Then cycle starts over again and Relay 1 activates
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    # Start EV disabled; ADJUSTABLE activation should make EV burn visible via current.
    h.set_entities({
        ENT['surplus_freeze_s']: 15,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['adjustable_primary_load']: 'HOME_BATTERY',
        ENT['adjustable_surplus_load_priority']: 2,
        ENT['surplus_adjustable_active']: False,
        ENT['actuator_ev_enabled']: False,
        ENT['actuator_ev_current_a']: 4,
        ENT['ev_max_current_a']: 28,
         ENT['relay1_priority']: 3,
        ENT['relay2_priority']: 1,
        ENT['relay1_surplus_allowed']: True,
        ENT['relay2_surplus_allowed']: True,
               
    })

    steps = [
        {
            'at_s': 0,
            'note': 't0 raw RPC crosses RELAY1 threshold so first activation decision targets RELAY1',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 15.0,
                'surplus_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
                
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_enabled']: False,
            },
        },
        {
            'at_s': 30,
            'note': 't30 RELAY1 is visible and EV becomes the next target once its threshold is reached',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 45.0,
                'surplus_explanation': 'Raw RPC 6.000 kW >= ADJUSTABLE threshold 5.520 kW',
                'surplus_next_target': 'ADJUSTABLE',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_ADJUSTABLE',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 60,
            'note': 't60 EV burn is visible and RELAY2 becomes eligible as the third activation',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Raw RPC 6.000 kW >= RELAY2 threshold 5.000 kW',
                'surplus_next_target': 'RELAY2',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY2',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY2',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 61,
            'note': 't61 RELAY2 command is now visible and all three surplus targets are stably active',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
                'surplus_next_target': 'NONE',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
            },
        },

        {
            'at_s': 76,
            'note': 't76 RELAY2 command is now visible and all three surplus targets are stably active',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 450,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'No eligible next surplus target',
                'surplus_next_target': 'NONE',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_ev_enabled']: True,
            },
        },
        
        {
            'at_s': 90,
            'note': 't90 surplus collapses so the lowest-priority active target RELAY2 is released first',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY2',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['policy_ev_current_a']: 28,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_RELAY2',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 91,
            'note': 't91 RELAY2 release is now visible while RELAY1 remains active and ADJUSTABLE gets released',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_ADJUSTABLE',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_ADJUSTABLE',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 4,
            },
        },
        {
            'at_s': 120,
            'note': 't120 EV is no longer active and RELAY1 becomes the final release decision',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY1',
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'RELEASE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 4,
            },
        },
        {
            'at_s': 121,
            'note': 't121 RELAY1 release remains the active decision while actuator visibility has not cleared yet',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.1,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'NOOP',
            },
            'expect_values': {
                ENT['surplus_r1_active']: False,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
        },
        {
            'at_s': 150,
            'note': 't150 RELAY1 release is visible and the next cycle starts by activating RELAY1 again',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.1,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 165.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'ACTIVATE_RELAY1',
            },
            'expect_values': {
                ENT['surplus_r1_active']: True,
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_enabled']: True,                
            },
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

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

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} entity={entity_id} "
                f"actual={actual} expected={expected}"
            )
