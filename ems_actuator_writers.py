from ems_adapter.entity_map import ENT
from ems_adapter.ha_adapter import get_attr, get_bool, get_float, get_int, get_str, publish_sensor, set_boolean, set_number


def _ent(key, fallback):
    """Return mapped entity id with a safe fallback for older/unit-test ENT maps."""
    return ENT.get(key, fallback)


def _quantize_50w(value):
    return int(round(float(value) / 50.0) * 50)


def _writer_enabled_from_policy(default=True):
    """Read the engine authority flag from policy attributes when available.

    Unit-test loaders strip HA adapter imports and may not inject get_attr. In
    that case we intentionally fall back to the caller-provided default.
    """
    get_attr_fn = globals().get('get_attr')
    if get_attr_fn is None:
        return default

    raw = get_attr_fn(ENT['policy_battery_target_w'], 'battery_write_enabled', default)
    if isinstance(raw, bool):
        return raw
    return str(raw).lower() in ('1', 'true', 'on', 'yes')


def _write_victron_actuator():
    control = get_str(_ent('control_profile', 'input_select.ems_control_profile'), 'AUTOMATIC')

    if control == 'MANUAL':
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'manual_skip',
            'written': False,
        }

    # In production the policy attribute is authoritative. If tests/older harnesses
    # do not expose it, MANUAL_SAFE is allowed to write so guard clamps can be tested.
    default_authority = control in ('AUTOMATIC', 'HORIZON_BY_HAEO', 'MANUAL_SAFE')
    if not _writer_enabled_from_policy(default=default_authority):
        return {
            'target': 'victron',
            'action': 'skip',
            'reason': 'policy_write_disabled',
            'written': False,
        }

    target_w = get_float(ENT['policy_battery_target_w'], 0)
    current_w = get_float(ENT['actuator_victron_setpoint_w'], 0)
    deadband = get_float(_ent('deadband_w', 'input_number.ems_deadband_w'), 100)
    ramp = get_float(_ent('ramp_max_w', 'input_number.ems_ramp_max_w'), 500)

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
        }

    step = max(min(delta, ramp), -ramp)
    new_setpoint = _quantize_50w(current_w + step)
    set_number(ENT['actuator_victron_setpoint_w'], new_setpoint)

    return {
        'target': 'victron',
        'action': 'write',
        'reason': 'manual_safe_clamp' if control == 'MANUAL_SAFE' else 'state_changed',
        'written': True,
        'current_w': current_w,
        'policy_target_w': target_w,
        'written_w': new_setpoint,
    }


def _write_ev_actuator():
    strategy_a = get_int(ENT['policy_ev_current_a'], -1)
    current_on = get_bool(ENT['actuator_ev_enabled'])
    current_level = get_int(ENT['actuator_ev_current_a'], 0)
    min_a = get_int(_ent('ev_min_current_a', 'input_number.ems_ev_min_current_a'), 4)

    if strategy_a < 0:
        return {
            'target': 'ev',
            'action': 'skip',
            'reason': 'policy_skip',
            'written': False,
        }

    if strategy_a > 0:
        enabled_changed = False
        current_changed = False
        if not current_on:
            set_boolean(ENT['actuator_ev_enabled'], True)
            enabled_changed = True
        if strategy_a != current_level:
            set_number(ENT['actuator_ev_current_a'], strategy_a)
            current_changed = True
        return {
            'target': 'ev',
            'action': 'enable_and_set_current',
            'reason': 'state_changed' if (enabled_changed or current_changed) else 'already_matching',
            'written': enabled_changed or current_changed,
            'policy_current_a': strategy_a,
            'new_current_a': strategy_a,
            'enabled_changed': enabled_changed,
            'current_changed': current_changed,
        }

    # Strategy 0 means EMS releases the active surplus command. Keep charger
    # state as-is, but restore the current selector to minimum if charger is on.
    if current_on and current_level != min_a:
        set_number(ENT['actuator_ev_current_a'], min_a)
        return {
            'target': 'ev',
            'action': 'restore_min_current',
            'reason': 'restore_min_current',
            'written': True,
            'previous_current_a': current_level,
            'new_current_a': min_a,
        }

    return {
        'target': 'ev',
        'action': 'skip',
        'reason': 'already_released',
        'written': False,
        'policy_current_a': strategy_a,
        'current_a': current_level,
    }


def _write_relay_actuator(policy_ent, actuator_ent, label):
    strategy = get_int(policy_ent, -1)
    is_on = get_bool(actuator_ent)

    if strategy < 0:
        return {
            'target': label,
            'action': 'skip',
            'reason': 'policy_skip',
            'written': False,
        }

    if strategy == 1 and not is_on:
        set_boolean(actuator_ent, True)
        return {
            'target': label,
            'action': 'turn_on',
            'reason': 'state_changed',
            'written': True,
        }

    if strategy == 0 and is_on:
        set_boolean(actuator_ent, False)
        return {
            'target': label,
            'action': 'turn_off',
            'reason': 'state_changed',
            'written': True,
        }

    return {
        'target': label,
        'action': 'skip',
        'reason': 'already_matching',
        'written': False,
        'policy_command': strategy,
        'is_on': is_on,
    }


def _publish_writer_trace(victron, ev, relay1, relay2):
    publish_sensor_fn = globals().get('publish_sensor')
    if publish_sensor_fn is None:
        return

    trace_ent = _ent('actuator_writer_trace', 'sensor.ems_actuator_writer_trace')
    attrs = {
        'victron': victron,
        'ev': ev,
        'relay1': relay1,
        'relay2': relay2,
    }
    publish_sensor_fn(trace_ent, 'ACTIVE', attrs)


@time_trigger('period(now, 30s)')
@state_trigger(
    'sensor.ems_policy_battery_target_w_pyscript or '
    'sensor.ems_policy_ev_current_a_pyscript or '
    'sensor.ems_policy_relay1_command_pyscript or '
    'sensor.ems_policy_relay2_command_pyscript or '
    'input_select.ems_control_profile'
)
def ems_actuator_writers_loop():
    victron = _write_victron_actuator()
    ev = _write_ev_actuator()
    relay1 = _write_relay_actuator(
        ENT['policy_relay1_command'],
        ENT['actuator_relay1'],
        'relay1',
    )
    relay2 = _write_relay_actuator(
        ENT['policy_relay2_command'],
        ENT['actuator_relay2'],
        'relay2',
    )
    _publish_writer_trace(victron, ev, relay1, relay2)
    return {
        'victron': victron,
        'ev': ev,
        'relay1': relay1,
        'relay2': relay2,
    }
