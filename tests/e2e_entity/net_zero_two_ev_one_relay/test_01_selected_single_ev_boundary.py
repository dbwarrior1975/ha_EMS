import pytest

from tests.e2e_entity.net_zero_two_ev_one_relay.scenario_steps import build_harness
from tests.e2e_entity.net_zero_two_ev_one_relay.scenario_steps import run_steps


@pytest.mark.scenario
def test_01_two_ev_boundary_targets_only_selected_ev(project_root):
    h = build_harness(project_root)
    E = h.ent

    steps = [
        {
            'at_s': 0,
            'note': 't0 selected EV is EV_GARAGE and the non-selected EV stays inactive.',
            'set': {
                E['required_power_consumption_kw']: 0.0,
                E['rpnz_w']: -10.0,
                E['grid_power_w']: -20.0,
            },
            'expect_policy': {
                'ev_device_ids': ('EV_CHARGER', 'EV_GARAGE'),
                'selected_ev_device_id': 'EV_GARAGE',
                'surplus_device_dispatch_decision': 'NOOP',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': False, 'target_w': 0},
            },
        },
        {
            'at_s': 30,
            'note': 't30 first adjustable activation already selects EV_GARAGE and keeps EV_CHARGER inactive.',
            'set': {
                E['required_power_consumption_kw']: 3.2,
                E['rpnz_w']: 3200.0,
                E['grid_power_w']: -3200.0,
                E['hourly_energy_balance']: -0.8,
            },
            'expect_policy': {
                'selected_ev_device_id': 'EV_GARAGE',
                'surplus_device_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
                'surplus_device_dispatch_device_id': 'EV_GARAGE',
            },
            'expect_device_policies': {
                'HOME_BATTERY': {'target_w': 1000},
                'EV_CHARGER': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': False, 'target_w': 0},
            },
        },
        {
            'at_s': 60,
            'note': 't60 selected EV_GARAGE is active and the next dispatch edge advances to RELAY1.',
            'set': {
                E['required_power_consumption_kw']: 3.2,
                E['rpnz_w']: 3200.0,
                E['grid_power_w']: -3200.0,
                E['hourly_energy_balance']: -0.8,
            },
            'expect_policy': {
                'selected_ev_device_id': 'EV_GARAGE',
                'surplus_device_dispatch_decision': 'ACTIVATE_RELAY1',
                'surplus_device_dispatch_device_id': 'RELAY1',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': True, 'target_w': 3680},
            },
            'expect_values': {
                'switch.ev_garage_enabled': True,
                'number.ev_garage_current_a': 16,
                E['actuator_ev_enabled']: False,
            },
        },
        {
            'at_s': 90,
            'note': 't90 writer keeps EV_GARAGE active at its max current while RELAY1 joins the active stack.',
            'set': {
                E['required_power_consumption_kw']: 3.2,
                E['rpnz_w']: 3200.0,
                E['grid_power_w']: -3200.0,
                E['hourly_energy_balance']: -0.8,
            },
            'expect_policy': {
                'selected_ev_device_id': 'EV_GARAGE',
                'surplus_device_dispatch_decision': 'NOOP',
                'surplus_device_active_device_stack': 'EV_GARAGE > RELAY1',
            },
            'expect_device_policies': {
                'EV_CHARGER': {'enabled': False, 'target_w': 0},
                'EV_GARAGE': {'enabled': True, 'target_w': 3680},
                'RELAY1': {'enabled': True},
            },
            'expect_values': {
                'switch.ev_garage_enabled': True,
                'number.ev_garage_current_a': 16,
                E['actuator_ev_enabled']: False,
                E['actuator_relay1']: True,
            },
            'expect_writer_trace': {
                'EV_CHARGER': {'action': 'skip', 'current_a': 6},
                'EV_GARAGE': {'action': 'enable_and_set_current', 'target_current_a': 16},
            },
        },
    ]

    run_steps(h, steps)

    policy_trace = h.getattrs(E['policy_decision_trace'])
    writer_trace = h.getattrs('sensor.ems_actuator_writer_trace')
    policy_ids = {item['device_id'] for item in policy_trace['device_policies']}
    writer_ids = set((writer_trace.get('devices') or {}).keys())

    assert policy_trace['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert policy_trace['selected_ev_device_id'] == 'EV_GARAGE'
    assert policy_ids >= {'EV_CHARGER', 'EV_GARAGE', 'HOME_BATTERY', 'RELAY1'}
    assert writer_ids >= {'EV_CHARGER', 'EV_GARAGE', 'RELAY1'}
