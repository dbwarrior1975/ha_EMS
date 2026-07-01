import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_TRACE = 'sensor.ems_dispatch_state_applier_trace'


@pytest.mark.unit
def test_dispatch_state_applier_trigger_uses_dispatch_command_sensor(project_root):
    source = (project_root / 'ems_dispatch_state_applier.py').read_text(encoding='utf-8')

    assert "@state_trigger('sensor.ems_surplus_dispatch_command_pyscript')" in source
    assert "@state_trigger('sensor.ems_policy_decision_trace_pyscript')" not in source


@pytest.mark.unit
def test_dispatch_state_applier_prefers_canonical_dispatch_command_over_trace(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['dispatch_command'],
        {
            'dispatch_command_version': '7',
            'surplus_device_dispatch_action': 'ACTIVATE',
            'surplus_device_dispatch_target': 'RELAY1',
            'surplus_device_dispatch_device_id': 'RELAY1',
            'surplus_freeze_until_ts': 60.0,
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'surplus_device_dispatch_action': 'CLEAR_ALL',
            'surplus_device_dispatch_target': '',
            'surplus_device_dispatch_device_id': '',
            'surplus_freeze_until_ts': 30.0,
        },
    )

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ('RELAY1',)
    assert trace['decision'] == 'ACTIVATE_RELAY1'
    assert trace['decision_source'] == 'dispatch_command'
    assert trace['dispatch_source_entity'] == ENT['dispatch_command']
    assert trace['dispatch_source_reason'] == 'canonical'
    assert trace['dispatch_command_version'] == '7'
    assert trace['device_dispatch_action'] == 'ACTIVATE'
    assert trace['device_dispatch_device_id'] == 'RELAY1'
    assert trace['dispatch_state_contract'] == 'device_id_primary'
    assert trace['active_surplus_device_ids'] == ('RELAY1',)
    assert trace['freeze_written'] is True
    assert trace['freeze_until_ts'] == 60.0
    assert trace['writes'] == ['on:RELAY1']


@pytest.mark.unit
def test_dispatch_state_applier_reports_adjustable_active_device_id_from_trace(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['dispatch_command'],
        {
            'dispatch_command_version': '11',
            'surplus_device_dispatch_action': 'ACTIVATE',
            'surplus_device_dispatch_target': 'ADJUSTABLE',
            'surplus_device_dispatch_device_id': 'HOME_BATTERY',
            'surplus_device_targets': (
                {
                    'device_id': 'HOME_BATTERY',
                    'decision_name': 'ADJUSTABLE',
                    'active': False,
                },
            ),
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'surplus_device_dispatch_action': 'ACTIVATE',
            'surplus_device_dispatch_target': 'ADJUSTABLE',
            'surplus_device_dispatch_device_id': 'HOME_BATTERY',
            'surplus_device_targets': (
                {
                    'device_id': 'HOME_BATTERY',
                    'decision_name': 'ADJUSTABLE',
                    'active': False,
                },
            ),
        },
    )

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ('HOME_BATTERY',)
    assert trace['decision'] == 'ACTIVATE_HOME_BATTERY'
    assert trace['device_dispatch_decision_name'] == 'ADJUSTABLE'
    assert trace['device_dispatch_device_id'] == 'HOME_BATTERY'
    assert trace['active_surplus_device_ids'] == ('HOME_BATTERY',)


@pytest.mark.unit
def test_dispatch_state_applier_missing_canonical_dispatch_command_is_noop(project_root):
    harness = QuarterScenarioHarness(project_root)

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ()
    assert trace['decision'] == 'NOOP'
    assert trace['decision_source'] == 'dispatch_command'
    assert trace['dispatch_source_reason'] == 'canonical_missing_or_invalid'
    assert trace['device_dispatch_action'] == 'NOOP'
    assert trace['device_dispatch_device_id'] == ''
    assert trace['writes'] == []


