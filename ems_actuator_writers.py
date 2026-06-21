from ems_adapter.ha_adapter import get_attr, get_bool, get_float, get_int, get_str, publish_sensor, set_boolean, set_number
from ems_core.domain.ev_power import ev_power_w_to_selector_current_a
from ems_core.domain.models import EmsDeviceConfig
from ems_core.domain.capabilities import clamp_target_w_for_capabilities, capability_block_reason


def _load_runtime_entities():
    ent = globals().get('ENT', {})
    if ent:
        return dict(ent)
    from ems_adapter.runtime_context import read_runtime_entities

    return read_runtime_entities(get_bool, get_float, get_int, get_str)


def _load_core_config():
    reader = globals().get('read_core_config')
    if reader is not None:
        return reader()
    from ems_adapter.runtime_context import read_core_config

    return read_core_config(get_bool, get_float, get_int, get_str)


def _ent(key, fallback, entities=None):
    if entities is not None and key in entities:
        return entities[key]
    ent = globals().get('ENT', {})
    return ent.get(key, fallback)


def _quantize_50w(value):
    return int(round(float(value) / 50.0) * 50)


def _device_policy_by_id(device_id, entities=None):
    get_attr_fn = globals().get('get_attr')
    if get_attr_fn is None:
        return None

    source_entities = (
        _ent('device_policies', 'sensor.ems_device_policies_pyscript', entities),
        _ent('policy_decision_trace', 'sensor.ems_policy_decision_trace_pyscript', entities),
    )
    for source_entity in source_entities:
        policies = get_attr_fn(source_entity, 'device_policies', None)
        if not policies:
            continue
        for policy in policies:
            if isinstance(policy, dict) and policy.get('device_id') == device_id:
                return policy
    return None


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


def _previous_device_state_mode(entities=None):
    get_attr_fn = globals().get('get_attr')
    if get_attr_fn is None:
        return ''

    mode = get_attr_fn(_ent('previous_device_state', 'sensor.ems_previous_device_state', entities), 'mode', '')
    if mode:
        return str(mode)
    return ''


def _capability_device_config_for_id(device_id):
    cfg = _load_core_config()
    if device_id == 'HOME_BATTERY':
        caps = cfg.home_battery.capabilities
        policy = cfg.home_battery.policy
        return EmsDeviceConfig(
            device_id='HOME_BATTERY',
            kind='BATTERY',
            response_kind='continuous',
            can_absorb_w=bool(caps.can_absorb_w),
            can_produce_w=bool(caps.can_produce_w),
            min_absorb_w=int(round(float(caps.min_absorb_w))),
            max_absorb_w=int(round(float(caps.max_absorb_w))),
            max_produce_w=int(round(abs(float(caps.max_produce_w or 0)))),
            step_w=max(1, int(round(float(caps.step_w)))),
            priority=int(round(float(policy.priority))),
        )
    if device_id == 'EV_CHARGER':
        caps = cfg.ev_charger.capabilities
        policy = cfg.ev_charger.policy
        return EmsDeviceConfig(
            device_id='EV_CHARGER',
            kind='EV_CHARGER',
            response_kind='selector',
            can_absorb_w=bool(caps.can_absorb_w),
            can_produce_w=bool(caps.can_produce_w),
            min_absorb_w=int(round(float(caps.min_absorb_w))),
            max_absorb_w=int(round(float(caps.max_absorb_w))),
            max_produce_w=int(round(abs(float(caps.max_produce_w or 0)))),
            step_w=max(1, int(round(float(caps.step_w)))),
            priority=int(round(float(policy.priority))),
        )
    relay = cfg.relay1 if device_id == 'RELAY1' else cfg.relay2
    caps = relay.capabilities
    policy = relay.policy
    return EmsDeviceConfig(
        device_id=device_id,
        kind='RELAY',
        response_kind='relay',
        can_absorb_w=bool(caps.can_absorb_w),
        can_produce_w=bool(caps.can_produce_w),
        min_absorb_w=int(round(float(caps.min_absorb_w))),
        max_absorb_w=int(round(float(caps.max_absorb_w))),
        max_produce_w=int(round(abs(float(caps.max_produce_w or 0)))),
        step_w=max(1, int(round(float(caps.step_w)))),
        priority=int(round(float(policy.priority))),
    )


