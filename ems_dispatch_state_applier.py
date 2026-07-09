from datetime import datetime

from ems_adapter.ha_adapter import get_attr, get_bool, get_float, get_int, get_str, publish_sensor, parse_input_datetime_ts
from ems_core.domain.constants import CANONICAL_DIAGNOSTICS_OUTPUTS


def _load_runtime_entities():
    from ems_adapter.runtime_context import read_runtime_entities
    return read_runtime_entities(get_bool, get_float, get_int, get_str)


def _entity_id(key, entities=None):
    if not isinstance(entities, dict):
        return None
    value = entities.get(key)
    if value in (None, ''):
        return None
    return str(value)


def _set_freeze_until_ts(entity_id, ts):
    if ts in (None, '', 'unknown', 'unavailable'):
        return False

    try:
        target_ts = float(ts)
    except Exception:
        return False

    current_ts = parse_input_datetime_ts(entity_id)
    if current_ts is not None and abs(current_ts - target_ts) < 1.0:
        return False

    dt = datetime.fromtimestamp(target_ts)
    input_datetime.set_datetime(
        entity_id=entity_id,
        date=dt.strftime('%Y-%m-%d'),
        time=dt.strftime('%H:%M:%S'),
    )
    return True


def _parse_active_device_ids(raw_value):
    if raw_value in (None, '', 'unknown', 'unavailable', 'none'):
        return ()
    if isinstance(raw_value, (list, tuple, set)):
        parsed = []
        for item in raw_value:
            text = str(item)
            if text:
                parsed.append(text)
        return tuple(parsed)
    text = str(raw_value).strip()
    if not text:
        return ()
    parsed = []
    for part in text.split(','):
        item = part.strip()
        if item:
            parsed.append(item)
    return tuple(parsed)


def _canonical_active_device_ids(active_ids):
    ordered = []
    seen = set()
    for raw_device_id in active_ids or ():
        device_id = str(raw_device_id or '')
        if not device_id or device_id in seen:
            continue
        seen.add(device_id)
        ordered.append(device_id)
    return tuple(ordered)


def _read_active_surplus_device_ids(entities=None):
    active_entity = _entity_id('active_surplus_devices', entities)
    if not active_entity:
        return ()
    device_ids = get_attr(active_entity, 'device_ids', None)
    parsed = _parse_active_device_ids(device_ids)
    if parsed:
        return parsed
    parsed = _parse_active_device_ids(get_str(active_entity, ''))
    if parsed:
        return parsed
    return ()


def _publish_active_surplus_device_ids(active_device_ids, entities=None):
    normalized = _canonical_active_device_ids(active_device_ids)
    active_entity = _entity_id('active_surplus_devices', entities)
    if not active_entity:
        return None
    publish_sensor(active_entity, ','.join(normalized), {
        'device_ids': normalized,
    })
    return normalized


def _valid_dispatch_action(action):
    return action in ('ACTIVATE', 'RELEASE', 'CLEAR_ALL', 'NOOP')


def _read_dispatch_command(entities=None):
    if entities is None:
        entities = _load_runtime_entities()
    dispatch_entity = _entity_id('dispatch_command', entities)
    if not dispatch_entity:
        return {
            'source_entity': '',
            'source_reason': 'missing_dispatch_command_mapping',
            'version': '',
            'source': 'dispatch_command',
            'action': 'NOOP',
            'device_id': '',
        }
    action = get_attr(dispatch_entity, 'surplus_dispatch_action', '')
    device_id = str(get_attr(dispatch_entity, 'surplus_dispatch_device_id', '') or '')
    version = get_attr(dispatch_entity, 'dispatch_command_version', '')
    if _valid_dispatch_action(action):
        return {
            'source_entity': dispatch_entity,
            'source_reason': 'canonical',
            'version': str(version or ''),
            'source': 'dispatch_command',
            'action': action,
            'device_id': device_id,
        }
    return {
        'source_entity': dispatch_entity,
        'source_reason': 'canonical_missing_or_invalid',
        'version': str(version or ''),
        'source': 'dispatch_command',
        'action': 'NOOP',
        'device_id': '',
    }


