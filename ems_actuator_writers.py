from ems_adapter.ha_adapter import get_attr, get_bool, get_float, get_int, get_str, publish_sensor, set_boolean, set_number
from ems_adapter.runtime_context import read_core_config, read_runtime_context, read_runtime_entities
from ems_core.domain.ev_power import ev_min_current_a_from_min_absorb_w, ev_power_w_to_current_a
from ems_core.domain.models import EmsDeviceConfig
from ems_core.domain.capabilities import clamp_target_w_for_capabilities, capability_block_reason
from ems_core.domain.constants import CANONICAL_DIAGNOSTICS_OUTPUTS


def _load_runtime_entities():
    return read_runtime_entities(get_bool, get_float, get_int, get_str)


def _load_core_config():
    return read_core_config(get_bool, get_float, get_int, get_str)


def _load_runtime_context():
    return read_runtime_context(get_bool, get_float, get_int, get_str)


def _registry_entity(key, entities=None):
    if not isinstance(entities, dict):
        return None
    value = entities.get(key)
    if value in (None, ''):
        return None
    return str(value)


def _device_adapter_entities(device_id, entities=None):
    if not isinstance(entities, dict):
        return {}
    devices = entities.get('devices', {})
    if not isinstance(devices, dict):
        return {}
    mapped = devices.get(str(device_id), {})
    return mapped if isinstance(mapped, dict) else {}


def _resolve_float_value(value, default=0.0):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        try:
            return float(value)
        except ValueError:
            return get_float(value, default)
    return float(default)


def _quantize_50w(value):
    return int(round(float(value) / 50.0) * 50)


def _device_policy_by_id(device_id, entities=None):
    policy, _source_entity, _source_reason = _device_policy_source_for_id(device_id, entities)
    return policy


def _device_policy_source_for_id(device_id, entities=None):
    source_entity = _registry_entity('device_policies', entities)
    if not source_entity:
        return None, '', 'missing_device_policies_mapping'
    policies = get_attr(source_entity, 'device_policies', None)
    if policies:
        for policy in policies:
            if isinstance(policy, dict) and policy.get('device_id') == device_id:
                return policy, source_entity, 'canonical'
    return None, '', 'missing_device_policy'


def _device_policy_enabled(policy, default=False):
    if policy is None or 'enabled' not in policy:
        return default
    raw = policy.get('enabled')
    if isinstance(raw, bool):
        return raw
    return str(raw).lower() in ('1', 'true', 'on', 'yes')


def _device_policy_target_w(policy, default=0):
    if policy is None or 'target_w' not in policy:
        return default
    return float(policy.get('target_w') or 0)


def _v3_battery_device_id(cfg):
    if hasattr(cfg, 'v3_battery_device_id'):
        return str(cfg.v3_battery_device_id() or '')
    if hasattr(cfg, 'device_ids_by_kind'):
        battery_ids = tuple(cfg.device_ids_by_kind('BATTERY') or ())
        return str(battery_ids[0]) if battery_ids else ''
    devices = getattr(cfg, 'devices', {}) or {}
    for device_id, device in devices.items():
        if str(getattr(device, 'kind', '') or '') == 'BATTERY':
            return str(device_id)
    return ''


def _capability_device_config_for_id(device_id, cfg=None):
    cfg = cfg or _load_core_config()
    device = cfg.device_by_id(device_id) if hasattr(cfg, 'device_by_id') else None
    if device is None:
        return None
    caps = device.capabilities
    policy = device.policy
    return EmsDeviceConfig(
        device_id=str(device.device_id),
        kind=str(device.kind),
        response_kind='continuous' if str(device.kind) == 'BATTERY' else ('selector' if str(device.kind) == 'EV_CHARGER' else 'relay'),
        can_absorb_w=bool(caps.can_absorb_w),
        can_produce_w=bool(caps.can_produce_w),
        min_absorb_w=int(round(float(caps.min_absorb_w))),
        max_absorb_w=int(round(float(caps.max_absorb_w))),
        max_produce_w=int(round(abs(float(caps.max_produce_w or 0)))),
        step_w=max(1, int(round(float(caps.step_w)))),
        priority=int(round(float(policy.priority))),
    )


