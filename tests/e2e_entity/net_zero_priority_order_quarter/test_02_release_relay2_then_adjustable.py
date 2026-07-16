import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import build_harness
from tests.e2e_entity.net_zero_priority_order_quarter.scenario_steps import run_steps
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices


@pytest.mark.scenario
def test_02_release_incremental_steps_then_anchor(project_root):
    """Release newest n-1 steps by excess RPC, then the anchor by RPNZ."""
    h = build_harness(project_root)
    E = h.ent

    seed_active_surplus_devices(
        h,
        active_device_ids=('RELAY1', 'EV_CHARGER', 'RELAY2'),
        actuator_relay1=True,
        actuator_relay2=True,
        actuator_ev_enabled=True,
        actuator_ev_current_a=28,
    )
    h.set_entities({E['surplus_freeze_until']: 75.0})

    steps = [
        {
            'at_s': 76,
            'note': 't76 all active remains stable while RPC still requests consumption',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=450, required_power_consumption_kw=6.0, at_s=76
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=450, required_power_consumption_kw=6.0, at_s=76
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'NOOP',
                'surplus_release_device_id': 'RELAY2',
                'surplus_active_activation_order': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
                'surplus_anchor_device_id': 'RELAY1',
                'surplus_explanation': 'No eligible next surplus target',
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2'),
            },
        },
        {
            'at_s': 90,
            'note': 't90 5 kW excess releases newest 5 kW RELAY2 using the n-1 rule',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=450, required_power_consumption_kw=-5.0, at_s=90
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=450, required_power_consumption_kw=-5.0, at_s=90
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'RELAY2',
                'surplus_release_device_id': 'RELAY2',
                'surplus_release_mode': 'n_minus_one_incremental',
                'surplus_release_power_w': 5000,
                'surplus_release_margin_w': 250,
                'surplus_release_threshold_w': 4750,
                'surplus_excess_consumption_w': 5000,
                'surplus_freeze_until_ts': 105.0,
                'surplus_explanation': (
                    'N-1 excess 5000 W >= RELAY2 release threshold 4750 W '
                    '(5000 W - 250 W margin)'
                ),
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
        },
        {
            'at_s': 91,
            'note': 't91 release settle freeze prevents a second release',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=450, required_power_consumption_kw=-6.2, at_s=91
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=450, required_power_consumption_kw=-6.2, at_s=91
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'NOOP',
                'surplus_freeze_until_ts': 105.0,
                'surplus_explanation': 'Freeze active -> wait for measurements to settle',
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1', 'EV_CHARGER'),
            },
        },
        {
            'at_s': 106,
            'note': 't106 after settle, 6.2 kW excess releases the newest EV step',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=450, required_power_consumption_kw=-6.2, at_s=106
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=450, required_power_consumption_kw=-6.2, at_s=106
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'EV_CHARGER',
                'surplus_release_device_id': 'EV_CHARGER',
                'surplus_release_mode': 'n_minus_one_incremental',
                'surplus_release_power_w': 5060,
                'surplus_release_margin_w': 253,
                'surplus_release_threshold_w': 4807,
                'surplus_excess_consumption_w': 6200,
                'surplus_freeze_until_ts': 121.0,
            },
            'expect_dispatch_state': {
                'active_surplus_device_ids': ('RELAY1',),
            },
        },
        {
            'at_s': 122,
            'note': 't122 the remaining first-activated RELAY1 anchor uses the old RPNZ rule',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=122
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=0.0, required_power_consumption_kw=0.0, at_s=122
            ),
            'expect_policy': {
                'surplus_dispatch_action': 'RELEASE',
                'surplus_dispatch_device_id': 'RELAY1',
                'surplus_release_device_id': 'RELAY1',
                'surplus_release_mode': 'anchor_rpnz_deadband',
                'surplus_explanation': (
                    'RPNZ <= 10 W release deadband -> '
                    'release lowest-priority active target'
                ),
            },
            'expect_dispatch_state': {'active_surplus_device_ids': ()},
        },
    ]

    run_steps(h, steps)
