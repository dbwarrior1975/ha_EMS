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
            'surplus_dispatch_action': 'ACTIVATE',
            'surplus_dispatch_device_id': 'RELAY1',
            'surplus_freeze_until_ts': 60.0,
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'surplus_dispatch_action': 'CLEAR_ALL',
            'surplus_dispatch_device_id': '',
            'surplus_freeze_until_ts': 30.0,
        },
    )

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ('RELAY1',)
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
def test_dispatch_state_applier_missing_canonical_dispatch_command_is_noop(project_root):
    harness = QuarterScenarioHarness(project_root)

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ()
    assert trace['decision_source'] == 'dispatch_command'
    assert trace['dispatch_source_reason'] == 'canonical_missing_or_invalid'
    assert trace['device_dispatch_action'] == 'NOOP'
    assert trace['device_dispatch_device_id'] == ''
    assert trace['writes'] == []


@pytest.mark.unit
def test_dispatch_state_applier_activates_nth_relay_by_device_id(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['dispatch_command'],
        {
            'dispatch_command_version': '21',
            'surplus_dispatch_action': 'ACTIVATE',
            'surplus_dispatch_device_id': 'RELAY3',
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
    assert trace['device_dispatch_device_id'] == 'RELAY3'
    assert trace['active_surplus_device_ids'] == ('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3')
    assert trace['writes'] == ['on:RELAY3']


@pytest.mark.unit
def test_dispatch_state_applier_releases_nth_relay_by_device_id(project_root):
    harness = QuarterScenarioHarness(project_root)
    harness.set_attrs(
        ENT['dispatch_command'],
        {
            'dispatch_command_version': '22',
            'surplus_dispatch_action': 'RELEASE',
            'surplus_dispatch_device_id': 'RELAY3',
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
            'surplus_dispatch_action': 'CLEAR_ALL',
            'surplus_dispatch_device_id': '',
        },
    )
    harness.set_attrs(
        ENT['active_surplus_devices'],
        {'device_ids': ('RELAY1', 'EV_CHARGER', 'RELAY2', 'RELAY3')},
    )

    harness._run_dispatch_state_applier_loop()

    trace = harness.getattrs(DISPATCH_TRACE)
    assert harness.getattrs(ENT['active_surplus_devices'])['device_ids'] == ()
    assert trace['active_surplus_device_ids'] == ()
    assert trace['writes'] == ['off:RELAY1', 'off:EV_CHARGER', 'off:RELAY2', 'off:RELAY3']



@pytest.mark.unit
def test_dispatch_state_applier_missing_required_mapping_fails_closed(project_root):
    harness = QuarterScenarioHarness(project_root)
    entities = dict(harness.ent)
    entities.pop('active_surplus_devices', None)
    harness.dispatch_state_applier_mod['_load_runtime_entities'] = lambda: entities

    result = harness.dispatch_state_applier_mod['ems_dispatch_state_applier_loop']()

    assert result['suppressed'] is True
    assert result['error_code'] == 'MISSING_ENTITY_MAPPING'
    assert result['missing_entity_mappings'] == ('active_surplus_devices',)
    trace = harness.getattrs(DISPATCH_TRACE)
    assert trace['actuator_writes_suppressed'] is True
    assert trace['writes'] == ()

@pytest.mark.unit
def test_dispatch_state_applier_fails_closed_when_runtime_context_is_invalid(monkeypatch, project_root):
    from ems_adapter import runtime_context

    harness = QuarterScenarioHarness(project_root)
    harness.dispatch_state_applier_mod['ENT'] = {}

    def _raise_context_error(*_args, **_kwargs):
        exc = ValueError('RUNTIME_PACKET_INVALID: measurements.schema_version missing')
        exc.path = 'measurements.schema_version'
        raise exc

    monkeypatch.setattr(runtime_context, 'read_runtime_entities', _raise_context_error)
    harness.dispatch_state_applier_mod['_load_runtime_entities'] = _raise_context_error

    result = harness.dispatch_state_applier_mod['ems_dispatch_state_applier_loop']()

    assert result == {
        'suppressed': True,
        'error_code': 'RUNTIME_CONTEXT_INVALID',
        'error_path': 'measurements.schema_version',
    }
    trace = harness.getattrs(DISPATCH_TRACE)
    assert trace['actuator_writes_suppressed'] is True
    assert trace['error_path'] == 'measurements.schema_version'
    assert trace['writes'] == ()
