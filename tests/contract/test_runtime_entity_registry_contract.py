from copy import deepcopy

import pytest

from ems_adapter.config_loader import load_grouped_ems_config
from ems_adapter.direct_runtime import build_static_topology
from ems_adapter.runtime_context import build_runtime_entities_from_policy_config_packet
from ems_core.domain.constants import CANONICAL_DIAGNOSTICS_OUTPUTS, CANONICAL_POLICY_OUTPUTS


def _topology(project_root, config=None):
    cfg = config or load_grouped_ems_config(project_root / 'EMS_config.yaml')
    return build_static_topology(cfg)


def _packet_registry():
    return {
        'schema_version': 5,
        'entity_registry': {
            'state': {
                'surplus_freeze_until': 'input_datetime.ems_surplus_freeze_until',
                'active_surplus_devices': 'sensor.ems_active_surplus_devices',
            },
            'devices': {
                'HOME_BATTERY': {'target_w': 'number.battery_target'},
                'EV_CHARGER': {'enabled': 'switch.charger_control', 'current_a': 'number.charger_current'},
                'RELAY1': {'enabled': 'switch.relay_1'},
                'RELAY2': {'enabled': 'switch.relay_2'},
            },
        },
    }


@pytest.mark.unit
def test_runtime_entity_registry_exposes_canonical_outputs(project_root):
    entities = build_runtime_entities_from_policy_config_packet(_packet_registry(), _topology(project_root))
    assert entities['device_policies'] == CANONICAL_POLICY_OUTPUTS['device_policies']
    assert entities['dispatch_command'] == CANONICAL_POLICY_OUTPUTS['dispatch_command']
    assert entities['policy_state'] == CANONICAL_POLICY_OUTPUTS['policy_state']
    assert entities['policy_diagnostics'] == CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics']
    assert entities['actuator_writer_trace'] == CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace']
    assert entities['dispatch_state_applier_trace'] == CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace']


@pytest.mark.unit
def test_runtime_entity_registry_is_template_packet_owned_and_device_native(project_root):
    entities = build_runtime_entities_from_policy_config_packet(_packet_registry(), _topology(project_root))
    assert entities['devices']['HOME_BATTERY']['target_w'].startswith('number.')
    assert entities['devices']['EV_CHARGER']['enabled'].startswith('switch.')
    assert entities['devices']['EV_CHARGER']['current_a'].startswith('number.')
    assert entities['devices']['RELAY1']['enabled'].startswith('switch.')
    assert 'actuator_ev_enabled' not in entities
    assert 'actuator_relay1' not in entities
    assert 'deadband_w' not in entities


@pytest.mark.unit
def test_runtime_entity_registry_routes_custom_devices_by_device_id(project_root):
    config = deepcopy(load_grouped_ems_config(project_root / 'EMS_config.yaml'))
    devices = config['ems']['devices']
    devices['EV_GARAGE'] = devices.pop('EV_CHARGER')
    devices['RELAY_SAUNA'] = devices.pop('RELAY1')
    packet = _packet_registry()
    registry_devices = packet['entity_registry']['devices']
    registry_devices['EV_GARAGE'] = registry_devices.pop('EV_CHARGER')
    registry_devices['RELAY_SAUNA'] = registry_devices.pop('RELAY1')

    entities = build_runtime_entities_from_policy_config_packet(packet, _topology(project_root, config))
    assert entities['ev_device_ids'] == ('EV_GARAGE',)
    assert set(entities['relay_device_ids']) == {'RELAY_SAUNA', 'RELAY2'}
    assert entities['devices']['EV_GARAGE']['enabled'] == 'switch.charger_control'
    assert entities['devices']['RELAY_SAUNA']['enabled'] == 'switch.relay_1'


@pytest.mark.unit
def test_runtime_entity_registry_keeps_explicit_empty_device_id_lists(project_root):
    config = deepcopy(load_grouped_ems_config(project_root / 'EMS_config.yaml'))
    config['ems']['devices'] = {
        device_id: device
        for device_id, device in config['ems']['devices'].items()
        if device.get('kind') == 'BATTERY'
    }
    entities = build_runtime_entities_from_policy_config_packet(_packet_registry(), _topology(project_root, config))
    assert entities['relay_device_ids'] == ()
    assert entities['ev_device_ids'] == ()
    assert set(entities['devices']) == {'HOME_BATTERY'}


@pytest.mark.unit
def test_missing_packet_mapping_is_not_filled_from_static_config(project_root):
    packet = _packet_registry()
    del packet['entity_registry']['devices']['EV_CHARGER']['current_a']
    entities = build_runtime_entities_from_policy_config_packet(packet, _topology(project_root))
    assert 'current_a' not in entities['devices']['EV_CHARGER']

@pytest.mark.unit
def test_runtime_packet_static_config_rejects_state_entity_mappings(project_root):
    config = deepcopy(load_grouped_ems_config(project_root / 'EMS_config.yaml'))
    config['ems']['state'] = {
        'surplus_freeze_until': 'input_datetime.should_not_live_here',
    }
    from ems_adapter.config_loader import validate_grouped_ems_config

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert any(issue.path == 'ems.state' for issue in result.errors)


@pytest.mark.unit
def test_runtime_packet_static_config_rejects_device_actuator_mappings(project_root):
    config = deepcopy(load_grouped_ems_config(project_root / 'EMS_config.yaml'))
    config['ems']['devices']['HOME_BATTERY']['adapter'] = {
        'target_w': 'number.should_not_live_here',
    }
    from ems_adapter.config_loader import validate_grouped_ems_config

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert any(issue.path == 'ems.devices.HOME_BATTERY.adapter' for issue in result.errors)


@pytest.mark.unit
def test_read_runtime_entities_reads_only_policy_config_packet(project_root, monkeypatch):
    from ems_adapter.runtime_context import read_runtime_entities

    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'EMS_config.yaml'))
    calls = []
    packet = _packet_registry()

    def _read_attrs(entity_id, default=None):
        calls.append(entity_id)
        return packet if entity_id == 'sensor.ems_policy_config_runtime' else default

    entities = read_runtime_entities(read_attrs=_read_attrs)
    assert calls == ['sensor.ems_policy_config_runtime']
    assert entities['devices']['HOME_BATTERY']['target_w'] == 'number.battery_target'
    assert entities['surplus_freeze_until'] == 'input_datetime.ems_surplus_freeze_until'
