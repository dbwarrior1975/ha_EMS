import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import run_steps
from tests.e2e_entity.net_zero_priority_order_quarter_3_relays.scenario_steps import seed_active_surplus_devices


@pytest.mark.scenario
def test_02_release_incremental_steps_then_anchor(project_root):
    """Four active loads unwind newest-first with one release per settle window."""
    h = build_harness(project_root)
    E = h.ent
    relay3_enabled = h.dev('RELAY3', 'enabled')

    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3'),
        actuator_relay1=True,
        actuator_relay2=True,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
        relay_states={'RELAY3': True},
    )
    h.set_entities({E['surplus_freeze_until']: 75.0})

    steps = [
        {
            'at_s': 76,
            'note': 't76 all four active remain stable',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=450, required_power_consumption_kw=8.0, at_s=76
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=450, required_power_consumption_kw=8.0, at_s=76
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'NOOP',
                'surplus_release_device_id': 'RELAY3',
                'surplus_active_activation_order': (
                    'RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3'
                ),
                'surplus_anchor_device_id': 'RELAY1',
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': (
                    'RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3'
                ),
            },
            'expect_values': {relay3_enabled: True},
        },
        {
            'at_s': 90,
            'note': 't90 7.2 kW excess releases newest 7.5 kW RELAY3',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=450, required_power_consumption_kw=-7.2, at_s=90
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=450, required_power_consumption_kw=-7.2, at_s=90
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'RELAY3',
                'surplus_release_mode': 'n_minus_one_incremental',
                'surplus_release_power_w': 7500,
                'surplus_release_margin_w': 375,
                'surplus_release_threshold_w': 7125,
                'surplus_excess_consumption_w': 7200,
                'surplus_freeze_until_ts': 105.0,
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
            },
        },
        {
            'at_s': 106,
            'note': 't106 after settle, 4.8 kW excess releases RELAY2',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=450, required_power_consumption_kw=-4.8, at_s=106
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=450, required_power_consumption_kw=-4.8, at_s=106
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'RELAY2',
                'surplus_release_power_w': 5000,
                'surplus_release_margin_w': 250,
                'surplus_release_threshold_w': 4750,
                'surplus_freeze_until_ts': 121.0,
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
            'expect_values': {relay3_enabled: False},
        },
        {
            'at_s': 122,
            'note': 't122 after settle, 6.2 kW excess releases EV_CHARGER',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=450, required_power_consumption_kw=-6.2, at_s=122
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=450, required_power_consumption_kw=-6.2, at_s=122
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'EV_CHARGER',
                'surplus_release_power_w': 5060,
                'surplus_release_margin_w': 253,
                'surplus_release_threshold_w': 4807,
                'surplus_freeze_until_ts': 137.0,
            },
            'expect_dispatch_state': {'active_surplus_device_ids': ('RELAY1',)},
        },
        {
            'at_s': 138,
            'note': 't138 the remaining RELAY1 anchor uses the old RPNZ rule',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=138
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=138
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'RELAY1',
                'surplus_release_mode': 'anchor_rpnz_deadband',
            },
            'expect_dispatch_state': {'active_surplus_device_ids': ()},
        },
    ]

    run_steps(h, steps)
