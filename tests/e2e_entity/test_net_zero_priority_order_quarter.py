import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_net_zero_priority_order_one_quarter(project_root):
    """
    Absolute-time NET_ZERO priority story:
    - RELAY1 (priority 3) activates first
    - EV (priority 2) activates second when its threshold is reached
    - RELAY2 (priority 1) activates third
    - when surplus collapses, release order is RELAY2 -> EV -> RELAY1
    - decision, latch visibility, and actuator visibility are separated when useful
    - Then cycle starts over again and Raly 1 activates
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    # Keep EV already enabled so later EV activation is visible on current level
    h.set_entities({
            ENT['surplus_freeze_s']: 15,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 4,
    })

    steps = [
        {
            'at_s': 0,
            'note': 't0 raw RPC crosses RELAY1 threshold so first activation decision targets RELAY1',
            'set': {
                ENT['required_power_consumption_kw']: 3.5,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_freeze_ts': 15.0,
            'expect_dispatch_decision': 'ACTIVATE_RELAY1',
            'expect_dispatch_explanation': 'Raw RPC 3.500 kW >= RELAY1 threshold 2.500 kW',
            'expect_next_target': 'RELAY1',
        },
        {
            'at_s': 30,
            'note': 't30 RELAY1 is visible and EV becomes the next target once its threshold is reached',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_EV',
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
            },
            'expect_freeze_ts': 45.0,
            'expect_dispatch_decision': 'ACTIVATE_EV',
            'expect_dispatch_explanation': 'Raw RPC 6.000 kW >= EV threshold 5.520 kW',
            'expect_next_target': 'EV',
        },
        {
            'at_s': 60,
            'note': 't60 EV burn is visible and RELAY2 becomes eligible as the third activation',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY2',
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 28,
            },
            'expect_freeze_ts': 75.0,
            'expect_dispatch_decision': 'ACTIVATE_RELAY2',
            'expect_dispatch_explanation': 'Raw RPC 6.000 kW >= RELAY2 threshold 5.000 kW',
            'expect_next_target': 'RELAY2',
        },
        {
            'at_s': 61,
            'note': 't61 RELAY2 command is now visible and all three surplus targets are stably active',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 500,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
            },
            'expect_freeze_ts': 75.0,
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Freeze active -> wait for measurements to settle',
            'expect_next_target': 'NONE',
        },

        {
            'at_s': 76,
            'note': 't76 RELAY2 command is now visible and all three surplus targets are stably active',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 450,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: True,
                ENT['surplus_r2_active']: True,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
            },
            'expect_freeze_ts': 75.0,
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'No eligible next surplus target',
            'expect_next_target': 'NONE',
        },
        
        {
            'at_s': 90,
            'note': 't90 surplus collapses so the lowest-priority active target RELAY2 is released first',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY2',
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: True,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 1,
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
            },
            'expect_dispatch_decision': 'RELEASE_RELAY2',
            'expect_dispatch_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
        },
        {
            'at_s': 91,
            'note': 't91 RELAY2 release is now visible while RELAY1 and EV remain active',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_EV',
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 28,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 28,
            },
            'expect_dispatch_decision': 'RELEASE_EV',
            'expect_dispatch_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
        },
        {
            'at_s': 120,
            'note': 't120 EV is no longer active and RELAY1 becomes the final release decision',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'RELEASE_RELAY1',
                ENT['surplus_r1_active']: False,
                ENT['surplus_ev_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 1,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 4,
            },
            'expect_dispatch_decision': 'RELEASE_RELAY1',
            'expect_dispatch_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
        },
        {
            'at_s': 121,
            'note': 't121 RELAY1 release remains the active decision while actuator visibility has not cleared yet',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.1,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'NOOP',
                ENT['surplus_r1_active']: False,
                ENT['surplus_ev_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_dispatch_decision': 'NOOP',
            'expect_dispatch_explanation': 'Waiting for RELAY1; raw RPC below threshold',
        },
        {
            'at_s': 150,
            'note': 't150 RELAY1 actuator release is now visible and the system returns to quiet idle state',
            'set': {
                ENT['required_power_consumption_kw']: 3.0,
                ENT['rpnz_w']: 0.1,
            },
            'expect_values': {
                ENT['surplus_dispatch_decision_pys']: 'ACTIVATE_RELAY1',
                ENT['surplus_r1_active']: True,
                ENT['surplus_ev_active']: False,
                ENT['surplus_r2_active']: False,
                ENT['policy_relay1_command']: 0,
                ENT['policy_relay2_command']: 0,
                ENT['policy_ev_current_a']: 0,
                ENT['actuator_relay1']: False,
                ENT['actuator_relay2']: False,
            },
            'expect_freeze_ts': 165.0,            
            'expect_dispatch_decision': 'ACTIVATE_RELAY1',
            'expect_dispatch_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
            'expect_next_target': 'RELAY1',
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'], at_s=step.get('at_s'))

        for entity_id, expected in step.get('expect_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f'step={idx} note={step["note"]} entity={entity_id} actual={actual} expected={expected}'
            )

        latch_trace = h.getattrs('sensor.ems_surplus_latch_trace')
        policy_trace = h.getattrs(ENT['policy_decision_trace'])

        if 'expect_dispatch_decision' in step:
            assert latch_trace['decision'] == step['expect_dispatch_decision'], (
                f'step={idx} note={step["note"]} decision={latch_trace["decision"]} '
                f'expected={step["expect_dispatch_decision"]}'
            )

        if 'expect_freeze_ts' in step:
            actual_freeze = policy_trace.get('surplus_freeze_until_ts')
            assert actual_freeze == step['expect_freeze_ts'], (
                f'step={idx} note={step["note"]} freeze_until_ts={actual_freeze} '
                f'expected={step["expect_freeze_ts"]}'
            )

        if 'expect_dispatch_explanation' in step:
            assert policy_trace['surplus_explanation'] == step['expect_dispatch_explanation'], (
                f'step={idx} note={step["note"]} surplus_explanation={policy_trace["surplus_explanation"]} '
                f'expected={step["expect_dispatch_explanation"]}'
            )

        if 'expect_next_target' in step:
            assert policy_trace['surplus_next_target'] == step['expect_next_target'], (
                f'step={idx} note={step["note"]} surplus_next_target={policy_trace["surplus_next_target"]} '
                f'expected={step["expect_next_target"]}'
            )

        assert policy_trace['goal'] == 'NET_ZERO'
        assert policy_trace['relay1_command'] == h.get(ENT['policy_relay1_command'])
        assert policy_trace['relay2_command'] == h.get(ENT['policy_relay2_command'])