@pytest.mark.unit
def test_dispatch_state_applier_activates_nth_relay_from_device_trace(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['dispatch_command'],
        {
            'dispatch_command_version': '21',
            'surplus_device_dispatch_action': 'ACTIVATE',
            'surplus_device_dispatch_target': 'RELAY3',
            'surplus_device_dispatch_device_id': 'RELAY3',
            'surplus_device_targets': (
                {'device_id': 'RELAY1', 'decision_name': 'RELAY1', 'active': True},
                {'device_id': 'EV_CHARGER', 'decision_name': 'ADJUSTABLE', 'active': True},
                {'device_id': 'RELAY2', 'decision_name': 'RELAY2', 'active': True},
                {'device_id': 'RELAY3', 'decision_name': 'RELAY3', 'active': False},
            ),
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'surplus_device_dispatch_action': 'ACTIVATE',
            'surplus_device_dispatch_target': 'RELAY3',
            'surplus_device_dispatch_device_id': 'RELAY3',
            'surplus_device_targets': (
                {'device_id': 'RELAY1', 'decision_name': 'RELAY1', 'active': True},
                {'device_id': 'EV_CHARGER', 'decision_name': 'ADJUSTABLE', 'active': True},
                {'device_id': 'RELAY2', 'decision_name': 'RELAY2', 'active': True},
                {'device_id': 'RELAY3', 'decision_name': 'RELAY3', 'active': False},
            ),
        },
    )
    harness.set_attrs(ENT['active_surplus_devices'], {'device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2')})

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == (
        'RELAY1',
        'EV_CHARGER',
        'RELAY2',
        'RELAY3',
    )
    assert trace['decision'] == 'ACTIVATE_RELAY3'
    assert trace['device_dispatch_decision_name'] == 'RELAY3'
    assert trace['device_dispatch_device_id'] == 'RELAY3'
    assert trace['active_surplus_device_ids'] == ('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3')
    assert trace['writes'] == ['on:RELAY3']


@pytest.mark.unit
def test_dispatch_state_applier_releases_nth_relay_from_decision_name(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['dispatch_command'],
        {
            'dispatch_command_version': '22',
            'surplus_device_dispatch_action': 'RELEASE',
            'surplus_device_dispatch_target': 'RELAY3',
            'surplus_device_dispatch_device_id': '',
            'surplus_device_targets': (
                {'device_id': 'RELAY1', 'decision_name': 'RELAY1', 'active': True},
                {'device_id': 'EV_CHARGER', 'decision_name': 'ADJUSTABLE', 'active': True},
                {'device_id': 'RELAY2', 'decision_name': 'RELAY2', 'active': True},
                {'device_id': 'RELAY3', 'decision_name': 'RELAY3', 'active': True},
            ),
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'surplus_device_dispatch_action': 'RELEASE',
            'surplus_device_dispatch_target': 'RELAY3',
            'surplus_device_dispatch_device_id': '',
            'surplus_device_targets': (
                {'device_id': 'RELAY1', 'decision_name': 'RELAY1', 'active': True},
                {'device_id': 'EV_CHARGER', 'decision_name': 'ADJUSTABLE', 'active': True},
                {'device_id': 'RELAY2', 'decision_name': 'RELAY2', 'active': True},
                {'device_id': 'RELAY3', 'decision_name': 'RELAY3', 'active': True},
            ),
        },
    )
    harness.set_attrs(
        ENT['active_surplus_devices'],
        {'device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3')},
    )

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == (
        'RELAY1',
        'EV_CHARGER',
        'RELAY2',
    )
    assert trace['decision'] == 'RELEASE_RELAY3'
    assert trace['device_dispatch_decision_name'] == 'RELAY3'
    assert trace['device_dispatch_device_id'] == 'RELAY3'
    assert trace['active_surplus_device_ids'] == ('RELAY1', 'EV_CHARGER', 'RELAY2')
    assert trace['writes'] == ['off:RELAY3']


@pytest.mark.unit
def test_dispatch_state_applier_clear_all_releases_all_active_device_ids(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['dispatch_command'],
        {
            'dispatch_command_version': '23',
            'surplus_device_dispatch_action': 'CLEAR_ALL',
            'surplus_device_dispatch_target': '',
            'surplus_device_dispatch_device_id': '',
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'surplus_device_dispatch_action': 'CLEAR_ALL',
            'surplus_device_dispatch_target': '',
            'surplus_device_dispatch_device_id': '',
        },
    )
    harness.set_attrs(
        ENT['active_surplus_devices'],
        {'device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3')},
    )

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ()
    assert trace['decision'] == 'CLEAR_ALL'
    assert trace['active_surplus_device_ids'] == ()
    assert trace['writes'] == ['off:RELAY1', 'off:EV_CHARGER', 'off:RELAY2', 'off:RELAY3']
