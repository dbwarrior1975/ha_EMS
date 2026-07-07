import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.custom_device_ids_selected_single_ev.scenario_steps import build_harness
from tests.e2e_entity.custom_device_ids_selected_single_ev.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_custom_device_ids_are_not_runtime_requirements(project_root):
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 custom EV and relay ids load without any fixed device-id dependency.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_policy': {
                'ev_device_ids': ('EV_MAIN', 'EV_GARAGE'),
                'relay_device_ids': ('RELAY_SAUNA', 'RELAY_BOILER'),
                'surplus_dispatch_decision': 'NOOP',
            },
            'expect_device_policies': {
                'EV_MAIN': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': False, 'target_w': 0},
                'RELAY_SAUNA': {'enabled': False},
                'RELAY_BOILER': {'enabled': False},
            },
        },
        {
            'at_s': 30,
            'note': 't30 custom selected EV_GARAGE is chosen immediately while EV_MAIN stays inactive.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=4000.0, required_power_consumption_kw=4.0, at_s=30),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=4000.0, required_power_consumption_kw=4.0, at_s=30),
            'expect_policy': {
                'surplus_dispatch_decision': 'ACTIVATE_EV_GARAGE',
                'surplus_dispatch_device_id': 'EV_GARAGE',
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 1000},
                'EV_MAIN': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': False, 'target_w': 0},
            },
        },
        {
            'at_s': 60,
            'note': 't60 custom selected EV gets the target and the next dispatch edge advances to RELAY_SAUNA.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=4000.0, required_power_consumption_kw=4.0, at_s=60),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=4000.0, required_power_consumption_kw=4.0, at_s=60),
            'expect_policy': {
                'surplus_dispatch_decision': 'ACTIVATE_RELAY_SAUNA',
                'surplus_dispatch_device_id': 'RELAY_SAUNA',
            },
            'expect_device_policies': {
                'EV_MAIN': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': True, 'target_w': 3680},
                'RELAY_SAUNA': {'enabled': False},
                'RELAY_BOILER': {'enabled': False},
            },
            'expect_values': {
                'switch.ev_garage_enabled': True,
                'number.ev_garage_current_a': 16,
                'switch.ev_main_enabled': False,
                'number.ev_main_current_a': 6,
            },
        },
        {
            'at_s': 90,
            'note': 't90 writer uses custom EV ids directly and the next dispatch edge advances to RELAY_BOILER without any RELAY1 or EV_CHARGER dependency.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=4000.0, required_power_consumption_kw=4.0, at_s=90),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=4000.0, required_power_consumption_kw=4.0, at_s=90),
            'expect_policy': {
                'surplus_dispatch_decision': 'ACTIVATE_RELAY_BOILER',
                'surplus_dispatch_device_id': 'RELAY_BOILER',
            },
            'expect_device_policies': {
                'EV_MAIN': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': True, 'target_w': 3680},
                'RELAY_SAUNA': {'enabled': True},
                'RELAY_BOILER': {'enabled': False},
            },
            'expect_values': {
                'switch.ev_garage_enabled': True,
                'number.ev_garage_current_a': 16,
                'switch.ev_main_enabled': False,
                'number.ev_main_current_a': 6,
                'switch.relay_sauna_enabled': True,
            },
            'expect_writer_trace': {
                'EV_MAIN': {'action': 'restore_min_current', 'target_current_a': 6},
                'EV_GARAGE': {'action': 'enable_and_set_current', 'target_current_a': 16},
            },
        },
    ]

    run_steps(h, steps)

    policy_trace = h.getattrs(E['policy_diagnostics'])
    writer_trace = h.getattrs('sensor.ems_actuator_writer_trace')
    policy_ids = {item['device_id'] for item in policy_trace['device_policies']}
    writer_ids = set((writer_trace.get('devices') or {}).keys())

    assert policy_trace['ev_device_ids'] == ('EV_MAIN', 'EV_GARAGE')
    assert policy_trace['relay_device_ids'] == ('RELAY_SAUNA', 'RELAY_BOILER')
    assert 'EV_CHARGER' not in policy_ids
    assert 'RELAY1' not in policy_ids
    assert 'EV_CHARGER' not in writer_ids
    assert 'RELAY1' not in writer_ids
    assert {'EV_MAIN', 'EV_GARAGE', 'RELAY_SAUNA', 'RELAY_BOILER'} <= policy_ids
    assert {'EV_MAIN', 'EV_GARAGE', 'RELAY_SAUNA', 'RELAY_BOILER'} <= writer_ids
