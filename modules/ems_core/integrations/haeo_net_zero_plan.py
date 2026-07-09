from ems_core.domain.models import (
    ControlProfile,
    ForecastProfile,
    GoalProfile,
    GuardProfile,
    HaeoNetZeroPlan,
)
from ems_core.domain.ev_power import ev_max_power_w


def quarter_key_for_ts(now_ts):
    quarter_start_ts = int(float(now_ts) // 900) * 900
    return str(quarter_start_ts)


def _positive_w(kw):
    try:
        return max(int(round(float(kw) * 1000.0)), 0)
    except (TypeError, ValueError):
        return 0


def _device_by_id(cfg, device_id):
    if not device_id or not hasattr(cfg, 'device_by_id'):
        return None
    return cfg.device_by_id(device_id)


def _device_kind(cfg, device_id):
    if hasattr(cfg, 'device_kind'):
        return str(cfg.device_kind(device_id) or '')
    device = _device_by_id(cfg, device_id)
    if device is None:
        return ''
    return str(getattr(device, 'kind', '') or '')


def _device_capability(cfg, device_id, field, default=None):
    if hasattr(cfg, 'device_capability'):
        return cfg.device_capability(device_id, field, default)
    device = _device_by_id(cfg, device_id)
    if device is None:
        return default
    capabilities = getattr(device, 'capabilities', None)
    if capabilities is None:
        return default
    return getattr(capabilities, field, default)



def _device_policy_value(cfg, device_id, field, default=None):
    if hasattr(cfg, 'device_policy_value'):
        return cfg.device_policy_value(device_id, field, default)
    device = _device_by_id(cfg, device_id)
    if device is None:
        return default
    policy = getattr(device, 'policy', None)
    if policy is None:
        return default
    return getattr(policy, field, default)

def _device_ids_by_kind(cfg, kind):
    ids = []
    if hasattr(cfg, 'device_ids_by_kind'):
        for device_id in (cfg.device_ids_by_kind(kind) or ()):
            ids.append(str(device_id))
        return tuple(ids)
    if hasattr(cfg, 'devices_by_kind'):
        for device in (cfg.devices_by_kind(kind) or ()):
            ids.append(str(device.device_id))
        return tuple(ids)
    return ()


def _ev_device_ids(cfg):
    if hasattr(cfg, 'device_ids_by_kind'):
        ids = []
        for device_id in cfg.device_ids_by_kind('EV_CHARGER'):
            ids.append(str(device_id))
        return tuple(ids)
    if hasattr(cfg, 'devices_by_kind'):
        ids = []
        for device in cfg.devices_by_kind('EV_CHARGER'):
            ids.append(str(device.device_id))
        return tuple(ids)
    return ()


def _ev_devices(cfg):
    if hasattr(cfg, 'devices_by_kind'):
        return tuple(cfg.devices_by_kind('EV_CHARGER'))
    return ()


def _default_ev_device_id(cfg):
    ev_device_ids = _ev_device_ids(cfg)
    if ev_device_ids:
        return str(ev_device_ids[0])
    return 'EV_CHARGER'


def _is_ev_device_id(cfg, device_id):
    if _device_kind(cfg, device_id) == 'EV_CHARGER':
        return True
    return str(device_id or '') == 'EV_CHARGER'


def _global_config_value(cfg, field_name, default=None):
    global_config = getattr(cfg, 'global_config', None)
    return getattr(global_config, field_name, default) if global_config is not None else default


def _v3_battery_device_id(cfg):
    if hasattr(cfg, 'v3_battery_device_id'):
        return str(cfg.v3_battery_device_id() or '')
    battery_ids = _device_ids_by_kind(cfg, 'BATTERY')
    return str(battery_ids[0]) if battery_ids else ''


def _selected_ev_device_id(cfg):
    primary_device_id = str(_global_config_value(cfg, 'primary_device_id', '') or '')
    if _is_ev_device_id(cfg, primary_device_id):
        return primary_device_id

    best_device_id = ''
    best_priority = None
    for device_id in _ev_device_ids(cfg):
        if not bool(_device_policy_value(cfg, device_id, 'surplus_allowed', False)):
            continue
        try:
            priority = int(_device_policy_value(cfg, device_id, 'priority', 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        if best_priority is None or priority > best_priority:
            best_device_id = str(device_id)
            best_priority = priority
    if best_device_id:
        return best_device_id
    return _default_ev_device_id(cfg)


def _ev_plan_params(cfg, ev_device_id):
    if _device_kind(cfg, ev_device_id) != 'EV_CHARGER':
        return {
            'ev_limit_w_cap': int(ev_max_power_w(cfg)),
        }

    return {
        'ev_limit_w_cap': int(round(float(_device_capability(cfg, ev_device_id, 'max_absorb_w', 0) or 0))),
    }


def compute_haeo_net_zero_plan(
    profiles,
    cfg,
    haeo,
    now_ts,
    *,
    previous_quarter_key='',
    previous_primary_load='',
    previous_primary_device_id='',
):
    quarter_key = quarter_key_for_ts(now_ts)
    selected_ev_device_id = _selected_ev_device_id(cfg)

    if profiles.control != ControlProfile.HORIZON_BY_HAEO:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='control_not_horizon_by_haeo')
    if profiles.goal != GoalProfile.NET_ZERO:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='goal_not_net_zero')
    if profiles.guard != GuardProfile.NORMAL_LIMITS:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='guard_not_normal_limits')
    if haeo.configured_forecast != ForecastProfile.HAEO:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='forecast_not_configured')
    if haeo.effective_forecast != ForecastProfile.HAEO or not haeo.fresh:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='forecast_not_effective')

    v3_battery_device_id = _v3_battery_device_id(cfg)
    battery_limit_w = min(
        _positive_w(haeo.battery_target_kw),
        int(round(float(_device_capability(cfg, v3_battery_device_id, 'max_absorb_w', 0) or 0))),
    )

    ev_params = _ev_plan_params(cfg, selected_ev_device_id)
    ev_limit_w = min(_positive_w(haeo.ev_target_kw), int(ev_params['ev_limit_w_cap']))

    if battery_limit_w <= 0 and ev_limit_w <= 0:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='zero_forecast')

    previous_primary = previous_primary_device_id or previous_primary_load

    if battery_limit_w > ev_limit_w:
        primary_device_id = v3_battery_device_id
        reason = 'battery_forecast_larger'
    elif ev_limit_w > battery_limit_w:
        primary_device_id = selected_ev_device_id
        reason = 'ev_forecast_larger'
    elif previous_primary == v3_battery_device_id or _is_ev_device_id(cfg, previous_primary):
        primary_device_id = previous_primary
        reason = 'tie_keep_previous'
    else:
        primary_device_id = v3_battery_device_id
        reason = 'tie_default_v3_battery'

    preferred_surplus_device_id = selected_ev_device_id if primary_device_id == v3_battery_device_id else v3_battery_device_id
    device_limits_w = {
        v3_battery_device_id: int(battery_limit_w),
        selected_ev_device_id: int(ev_limit_w),
    }
    changed = (
        quarter_key != (previous_quarter_key or '')
        or primary_device_id != (previous_primary or '')
    )

    return HaeoNetZeroPlan(
        active=True,
        quarter_key=quarter_key,
        primary_load=primary_device_id,
        primary_device_id=primary_device_id,
        preferred_surplus_device_id=preferred_surplus_device_id,
        device_limits_w=device_limits_w,
        reason=reason,
        changed=bool(changed),
    )
