from ems_core.domain.models import (
    ControlProfile,
    ForecastProfile,
    GoalProfile,
    GuardProfile,
    HaeoNetZeroPlan,
)
from ems_core.integrations.haeo_horizon import ev_kw_to_selector_current_a


def quarter_key_for_ts(now_ts):
    quarter_start_ts = int(float(now_ts) // 900) * 900
    return str(quarter_start_ts)


def _positive_w(kw):
    try:
        return max(int(round(float(kw) * 1000.0)), 0)
    except (TypeError, ValueError):
        return 0


def compute_haeo_net_zero_plan(
    profiles,
    cfg,
    haeo,
    now_ts,
    *,
    previous_quarter_key='',
    previous_primary_load='',
):
    quarter_key = quarter_key_for_ts(now_ts)

    if profiles.control != ControlProfile.HORIZON_BY_HAEO:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, reason='control_not_horizon_by_haeo')
    if profiles.goal != GoalProfile.NET_ZERO:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, reason='goal_not_net_zero')
    if profiles.guard != GuardProfile.NORMAL_LIMITS:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, reason='guard_not_normal_limits')
    if haeo.configured_forecast != ForecastProfile.HAEO:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, reason='forecast_not_configured')
    if haeo.effective_forecast != ForecastProfile.HAEO or not haeo.fresh:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, reason='forecast_not_effective')

    battery_limit_w = min(_positive_w(haeo.battery_target_kw), int(round(float(cfg.max_solar_charge_w))))

    phases = max(int(cfg.ev_charger_phases), 1)
    ev_max_w = int(round(int(cfg.ev_max_current_a) * phases * 230))
    ev_limit_w = min(_positive_w(haeo.ev_target_kw), ev_max_w)
    ev_limit_a = ev_kw_to_selector_current_a(
        ev_limit_w / 1000.0,
        phases,
        cfg.ev_max_current_a,
        min_a=cfg.ev_min_current_a,
        step_a=getattr(cfg, 'ev_current_step_a', 4),
    )

    if battery_limit_w <= 0 and ev_limit_w <= 0:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, reason='zero_forecast')

    if battery_limit_w > ev_limit_w:
        primary_load = 'HOME_BATTERY'
        reason = 'battery_forecast_larger'
    elif ev_limit_w > battery_limit_w:
        primary_load = 'EV_CHARGER'
        reason = 'ev_forecast_larger'
    elif previous_primary_load in ('HOME_BATTERY', 'EV_CHARGER'):
        primary_load = previous_primary_load
        reason = 'tie_keep_previous'
    else:
        primary_load = 'HOME_BATTERY'
        reason = 'tie_default_home_battery'

    adjustable_surplus_load = 'EV_CHARGER' if primary_load == 'HOME_BATTERY' else 'HOME_BATTERY'
    changed = (
        quarter_key != (previous_quarter_key or '')
        or primary_load != (previous_primary_load or '')
    )

    return HaeoNetZeroPlan(
        active=True,
        quarter_key=quarter_key,
        primary_load=primary_load,
        adjustable_surplus_load=adjustable_surplus_load,
        battery_limit_w=int(battery_limit_w),
        ev_limit_w=int(ev_limit_w),
        ev_limit_a=int(ev_limit_a),
        reason=reason,
        changed=bool(changed),
    )
