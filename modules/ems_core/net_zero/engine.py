from ems_core.domain.models import (
    ControlProfile, GoalProfile, ForecastProfile, GuardProfile, DominantLimitation,
    HaeoTargets, HaeoNetZeroPlan, SurplusTargetConfig, SurplusDispatchInput, NetZeroOutputs,
    DevicePolicy,
)
from ems_core.domain.ev_power import (
    ev_current_a_to_power_w,
    ev_max_power_w,
    ev_min_power_w,
    ev_phase_power_w,
    ev_power_step_w,
)
from ems_core.net_zero.battery_controller import candidate_sp_net_zero
from ems_core.net_zero.load_projection import ev_strategy_current_a, relay_strategy_command
from ems_core.net_zero.surplus_allocator import (
    active_device_stack,
    active_stack,
    compute_surplus_device_dispatch,
    compute_surplus_dispatch,
    next_device_target,
    next_target,
    release_device_target,
    release_target,
)
from ems_core.net_zero.surplus_device_targets import (
    build_surplus_device_targets,
    device_dispatch_to_legacy_dispatch,
    device_targets_payload,
    device_targets_to_legacy_targets,
)


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


def explain(profiles, configured_fc, effective_fc, haeo_nz_plan_active=False):
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
    if profiles.goal == GoalProfile.NET_ZERO and haeo_nz_plan_active:
        return 'HAEO net zero plan active'
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


def _normalized_discharge_limit_w(cfg):
    configured = float(getattr(cfg, 'max_battery_discharge_w', cfg.strict_limits_max_w))
    # Canonical config is negative (export/discharge domain), but keep
    # legacy positive magnitude values backward-compatible.
    if configured < 0.0:
        return int(round(abs(configured))), 'canonical_negative', configured
    if configured > 0.0:
        return int(round(configured)), 'legacy_positive', configured
    return 0, 'zero_discharge', configured


def _normal_limits_discharge_cap(raw, cfg):
    limit, _, _ = _normalized_discharge_limit_w(cfg)
    return max(int(raw), -limit)


def _battery_protect_charge_floor_w(cfg):
    return int(round(max(float(getattr(cfg, 'battery_protect_charge_floor_w', 0.0)), 0.0)))


def _haeo_plan_primary_device_id(plan):
    return getattr(plan, 'primary_device_id', '') or getattr(plan, 'primary_load', '')


def _haeo_plan_adjustable_device_id(plan):
    return getattr(plan, 'adjustable_device_id', '') or getattr(plan, 'adjustable_surplus_load', '')


def _haeo_plan_device_limit_w(plan, device_id, legacy_limit_w=0):
    limits = getattr(plan, 'device_limits_w', {}) or {}
    if isinstance(limits, dict) and device_id in limits:
        return int(limits.get(device_id, 0) or 0)
    return int(legacy_limit_w or 0)


def _decision_text_from_dispatch(surplus_decision, combo_change_requires_clear):
    if combo_change_requires_clear:
        return 'CLEAR_ALL'
    if surplus_decision.clear_all:
        return 'CLEAR_ALL'
    if surplus_decision.activate:
        return 'ACTIVATE_' + surplus_decision.activate
    if surplus_decision.release:
        return 'RELEASE_' + surplus_decision.release
    return 'NOOP'


def _dispatch_action_and_target(decision_text):
    text = str(decision_text or 'NOOP')
    if text == 'CLEAR_ALL':
        return 'CLEAR_ALL', ''
    if text.startswith('ACTIVATE_'):
        return 'ACTIVATE', text[len('ACTIVATE_'):]
    if text.startswith('RELEASE_'):
        return 'RELEASE', text[len('RELEASE_'):]
    return 'NOOP', ''


def _device_id_for_decision_name(targets, decision_name):
    if not decision_name:
        return ''
    for target in targets:
        if target.decision_name == decision_name:
            return target.device_id
    return ''


