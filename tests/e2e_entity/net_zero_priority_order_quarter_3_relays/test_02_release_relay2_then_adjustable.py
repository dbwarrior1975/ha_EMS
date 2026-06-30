import pytest

from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import run_steps
from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import seed_active_surplus_devices

@pytest.mark.scenario
def test_02_release_relay2_then_adjustable(project_root):
    """Phase 2: from fully active state, release order begins RELAY3 -> RELAY2."""
    h = build_harness(project_root)
    E = h.ent
    relay3_enabled = h.dev('RELAY3', 'enabled')

    # Seed end-of-phase-1 state so this phase is independent.
    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3'),
        actuator_relay1=True,
        actuator_relay2=True,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
        relay_states={'RELAY3': True},
    )
    h.set_entities({
        E['surplus_freeze_until']: 75.0,
    })

    steps = [
        {
            'at_s': 76,
            'note': 't76 all four active remain stable with no eligible next target',
            'set': {
                E['required_power_consumption_kw']: 6.0,
                E['rpnz_w']: 450,
            },
            'expect_policy': {
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_release_candidate': 'RELAY3',
                'surplus_device_release_device_id': 'RELAY3',
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'No eligible next surplus target',
                'surplus_next_target': 'NONE',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'RELAY3': {'enabled': True, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                relay3_enabled: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_ev_enabled']: True,
            },
        },
        {
            'at_s': 90,
            'note': 't90 surplus collapses so RELAY3 is released first',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_device_dispatch_decision': 'RELEASE_RELAY3',
                'surplus_device_release_candidate': 'RELAY3',
                'surplus_device_release_device_id': 'RELAY3',
                'surplus_explanation': 'RPNZ <= 10 W release deadband -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'RELAY3': {'enabled': True, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                relay3_enabled: True,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 91,
            'note': 't91 RELAY3 release is visible and RELAY2 gets released next',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_device_dispatch_decision': 'RELEASE_RELAY2',
                'surplus_device_release_candidate': 'RELAY2',
                'surplus_device_release_device_id': 'RELAY2',
                'surplus_explanation': 'RPNZ <= 10 W release deadband -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'RELAY3': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                relay3_enabled: False,
                E['actuator_ev_current_a']: 28,
            },
        },

        {
            'at_s': 92,
            'note': 't92 RELAY2 release is visible and EV_CHARGER gets released next',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_device_dispatch_decision': 'RELEASE_ADJUSTABLE',
                'surplus_device_release_candidate': 'ADJUSTABLE',
                'surplus_device_release_device_id': 'EV_CHARGER',
                'surplus_explanation': 'RPNZ <= 10 W release deadband -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'RELAY3': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: False,
                relay3_enabled: False,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 93,
            'note': 't93 EV charger release is visible and RELAY1 releasing is visible on policy',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: 0.0,
            },
            'expect_policy': {
                'surplus_device_dispatch_decision': 'RELEASE_RELAY1',
                'surplus_device_release_candidate': 'RELAY1',
                'surplus_device_release_device_id': 'RELAY1',
                'surplus_explanation': 'RPNZ <= 10 W release deadband -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'RELAY3': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': False},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: False,
                relay3_enabled: False,
                E['actuator_ev_current_a']: 8,
            },
        },
    ]

    run_steps(h, steps)