def _write_battery_actuator(entities=None):
    control = get_str(_ent('control_profile', 'input_select.ems_control_profile', entities), 'AUTOMATIC')

    if control == 'MANUAL':
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'manual_skip',
            'written': False,
        }

    device_policy = _device_policy_by_id('HOME_BATTERY', entities)
    if device_policy is None:
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'missing_device_policy',
            'written': False,
            'policy_source': 'missing_device_policy',
        }

    policy_source = 'device_policy'
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
    capability_cfg = _capability_device_config_for_id('HOME_BATTERY')
    capability_reason = capability_block_reason(capability_cfg, target_w)
    target_w = clamp_target_w_for_capabilities(capability_cfg, target_w)
    battery_entity = _ent('actuator_battery_setpoint_w', 'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point', entities)
    current_w = get_float(battery_entity, 0)
    deadband = get_float(_ent('deadband_w', 'input_number.ems_deadband_w', entities), 100)
    ramp = get_float(_ent('ramp_max_w', 'input_number.ems_ramp_max_w', entities), 500)

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


def _write_ev_actuator(device_id='EV_CHARGER', entities=None):
    device_policy = _device_policy_by_id(device_id, entities) if device_id else None
    if device_policy is None:
        return {
            'target': 'ev',
            'action': 'skip',
            'reason': 'missing_device_policy',
            'written': False,
            'policy_source': 'missing_device_policy',
        }

    policy_source = 'device_policy'
    enabled_entity = _ent('actuator_ev_enabled', 'switch.charger_control', entities)
    current_entity = _ent('actuator_ev_current_a', 'number.charger_current_level', entities)
    current_on = get_bool(enabled_entity)
    current_level = get_int(current_entity, 0)
    min_a = get_int(_ent('ev_min_current_a', 'input_number.ems_ev_min_current_a', entities), 6)
    max_a = get_int(_ent('ev_max_current_a', 'input_number.ems_ev_max_current_a', entities), 28)
    step_a = get_int(_ent('ev_current_step_a', 'input_number.ems_ev_current_step_a', entities), 4)
    phases = get_int(_ent('ev_charger_phases', 'input_number.ems_ev_charger_phases', entities), 1)
    ev_policy_mode = str(device_policy.get('mode') or _previous_device_state_mode(entities) or '')
    capability_reason = ''
    if ev_policy_mode == 'skip':
        strategy_a = -1
    else:
        # EV device policy is watt-based in the canonical production contract.
        # Any current_a payload is treated only as compatibility/trace metadata.
        target_w = _device_policy_target_w(device_policy, default=0)
        capability_cfg = _capability_device_config_for_id(device_id or 'EV_CHARGER')
        capability_reason = capability_block_reason(capability_cfg, target_w)
        target_w = clamp_target_w_for_capabilities(capability_cfg, target_w)
        if capability_reason:
            ev_policy_mode = 'hard_off'
        strategy_a = ev_power_w_to_selector_current_a(
            target_w,
            phases,
            max_a,
            min_a=min_a,
            step_a=step_a,
        )

    if strategy_a < 0:
        return {
            'target': 'ev',
            'action': 'skip',
            'reason': 'policy_skip',
            'written': False,
            'policy_source': policy_source,
        }

    if strategy_a > 0:
        enabled_changed = False
        current_changed = False
        if not current_on:
            set_boolean(enabled_entity, True)
            enabled_changed = True
        if strategy_a != current_level:
            set_number(current_entity, strategy_a)
            current_changed = True
        return {
            'target': 'ev',
            'action': 'enable_and_set_current',
            'reason': capability_reason or ('state_changed' if (enabled_changed or current_changed) else 'already_matching'),
            'written': enabled_changed or current_changed,
            'policy_current_a': strategy_a,
            'target_current_a': strategy_a,
            'enabled_changed': enabled_changed,
            'current_changed': current_changed,
            'policy_source': policy_source,
        }

    if ev_policy_mode == 'hard_off':
        enabled_changed = False
        current_changed = False
        if current_on:
            set_boolean(enabled_entity, False)
            enabled_changed = True
        # Charger selector cannot be written below its hardware minimum. Keep it
        # at minimum while disabling the charger switch.
        if current_level != min_a:
            set_number(current_entity, min_a)
            current_changed = True
        return {
            'target': 'ev',
            'action': 'hard_off',
            'reason': capability_reason or 'hard_off',
            'written': enabled_changed or current_changed,
            'policy_current_a': strategy_a,
            'target_current_a': min_a,
            'enabled_changed': enabled_changed,
            'current_changed': current_changed,
            'policy_source': policy_source,
        }

    # Strategy 0 means EMS releases the active surplus command. Keep charger
    # state as-is, but restore the current selector to minimum if charger is on.
    if current_on and current_level != min_a:
        set_number(current_entity, min_a)
        return {
            'target': 'ev',
            'action': 'restore_min_current',
            'reason': capability_reason or 'restore_min_current',
            'written': True,
            'previous_current_a': current_level,
            'target_current_a': min_a,
            'policy_source': policy_source,
        }

    return {
        'target': 'ev',
        'action': 'skip',
        'reason': capability_reason or 'already_released',
        'written': False,
        'policy_current_a': strategy_a,
        'current_a': current_level,
        'policy_source': policy_source,
    }


