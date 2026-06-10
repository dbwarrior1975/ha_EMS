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


def _normalized_adjustable_surplus_load(cfg):
    raw = str(getattr(cfg, 'adjustable_surplus_load', '') or '').strip().lower()
    if raw in ('ev_charger', 'ev', 'charger_current'):
        return 'EV_CHARGER'
    if raw in ('home_battery', 'battery', 'actuator_battery_setpoint_w'):
        return 'HOME_BATTERY'
    return 'HOME_BATTERY'


def _uses_ev_adjustable_mode(cfg):
    return _normalized_adjustable_surplus_load(cfg) == 'EV_CHARGER'


def _normalized_adjustable_primary_load(cfg):
    raw = str(getattr(cfg, 'adjustable_primary_load', '') or '').strip().lower()
    if raw in ('ev_charger', 'ev', 'charger_current'):
        return 'EV_CHARGER'
    if raw in ('home_battery', 'battery', 'actuator_battery_setpoint_w'):
        return 'HOME_BATTERY'
    return ''


def _battery_target_and_authority(
    profiles,
    cfg,
    m,
    haeo,
    nz,
    *,
    ev_burn_active=False,
    ev_release_pending=False,
    ev_target_w=0.0,
    adjustable_surplus_active=False,
    use_ev_primary_mode=False,
):
    battery_min_floor_w = None
    battery_min_floor_reason = 'not_applicable'
    adjustable_surplus_active_next = bool(adjustable_surplus_active)

    if profiles.control == ControlProfile.MANUAL:
        return int(round(m.current_battery_setpoint_w)), False, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.control == ControlProfile.MANUAL_SAFE:
        current = int(round(m.current_battery_setpoint_w))

        if profiles.guard == GuardProfile.DEGRADED:
            return 0, True, battery_min_floor_w, battery_min_floor_reason, False

        if profiles.guard == GuardProfile.BATTERY_PROTECT:
            return max(current, 0), True, battery_min_floor_w, battery_min_floor_reason, False

        if profiles.guard == GuardProfile.STRICT_LIMITS:
            limit = int(cfg.strict_limits_max_w)
            return min(max(current, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason, False

        return current, False, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.goal == GoalProfile.NET_ZERO:
        effective_rpnz_w = nz.rpnz_w
        min_charge_floor_w = 100.0
        ev_primary_positive_rpnz = bool(use_ev_primary_mode) and float(nz.rpnz_w) > 0.0
        adjustable_is_home_battery = _normalized_adjustable_surplus_load(cfg) == 'HOME_BATTERY'
        configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)

        if use_ev_primary_mode:
            # EV primary path does not use legacy battery default floor.
            min_charge_floor_w = float(cfg.nz_battery_floor_ev_active_w)
            battery_min_floor_reason = 'ev_active_floor_override'

            battery_min_floor_w = float(min_charge_floor_w)
            effective_rpnz_w = float(nz.rpnz_w) - float(max(ev_target_w, 0.0))

            ev_max_w = float(cfg.ev_max_current_a * max(cfg.ev_charger_phases, 1) * 230)
            if (
                ev_burn_active
                and (not ev_primary_positive_rpnz)
                and float(nz.rpnz_w) >= 0.0
                and float(nz.required_power_consumption_kw) * 1000.0 <= ev_max_w
            ):
                raw = int(round(min_charge_floor_w))
                if profiles.guard == GuardProfile.DEGRADED:
                    return 0, True, battery_min_floor_w, battery_min_floor_reason, False
                if profiles.guard == GuardProfile.BATTERY_PROTECT:
                    return max(raw, 0), True, battery_min_floor_w, battery_min_floor_reason, False
                if profiles.guard == GuardProfile.STRICT_LIMITS:
                    limit = int(cfg.strict_limits_max_w)
                    return min(max(raw, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason, False
                return raw, True, battery_min_floor_w, battery_min_floor_reason, False

        if battery_min_floor_w is None:
            battery_min_floor_w = float(min_charge_floor_w)

        if ev_primary_positive_rpnz:
            raw = int(round(min_charge_floor_w))
        else:
            if (
                use_ev_primary_mode
                and ev_burn_active
                and float(nz.rpnz_w) <= 0.0
                and (not ev_release_pending)
            ):
                adjustable_surplus_active_next = False
                raw = int(round(min_charge_floor_w))
            else:
                adjustable_surplus_active_next = False
                raw = candidate_sp_net_zero(
                    rpnz_w=effective_rpnz_w,
                    grid_actual_w=m.grid_power_w,
                    current_sp_w=m.current_battery_setpoint_w,
                    deadband_w=cfg.deadband_w,
                    ramp_w=cfg.ramp_max_w,
                    max_sp_w=cfg.max_solar_charge_w,
                    min_charge_floor_w=min_charge_floor_w,
                )

        if (
            use_ev_primary_mode
            and adjustable_is_home_battery
            and bool(adjustable_surplus_active)
            and float(nz.rpnz_w) >= 0.0
        ):
            activation_clamped_w = min(max(configured_activation_w, 0.0), float(cfg.max_solar_charge_w))
            raw = int(round(activation_clamped_w))

        activation_gate_active = (
            adjustable_is_home_battery
            and configured_activation_w > 0.0
            and (not bool(adjustable_surplus_active))
            and float(nz.required_power_consumption_kw) < (configured_activation_w / 1000.0)
        )
        if activation_gate_active:
            current_sp = int(round(m.current_battery_setpoint_w))
            # Activation gate protects only positive charging ramp-up before activation.
            # Negative-domain recovery toward zero must stay under normal controller dynamics.
            if raw > current_sp and raw >= 0 and current_sp >= 0:
                raw = current_sp
                battery_min_floor_reason = 'activation_gate_hold'
    elif haeo.effective_forecast == ForecastProfile.HAEO and profiles.goal in (GoalProfile.MAX_EXPORT, GoalProfile.CHEAP_GRID_CHARGE):
        raw = int(round(haeo.battery_target_kw * 1000.0))
    elif profiles.goal == GoalProfile.MAX_EXPORT:
        raw = -4000
    elif profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        raw = 100
    else:
        raw = int(round(cfg.default_sp_w))

    if profiles.guard == GuardProfile.DEGRADED:
        return 0, True, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return max(raw, 0), True, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.guard == GuardProfile.STRICT_LIMITS:
        limit = int(cfg.strict_limits_max_w)
        return min(max(raw, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason, False

    return raw, True, battery_min_floor_w, battery_min_floor_reason, adjustable_surplus_active_next


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
    adjustable_surplus_active,
    ev_release_pending,
    pv_power_kw,
    ev_hard_off_active,
    ev_low_pv_cycles,
    rpc_kw,
    rpnz_w,
    grid_power_w,
    current_ev_current_a,
    use_ev_adjustable_mode=False,
    use_ev_primary_mode=False,
    use_ev_primary_home_battery_combo=False,
):
    current_a = ev_strategy_current_a(
        profiles,
        cfg,
        haeo,
        burn_active,
    )

    if (
        burn_active
        and adjustable_surplus_active
        and (not ev_release_pending)
        and use_ev_adjustable_mode
        and float(rpnz_w) > 0.0
    ):
        current_a = int(cfg.ev_max_current_a)

    if (
        burn_active
        and (not ev_release_pending)
        and use_ev_adjustable_mode
        and float(rpnz_w) > 0.0
        and int(max(current_ev_current_a, 0)) >= int(cfg.ev_max_current_a)
    ):
        current_a = int(cfg.ev_max_current_a)

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
        if use_ev_primary_home_battery_combo:
            return 'hard_off', 0, next_low_pv_cycles, True
        ev_threshold_kw = max(
            ((cfg.ev_max_current_a - cfg.ev_min_current_a) * max(cfg.ev_charger_phases, 1) * 230) / 1000.0,
            0,
        )
        if rpc_kw >= ev_threshold_kw:
            return 'burn', int(cfg.ev_max_current_a), next_low_pv_cycles, False
        return 'hard_off', 0, next_low_pv_cycles, True

    if hard_off_allowed and next_low_pv_cycles >= int(cfg.ev_hard_off_low_pv_cycles):
        return 'hard_off', 0, next_low_pv_cycles, True

    restore_min_a = int(cfg.ev_min_current_a) if use_ev_primary_mode else 0
    return 'restore_min', restore_min_a, next_low_pv_cycles, False


def _primary_ev_step_current_a(cfg, envelope_w):
    phases = max(int(cfg.ev_charger_phases), 1)
    per_amp_w = float(phases * 230)
    positive_envelope_w = max(float(envelope_w), 0.0)
    raw_a = int(round(positive_envelope_w / per_amp_w))
    if raw_a <= 0:
        return 0

    min_a = max(1, int(cfg.ev_min_current_a))
    max_a = max(min_a, int(cfg.ev_max_current_a))
    step_a = max(1, int(getattr(cfg, 'ev_current_step_a', min_a) or min_a))

    if raw_a <= min_a:
        quantized_a = min_a
    else:
        # Quantize above minimum using configurable EV current steps.
        offset = raw_a - min_a
        quantized_a = min_a + (offset // step_a) * step_a

    return int(min(max(quantized_a, min_a), max_a))


def _primary_power_envelope_w(cfg, m, nz):
    phases = max(int(cfg.ev_charger_phases), 1)
    current_ev_w = float(max(int(max(m.charger_current_a, 0)), 0) * phases * 230)
    ev_max_w = float(int(cfg.ev_max_current_a) * phases * 230)
    return candidate_sp_net_zero(
        rpnz_w=float(nz.rpnz_w),
        grid_actual_w=float(m.grid_power_w),
        current_sp_w=current_ev_w,
        deadband_w=float(cfg.deadband_w),
        ramp_w=float(cfg.ramp_max_w),
        max_sp_w=ev_max_w,
        min_charge_floor_w=0.0,
    )


def _apply_force_rising_edge_freeze(
    now_ts,
    freeze_until_ts,
    freeze_s,
    relay1_force_on,
    relay2_force_on,
    prev_relay1_force_on,
    prev_relay2_force_on,
):
    freeze_until = freeze_until_ts
    rising_edge = (relay1_force_on and (not prev_relay1_force_on)) or (
        relay2_force_on and (not prev_relay2_force_on)
    )
    if rising_edge:
        target_freeze = now_ts + freeze_s
        if freeze_until is None:
            freeze_until = target_freeze
        else:
            freeze_until = max(float(freeze_until), float(target_freeze))
    return freeze_until


def compute_net_zero_engine_outputs(
    profiles, cfg, m, haeo, nz, now_ts, *,
    freeze_until_ts,
    ev_burn_active,
    relay1_surplus_allowed,
    relay2_surplus_allowed,
    relay1_force_on,
    relay2_force_on,
    relay1_net_zero_active,
    relay2_net_zero_active,
    adjustable_surplus_active=False,
    pv_power_kw=None,
    ev_hard_off_active=False,
    ev_low_pv_cycles=0,
    ev_hard_off_release_ready_cycles=0,
    prev_relay1_force_on=False,
    prev_relay2_force_on=False,
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

    adjustable_surplus_load = _normalized_adjustable_surplus_load(cfg)
    requested_primary_load = _normalized_adjustable_primary_load(cfg)
    if not requested_primary_load:
        adjustable_primary_load = adjustable_surplus_load
        primary_surplus_combo_valid = True
        primary_surplus_combo_reason = 'implicit_legacy_default'
    else:
        adjustable_primary_load = requested_primary_load
        primary_surplus_combo_valid = adjustable_primary_load != adjustable_surplus_load
        primary_surplus_combo_reason = 'supported_cross_combo' if primary_surplus_combo_valid else 'unsupported_same_target_combo'

    if not primary_surplus_combo_valid:
        adjustable_primary_load = 'HOME_BATTERY' if adjustable_surplus_load == 'EV_CHARGER' else 'EV_CHARGER'
        primary_surplus_combo_reason = 'fallback_to_cross_combo'

    use_ev_surplus_mode = adjustable_surplus_load == 'EV_CHARGER'
    use_ev_primary_mode = adjustable_primary_load == 'EV_CHARGER'
    use_ev_primary_home_battery_combo = use_ev_primary_mode and (not use_ev_surplus_mode)

    configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)
    if configured_activation_w > 0.0:
        adjustable_threshold_kw = configured_activation_w / 1000.0
    else:
        # Legacy fallback keeps previous behavior when explicit activation threshold is not configured.
        adjustable_threshold_kw = (
            max(
                ((cfg.ev_max_current_a - cfg.ev_min_current_a) * max(cfg.ev_charger_phases, 1) * 230) / 1000.0,
                0,
            )
            if use_ev_surplus_mode
            else float(cfg.max_solar_charge_w) / 1000.0
        )
    adjustable_active_current = bool(adjustable_surplus_active or ev_burn_active)
    adjustable_priority = int(getattr(cfg, 'adjustable_surplus_load_priority', cfg.ev_priority))
    relay1_enabled = bool(relay1_surplus_allowed)
    relay2_enabled = bool(relay2_surplus_allowed)
    targets = (
        SurplusTargetConfig(
            'ADJUSTABLE',
            priority=adjustable_priority,
            rank=1,
            threshold_kw=adjustable_threshold_kw,
            enabled=True,
            force_on=False,
            active=adjustable_active_current,
        ),
        SurplusTargetConfig(
            'RELAY1',
            priority=cfg.relay1_priority,
            rank=2,
            threshold_kw=cfg.relay1_power_kw,
            enabled=relay1_enabled,
            force_on=relay1_force_on,
            active=relay1_net_zero_active,
        ),
        SurplusTargetConfig(
            'RELAY2',
            priority=cfg.relay2_priority,
            rank=3,
            threshold_kw=cfg.relay2_power_kw,
            enabled=relay2_enabled,
            force_on=relay2_force_on,
            active=relay2_net_zero_active,
        ),
    )

    surplus_active = net_zero_surplus_policy_active(profiles, eff_fc)

    effective_freeze_until_ts = _apply_force_rising_edge_freeze(
        now_ts=now_ts,
        freeze_until_ts=freeze_until_ts,
        freeze_s=cfg.surplus_freeze_s,
        relay1_force_on=relay1_force_on,
        relay2_force_on=relay2_force_on,
        prev_relay1_force_on=prev_relay1_force_on,
        prev_relay2_force_on=prev_relay2_force_on,
    )

    surplus_inp = SurplusDispatchInput(
        policy_active=surplus_active,
        freeze_until_ts=effective_freeze_until_ts,
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

    primary_release_target = 'ADJUSTABLE'
    low_pv = (
        pv_power_kw is not None
        and float(pv_power_kw) < float(cfg.ev_hard_off_pv_threshold_kw)
    )
    battery_to_ev_loop_risk = (
        low_pv
        and float(m.current_battery_setpoint_w) < 0.0
        and int(cfg.ev_force_current_a) <= 0
    )

    ev_min_power_kw = (
        float(int(cfg.ev_min_current_a) * max(int(cfg.ev_charger_phases), 1) * 230) / 1000.0
    )
    hard_off_release_rpc_kw = ev_min_power_kw if use_ev_primary_home_battery_combo else 0.0
    hard_off_release_cycles_required = max(1, int(getattr(cfg, 'ev_hard_off_release_cycles', 2) or 2))
    hard_off_release_condition = (
        use_ev_primary_home_battery_combo
        and ev_hard_off_active
        and (pv_power_kw is not None)
        and float(pv_power_kw) >= float(cfg.ev_hard_off_pv_threshold_kw)
        and float(nz.required_power_consumption_kw) >= float(hard_off_release_rpc_kw)
        and (not battery_to_ev_loop_risk)
    )
    hard_off_release_ready_cycles_next = (
        int(ev_hard_off_release_ready_cycles) + 1
        if hard_off_release_condition
        else 0
    )

    # V2: primary EV path is continuously evaluated from RPNZ even when
    # ADJUSTABLE dispatch target is HOME_BATTERY.
    ev_primary_burn_active = (
        use_ev_primary_mode
        and (
            (
                (not use_ev_primary_home_battery_combo)
                and float(nz.rpnz_w) > 0.0
            )
            or (
                use_ev_primary_home_battery_combo
                and (
                    (
                        (not ev_hard_off_active)
                        and float(nz.rpnz_w) > 0.0
                    )
                    or (
                        ev_hard_off_active
                        and hard_off_release_ready_cycles_next >= hard_off_release_cycles_required
                    )
                )
            )
        )
        and (not battery_to_ev_loop_risk)
    )
    # Keep legacy deterministic dispatch-tied burn when EV is the ADJUSTABLE target.
    ev_surplus_burn_active = (
        use_ev_surplus_mode
        and adjustable_active_current
        and (not battery_to_ev_loop_risk)
    )
    ev_burn_for_cycle = ev_surplus_burn_active or ev_primary_burn_active
    ev_policy_mode, ev_current_a, next_low_pv_cycles, ev_hard_off_active_next = _ev_policy_mode_and_current(
        profiles,
        cfg,
        normalized_haeo,
        burn_active=ev_burn_for_cycle,
        adjustable_surplus_active=adjustable_active_current,
        ev_release_pending=(surplus_decision.release == primary_release_target),
        pv_power_kw=pv_power_kw,
        ev_hard_off_active=ev_hard_off_active,
        ev_low_pv_cycles=ev_low_pv_cycles,
        rpc_kw=nz.required_power_consumption_kw,
        rpnz_w=nz.rpnz_w,
        grid_power_w=m.grid_power_w,
        current_ev_current_a=m.charger_current_a,
        use_ev_adjustable_mode=use_ev_surplus_mode,
        use_ev_primary_mode=use_ev_primary_mode,
        use_ev_primary_home_battery_combo=use_ev_primary_home_battery_combo,
    )

    if (
        profiles.goal == GoalProfile.NET_ZERO
        and use_ev_surplus_mode
        and (surplus_decision.clear_all or surplus_decision.release == primary_release_target)
        and ev_policy_mode != 'skip'
    ):
        ev_policy_mode = 'restore_min'
        ev_current_a = 0

    primary_envelope_w = None
    if use_ev_primary_mode and (not use_ev_surplus_mode) and ev_policy_mode == 'burn':
        primary_envelope_w = _primary_power_envelope_w(cfg, m, nz)
        stepped_primary_a = _primary_ev_step_current_a(cfg, primary_envelope_w)
        ev_current_a = stepped_primary_a
        ev_policy_mode = 'burn' if stepped_primary_a > 0 else 'restore_min'

    ev_target_w = float(max(ev_current_a, 0) * max(cfg.ev_charger_phases, 1) * 230)
    ev_burn_active_for_battery = (
        (ev_policy_mode == 'burn' and int(max(ev_current_a, 0)) > 0)
        or (
            use_ev_primary_mode
            and ev_policy_mode == 'restore_min'
            and int(max(ev_current_a, 0)) > 0
            and not battery_to_ev_loop_risk
        )
    )
    battery_target_w, battery_write_enabled, battery_min_floor_w, battery_min_floor_reason, adjustable_surplus_active_next = _battery_target_and_authority(
        profiles,
        cfg,
        m,
        normalized_haeo,
        nz,
        ev_burn_active=ev_burn_active_for_battery,
        ev_release_pending=(surplus_decision.release == primary_release_target),
        ev_target_w=ev_target_w,
        adjustable_surplus_active=adjustable_surplus_active,
        use_ev_primary_mode=use_ev_primary_mode,
    )

    return NetZeroOutputs(
        battery_target_w=battery_target_w,
        battery_write_enabled=battery_write_enabled,
        ev_current_a=ev_current_a,
        relay1_command=relay_strategy_command(profiles, relay1_surplus_allowed, relay1_force_on, relay1_net_zero_active),
        relay2_command=relay_strategy_command(profiles, relay2_surplus_allowed, relay2_force_on, relay2_net_zero_active),
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
            'surplus_primary_target': primary_release_target,
            'surplus_freeze_until_ts': (
                surplus_decision.freeze_until_ts
                if surplus_decision.freeze_until_ts is not None
                else effective_freeze_until_ts
            ),
            'surplus_rpc_kw': nz.required_power_consumption_kw,
            'surplus_rpnz_w': nz.rpnz_w,
            'battery_write_enabled': battery_write_enabled,
            'ev_policy_mode': ev_policy_mode,
            'ev_low_pv_cycles': next_low_pv_cycles,
            'ev_hard_off_active': ev_hard_off_active_next,
            'ev_hard_off_release_ready_cycles': hard_off_release_ready_cycles_next,
            'ev_hard_off_release_cycles_required': hard_off_release_cycles_required,
            'ev_hard_off_release_rpc_kw': hard_off_release_rpc_kw,
            'pv_power_kw': pv_power_kw,
            'ev_hard_off_pv_threshold_kw': cfg.ev_hard_off_pv_threshold_kw,
            'battery_to_ev_loop_risk': bool(battery_to_ev_loop_risk),
            'ev_primary_charge_mode': bool(cfg.ev_primary_charge_mode),
            'ev_adjustable_mode': bool(use_ev_surplus_mode),
            'ev_primary_burn_active': bool(ev_primary_burn_active),
            'ev_surplus_burn_active': bool(ev_surplus_burn_active),
            'ev_current_step_a': int(getattr(cfg, 'ev_current_step_a', cfg.ev_min_current_a)),
            'primary_power_envelope_w': primary_envelope_w,
            'adjustable_surplus_load_priority': int(getattr(cfg, 'adjustable_surplus_load_priority', cfg.ev_priority)),
            'adjustable_surplus_load': adjustable_surplus_load,
            'adjustable_surplus_activation': configured_activation_w,
            'adjustable_primary_load': adjustable_primary_load,
            'primary_surplus_combo_valid': bool(primary_surplus_combo_valid),
            'primary_surplus_combo_reason': primary_surplus_combo_reason,
            'battery_min_floor_w': battery_min_floor_w,
            'battery_min_floor_reason': battery_min_floor_reason,
            'surplus_adjustable_active': bool(adjustable_surplus_active_next),
            'prev_relay1_force_on': bool(relay1_force_on),
            'prev_relay2_force_on': bool(relay2_force_on),
        },
    )
