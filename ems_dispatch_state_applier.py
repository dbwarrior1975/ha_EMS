from datetime import datetime

from ems_adapter.ha_adapter import get_attr, get_bool, get_float, get_int, get_str, publish_sensor, parse_input_datetime_ts


def _load_runtime_entities():
    ent = globals().get('ENT', {})
    if ent:
        return dict(ent)
    from ems_adapter.runtime_context import read_runtime_entities

    return read_runtime_entities(get_bool, get_float, get_int, get_str)


def _entity_id(key, fallback, entities=None):
    if entities is not None and key in entities:
        return entities[key]
    ent = globals().get('ENT', {})
    return ent.get(key, fallback)


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


def _read_surplus_device_targets(entities=None):
    trace_entity = _entity_id('policy_decision_trace', 'sensor.ems_policy_decision_trace_pyscript', entities)
    targets = get_attr(trace_entity, 'surplus_device_targets', []) or []
    if isinstance(targets, (list, tuple)):
        parsed = []
        for target in targets:
            if isinstance(target, dict):
                parsed.append(target)
        return tuple(parsed)
    return ()


def _target_device_id_for_decision_name(decision_name, targets):
    target_name = str(decision_name or '')
    if not target_name:
        return ''
    for target in targets or ():
        if str(target.get('decision_name') or '') == target_name:
            return str(target.get('device_id') or '')
    return ''


def _target_decision_name_for_device_id(device_id, targets):
    resolved_device_id = str(device_id or '')
    if not resolved_device_id:
        return ''
    for target in targets or ():
        if str(target.get('device_id') or '') == resolved_device_id:
            return str(target.get('decision_name') or '')
    return ''


def _read_active_surplus_device_ids(entities=None):
    active_entity = _entity_id('active_surplus_devices', 'sensor.ems_active_surplus_devices', entities)
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
    publish_sensor(_entity_id('active_surplus_devices', 'sensor.ems_active_surplus_devices', entities), ','.join(normalized), {
        'device_ids': normalized,
    })
    return normalized


def _valid_dispatch_action(action):
    return action in ('ACTIVATE', 'RELEASE', 'CLEAR_ALL', 'NOOP')


def _decision_text_from_device_command(action, device_id, target=''):
    if action == 'CLEAR_ALL':
        return 'CLEAR_ALL'
    if action == 'NOOP':
        return 'NOOP'
    if action in ('ACTIVATE', 'RELEASE') and device_id:
        return action + '_' + str(device_id)
    if action in ('ACTIVATE', 'RELEASE') and target:
        return action + '_' + str(target)
    return 'NOOP'


def _read_dispatch_command():
    entities = _load_runtime_entities()
    trace_entity = _entity_id('policy_decision_trace', 'sensor.ems_policy_decision_trace_pyscript', entities)
    action = get_attr(trace_entity, 'surplus_device_dispatch_action', '')
    target = get_attr(trace_entity, 'surplus_device_dispatch_target', '')
    device_id = get_attr(trace_entity, 'surplus_device_dispatch_device_id', '')
    targets = _read_surplus_device_targets(entities)
    resolved_device_id = str(device_id or _target_device_id_for_decision_name(target, targets) or '')
    decision_name = _target_decision_name_for_device_id(resolved_device_id, targets) or str(target or '')

    if _valid_dispatch_action(action):
        return {
            'source': 'device_trace',
            'action': action,
            'target': target,
            'device_id': resolved_device_id,
            'decision_name': decision_name,
            'decision': _decision_text_from_device_command(action, resolved_device_id, target),
        }

    return {
        'source': 'device_trace',
        'action': 'NOOP',
        'target': '',
        'device_id': '',
        'decision_name': '',
        'decision': 'NOOP',
    }


def _apply_device_dispatch(action, target, device_id, entities=None):
    written = []
    active_ids = list(_read_active_surplus_device_ids(entities))
    targets = _read_surplus_device_targets(entities)
    resolved_device_id = str(device_id or _target_device_id_for_decision_name(target, targets) or '')

    if action == 'ACTIVATE':
        if resolved_device_id and resolved_device_id not in active_ids:
            written.append(_write_label('on', resolved_device_id))
            active_ids.append(resolved_device_id)

    elif action == 'RELEASE':
        if resolved_device_id in active_ids:
            written.append(_write_label('off', resolved_device_id))
            filtered_active_ids = []
            for active_id in active_ids:
                if active_id != resolved_device_id:
                    filtered_active_ids.append(active_id)
            active_ids = filtered_active_ids

    elif action == 'CLEAR_ALL':
        for active_device_id in active_ids:
            written.append(_write_label('off', active_device_id))
        active_ids = []

    normalized_active_ids = _publish_active_surplus_device_ids(active_ids, entities)
    return written


def _write_label(prefix, device_id):
    return prefix + ':' + str(device_id)


def _active_surplus_device_ids(command, entities=None):
    active = _read_active_surplus_device_ids(entities)
    if active:
        return active
    return ()


@time_trigger('period(now, 30s)')
@state_trigger('sensor.ems_policy_decision_trace_pyscript')
def ems_dispatch_state_applier_loop():
    entities = _load_runtime_entities()
    command = _read_dispatch_command()
    decision = command['decision']
    trace_entity = _entity_id('policy_decision_trace', 'sensor.ems_policy_decision_trace_pyscript', entities)
    freeze_until_ts = get_attr(trace_entity, 'surplus_freeze_until_ts', None)

    writes = _apply_device_dispatch(command['action'], command['target'], command['device_id'], entities)
    freeze_written = _set_freeze_until_ts(_entity_id('surplus_freeze_until', 'input_datetime.ems_surplus_freeze_until', entities), freeze_until_ts)
    active_device_ids = _active_surplus_device_ids(command, entities)

    publish_sensor('sensor.ems_dispatch_state_applier_trace', decision, {
        'decision': decision,
        'decision_source': command['source'],
        'device_dispatch_action': command['action'],
        'device_dispatch_target': command['target'],
        'device_dispatch_device_id': command['device_id'],
        'device_dispatch_decision_name': command['decision_name'],
        'dispatch_state_contract': 'device_id_primary',
        'active_surplus_device_ids': active_device_ids,
        'writes': writes,
        'freeze_written': freeze_written,
        'freeze_until_ts': freeze_until_ts,
    })
