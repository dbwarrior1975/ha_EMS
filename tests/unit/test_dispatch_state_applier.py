import pytest

from tests.entity_ids import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


DISPATCH_TRACE = 'sensor.ems_dispatch_state_applier_trace'


@pytest.mark.unit
def test_dispatch_state_applier_uses_device_trace_when_legacy_sensor_conflicts(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['policy_decision_trace'],
        {
            'surplus_device_dispatch_action': 'ACTIVATE',
            'surplus_device_dispatch_target': 'RELAY1',
            'surplus_device_dispatch_device_id': 'RELAY1',
            'surplus_freeze_until_ts': 60.0,
        },
    )

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ('RELAY1',)
    assert trace['decision'] == 'ACTIVATE_RELAY1'
    assert trace['decision_source'] == 'device_trace'
    assert trace['device_dispatch_action'] == 'ACTIVATE'
    assert trace['device_dispatch_device_id'] == 'RELAY1'
    assert trace['dispatch_state_contract'] == 'device_id_primary'
    assert trace['active_surplus_device_ids'] == ('RELAY1',)
    assert trace['freeze_written'] is True
    assert trace['freeze_until_ts'] == 60.0
    assert trace['writes'] == ['relay1_on']


@pytest.mark.unit
def test_dispatch_state_applier_reports_adjustable_active_device_id_from_trace(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['policy_decision_trace'],
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
    assert trace['decision'] == 'ACTIVATE_ADJUSTABLE'
    assert trace['device_dispatch_device_id'] == 'HOME_BATTERY'
    assert trace['active_surplus_device_ids'] == ('HOME_BATTERY',)


@pytest.mark.unit
def test_dispatch_state_applier_noops_without_device_trace(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(ENT['policy_decision_trace'], {})

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ()
    assert trace['decision'] == 'NOOP'
    assert trace['decision_source'] == 'device_trace'
    assert trace['device_dispatch_action'] == 'NOOP'
    assert trace['device_dispatch_device_id'] == ''
    assert trace['writes'] == []


@pytest.mark.unit
def test_dispatch_state_applier_ignores_legacy_sensor_without_device_trace(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_entities(
        {
            ENT['active_surplus_devices']: 'EV_CHARGER',
        }
    )
    harness.set_attrs(ENT['active_surplus_devices'], {'device_ids': ('EV_CHARGER',)})
    harness.set_attrs(ENT['policy_decision_trace'], {})

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ('EV_CHARGER',)
    assert trace['decision'] == 'NOOP'
    assert trace['decision_source'] == 'device_trace'
    assert trace['device_dispatch_action'] == 'NOOP'
    assert trace['device_dispatch_device_id'] == ''
    assert trace['writes'] == []
