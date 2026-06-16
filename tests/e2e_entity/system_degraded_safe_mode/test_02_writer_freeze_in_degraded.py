import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.system_degraded_safe_mode.scenario_steps import build_harness, run_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_writer_freeze_in_system_degraded(project_root):
    h = build_harness(project_root)
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
            'set': {
                ENT['required_power_consumption_kw']: 4.0,
                ENT['rpnz_w']: 500,
            },
            'expect_policy': {
                'guard': 'DEGRADED',
                'dominant_limitation': 'SYSTEM_DEGRADED',
            },
            'expect_values': {
                ENT['actuator_relay1']: True,
                ENT['actuator_ev_enabled']: True,
                ENT['actuator_ev_current_a']: 6,
                ENT['actuator_battery_setpoint_w']: 0.0,
            },
            'expect_writer_trace': {
                'victron': {
                    'reason': 'deadband',
                },
                'ev': {
                    'reason': 'restore_min_current',
                },
                'relay1': {
                    'reason': 'policy_skip',
                },
                'relay2': {
                    'reason': 'policy_skip',
                },
            },
        },
    ]

    run_steps(h, steps)