def _write_battery_actuator(device_id=None, entities=None, cfg=None):
    if entities is None:
        entities = _load_runtime_entities()
    cfg = cfg or _load_core_config()
    device_id = str(device_id or _v3_battery_device_id(cfg) or '')
    profiles = getattr(cfg, 'profiles', None)
    control = str(getattr(profiles, 'control', 'AUTOMATIC') or 'AUTOMATIC')

    if control == 'MANUAL':
        return {
            'target': 'victron',
            'device_id': device_id,
            'action': 'skip',
            'reason': 'manual_skip',
            'written': False,
        }

    device_policy = _device_policy_by_id(device_id, entities) if device_id else None
    if device_policy is None:
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'missing_device_policy',
            'written': False,
            'policy_source': 'missing_device_policy',
        }

    policy_source = 'canonical'
    write_enabled = _device_policy_enabled(device_policy)
    if not write_enabled:
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'policy_write_disabled',
            'written': False,
            'policy_source': policy_source,
        }

    target_w = _device_policy_target_w(device_policy, default=0)
    capability_cfg = _capability_device_config_for_id(device_id, cfg=cfg)
    if capability_cfg is None:
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'missing_device_config',
            'written': False,
            'policy_source': policy_source,
        }
    capability_reason = capability_block_reason(capability_cfg, target_w)
    target_w = clamp_target_w_for_capabilities(capability_cfg, target_w)

    device_mapping = _device_adapter_entities(device_id, entities)
    battery_entity = device_mapping.get('target_w')
    if not battery_entity:
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'missing_actuator_entity',
            'written': False,
            'policy_source': policy_source,
        }
    current_w = get_float(battery_entity, 0)
    global_cfg = getattr(cfg, 'global_config', None)
    deadband = float(getattr(global_cfg, 'deadband_w', 100.0) or 100.0)
    ramp = float(getattr(global_cfg, 'ramp_w', 500.0) or 500.0)

    delta = target_w - current_w
    if abs(delta) < deadband:
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'deadband',
            'written': False,
            'current_w': current_w,
            'target_w': target_w,
            'delta_w': delta,
            'policy_source': policy_source,
            'capability_reason': capability_reason,
        }

    step = max(min(delta, ramp), -ramp)
    new_setpoint = _quantize_50w(current_w + step)
    set_number(battery_entity, new_setpoint)

    return {
        'target': 'victron',
        'action': 'write',
        'reason': capability_reason or ('manual_safe_clamp' if control == 'MANUAL_SAFE' else 'state_changed'),
        'written': True,
        'current_w': current_w,
        'policy_target_w': target_w,
        'written_w': new_setpoint,
        'policy_source': policy_source,
    }


