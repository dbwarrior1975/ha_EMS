import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import run_steps
from tests.e2e_entity.refactored_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_02_release_relay2_then_adjustable(project_root):
    """Phase 2: from fully active state, release order begins RELAY2 -> ADJUSTABLE."""
    h = build_harness(project_root)

    # Seed end-of-phase-1 state so this phase is independent.
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1', 'EV_CHARGER', 'RELAY2'),
        actuator_relay1=True,
        actuator_relay2=True,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
    )
    h.set_entities({
        ENT['surplus_freeze_until']: 75.0,
    })

    steps = [
        {
            'at_s': 76,
            'note': 't76 all active remains stable with no eligible next target',
            'set': {
                ENT['required_power_consumption_kw']: 6.0,
                ENT['rpnz_w']: 450,
            },
            'expect_policy': {
                'surplus_device_parity_ok': True,
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_release_candidate': 'RELAY2',
                'surplus_device_release_device_id': 'RELAY2',
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'No eligible next surplus target',
                'surplus_next_target': 'NONE',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'EV_CHARGER': {'current_a': 28, 'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
            },
            'expect_values': {
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
                ENT['actuator_ev_enabled']: True,
            },
        },
        {
            'at_s': 90,
            'note': 't90 surplus collapses so RELAY2 is released first',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_device_parity_ok': True,
                'surplus_device_dispatch_decision': 'RELEASE_RELAY2',
                'surplus_device_release_candidate': 'RELAY2',
                'surplus_device_release_device_id': 'RELAY2',
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'EV_CHARGER': {'current_a': 28, 'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
            'expect_values': {
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: True,
                ENT['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 91,
            'note': 't91 RELAY2 release is visible and ADJUSTABLE gets released next',
            'set': {
                ENT['required_power_consumption_kw']: 0.0,
                ENT['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_device_parity_ok': True,
                'surplus_device_dispatch_decision': 'RELEASE_ADJUSTABLE',
                'surplus_device_release_candidate': 'ADJUSTABLE',
                'surplus_device_release_device_id': 'EV_CHARGER',
                'surplus_explanation': 'RPNZ <= 0 -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'current_a': 0, 'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
            'expect_values': {
                ENT['actuator_relay1']: True,
                ENT['actuator_relay2']: False,
                ENT['actuator_ev_current_a']: 6,
            },
        },
    ]

    run_steps(h, steps)