def _dispatch_action_and_device_id_from_device_dispatch(surplus_decision, combo_change_requires_clear):
    if combo_change_requires_clear or surplus_decision.clear_all:
        return 'CLEAR_ALL', ''
    if surplus_decision.activate:
        return 'ACTIVATE', surplus_decision.activate
    if surplus_decision.release:
        return 'RELEASE', surplus_decision.release
    return 'NOOP', ''


def _kw_to_w(power_kw):
    return int(round(float(power_kw) * 1000.0))


def _device_policy_payload(policy):
    payload = {
        'device_id': policy.device_id,
        'target_w': int(policy.target_w),
        'enabled': bool(policy.enabled),
        'mode': policy.mode,
        'reason': policy.reason,
    }
    if policy.device_id == 'EV_CHARGER' and policy.current_a is not None:
        payload['current_a'] = int(policy.current_a)
    return payload


def _device_policy_payloads(device_policies):
    payloads = []
    for policy in device_policies:
        payloads.append(_device_policy_payload(policy))
    return tuple(payloads)


def _build_device_policies(
    cfg,
    *,
    battery_target_w,
    battery_write_enabled,
    ev_current_a,
    ev_target_w,
    ev_policy_mode,
    relay1_command,
    relay2_command,
):
    relay1_target_w = _kw_to_w(getattr(cfg, 'relay1_power_kw', 0.0)) if int(relay1_command) > 0 else 0
    relay2_target_w = _kw_to_w(getattr(cfg, 'relay2_power_kw', 0.0)) if int(relay2_command) > 0 else 0
    return (
        DevicePolicy(
            device_id='HOME_BATTERY',
            target_w=int(round(float(battery_target_w))),
            enabled=bool(battery_write_enabled),
            mode='power',
            reason='battery_policy',
        ),
        DevicePolicy(
            device_id='EV_CHARGER',
            target_w=int(round(float(ev_target_w))),
            enabled=int(ev_current_a) > 0,
            mode=str(ev_policy_mode),
            reason='ev_policy',
            current_a=int(ev_current_a),
        ),
        DevicePolicy(
            device_id='RELAY1',
            target_w=relay1_target_w,
            enabled=int(relay1_command) > 0,
            mode='skip' if int(relay1_command) < 0 else 'relay',
            reason='relay_policy',
        ),
        DevicePolicy(
            device_id='RELAY2',
            target_w=relay2_target_w,
            enabled=int(relay2_command) > 0,
            mode='skip' if int(relay2_command) < 0 else 'relay',
            reason='relay_policy',
        ),
    )


def _legacy_outputs_from_device_policies(device_policies):
    by_id = {}
    for policy in device_policies:
        by_id[policy.device_id] = policy

    ev_policy = by_id['EV_CHARGER']
    relay1_policy = by_id['RELAY1']
    relay2_policy = by_id['RELAY2']

    if ev_policy.current_a is None:
        ev_current_a = 0
    else:
        ev_current_a = int(ev_policy.current_a)

    if relay1_policy.mode == 'skip':
        relay1_command = -1
    else:
        relay1_command = 1 if relay1_policy.enabled else 0

    if relay2_policy.mode == 'skip':
        relay2_command = -1
    else:
        relay2_command = 1 if relay2_policy.enabled else 0

    return {
        'battery_target_w': int(by_id['HOME_BATTERY'].target_w),
        'battery_write_enabled': bool(by_id['HOME_BATTERY'].enabled),
        'ev_current_a': int(ev_current_a),
        'relay1_command': int(relay1_command),
        'relay2_command': int(relay2_command),
    }