def _write_ev_actuator(device_id='EV_CHARGER', entities=None, cfg=None):
    if entities is None:
        entities = _load_runtime_entities()
    cfg = cfg or _load_core_config()
    device_policy = _device_policy_by_id(device_id, entities) if device_id else None
    if device_policy is None:
        return {
            'target': 'ev',
            'action': 'skip',
            'reason': 'missing_device_policy',
            'written': False,
            'policy_source': 'missing_device_policy',
        }

    policy_source = 'canonical'
    device_runtime = _device_adapter_entities(device_id, entities)
    enabled_entity = device_runtime.get('enabled')
    current_entity = device_runtime.get('current_a')
    if not enabled_entity or not current_entity:
        return {
            'target': device_id,
            'action': 'skip',
            'reason': 'missing_actuator_entity',
            'written': False,
            'policy_source': policy_source,
        }
    current_on = get_bool(enabled_entity)
    current_level = get_int(current_entity, 0)
    core_device = cfg.device_by_id(device_id) if hasattr(cfg, 'device_by_id') else None
    adapter_cfg = getattr(core_device, 'adapter', None) if core_device is not None else None
    step_a = float(getattr(adapter_cfg, 'current_step_a', 4.0) or 4.0)
    phases = float(getattr(adapter_cfg, 'phases', 1.0) or 1.0)
    voltage_v = float(getattr(adapter_cfg, 'voltage_v', 230.0) or 230.0)
    ev_policy_mode = str(device_policy.get('mode') or '')
    capability_reason = ''
    target_w = _device_policy_target_w(device_policy, default=0)
    capability_cfg = _capability_device_config_for_id(device_id or 'EV_CHARGER', cfg=cfg)
    if capability_cfg is None:
        return {
            'target': device_id,
            'action': 'skip',
            'reason': 'missing_device_config',
            'written': False,
            'policy_source': policy_source,
        }
    min_absorb_w = float(capability_cfg.min_absorb_w)
    max_absorb_w = float(capability_cfg.max_absorb_w)
    derived_min_a = ev_min_current_a_from_min_absorb_w(
        min_absorb_w,
        phases=phases,
        voltage_v=voltage_v,
        current_step_a=step_a,
    )
    if ev_policy_mode == 'skip':
        target_current_a = -1
    else:
        capability_reason = capability_block_reason(capability_cfg, target_w)
        target_w = clamp_target_w_for_capabilities(capability_cfg, target_w)
        if capability_reason:
            ev_policy_mode = 'hard_off'
        target_current_a = 0
        if target_w > 0 and ev_policy_mode != 'hard_off':
            target_current_a = ev_power_w_to_current_a(
                target_w,
                phases=phases,
                voltage_v=voltage_v,
                min_absorb_w=min_absorb_w,
                max_absorb_w=max_absorb_w,
                current_step_a=step_a,
            )

    if target_current_a < 0:
        return {
            'target': 'ev',
            'action': 'skip',
            'reason': 'policy_skip',
            'written': False,
            'policy_source': policy_source,
        }

    if target_current_a > 0:
        enabled_changed = False
        current_changed = False
        if not current_on:
            set_boolean(enabled_entity, True)
            enabled_changed = True
        if target_current_a != current_level:
            set_number(current_entity, target_current_a)
            current_changed = True
        return {
            'target': 'ev',
            'action': 'enable_and_set_current',
            'reason': capability_reason or ('state_changed' if (enabled_changed or current_changed) else 'already_matching'),
            'written': enabled_changed or current_changed,
            'policy_target_w': target_w,
            'target_current_a': target_current_a,
            'enabled_changed': enabled_changed,
            'current_changed': current_changed,
            'policy_source': policy_source,
        }

    if ev_policy_mode == 'restore_min':
        current_changed = False
        if current_level != derived_min_a:
            set_number(current_entity, derived_min_a)
            current_changed = True
        return {
            'target': 'ev',
            'action': 'restore_min_current',
            'reason': capability_reason or 'restore_min',
            'written': current_changed,
            'policy_target_w': target_w,
            'target_current_a': derived_min_a,
            'enabled_changed': False,
            'current_changed': current_changed,
            'policy_source': policy_source,
        }

    enabled_changed = False
    current_changed = False
    if current_on:
        set_boolean(enabled_entity, False)
        enabled_changed = True
    if current_level != derived_min_a:
        set_number(current_entity, derived_min_a)
        current_changed = True
    if ev_policy_mode == 'hard_off':
        return {
            'target': 'ev',
            'action': 'hard_off',
            'reason': capability_reason or 'hard_off',
            'written': enabled_changed or current_changed,
            'policy_target_w': target_w,
            'target_current_a': derived_min_a,
            'enabled_changed': enabled_changed,
            'current_changed': current_changed,
            'policy_source': policy_source,
        }

    if enabled_changed or current_changed:
        return {
            'target': 'ev',
            'action': 'disable_and_restore_min_current',
            'reason': capability_reason or 'target_zero_disable',
            'written': True,
            'policy_target_w': target_w,
            'target_current_a': derived_min_a,
            'enabled_changed': enabled_changed,
            'current_changed': current_changed,
            'policy_source': policy_source,
        }

    return {
        'target': 'ev',
        'action': 'skip',
        'reason': capability_reason or 'already_disabled',
        'written': False,
        'policy_target_w': target_w,
        'current_a': current_level,
        'policy_source': policy_source,
    }


