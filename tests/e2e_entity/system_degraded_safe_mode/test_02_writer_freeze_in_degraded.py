import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.system_degraded_safe_mode.scenario_steps import build_harness, run_steps
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_writer_freeze_in_system_degraded(project_root):
    h = build_harness(project_root)
    E = h.ent
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1', 'EV_CHARGER'),
        actuator_relay1=True,
        actuator_ev_enabled=True,
        actuator_ev_current_a=16,
    )

    steps = [
        {
            'at_s': 1000,
            'note': 'degraded clears latches and skips relay writes while restoring ev minimum',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500, required_power_consumption_kw=4.0, at_s=1000),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500, required_power_consumption_kw=4.0, at_s=1000),
            'expect_policy': {
                'guard': 'DEGRADED',
                'dominant_limitation': 'SYSTEM_DEGRADED',
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 8,
                E['actuator_battery_setpoint_w']: 0.0,
            },
            'expect_writer_trace': {
                'victron': {
                    'reason': 'deadband',
                },
                'EV_CHARGER': {
                    'reason': 'restore_min',
                },
                'RELAY1': {
                    'reason': 'policy_skip',
                },
                'RELAY2': {
                    'reason': 'policy_skip',
                },
            },
        },
    ]

    run_steps(h, steps)