def _write_relay_actuator(policy_ent, actuator_ent, label, device_id=None, entities=None):
    device_policy = _device_policy_by_id(device_id, entities) if device_id else None
    if device_policy is None:
        return {
            'target': label,
            'action': 'skip',
            'reason': 'missing_device_policy',
            'written': False,
            'policy_source': 'missing_device_policy',
        }

    policy_source = 'device_policy'
    capability_reason = ''
    if device_id:
        capability_cfg = _capability_device_config_for_id(device_id)
        desired_target_w = _device_policy_target_w(device_policy, default=0)
        capability_reason = capability_block_reason(capability_cfg, desired_target_w)
    if str(device_policy.get('mode') or '') == 'skip':
        strategy = -1
    else:
        if capability_reason:
            strategy = 0
        else:
            strategy = 1 if _device_policy_enabled(device_policy) else 0
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


def _publish_writer_trace(victron, ev, relay1, relay2, entities=None):
    publish_sensor_fn = globals().get('publish_sensor')
    if publish_sensor_fn is None:
        return

    trace_ent = _ent('actuator_writer_trace', 'sensor.ems_actuator_writer_trace', entities)
    attrs = {
        'writer_policy_contract': 'device_policy_primary',
        'victron': victron,
        'ev': ev,
        'relay1': relay1,
        'relay2': relay2,
    }
    publish_sensor_fn(trace_ent, 'ACTIVE', attrs)


@time_trigger('period(now, 30s)')
@state_trigger(
    'sensor.ems_policy_decision_trace_pyscript or '
    'input_select.ems_control_profile'
)
def ems_actuator_writers_loop():
    entities = _load_runtime_entities()
    victron = _write_battery_actuator(entities)
    ev = _write_ev_actuator(entities=entities)
    relay1 = _write_relay_actuator(
        _ent('policy_relay1_command', 'sensor.ems_policy_relay1_command_pyscript', entities),
        _ent('actuator_relay1', 'switch.relay_1_2', entities),
        'relay1',
        device_id='RELAY1',
        entities=entities,
    )
    relay2 = _write_relay_actuator(
        _ent('policy_relay2_command', 'sensor.ems_policy_relay2_command_pyscript', entities),
        _ent('actuator_relay2', 'switch.relay_2_2', entities),
        'relay2',
        device_id='RELAY2',
        entities=entities,
    )
    _publish_writer_trace(victron, ev, relay1, relay2, entities)
    return {
        'victron': victron,
        'ev': ev,
        'relay1': relay1,
        'relay2': relay2,
    }
