import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_two_ev_one_relay.scenario_steps import build_harness
from tests.e2e_entity.net_zero_two_ev_one_relay.scenario_steps import run_steps


@pytest.mark.scenario
def test_two_evs_arbitrate_by_device_priority_and_receive_independent_policies(project_root):
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 'All three eligible absorb devices start inactive in one strict-priority pool.',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0
            ),
            'expect_policy': {'surplus_device_dispatch_decision': 'NOOP'},
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': False, 'target_w': 0},
            },
        },
        {
            'at_s': 30,
            'note': 'RPC clears the highest-priority EV_GARAGE 4.4 kW threshold first.',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=5000.0, required_power_consumption_kw=5.0, at_s=30
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=5000.0, required_power_consumption_kw=5.0, at_s=30
            ),
            'expect_policy': {
                'surplus_device_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_device_dispatch_device_id': 'EV_GARAGE',
            },
        },
        {
            'at_s': 60,
            'note': 'With EV_GARAGE active, EV_CHARGER is the next candidate at its own 3.6 kW threshold.',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=4000.0, required_power_consumption_kw=4.0, at_s=60
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=4000.0, required_power_consumption_kw=4.0, at_s=60
            ),
            'expect_policy': {
                'surplus_device_dispatch_decision': 'ACTIVATE_EV_CHARGER',
                'surplus_device_dispatch_device_id': 'EV_CHARGER',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': True, 'target_w': 3680},
            },
        },
        {
            'at_s': 90,
            'note': 'Both EVs now own independent max-absorb DevicePolicy outputs; RELAY1 is next.',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=3000.0, required_power_consumption_kw=3.0, at_s=90
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=3000.0, required_power_consumption_kw=3.0, at_s=90
            ),
            'expect_policy': {
                'surplus_device_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_device_dispatch_device_id': 'RELAY1',
                'surplus_device_active_device_stack': 'EV_GARAGE > EV_CHARGER',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True, 'target_w': 6440},
                'EV_GARAGE': {'enabled': True, 'target_w': 3680},
                'RELAY1': {'enabled': False, 'target_w': 0},
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                'switch.ev_garage_enabled': True,
                E['actuator_relay1']: False,
            },
            'expect_writer_trace': {
                'EV_CHARGER': {'action': 'enable_and_set_current', 'target_current_a': 28},
                'EV_GARAGE': {'action': 'enable_and_set_current', 'target_current_a': 16},
            },
        },
        {
            'at_s': 120,
            'note': 'The existing stack semantics retain both EVs while RELAY1 joins the active stack.',
            'set': runtime_inputs_for_net_zero_intent(
                E, rpnz_w=3000.0, required_power_consumption_kw=3.0, at_s=120
            ),
            'expect_derived': expect_derived_for_net_zero_intent(
                rpnz_w=3000.0, required_power_consumption_kw=3.0, at_s=120
            ),
            'expect_policy': {
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_active_device_stack': 'EV_GARAGE > EV_CHARGER > RELAY1',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': True, 'target_w': 6440},
                'EV_GARAGE': {'enabled': True, 'target_w': 3680},
                'RELAY1': {'enabled': True, 'target_w': 2600},
            },
        },
    ]

    run_steps(h, steps)

    attrs = h.getattrs(E['policy_diagnostics'])
    candidates = {item['device_id']: item for item in attrs['surplus_candidates']}
    policies = {item['device_id']: item for item in attrs['device_policies']}

    assert attrs['surplus_candidate_device_ids'] == ('EV_GARAGE', 'EV_CHARGER', 'RELAY1')
    assert candidates['EV_GARAGE']['priority'] == 4
    assert candidates['EV_CHARGER']['priority'] == 3
    assert candidates['RELAY1']['priority'] == 2
    assert candidates['EV_GARAGE']['activation_threshold_w'] == 4400
    assert candidates['EV_CHARGER']['activation_threshold_w'] == 3600
    assert candidates['RELAY1']['activation_threshold_w'] == 2600
    assert candidates['EV_GARAGE']['surplus_dispatch_mode'] == 'max_absorb'
    assert candidates['EV_CHARGER']['surplus_dispatch_mode'] == 'max_absorb'
    assert candidates['RELAY1']['surplus_dispatch_mode'] == 'fixed'
    assert policies['EV_GARAGE']['target_w'] == 3680
    assert policies['EV_CHARGER']['target_w'] == 6440
    assert attrs['surplus_targets_by_device_id']['EV_GARAGE'] == 3680
    assert attrs['surplus_targets_by_device_id']['EV_CHARGER'] == 6440


@pytest.mark.scenario
def test_force_on_is_independent_per_surplus_candidate(project_root):
    h = build_harness(project_root)
    E = h.ent
    h.set_entities({
        E['devices']['EV_GARAGE']['force_on']: True,
        E['devices']['EV_CHARGER']['force_on']: False,
        E['devices']['RELAY1']['force_on']: False,
    })

    run_steps(
        h,
        [
            {
                'at_s': 0,
                'note': 'Only EV_GARAGE carries force-on semantics in the shared candidate pool.',
                'set': runtime_inputs_for_net_zero_intent(
                    E, rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0
                ),
                'expect_derived': expect_derived_for_net_zero_intent(
                    rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0
                ),
            }
        ],
    )

    candidates = {
        item['device_id']: item
        for item in h.getattrs(E['policy_diagnostics'])['surplus_candidates']
    }
    assert candidates['EV_GARAGE']['force_on'] is True
    assert candidates['EV_CHARGER']['force_on'] is False
    assert candidates['RELAY1']['force_on'] is False
