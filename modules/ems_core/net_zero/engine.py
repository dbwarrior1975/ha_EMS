from ems_core.domain.models import (
    ControlProfile, GoalProfile, ForecastProfile, GuardProfile, DominantLimitation,
    HaeoTargets, SurplusTargetConfig, SurplusDispatchInput, NetZeroOutputs
)
from ems_core.net_zero.battery_controller import candidate_sp_net_zero
from ems_core.net_zero.load_projection import ev_strategy_current_a, relay_strategy_command
from ems_core.net_zero.surplus_allocator import compute_surplus_dispatch, next_target, release_target, active_stack


def configured_forecast(control, forecast_profile):
    if control in (ControlProfile.MANUAL, ControlProfile.MANUAL_SAFE):
        return ForecastProfile.NONE
    if forecast_profile == ForecastProfile.HAEO:
        return ForecastProfile.HAEO
    if forecast_profile == ForecastProfile.NONE and control == ControlProfile.HORIZON_BY_HAEO:
        return ForecastProfile.HAEO
    return ForecastProfile.NONE


def effective_forecast(configured, haeo_fresh):
    return ForecastProfile.HAEO if configured == ForecastProfile.HAEO and haeo_fresh else ForecastProfile.NONE


def dominant_limitation(profiles, configured_fc, effective_fc):
    if profiles.guard == GuardProfile.DEGRADED:
        return DominantLimitation.SYSTEM_DEGRADED
    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return DominantLimitation.BATTERY_SOC_LIMIT
    if profiles.control == ControlProfile.MANUAL:
        return DominantLimitation.USER_MANUAL_OVERRIDE
    if profiles.control == ControlProfile.MANUAL_SAFE:
        return DominantLimitation.MANUAL_SAFE_ACTIVE
    if profiles.guard == GuardProfile.STRICT_LIMITS:
        return DominantLimitation.STRICT_POWER_LIMITS
    if configured_fc == ForecastProfile.HAEO and effective_fc != ForecastProfile.HAEO:
        return DominantLimitation.FORECAST_FALLBACK_LOCAL
    return DominantLimitation.OPTIMIZATION_ACTIVE


def explain(profiles, configured_fc, effective_fc):
    if profiles.guard == GuardProfile.DEGRADED:
        return 'Guard forces degraded fallback'
    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return 'Guard prevents harmful battery discharge'
    if profiles.control == ControlProfile.MANUAL:
        return 'User manual control active'
    if profiles.control == ControlProfile.MANUAL_SAFE:
        return 'User manual control with guard enforcement'
    if profiles.goal == GoalProfile.NET_ZERO and configured_fc == ForecastProfile.HAEO and effective_fc == ForecastProfile.NONE:
        return 'Net zero goal with configured HAEO forecast, but stale forecast causes local fallback'
    if profiles.goal == GoalProfile.NET_ZERO and effective_fc == ForecastProfile.HAEO:
        return 'Net zero goal with HAEO forecast visible, but local policy remains dominant'
    if profiles.goal == GoalProfile.NET_ZERO:
        return 'Local quarter balancing without forecast'
    if profiles.goal == GoalProfile.MAX_EXPORT and effective_fc == ForecastProfile.HAEO:
        return 'Export-oriented policy with HAEO forecast assistance'
    if profiles.goal == GoalProfile.CHEAP_GRID_CHARGE and effective_fc == ForecastProfile.HAEO:
        return 'Cheap charge policy with HAEO forecast assistance'
    if profiles.goal == GoalProfile.MAX_EXPORT:
        return 'Local export-oriented policy'
    if profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        return 'Local cheap-charge policy'
    return 'Policy active'


