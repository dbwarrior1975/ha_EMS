import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_no_relays_ev_only.scenario_steps import build_harness
from tests.e2e_entity.net_zero_no_relays_ev_only.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_ev_only_boundary_runs_without_relay_policies(project_root):
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 no relays configured: policy exposes only EV adjustable target and battery policy.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=-10.0, required_power_consumption_kw=0.0, at_s=0),
            'expect_policy': {
                'relay_device_ids': (),
                'surplus_dispatch_action': 'NOOP',
                'surplus_active_device_ids': (),
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 0},
                'EV_CHARGER': {'enabled': False, 'mode': 'restore_min'},
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 0.0,
            },
        },
        {
            'at_s': 30,
            'note': 't30 EV-only path activates adjustable EV target without any relay dispatch branch.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=7.0, at_s=30),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=7.0, at_s=30),
            'expect_policy': {
                'relay_device_ids': (),
                'surplus_dispatch_action': 'ACTIVATE',
                'surplus_dispatch_device_id': 'EV_CHARGER',
                },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 1000},
                'EV_CHARGER': {'enabled': False},
            },
            'expect_values': {
                E['actuator_ev_enabled']: False,
                E['actuator_ev_current_a']: 6,
                E['actuator_battery_setpoint_w']: 1000,
            },
        },
        {
            'at_s': 60,
            'note': 't60 with EV adjustable active the writer enables the charger and relay registry remains empty.',
            'set': runtime_inputs_for_net_zero_intent(E, rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=60),
            'expect_derived': expect_derived_for_net_zero_intent(rpnz_w=500.0, required_power_consumption_kw=3.0, at_s=60),
            'expect_policy': {
                'relay_device_ids': (),
                'surplus_dispatch_action': 'NOOP',
                'surplus_active_device_ids': ('EV_CHARGER',),
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 2000},
                'EV_CHARGER': {'enabled': True, 'mode': 'burn', 'target_w': 6440},
            },
            'expect_values': {
                E['actuator_ev_enabled']: True,
                E['actuator_ev_current_a']: 28,
                E['actuator_battery_setpoint_w']: 2000,
            },
        },
    ]

    run_steps(h, steps)

    policy_trace = h.getattrs(E['policy_diagnostics'])
    writer_trace = h.getattrs('sensor.ems_actuator_writer_trace')
    policy_ids = {item['device_id'] for item in policy_trace['device_policies']}
    writer_ids = set((writer_trace.get('devices') or {}).keys())

    assert policy_trace['relay_device_ids'] == ()
    assert policy_ids == {'HOME_BATTERY', 'EV_CHARGER'}
    assert writer_ids == {'EV_CHARGER'}