def _device_policy_parity_mismatch(device_policies, *, battery_target_w, battery_write_enabled, ev_current_a, relay1_command, relay2_command):
    derived = _legacy_outputs_from_device_policies(device_policies)
    mismatches = []
    if derived['battery_target_w'] != int(round(float(battery_target_w))):
        mismatches.append('HOME_BATTERY.target_w')
    if derived['battery_write_enabled'] != bool(battery_write_enabled):
        mismatches.append('HOME_BATTERY.enabled')
    if derived['ev_current_a'] != int(ev_current_a):
        mismatches.append('EV_CHARGER.current_a')
    if derived['relay1_command'] != int(relay1_command):
        mismatches.append('RELAY1.command')
    if derived['relay2_command'] != int(relay2_command):
        mismatches.append('RELAY2.command')
    return ','.join(mismatches)


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
    haeo_nz_plan=None,
):
    battery_min_floor_w = None
    battery_min_floor_reason = 'not_applicable'
    adjustable_surplus_active_next = bool(adjustable_surplus_active)

    if profiles.control == ControlProfile.MANUAL:
        return int(round(m.current_battery_setpoint_w)), False, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.control == ControlProfile.MANUAL_SAFE:
        current = int(round(m.current_battery_setpoint_w))
        battery_protect_floor = _battery_protect_charge_floor_w(cfg)

        if profiles.guard == GuardProfile.DEGRADED:
            return 0, True, battery_min_floor_w, battery_min_floor_reason, False

        if profiles.guard == GuardProfile.BATTERY_PROTECT:
            return max(current, battery_protect_floor), True, battery_min_floor_w, battery_min_floor_reason, False

        if profiles.guard == GuardProfile.STRICT_LIMITS:
            limit = int(cfg.strict_limits_max_w)
            return min(max(current, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason, False

        return current, False, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.goal == GoalProfile.NET_ZERO:
        effective_rpnz_w = nz.rpnz_w
        min_charge_floor_w = float(cfg.nz_battery_floor_default_w)
        ev_primary_positive_rpnz = bool(use_ev_primary_mode) and float(nz.rpnz_w) > 0.0
        adjustable_is_home_battery = _normalized_adjustable_surplus_load(cfg) == 'HOME_BATTERY'
        configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)

        if use_ev_primary_mode:
            # EV primary path does not use legacy battery default floor.
            min_charge_floor_w = float(cfg.nz_battery_floor_ev_active_w)
            battery_min_floor_reason = 'ev_active_floor_override'

            battery_min_floor_w = float(min_charge_floor_w)
            effective_rpnz_w = float(nz.rpnz_w) - float(max(ev_target_w, 0.0))

            ev_max_w = float(ev_max_power_w(cfg))
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
                if profiles.guard == GuardProfile.NORMAL_LIMITS:
                    raw = _normal_limits_discharge_cap(raw, cfg)
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

        if (
            haeo_nz_plan is not None
            and bool(getattr(haeo_nz_plan, 'active', False))
            and raw > _haeo_plan_device_limit_w(
                haeo_nz_plan,
                'HOME_BATTERY',
                getattr(haeo_nz_plan, 'battery_limit_w', 0),
            )
        ):
            raw = _haeo_plan_device_limit_w(
                haeo_nz_plan,
                'HOME_BATTERY',
                getattr(haeo_nz_plan, 'battery_limit_w', 0),
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
        return 0, True, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return max(raw, _battery_protect_charge_floor_w(cfg)), True, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.guard == GuardProfile.STRICT_LIMITS:
        limit = int(cfg.strict_limits_max_w)
        return min(max(raw, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.guard == GuardProfile.NORMAL_LIMITS:
        raw = _normal_limits_discharge_cap(raw, cfg)

    return raw, True, battery_min_floor_w, battery_min_floor_reason, adjustable_surplus_active_next


def net_zero_surplus_policy_active(profiles, effective_fc, haeo_nz_plan_active=False):
    return (
        profiles.control == ControlProfile.AUTOMATIC
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and effective_fc == ForecastProfile.NONE
    ) or (
        profiles.control == ControlProfile.HORIZON_BY_HAEO
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and bool(haeo_nz_plan_active)
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
    haeo_nz_plan=None,
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

    if (
        profiles.goal == GoalProfile.NET_ZERO
        and haeo_nz_plan is not None
        and bool(getattr(haeo_nz_plan, 'active', False))
        and current_a > 0
    ):
        limit_a = int(getattr(haeo_nz_plan, 'ev_limit_a', 0))
        current_a = min(int(current_a), limit_a) if limit_a > 0 else 0

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
        ev_threshold_kw = max((ev_max_power_w(cfg) - ev_min_power_w(cfg)) / 1000.0, 0)
        if rpc_kw >= ev_threshold_kw:
            return 'burn', int(cfg.ev_max_current_a), next_low_pv_cycles, False
        return 'hard_off', 0, next_low_pv_cycles, True

    if hard_off_allowed and next_low_pv_cycles >= int(cfg.ev_hard_off_low_pv_cycles):
        return 'hard_off', 0, next_low_pv_cycles, True

    restore_min_a = int(cfg.ev_min_current_a) if use_ev_primary_mode else 0
    return 'restore_min', restore_min_a, next_low_pv_cycles, False


def _primary_ev_step_current_a(cfg, envelope_w):
    per_amp_w = float(ev_phase_power_w(cfg.ev_charger_phases))
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
    current_ev_w = float(ev_current_a_to_power_w(m.charger_current_a, cfg.ev_charger_phases))
    ev_max_w = float(ev_max_power_w(cfg))
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
    haeo_nz_plan=None,
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

    if haeo_nz_plan is None:
        haeo_nz_plan = HaeoNetZeroPlan(False, device_limits_w={})
    haeo_nz_plan_active = bool(getattr(haeo_nz_plan, 'active', False))

    if haeo_nz_plan_active:
        adjustable_primary_load = _haeo_plan_primary_device_id(haeo_nz_plan)
        adjustable_surplus_load = _haeo_plan_adjustable_device_id(haeo_nz_plan)
        primary_surplus_combo_valid = adjustable_primary_load != adjustable_surplus_load
        primary_surplus_combo_reason = 'haeo_net_zero_plan'
        primary_surplus_combo_source = 'HAEO_NET_ZERO_PLAN'
    else:
        adjustable_surplus_load = _normalized_adjustable_surplus_load(cfg)
        requested_primary_load = _normalized_adjustable_primary_load(cfg)
        primary_surplus_combo_source = 'CONFIG'
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
        primary_surplus_combo_source = 'CONFIG'

    combo_fallback_active = primary_surplus_combo_reason == 'fallback_to_cross_combo'
    combo_fallback_warning = (
        'Unsupported primary/surplus same-target combo detected; '
        'runtime forced fallback_to_cross_combo'
        if combo_fallback_active
        else ''
    )

    use_ev_surplus_mode = adjustable_surplus_load == 'EV_CHARGER'
    use_ev_primary_mode = adjustable_primary_load == 'EV_CHARGER'
    use_ev_primary_home_battery_combo = use_ev_primary_mode and (not use_ev_surplus_mode)

    configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)
    if configured_activation_w > 0.0:
        adjustable_threshold_kw = configured_activation_w / 1000.0
    else:
        # Legacy fallback keeps previous behavior when explicit activation threshold is not configured.
        adjustable_threshold_kw = (
            max((ev_max_power_w(cfg) - ev_min_power_w(cfg)) / 1000.0, 0)
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
    surplus_device_targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id=adjustable_surplus_load,
        adjustable_priority=adjustable_priority,
        adjustable_active=adjustable_active_current,
        relay1_enabled=relay1_enabled,
        relay1_force_on=relay1_force_on,
        relay1_active=relay1_net_zero_active,
        relay2_enabled=relay2_enabled,
        relay2_force_on=relay2_force_on,
        relay2_active=relay2_net_zero_active,
    )
    surplus_device_legacy_targets = device_targets_to_legacy_targets(surplus_device_targets)

    surplus_active = net_zero_surplus_policy_active(profiles, eff_fc, haeo_nz_plan_active=haeo_nz_plan_active)

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
    surplus_device_inp = SurplusDispatchInput(
        policy_active=surplus_active,
        freeze_until_ts=effective_freeze_until_ts,
        rpc_kw=nz.required_power_consumption_kw,
        rpnz_w=nz.rpnz_w,
        targets=surplus_device_targets,
    )
    surplus_device_decision = compute_surplus_device_dispatch(surplus_device_inp, now_ts, cfg.surplus_freeze_s)
    surplus_device_next = next_device_target(surplus_device_targets)
    surplus_device_release = release_device_target(surplus_device_targets)

    combo_change_requires_clear = (
        haeo_nz_plan_active
        and bool(getattr(haeo_nz_plan, 'changed', False))
        and (
            bool(adjustable_active_current)
            or bool(relay1_net_zero_active)
            or bool(relay2_net_zero_active)
        )
    )
    combo_change_freeze_until_ts = (
        float(now_ts) + float(cfg.surplus_freeze_s)
        if combo_change_requires_clear
        else None
    )
    surplus_state_clear_reason = 'HAEO_COMBO_CHANGED' if combo_change_requires_clear else ''
    decision_text = _decision_text_from_dispatch(surplus_decision, combo_change_requires_clear)
    surplus_device_legacy_decision = device_dispatch_to_legacy_dispatch(
        surplus_device_decision,
        surplus_device_targets,
    )
    surplus_device_decision_text = _decision_text_from_dispatch(
        surplus_device_legacy_decision,
        combo_change_requires_clear,
    )
    surplus_device_action, surplus_device_target_device_id = _dispatch_action_and_device_id_from_device_dispatch(
        surplus_device_decision,
        combo_change_requires_clear,
    )
    _, surplus_device_target_name = _dispatch_action_and_target(surplus_device_decision_text)
    surplus_device_target_device_id = _device_id_for_decision_name(
        surplus_device_targets,
        surplus_device_target_name,
    ) if surplus_device_target_name else surplus_device_target_device_id
    surplus_device_active_stack = active_stack(surplus_device_legacy_targets)
    surplus_device_active_device_stack = active_device_stack(surplus_device_targets)
    surplus_device_next_target = surplus_device_next.decision_name if surplus_device_next else 'NONE'
    surplus_device_release_candidate = surplus_device_release.decision_name if surplus_device_release else 'NONE'
    surplus_device_next_device_id = surplus_device_next.device_id if surplus_device_next else ''
    surplus_device_release_device_id = surplus_device_release.device_id if surplus_device_release else ''
    parity_mismatches = []
    if surplus_device_active_stack != active_stack(targets):
        parity_mismatches.append('active_stack')
    if surplus_device_next_target != (nxt.name if nxt else 'NONE'):
        parity_mismatches.append('next_target')
    if surplus_device_release_candidate != (rel.name if rel else 'NONE'):
        parity_mismatches.append('release_candidate')
    if surplus_device_decision_text != decision_text:
        parity_mismatches.append('dispatch_decision')
    if _dispatch_action_and_target(decision_text) != (surplus_device_action, surplus_device_target_name):
        parity_mismatches.append('dispatch_action')
    if surplus_device_legacy_decision.explanation != surplus_decision.explanation:
        parity_mismatches.append('explanation')
    if surplus_device_legacy_decision.freeze_until_ts != surplus_decision.freeze_until_ts:
        parity_mismatches.append('freeze_until_ts')
    surplus_device_parity_ok = not parity_mismatches
    surplus_device_parity_mismatch = ','.join(parity_mismatches)

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

    ev_min_power_kw = float(ev_min_power_w(cfg)) / 1000.0
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
    if combo_change_requires_clear:
        ev_primary_burn_active = False
        ev_surplus_burn_active = False
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
        haeo_nz_plan=haeo_nz_plan,
    )

    if (
        profiles.goal == GoalProfile.NET_ZERO
        and (
            combo_change_requires_clear
            or (
                use_ev_surplus_mode
                and (surplus_decision.clear_all or surplus_decision.release == primary_release_target)
            )
        )
        and ev_policy_mode != 'skip'
    ):
        ev_policy_mode = 'restore_min'
        ev_current_a = 0

    primary_envelope_w = None
    if use_ev_primary_mode and (not use_ev_surplus_mode) and ev_policy_mode == 'burn':
        primary_envelope_w = _primary_power_envelope_w(cfg, m, nz)
        stepped_primary_a = _primary_ev_step_current_a(cfg, primary_envelope_w)
        if haeo_nz_plan_active:
            limit_a = int(getattr(haeo_nz_plan, 'ev_limit_a', 0))
            stepped_primary_a = min(int(stepped_primary_a), limit_a) if limit_a > 0 else 0
        ev_current_a = stepped_primary_a
        ev_policy_mode = 'burn' if stepped_primary_a > 0 else 'restore_min'

    ev_target_w = float(ev_current_a_to_power_w(ev_current_a, cfg.ev_charger_phases))
    ev_burn_active_for_battery = (
        (ev_policy_mode == 'burn' and int(max(ev_current_a, 0)) > 0)
        or (
            use_ev_primary_mode
            and ev_policy_mode == 'restore_min'
            and bool(m.charger_on)
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
        haeo_nz_plan=haeo_nz_plan,
    )
    discharge_limit_w, discharge_limit_sign_mode, configured_discharge_limit_w = _normalized_discharge_limit_w(cfg)
    relay1_command = relay_strategy_command(profiles, relay1_surplus_allowed, relay1_force_on, relay1_net_zero_active)
    relay2_command = relay_strategy_command(profiles, relay2_surplus_allowed, relay2_force_on, relay2_net_zero_active)
    device_policies = _build_device_policies(
        cfg,
        battery_target_w=battery_target_w,
        battery_write_enabled=battery_write_enabled,
        ev_current_a=ev_current_a,
        ev_target_w=ev_target_w,
        ev_policy_mode=ev_policy_mode,
        relay1_command=relay1_command,
        relay2_command=relay2_command,
    )
    legacy_outputs = _legacy_outputs_from_device_policies(device_policies)
    device_policy_parity_mismatch = _device_policy_parity_mismatch(
        device_policies,
        battery_target_w=battery_target_w,
        battery_write_enabled=battery_write_enabled,
        ev_current_a=ev_current_a,
        relay1_command=relay1_command,
        relay2_command=relay2_command,
    )

    return NetZeroOutputs(
        battery_target_w=legacy_outputs['battery_target_w'],
        battery_write_enabled=legacy_outputs['battery_write_enabled'],
        ev_current_a=legacy_outputs['ev_current_a'],
        relay1_command=legacy_outputs['relay1_command'],
        relay2_command=legacy_outputs['relay2_command'],
        surplus_policy_active=surplus_active,
        surplus_next_target=nxt.name if nxt else 'NONE',
        surplus_next_threshold_kw=round(nxt.threshold_kw, 3) if nxt else 0,
        surplus_release_candidate=rel.name if rel else 'NONE',
        surplus_dispatch_decision=decision_text,
        surplus_explanation=surplus_decision.explanation,
        effective_forecast=eff_fc,
        dominant_limitation=dominant_limitation(profiles, conf_fc, eff_fc),
        explanation=explain(profiles, conf_fc, eff_fc, haeo_nz_plan_active=haeo_nz_plan_active),
        device_policies=device_policies,
        attrs={
            'configured_forecast': conf_fc,
            'active_stack': active_stack(targets),
            'surplus_device_active_stack': surplus_device_active_stack,
            'surplus_device_active_device_stack': surplus_device_active_device_stack,
            'surplus_device_next_target': surplus_device_next_target,
            'surplus_device_next_device_id': surplus_device_next_device_id,
            'surplus_device_release_candidate': surplus_device_release_candidate,
            'surplus_device_release_device_id': surplus_device_release_device_id,
            'surplus_device_dispatch_decision': surplus_device_decision_text,
            'surplus_device_dispatch_action': surplus_device_action,
            'surplus_device_dispatch_target': surplus_device_target_name,
            'surplus_device_dispatch_device_id': surplus_device_target_device_id,
            'surplus_device_dispatch_contract': 'device_id_primary',
            'surplus_dispatch_decision_role': 'ha_compatibility_mirror',
            'surplus_device_parity_ok': bool(surplus_device_parity_ok),
            'surplus_device_parity_mismatch': surplus_device_parity_mismatch,
            'surplus_device_targets': device_targets_payload(surplus_device_targets),
            'device_policy_parity_ok': device_policy_parity_mismatch == '',
            'device_policy_parity_mismatch': device_policy_parity_mismatch,
            'device_policies': _device_policy_payloads(device_policies),
            'surplus_primary_target': primary_release_target,
            'surplus_freeze_until_ts': (
                combo_change_freeze_until_ts
                if combo_change_freeze_until_ts is not None
                else (
                    surplus_decision.freeze_until_ts
                    if surplus_decision.freeze_until_ts is not None
                    else effective_freeze_until_ts
                )
            ),
            'surplus_state_clear_reason': surplus_state_clear_reason,
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
            'ev_adjustable_mode': bool(use_ev_surplus_mode),
            'ev_primary_burn_active': bool(ev_primary_burn_active),
            'ev_surplus_burn_active': bool(ev_surplus_burn_active),
            'ev_current_step_a': int(getattr(cfg, 'ev_current_step_a', cfg.ev_min_current_a)),
            'ev_min_power_w': int(ev_min_power_w(cfg)),
            'ev_max_power_w': int(ev_max_power_w(cfg)),
            'ev_power_step_w': int(ev_power_step_w(cfg)),
            'ev_target_w': int(round(ev_target_w)),
            'primary_power_envelope_w': primary_envelope_w,
            'adjustable_surplus_load_priority': int(getattr(cfg, 'adjustable_surplus_load_priority', cfg.ev_priority)),
            'adjustable_surplus_load': adjustable_surplus_load,
            'adjustable_surplus_activation': configured_activation_w,
            'adjustable_primary_load': adjustable_primary_load,
            'primary_surplus_combo_source': primary_surplus_combo_source,
            'primary_surplus_combo_valid': bool(primary_surplus_combo_valid),
            'primary_surplus_combo_reason': primary_surplus_combo_reason,
            'primary_surplus_combo_fallback_active': bool(combo_fallback_active),
            'primary_surplus_combo_warning': combo_fallback_warning,
            'battery_min_floor_w': battery_min_floor_w,
            'battery_min_floor_reason': battery_min_floor_reason,
            'discharge_limit_w': int(discharge_limit_w),
            'discharge_limit_sign_mode': discharge_limit_sign_mode,
            'configured_discharge_limit_w': float(configured_discharge_limit_w),
            'surplus_adjustable_active': bool(adjustable_surplus_active_next),
            'haeo_nz_plan_active': bool(haeo_nz_plan_active),
            'haeo_nz_quarter_key': getattr(haeo_nz_plan, 'quarter_key', ''),
            'haeo_nz_combo_changed': bool(getattr(haeo_nz_plan, 'changed', False)),
            'haeo_nz_primary_device_id': _haeo_plan_primary_device_id(haeo_nz_plan),
            'haeo_nz_adjustable_device_id': _haeo_plan_adjustable_device_id(haeo_nz_plan),
            'haeo_nz_device_limits_w': getattr(haeo_nz_plan, 'device_limits_w', {}) or {},
            'haeo_nz_battery_limit_w': int(getattr(haeo_nz_plan, 'battery_limit_w', 0)),
            'haeo_nz_ev_limit_w': int(getattr(haeo_nz_plan, 'ev_limit_w', 0)),
            'haeo_nz_ev_limit_a': int(getattr(haeo_nz_plan, 'ev_limit_a', 0)),
            'haeo_nz_combo_reason': getattr(haeo_nz_plan, 'reason', ''),
            'prev_relay1_force_on': bool(relay1_force_on),
            'prev_relay2_force_on': bool(relay2_force_on),
        },
    )