def _battery_target_and_authority(profiles, cfg, m, haeo, nz):
    # MANUAL = optimizer may still observe, but writer must not touch battery shadow setpoint
    if profiles.control == ControlProfile.MANUAL:
        return int(round(m.current_battery_setpoint_w)), False

    # MANUAL_SAFE = user-oriented battery control, but guard may clamp unsafe values
    if profiles.control == ControlProfile.MANUAL_SAFE:
        current = int(round(m.current_battery_setpoint_w))

        if profiles.guard == GuardProfile.DEGRADED:
            return 0, True

        if profiles.guard == GuardProfile.BATTERY_PROTECT:
            return max(current, 0), True

        if profiles.guard == GuardProfile.STRICT_LIMITS:
            limit = int(cfg.strict_limits_max_w)
            return min(max(current, -limit), limit), True

        # In ordinary MANUAL_SAFE, leave current value untouched
        return current, False

    # Automatic / forecast-driven paths
    if profiles.goal == GoalProfile.NET_ZERO:
        raw = candidate_sp_net_zero(
            rpnz_w=nz.rpnz_w,
            grid_actual_w=m.grid_power_w,
            current_sp_w=m.current_battery_setpoint_w,
            deadband_w=cfg.deadband_w,
            ramp_w=cfg.ramp_max_w,
            max_sp_w=cfg.max_solar_charge_w,
        )
    elif haeo.effective_forecast == ForecastProfile.HAEO and profiles.goal in (GoalProfile.MAX_EXPORT, GoalProfile.CHEAP_GRID_CHARGE):
        raw = int(round(haeo.battery_target_kw * 1000.0))
    elif profiles.goal == GoalProfile.MAX_EXPORT:
        raw = -4000
    elif profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        raw = 100
    else:
        raw = int(round(cfg.default_sp_w))

    if profiles.guard == GuardProfile.DEGRADED:
        return 0, True

    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return max(raw, 0), True

    if profiles.guard == GuardProfile.STRICT_LIMITS:
        limit = int(cfg.strict_limits_max_w)
        return min(max(raw, -limit), limit), True

    return raw, True


def net_zero_surplus_policy_active(profiles, effective_fc):
    return (
        profiles.control == ControlProfile.AUTOMATIC
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and effective_fc == ForecastProfile.NONE
    )


def _ev_policy_mode_and_current(
    profiles, cfg, haeo, *,
    burn_active,
    pv_power_kw,
    ev_hard_off_active,
    ev_low_pv_cycles,
    rpc_kw,
):
    current_a = ev_strategy_current_a(profiles, cfg, haeo, burn_active)

    if profiles.goal == GoalProfile.MAX_EXPORT and current_a == 0:
        return 'hard_off', 0, 0, False

    if current_a < 0:
        return 'skip', current_a, 0, False

    if current_a > 0:
        return 'burn', current_a, 0, False

    low_pv_threshold = float(cfg.ev_hard_off_pv_threshold_kw)
    low_pv = pv_power_kw is not None and float(pv_power_kw) < low_pv_threshold
    next_low_pv_cycles = int(ev_low_pv_cycles) + 1 if low_pv else 0

    hard_off_allowed = (
        profiles.control == ControlProfile.AUTOMATIC
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and not burn_active
        and cfg.ev_force_current_a <= 0
    )

    if hard_off_allowed and ev_hard_off_active:
        ev_threshold_kw = max(
            ((cfg.ev_max_current_a - cfg.ev_min_current_a) * max(cfg.ev_charger_phases, 1) * 230) / 1000.0,
            0,
        )
        if rpc_kw >= ev_threshold_kw:
            return 'burn', int(cfg.ev_max_current_a), next_low_pv_cycles, False
        return 'hard_off', 0, next_low_pv_cycles, True

    if hard_off_allowed and next_low_pv_cycles >= int(cfg.ev_hard_off_low_pv_cycles):
        return 'hard_off', 0, next_low_pv_cycles, True

    return 'restore_min', 0, next_low_pv_cycles, False


