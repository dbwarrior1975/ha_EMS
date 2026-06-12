import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.system_degraded_safe_mode.scenario_steps import build_harness, run_steps


@pytest.mark.scenario
def test_writer_freeze_in_system_degraded(project_root):
    h = build_harness(project_root)
    h.set_entities({
        ENT['surplus_adjustable_active']: True,
        ENT['surplus_r1_active']: True,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 16,
        ENT['actuator_relay1']: True,
    })

    steps = [
        {
            'at_s': 1000,
            'note': 'degraded clears latches and skips relay writes while restoring ev minimum',
            'set': {
                ENT['required_power_consumption_kw']: 4.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'guard': 'DEGRADED',
                'dominant_limitation': 'SYSTEM_DEGRADED',
                'surplus_dispatch_decision': 'CLEAR_ALL',
            },
            'expect_policy_values': {
                ENT['surplus_dispatch_decision_pys']: 'CLEAR_ALL',
                ENT['policy_relay1_command']: -1,
                ENT['policy_relay2_command']: -1,
                ENT['policy_ev_current_a']: 0,
                ENT['policy_battery_target_w']: 0,
            },
            'expect_dispatch_state': {
                'decision': 'CLEAR_ALL',
            },
            'expect_values': {
                ENT['surplus_adjustable_active']: False,
                ENT['surplus_r1_active']: False,
                ENT['actuator_relay1']: True,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 4,
                ENT['actuator_battery_setpoint_w']: 0.0,
            },
            'expect_writer_trace': {
                'ev': {
                    'reason': 'restore_min_current',
                },
                'relay1': {
                    'reason': 'policy_skip',
                },
            },
        },
    ]

    run_steps(h, steps)
