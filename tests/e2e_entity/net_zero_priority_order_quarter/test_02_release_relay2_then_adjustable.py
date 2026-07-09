import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

@pytest.mark.scenario
def test_02_release_relay2_then_adjustable(project_root):
    """Phase 2: from fully active state, release order begins RELAY2 -> EV_CHARGER."""
    h = build_harness(project_root)
    E = h.ent

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
        E['surplus_freeze_until']: 75.0,
    })

    steps = [
        {
            'at_s': 76,
            'note': 't76 all active remains stable with no eligible next target',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=450, required_power_consumption_kw=6.0, at_s=76),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=450, required_power_consumption_kw=6.0, at_s=76),
            'expect_policy': {
                'surplus_dispatch_action': 'NOOP',
                'surplus_release_device_id': 'RELAY2',
                'surplus_freeze_until_ts': 75.0,
                'surplus_explanation': 'No eligible next surplus target',
                'surplus_next_device_id': '',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_ev_enabled']: True,
            },
        },
        {
            'at_s': 90,
            'note': 't90 surplus collapses so RELAY2 is released first',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=90),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=90),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'RELAY2',
                'surplus_release_device_id': 'RELAY2',
                'surplus_explanation': 'RPNZ <= 10 W release deadband -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': True, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: True,
                E['actuator_ev_current_a']: 28,
            },
        },
        {
            'at_s': 91,
            'note': 't91 RELAY2 release is visible and EV_CHARGER gets released next',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=91),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=91),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'EV_CHARGER',
                'surplus_release_device_id': 'EV_CHARGER',
                'surplus_explanation': 'RPNZ <= 10 W release deadband -> release lowest-priority active target',
            },
            'expect_device_policies': {
                'RELAY1': {'enabled': True, 'mode': 'relay'},
                'RELAY2': {'enabled': False, 'mode': 'relay'},
                'EV_CHARGER': {'enabled': True},
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
            'expect_values': {
                E['actuator_relay1']: True,
                E['actuator_relay2']: False,
                E['actuator_ev_current_a']: 28,
            },
        },

        {
            'at_s': 92,
            'note': 't92 EV charger release is visible and RELAY1 releasing is visible on policy',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=92),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=92),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'RELAY1',
                'surplus_release_device_id': 'RELAY1',
                'surplus_explanation': 'RPNZ <= 10 W release deadband -> release lowest-priority active target',
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
    ]

    run_steps(h, steps)
