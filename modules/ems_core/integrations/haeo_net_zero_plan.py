from ems_core.domain.models import (
    ControlProfile,
    ForecastProfile,
    GoalProfile,
    GuardProfile,
    HaeoNetZeroPlan,
)
from ems_core.domain.ev_power import ev_max_power_w, ev_power_w_to_selector_current_a


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


def _ev_devices(cfg):
    if hasattr(cfg, 'devices_by_kind'):
        return tuple(cfg.devices_by_kind('EV_CHARGER'))
    return ()


def _default_ev_device_id(cfg):
    ev_devices = _ev_devices(cfg)
    if ev_devices:
        return str(ev_devices[0].device_id)
    return 'EV_CHARGER'


def _is_ev_device_id(cfg, device_id):
    device = _device_by_id(cfg, device_id)
    if device is not None:
        return str(getattr(device, 'kind', '')) == 'EV_CHARGER'
    return str(device_id or '') == 'EV_CHARGER'


def _selected_ev_device_id(cfg):
    adjustable_surplus_load = str(getattr(cfg, 'adjustable_surplus_load', '') or '')
    adjustable_primary_load = str(getattr(cfg, 'adjustable_primary_load', '') or '')
    if _is_ev_device_id(cfg, adjustable_surplus_load):
        return adjustable_surplus_load
    if _is_ev_device_id(cfg, adjustable_primary_load):
        return adjustable_primary_load
    return _default_ev_device_id(cfg)


def _ev_plan_params(cfg, ev_device_id):
    device = _device_by_id(cfg, ev_device_id)
    if device is None or str(getattr(device, 'kind', '')) != 'EV_CHARGER':
        return {
            'ev_limit_w_cap': int(ev_max_power_w(cfg)),
            'phases': int(getattr(cfg, 'ev_charger_phases', 1)),
            'max_current_a': int(getattr(cfg, 'ev_max_current_a', 0)),
            'min_current_a': int(getattr(cfg, 'ev_min_current_a', 0)),
            'step_a': int(getattr(cfg, 'ev_current_step_a', 4)),
        }

    adapter = device.adapter
    capabilities = device.capabilities
    return {
        'ev_limit_w_cap': int(round(float(capabilities.max_absorb_w))),
        'phases': int(round(float(adapter.phases))),
        'max_current_a': int(round(float(adapter.current_max_a))),
        'min_current_a': int(round(float(adapter.current_min_a))),
        'step_a': int(round(float(adapter.current_step_a))),
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

    battery_limit_w = min(_positive_w(haeo.battery_target_kw), int(round(float(cfg.max_solar_charge_w))))

    ev_params = _ev_plan_params(cfg, selected_ev_device_id)
    ev_limit_w = min(_positive_w(haeo.ev_target_kw), int(ev_params['ev_limit_w_cap']))
    ev_limit_a = ev_power_w_to_selector_current_a(
        ev_limit_w,
        ev_params['phases'],
        ev_params['max_current_a'],
        min_a=ev_params['min_current_a'],
        step_a=ev_params['step_a'],
    )

    if battery_limit_w <= 0 and ev_limit_w <= 0:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='zero_forecast')

    previous_primary = previous_primary_device_id or previous_primary_load

    if battery_limit_w > ev_limit_w:
        primary_device_id = 'HOME_BATTERY'
        reason = 'battery_forecast_larger'
    elif ev_limit_w > battery_limit_w:
        primary_device_id = selected_ev_device_id
        reason = 'ev_forecast_larger'
    elif previous_primary == 'HOME_BATTERY' or _is_ev_device_id(cfg, previous_primary):
        primary_device_id = previous_primary
        reason = 'tie_keep_previous'
    else:
        primary_device_id = 'HOME_BATTERY'
        reason = 'tie_default_home_battery'

    adjustable_device_id = selected_ev_device_id if primary_device_id == 'HOME_BATTERY' else 'HOME_BATTERY'
    device_limits_w = {
        'HOME_BATTERY': int(battery_limit_w),
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
        adjustable_surplus_load=adjustable_device_id,
        primary_device_id=primary_device_id,
        adjustable_device_id=adjustable_device_id,
        device_limits_w=device_limits_w,
        battery_limit_w=int(battery_limit_w),
        ev_limit_w=int(ev_limit_w),
        ev_limit_a=int(ev_limit_a),
        reason=reason,
        changed=bool(changed),
    )
