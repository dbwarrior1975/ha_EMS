from ems_adapter.entity_map import ENT
from ems_adapter.ha_adapter import get_bool, get_float, get_int, get_str, set_boolean, set_number, publish_sensor


def _quantize_50w(value):
    return int(round(float(value) / 50.0) * 50)


def _write_victron_shadow():
    control = get_str('input_select.ems_control_profile', 'AUTOMATIC')
    target_w = get_float(ENT['policy_battery_target_w'], 0)
    current_w = get_float(ENT['shadow_victron_setpoint_w'], 0)
    deadband = get_float('input_number.ems_deadband_w', 100)
    ramp = get_float('input_number.ems_ramp_max_w', 500)

    # MANUAL = absolute hands off
    if control == 'MANUAL':
        return {
            'written': False,
            'target_w': target_w,
            'current_w': current_w,
            'reason': 'manual_skip',
        }

    # MANUAL_SAFE = only apply safety correction if policy target differs from current value
    if control == 'MANUAL_SAFE':
        if target_w != current_w:
            set_number(ENT['shadow_victron_setpoint_w'], target_w)
            return {
                'written': True,
                'target_w': target_w,
                'current_w': current_w,
                'new_setpoint_w': target_w,
                'reason': 'manual_safe_clamp',
            }

        return {
            'written': False,
            'target_w': target_w,
            'current_w': current_w,
            'reason': 'manual_safe_no_change',
        }

    # AUTOMATIC / normal writer behavior
    delta = target_w - current_w
    if abs(delta) < deadband:
        return {
            'written': False,
            'target_w': target_w,
            'current_w': current_w,
            'reason': 'inside_deadband',
        }

    step = min(delta, ramp) if delta > 0 else max(delta, -ramp)
    new_setpoint = _quantize_50w(current_w + step)
    set_number(ENT['shadow_victron_setpoint_w'], new_setpoint)

    return {
        'written': True,
        'target_w': target_w,
        'current_w': current_w,
        'new_setpoint_w': new_setpoint,
        'reason': 'ramp_applied',
    }


def _write_ev_shadow():
    strategy_a = get_int(ENT['policy_ev_current_a'], -1)
    current_on = get_bool(ENT['shadow_ev_enabled'])
    current_level = get_int(ENT['shadow_ev_current_a'], 0)
    min_a = get_int('input_number.ems_ev_min_current_a', 4)

    result = {
        'strategy_a': strategy_a,
        'current_on': current_on,
        'current_level_a': current_level,
        'written': False,
    }

    if strategy_a < 0:
        result['reason'] = 'skip'
        return result

    if strategy_a > 0:
        if not current_on:
            set_boolean(ENT['shadow_ev_enabled'], True)
            current_on = True

        if strategy_a != current_level:
            set_number(ENT['shadow_ev_current_a'], strategy_a)

        result.update({
            'written': True,
            'new_enabled': True,
            'new_current_a': strategy_a,
            'reason': 'active_current',
        })
        return result

    if current_on and current_level != min_a:
        set_number(ENT['shadow_ev_current_a'], min_a)
        result.update({
            'written': True,
            'new_enabled': True,
            'new_current_a': min_a,
            'reason': 'restore_min_current',
        })
    else:
        result['reason'] = 'no_change'

    return result


def _write_relay_shadow(policy_ent, shadow_ent, label):
    strategy = get_int(policy_ent, -1)
    is_on = get_bool(shadow_ent)

    result = {
        'strategy': strategy,
        'current_on': is_on,
        'written': False,
        'label': label,
    }

    if strategy < 0:
        result['reason'] = 'skip'
        return result

    desired = bool(strategy)
    if desired != is_on:
        set_boolean(shadow_ent, desired)
        result.update({'written': True, 'new_on': desired, 'reason': 'state_changed'})
    else:
        result['reason'] = 'no_change'

    return result


@time_trigger('period(now, 30s)')
@state_trigger(
    'sensor.ems_policy_battery_target_w_pyscript or '
    'sensor.ems_policy_ev_current_a_pyscript or '
    'sensor.ems_policy_relay1_command_pyscript or '
    'sensor.ems_policy_relay2_command_pyscript or '
    'input_select.ems_control_profile'
)
def ems_shadow_writers_loop():
    vic = _write_victron_shadow()
    ev = _write_ev_shadow()
    r1 = _write_relay_shadow(ENT['policy_relay1_command'], ENT['shadow_relay1'], 'relay1')
    r2 = _write_relay_shadow(ENT['policy_relay2_command'], ENT['shadow_relay2'], 'relay2')

    publish_sensor(
        'sensor.ems_shadow_writer_trace',
        'ACTIVE',
        {
            'victron': vic,
            'ev': ev,
            'relay1': r1,
            'relay2': r2,
        },
    )
