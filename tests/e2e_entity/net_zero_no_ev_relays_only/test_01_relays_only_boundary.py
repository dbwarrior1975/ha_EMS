import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_no_ev_relays_only.scenario_steps import build_harness
from tests.e2e_entity.net_zero_no_ev_relays_only.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_relays_only_boundary_runs_without_ev_policy(project_root):
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 no EV configured: policy stays battery-relay only and no surplus device is active yet.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_policy': {
                'ev_device_ids': (),
                'surplus_dispatch_decision': 'NOOP',
                'surplus_active_device_ids': (),
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
                'RELAY1': {'enabled': False},
                'RELAY2': {'enabled': False},
            },
            'expect_values': {
                E['actuator_relay1']: False,
                E['actuator_relay2']: False,
                E['actuator_battery_setpoint_w']: 0.0,
            },
        },
        {
            'at_s': 30,
            'note': 't30 relays-only path first activates HOME_BATTERY adjustable target without creating any EV policy.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=2.6, at_s=30),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=2.6, at_s=30),
            'expect_policy': {
                'ev_device_ids': (),
                'surplus_dispatch_decision': 'ACTIVATE_HOME_BATTERY',
                'surplus_dispatch_device_id': 'HOME_BATTERY',
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 1000},
                'RELAY1': {'enabled': False},
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 60,
            'note': 't60 after battery is active the next dispatch edge can advance to RELAY1 while EV remains absent.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=60),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=60),
            'expect_policy': {
                'ev_device_ids': (),
                'surplus_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_active_device_ids': ('HOME_BATTERY',),
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 2000},
                'RELAY1': {'enabled': False},
            },
            'expect_values': {
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
    ]

    run_steps(h, steps)

    policy_trace = h.getattrs(E['policy_diagnostics'])
    writer_trace = h.getattrs('sensor.ems_actuator_writer_trace')
    policy_ids = {item['device_id'] for item in policy_trace['device_policies']}
    writer_ids = set((writer_trace.get('devices') or {}).keys())

    assert policy_trace['ev_device_ids'] == ()
    assert 'EV_CHARGER' not in policy_ids
    assert 'EV_CHARGER' not in writer_ids
    assert {'RELAY1', 'RELAY2'} <= writer_ids
