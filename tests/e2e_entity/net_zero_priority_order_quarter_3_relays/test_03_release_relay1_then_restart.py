import pytest

from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_03_release_relay1_then_restart(project_root):
    """Phase 3: final RELAY1 release and start of the next activation cycle."""
    h = build_harness(project_root)
    E = h.ent

    # Seed post-adjustable-release state so this phase is independent.
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1',),
        actuator_relay1=True,
        actuator_relay2=False,
        actuator_ev_enabled=True,
        actuator_ev_current_a=6,
    )

    steps = [
        {
            'at_s': 120,
            'note': 't120 RELAY1 becomes the final release decision',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: False,
                E['actuator_ev_current_a']: 8,
            },
        },
        {
            'at_s': 121,
            'note': 't121 release visibility clears and policy idles below RELAY1 threshold',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.1,
            },
            'expect_policy': {
                'surplus_explanation': 'Waiting for RELAY1; raw RPC below threshold',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
            },
        },
        {
            'at_s': 150,
            'note': 't150 next cycle starts and RELAY1 is activated again',
            'set': {
                E['required_power_consumption_kw']: 3.0,
                E['rpnz_w']: 0.1,
            },
            'expect_policy': {
                'surplus_freeze_until_ts': 165.0,
                'surplus_explanation': 'Raw RPC 3.000 kW >= RELAY1 threshold 2.500 kW',
                'surplus_next_target': 'RELAY1',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': False, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
                E['actuator_ev_enabled']: False,
            },
        },
    ]

    run_steps(h, steps)