def compute_net_zero_engine_outputs(
    profiles, cfg, m, haeo, nz, now_ts, *,
    freeze_until_ts,
    ev_burn_active,
    relay1_enabled_import_zero,
    relay2_enabled_import_zero,
    relay1_force_on,
    relay2_force_on,
    relay1_net_zero_active,
    relay2_net_zero_active,
    pv_power_kw=None,
    ev_hard_off_active=False,
    ev_low_pv_cycles=0,
):
    conf_fc = configured_forecast(profiles.control, profiles.forecast)
    eff_fc = effective_forecast(conf_fc, haeo.fresh)

    normalized_haeo = HaeoTargets(
        effective_forecast=eff_fc,
        configured_forecast=conf_fc,
        fresh=haeo.fresh,
        battery_target_kw=haeo.battery_target_kw,
        ev_target_kw=haeo.ev_target_kw,
    )

    ev_threshold_kw = max(
        ((cfg.ev_max_current_a - cfg.ev_min_current_a) * max(cfg.ev_charger_phases, 1) * 230) / 1000.0,
        0,
    )

    targets = (
        SurplusTargetConfig(
            'EV',
            priority=cfg.ev_priority,
            rank=1,
            threshold_kw=ev_threshold_kw,
            enabled=True,
            force_on=False,
            active=ev_burn_active,
        ),
        SurplusTargetConfig(
            'RELAY1',
            priority=cfg.relay1_priority,
            rank=2,
            threshold_kw=cfg.relay1_power_kw,
            enabled=relay1_enabled_import_zero,
            force_on=relay1_force_on,
            active=relay1_net_zero_active,
        ),
        SurplusTargetConfig(
            'RELAY2',
            priority=cfg.relay2_priority,
            rank=3,
            threshold_kw=cfg.relay2_power_kw,
            enabled=relay2_enabled_import_zero,
            force_on=relay2_force_on,
            active=relay2_net_zero_active,
        ),
    )

    surplus_active = net_zero_surplus_policy_active(profiles, eff_fc)

    surplus_inp = SurplusDispatchInput(
        policy_active=surplus_active,
        freeze_until_ts=freeze_until_ts,
        rpc_kw=nz.required_power_consumption_kw,
        rpnz_w=nz.rpnz_w,
        targets=targets,
    )
    surplus_decision = compute_surplus_dispatch(surplus_inp, now_ts, cfg.surplus_freeze_s)
    nxt = next_target(targets)
    rel = release_target(targets)

    if surplus_decision.clear_all:
        decision_text = 'CLEAR_ALL'
    elif surplus_decision.activate:
        decision_text = 'ACTIVATE_' + surplus_decision.activate
    elif surplus_decision.release:
        decision_text = 'RELEASE_' + surplus_decision.release
    else:
        decision_text = 'NOOP'

    battery_target_w, battery_write_enabled = _battery_target_and_authority(
        profiles, cfg, m, normalized_haeo, nz
    )
    ev_policy_mode, ev_current_a, next_low_pv_cycles, ev_hard_off_active_next = _ev_policy_mode_and_current(
        profiles,
        cfg,
        normalized_haeo,
        burn_active=ev_burn_active,
        pv_power_kw=pv_power_kw,
        ev_hard_off_active=ev_hard_off_active,
        ev_low_pv_cycles=ev_low_pv_cycles,
        rpc_kw=nz.required_power_consumption_kw,
    )

    return NetZeroOutputs(
        battery_target_w=battery_target_w,
        battery_write_enabled=battery_write_enabled,
        ev_current_a=ev_current_a,
        relay1_command=relay_strategy_command(profiles, relay1_enabled_import_zero, relay1_force_on, relay1_net_zero_active),
        relay2_command=relay_strategy_command(profiles, relay2_enabled_import_zero, relay2_force_on, relay2_net_zero_active),
        surplus_policy_active=surplus_active,
        surplus_next_target=nxt.name if nxt else 'NONE',
        surplus_next_threshold_kw=round(nxt.threshold_kw, 3) if nxt else 0,
        surplus_release_candidate=rel.name if rel else 'NONE',
        surplus_dispatch_decision=decision_text,
        surplus_explanation=surplus_decision.explanation,
        effective_forecast=eff_fc,
        dominant_limitation=dominant_limitation(profiles, conf_fc, eff_fc),
        explanation=explain(profiles, conf_fc, eff_fc),
        attrs={
            'configured_forecast': conf_fc,
            'active_stack': active_stack(targets),
            'surplus_freeze_until_ts': surplus_decision.freeze_until_ts,
            'surplus_rpc_kw': nz.required_power_consumption_kw,
            'surplus_rpnz_w': nz.rpnz_w,
            'battery_write_enabled': battery_write_enabled,
            'ev_policy_mode': ev_policy_mode,
            'ev_low_pv_cycles': next_low_pv_cycles,
            'ev_hard_off_active': ev_hard_off_active_next,
            'pv_power_kw': pv_power_kw,
            'ev_hard_off_pv_threshold_kw': cfg.ev_hard_off_pv_threshold_kw,
        },
    )