def _apply_device_dispatch(action, device_id, entities=None):
    written = []
    active_ids = list(_read_active_surplus_device_ids(entities))
    resolved_device_id = str(device_id or '')

    if action == 'ACTIVATE':
        if resolved_device_id and resolved_device_id not in active_ids:
            written.append(_write_label('on', resolved_device_id))
            active_ids.append(resolved_device_id)

    elif action == 'RELEASE':
        if resolved_device_id in active_ids:
            written.append(_write_label('off', resolved_device_id))
            remaining_active_ids = []
            for active_id in active_ids:
                if active_id != resolved_device_id:
                    remaining_active_ids.append(active_id)
            active_ids = remaining_active_ids

    elif action == 'CLEAR_ALL':
        for active_device_id in active_ids:
            written.append(_write_label('off', active_device_id))
        active_ids = []

    _publish_active_surplus_device_ids(active_ids, entities)
    return written

def _write_label(prefix, device_id):
    return prefix + ':' + str(device_id)


def _active_surplus_device_ids(command, entities=None):
    active = _read_active_surplus_device_ids(entities)
    if active:
        return active
    return ()


@time_trigger('period(now, 30s)')
@state_trigger('sensor.ems_surplus_dispatch_command_pyscript')
def ems_dispatch_state_applier_loop():
    try:
        entities = _load_runtime_entities()
    except Exception as exc:
        publish_sensor(CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace'], 'SUPPRESSED', {
            'dispatch_state_contract': 'device_id_primary',
            'actuator_writes_suppressed': True,
            'error': True,
            'error_code': 'RUNTIME_CONTEXT_INVALID',
            'error_path': getattr(exc, 'path', ''),
            'error_message': str(exc),
            'writes': (),
        })
        return {
            'suppressed': True,
            'error_code': 'RUNTIME_CONTEXT_INVALID',
            'error_path': getattr(exc, 'path', ''),
        }

    missing_mapping_values = []
    for key in ('dispatch_command', 'active_surplus_devices', 'surplus_freeze_until', 'dispatch_state_applier_trace'):
        if not _entity_id(key, entities):
            missing_mapping_values.append(key)
    missing_mappings = tuple(missing_mapping_values)
    if missing_mappings:
        publish_sensor(CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace'], 'SUPPRESSED', {
            'dispatch_state_contract': 'device_id_primary',
            'actuator_writes_suppressed': True,
            'error': True,
            'error_code': 'MISSING_ENTITY_MAPPING',
            'missing_entity_mappings': missing_mappings,
            'writes': (),
        })
        return {
            'suppressed': True,
            'error_code': 'MISSING_ENTITY_MAPPING',
            'missing_entity_mappings': missing_mappings,
        }

    command = _read_dispatch_command(entities)
    freeze_until_ts = get_attr(command['source_entity'], 'surplus_freeze_until_ts', None)
    writes = _apply_device_dispatch(command['action'], command['device_id'], entities)
    freeze_written = _set_freeze_until_ts(_entity_id('surplus_freeze_until', entities), freeze_until_ts)
    active_device_ids = _active_surplus_device_ids(command, entities)

    publish_sensor(_entity_id('dispatch_state_applier_trace', entities), command['action'], {
        'decision_source': command['source'],
        'dispatch_source_entity': command['source_entity'],
        'dispatch_source_reason': command['source_reason'],
        'dispatch_command_version': command['version'],
        'device_dispatch_action': command['action'],
        'device_dispatch_device_id': command['device_id'],
        'dispatch_state_contract': 'device_id_primary',
        'active_surplus_device_ids': active_device_ids,
        'writes': writes,
        'freeze_written': freeze_written,
        'freeze_until_ts': freeze_until_ts,
    })