def _write_relay_actuator(label, device_id=None, entities=None, cfg=None):
    if entities is None:
        entities = _load_runtime_entities()
    cfg = cfg or _load_core_config()
    device_policy = _device_policy_by_id(device_id, entities) if device_id else None
    if device_policy is None:
        return {
            'target': label,
            'action': 'skip',
            'reason': 'missing_device_policy',
            'written': False,
            'policy_source': 'missing_device_policy',
        }

    policy_source = 'canonical'
    device_runtime = _device_adapter_entities(device_id or '', entities)
    actuator_ent = device_runtime.get('enabled')
    if not actuator_ent:
        return {
            'target': label,
            'action': 'skip',
            'reason': 'missing_actuator_entity',
            'written': False,
            'policy_source': policy_source,
        }
    capability_reason = ''
    if device_id:
        capability_cfg = _capability_device_config_for_id(device_id, cfg=cfg)
        if capability_cfg is None:
            return {
                'target': label,
                'action': 'skip',
                'reason': 'missing_device_config',
                'written': False,
                'policy_source': policy_source,
            }
        desired_target_w = _device_policy_target_w(device_policy, default=0)
        capability_reason = capability_block_reason(capability_cfg, desired_target_w)
    if str(device_policy.get('mode') or '') == 'skip':
        strategy = -1
    else:
        strategy = 0 if capability_reason else (1 if _device_policy_enabled(device_policy) else 0)
    is_on = get_bool(actuator_ent)

    if strategy < 0:
        return {
            'target': label,
            'action': 'skip',
            'reason': 'policy_skip',
            'written': False,
            'policy_source': policy_source,
        }
    if strategy == 1 and not is_on:
        set_boolean(actuator_ent, True)
        return {
            'target': label,
            'action': 'turn_on',
            'reason': capability_reason or 'state_changed',
            'written': True,
            'policy_source': policy_source,
        }
    if strategy == 0 and is_on:
        set_boolean(actuator_ent, False)
        return {
            'target': label,
            'action': 'turn_off',
            'reason': capability_reason or 'state_changed',
            'written': True,
            'policy_source': policy_source,
        }
    return {
        'target': label,
        'action': 'skip',
        'reason': capability_reason or 'already_matching',
        'written': False,
        'policy_command': strategy,
        'is_on': is_on,
        'policy_source': policy_source,
    }


def _publish_writer_trace(victron, device_traces, entities=None):
    trace_ent = _registry_entity('actuator_writer_trace', entities)
    device_policies_entity = _registry_entity('device_policies', entities)
    if not trace_ent or not device_policies_entity:
        return False
    attrs = {
        'writer_policy_contract': 'device_policy_primary',
        'writer_trace_canonical_contract': 'devices',
        'policy_source_entity': device_policies_entity,
        'policy_source_reason': 'canonical',
        'device_policies_version': get_str(device_policies_entity, ''),
        'victron': victron,
        'devices': device_traces,
    }
    publish_sensor(trace_ent, 'ACTIVE', attrs)
    return True


@time_trigger('period(now, 30s)')
@state_trigger(
    'sensor.ems_device_policies_pyscript or '
    'input_select.ems_control_profile'
)
def ems_actuator_writers_loop():
    entities = {}
    try:
        cfg, entities = _load_runtime_context()
    except Exception as exc:
        publish_sensor(CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace'], 'SUPPRESSED', {
            'writer_policy_contract': 'device_policy_primary',
            'actuator_writes_suppressed': True,
            'error': True,
            'error_code': 'RUNTIME_CONTEXT_INVALID',
            'error_path': getattr(exc, 'path', ''),
            'error_message': str(exc),
        })
        return {
            'suppressed': True,
            'error_code': 'RUNTIME_CONTEXT_INVALID',
            'error_path': getattr(exc, 'path', ''),
        }
    victron = _write_battery_actuator(entities=entities, cfg=cfg)
    device_traces = {}
    for device in getattr(cfg, 'devices', {}).values():
        device_id = str(device.device_id)
        kind = str(device.kind)
        if kind == 'EV_CHARGER':
            device_traces[device_id] = _write_ev_actuator(device_id=device_id, entities=entities, cfg=cfg)
        elif kind == 'RELAY':
            device_traces[device_id] = _write_relay_actuator(
                device_id.lower(),
                device_id=device_id,
                entities=entities,
                cfg=cfg,
            )
    _publish_writer_trace(victron, device_traces, entities)
    result = {
        'victron': victron,
        'devices': device_traces,
        'writer_trace_canonical_contract': 'devices',
    }
    return result
