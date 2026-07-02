from types import SimpleNamespace

from ems_core.domain.models import (
    ControlProfile, GoalProfile, ForecastProfile, GuardProfile, DominantLimitation,
    HaeoTargets, HaeoNetZeroPlan, SurplusDispatchInput, NetZeroOutputs,
    DevicePolicy, EmsDeviceConfig,
)
from ems_core.domain.capabilities import clamp_target_w_for_capabilities, capability_block_reason
from ems_core.domain.ev_power import (
    ev_current_a_to_power_w,
    ev_max_power_w,
    ev_min_power_w,
)
from ems_core.net_zero.battery_controller import candidate_sp_net_zero
from ems_core.net_zero.load_projection import ev_strategy_target_w, relay_strategy_command
from ems_core.net_zero.surplus_allocator import (
    RPNZ_PRACTICAL_ZERO_W,
    active_device_stack,
    compute_surplus_device_dispatch,
    next_device_target,
    release_device_target,
)
from ems_core.net_zero.surplus_device_targets import build_surplus_device_targets, decision_name_for_device_id, device_targets_payload


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


def _resolved_device_id(cfg, raw_value, default=''):
    text = str(raw_value or '').strip()
    if not text:
        return str(default or '')
    if hasattr(cfg, 'device_kind'):
        if cfg.device_kind(text):
            return text
    if hasattr(cfg, 'device_by_id'):
        device = cfg.device_by_id(text)
        if device is not None:
            return str(device.device_id)
    return text


def _normalized_adjustable_surplus_load(cfg):
    raw = str(getattr(cfg, 'adjustable_surplus_load', '') or '').strip().lower()
    if raw in ('ev_charger', 'ev', 'charger_current'):
        selected_ev_device_id = _default_ev_device_id(cfg)
        return selected_ev_device_id or 'HOME_BATTERY'
    if raw in ('home_battery', 'battery', 'actuator_battery_setpoint_w'):
        return 'HOME_BATTERY'
    resolved = _resolved_device_id(cfg, getattr(cfg, 'adjustable_surplus_load', ''), '')
    if resolved:
        return resolved
    return 'HOME_BATTERY'


def _uses_ev_adjustable_mode(cfg):
    return _is_ev_device_id(cfg, _normalized_adjustable_surplus_load(cfg))


def _normalized_adjustable_primary_load(cfg):
    raw = str(getattr(cfg, 'adjustable_primary_load', '') or '').strip().lower()
    if raw in ('ev_charger', 'ev', 'charger_current'):
        return _default_ev_device_id(cfg)
    if raw in ('home_battery', 'battery', 'actuator_battery_setpoint_w'):
        return 'HOME_BATTERY'
    resolved = _resolved_device_id(cfg, getattr(cfg, 'adjustable_primary_load', ''), '')
    if resolved:
        return resolved
    return ''


def _device_by_id(cfg, device_id):
    if not device_id:
        return None
    if hasattr(cfg, 'device_by_id'):
        return cfg.device_by_id(device_id)
    return None


def _device_kind(cfg, device_id):
    if not device_id:
        return ''
    if hasattr(cfg, 'device_kind'):
        return str(cfg.device_kind(device_id) or '')
    device = _device_by_id(cfg, device_id)
    if device is None:
        return ''
    return str(getattr(device, 'kind', '') or '')


def _device_ids_by_kind(cfg, kind):
    if hasattr(cfg, 'device_ids_by_kind'):
        ids = []
        for device_id in cfg.device_ids_by_kind(kind):
            ids.append(str(device_id))
        return tuple(ids)
    if hasattr(cfg, 'devices_by_kind'):
        ids = []
        for device in cfg.devices_by_kind(kind):
            ids.append(str(device.device_id))
        return tuple(ids)
    return ()


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


def _device_adapter_value(cfg, device_id, field, default=None):
    if hasattr(cfg, 'device_adapter_value'):
        return cfg.device_adapter_value(device_id, field, default)
    device = _device_by_id(cfg, device_id)
    if device is None:
        return default
    adapter = getattr(device, 'adapter', None)
    if adapter is None:
        return default
    return getattr(adapter, field, default)


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


def _device_can_absorb(cfg, device_id):
    return bool(_device_capability(cfg, device_id, 'can_absorb_w', False))


def _device_response_kind(kind):
    kind = str(kind or '')
    if kind == 'BATTERY':
        return 'continuous'
    if kind == 'EV_CHARGER':
        return 'selector'
    return 'relay'


def _is_ev_device_id(cfg, device_id):
    device_id = str(device_id or '')
    kind = _device_kind(cfg, device_id)
    if kind:
        return kind == 'EV_CHARGER'
    return device_id == 'EV_CHARGER'


def _default_ev_device_id(cfg):
    ev_device_ids = _device_ids_by_kind(cfg, 'EV_CHARGER')
    if ev_device_ids:
        return str(ev_device_ids[0])
    if hasattr(cfg, 'device_ids_by_kind') or hasattr(cfg, 'devices_by_kind'):
        return ''
    return 'EV_CHARGER'


def _selected_ev_device_id_for_roles(cfg, adjustable_surplus_load, adjustable_primary_load=''):
    if _is_ev_device_id(cfg, adjustable_surplus_load):
        return str(adjustable_surplus_load)
    if _is_ev_device_id(cfg, adjustable_primary_load):
        return str(adjustable_primary_load)
    return _default_ev_device_id(cfg)


def _selected_ev_context(cfg, device_id):
    def _positive_float(value, default):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        return parsed if parsed > 0 else float(default)

    def _non_negative_float(value, default=0.0):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        return parsed if parsed >= 0 else float(default)

    def _int_or_default(value, default=0):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return int(default)

    kind = _device_kind(cfg, device_id)
    device = None
    if kind != 'EV_CHARGER':
        return SimpleNamespace(
            device_id='',
            device=None,
            adapter=None,
            capabilities=None,
            policy=None,
            current_step_a=1,
            phases=1,
            voltage_v=230.0,
            min_absorb_w=0.0,
            max_absorb_w=0.0,
            power_step_w=0.0,
            force_on=False,
            hard_off_pv_threshold_kw=0.0,
            hard_off_low_pv_cycles=0,
            hard_off_release_cycles=0,
            priority=0,
        )
    if not hasattr(cfg, 'device_adapter_value'):
        device = _device_by_id(cfg, device_id)

    current_step_a = _positive_float(_device_adapter_value(cfg, device_id, 'current_step_a', None), 1.0)
    phases = _positive_float(_device_adapter_value(cfg, device_id, 'phases', None), 1.0)
    voltage_v = _positive_float(_device_adapter_value(cfg, device_id, 'voltage_v', None), 230.0)

    raw_force_on = _device_policy_value(cfg, device_id, 'force_on', False)
    if isinstance(raw_force_on, str):
        text = raw_force_on.strip().lower()
        if text in ('true', 'on', '1', 'yes'):
            force_on = True
        elif text in ('false', 'off', '0', 'no', '', 'unknown', 'unavailable', 'none'):
            force_on = False
        else:
            # Grouped-config entity refs must not coerce truthy just because they
            # are non-empty strings.
            force_on = False
    else:
        force_on = bool(raw_force_on)

    low_pv_threshold = _non_negative_float(_device_policy_value(cfg, device_id, 'low_pv_threshold_w', 0), 0.0)
    hard_off_pv_threshold_kw = (
        low_pv_threshold / 1000.0
        if low_pv_threshold > 50.0
        else low_pv_threshold
    )
    min_absorb_w = _non_negative_float(_device_capability(cfg, device_id, 'min_absorb_w', None), 0.0)
    max_absorb_w = _non_negative_float(_device_capability(cfg, device_id, 'max_absorb_w', None), 0.0)
    configured_step_w = _non_negative_float(_device_capability(cfg, device_id, 'step_w', 0), 0.0)
    power_step_w = configured_step_w if configured_step_w > 0 else float(
        ev_current_a_to_power_w(
            current_step_a,
            phases,
            voltage_v,
        )
    )

    return SimpleNamespace(
        device_id=str(device_id or ''),
        device=device,
        adapter=getattr(device, 'adapter', None),
        capabilities=getattr(device, 'capabilities', None),
        policy=getattr(device, 'policy', None),
        current_step_a=int(round(current_step_a)),
        phases=int(round(phases)),
        voltage_v=float(voltage_v),
        min_absorb_w=min_absorb_w,
        max_absorb_w=max_absorb_w,
        power_step_w=float(power_step_w),
        force_on=force_on,
        hard_off_pv_threshold_kw=hard_off_pv_threshold_kw,
        hard_off_low_pv_cycles=_int_or_default(
            _device_policy_value(cfg, device_id, 'hard_off_low_pv_cycles', 0),
            0,
        ),
        hard_off_release_cycles=_int_or_default(
            _device_policy_value(cfg, device_id, 'hard_off_release_cycles', 0),
            0,
        ),
        priority=_int_or_default(
            _device_policy_value(cfg, device_id, 'priority', 0),
            0,
        ),
    )

def _ev_runtime_state(m, device_id):
    return dict((getattr(m, 'ev_states', {}) or {}).get(str(device_id), {}) or {})


def _ev_runtime_enabled(m, device_id):
    return bool(_ev_runtime_state(m, device_id).get('enabled', False))


def _ev_runtime_current_a(m, device_id):
    return int(_ev_runtime_state(m, device_id).get('current_a', 0) or 0)


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


def _decision_text_from_dispatch(targets, surplus_decision, combo_change_requires_clear):
    if combo_change_requires_clear or surplus_decision.clear_all:
        return 'CLEAR_ALL'
    if surplus_decision.activate:
        decision_name = decision_name_for_device_id(targets, surplus_decision.activate) or surplus_decision.activate
        return 'ACTIVATE_' + decision_name
    if surplus_decision.release:
        decision_name = decision_name_for_device_id(targets, surplus_decision.release) or surplus_decision.release
        return 'RELEASE_' + decision_name
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
    return payload


def _capability_device_config_for_id(cfg, device_id):
    kind = _device_kind(cfg, device_id)
    if kind:
        min_absorb_w = _device_capability(cfg, device_id, 'min_absorb_w', 0)
        max_absorb_w = _device_capability(cfg, device_id, 'max_absorb_w', 0)
        max_produce_w = _device_capability(cfg, device_id, 'max_produce_w', 0)
        step_w = _device_capability(cfg, device_id, 'step_w', 0)
        return EmsDeviceConfig(
            device_id=str(device_id),
            kind=str(kind),
            response_kind=_device_response_kind(kind),
            can_absorb_w=bool(_device_capability(cfg, device_id, 'can_absorb_w', False)),
            can_produce_w=bool(_device_capability(cfg, device_id, 'can_produce_w', False)),
            min_absorb_w=int(round(float(min_absorb_w or 0))),
            max_absorb_w=int(round(float(max_absorb_w or 0))),
            max_produce_w=int(round(abs(float(max_produce_w or 0)))),
            step_w=max(1, int(round(float(step_w or 0)))),
            priority=int(round(float(_device_policy_value(cfg, device_id, 'priority', 0) or 0))),
        )
    raise KeyError(f'unknown device_id: {device_id}')


def _relay_devices(cfg):
    return tuple(_device_ids_by_kind(cfg, 'RELAY'))


def _ev_devices(cfg):
    return tuple(_device_ids_by_kind(cfg, 'EV_CHARGER'))


def _relay_device_ids_payload(cfg):
    payload = []
    for relay in _relay_devices(cfg):
        payload.append(str(relay))
    return tuple(payload)


def _ev_device_ids_payload(cfg):
    payload = []
    for ev in _ev_devices(cfg):
        payload.append(str(ev))
    return tuple(payload)


def _relay_runtime_candidates(cfg, relay_device_states):
    candidates = []
    state_map = relay_device_states or {}
    for relay in _relay_devices(cfg):
        device_id = str(relay)
        state = dict(state_map.get(device_id, {}) or {})
        threshold_w = max(int(round(float(_device_capability(cfg, device_id, 'max_absorb_w', 0) or 0))), 0)
        candidates.append(
            {
                'device_id': device_id,
                'priority': int(round(float(_device_policy_value(cfg, device_id, 'priority', 0) or 0))),
                'threshold_w': threshold_w,
                'enabled': bool(state.get('surplus_allowed', False)) and _device_can_absorb(cfg, device_id),
                'force_on': bool(state.get('force_on', False)),
                'active': bool(state.get('active', False)),
            }
        )
    return tuple(candidates)


def _selected_ev_device_id(cfg, adjustable_surplus_load):
    return _selected_ev_device_id_for_roles(cfg, adjustable_surplus_load, '')


def _has_ev_devices(cfg):
    return bool(_ev_devices(cfg))


def _default_previous_ev_device_state(device_id=''):
    return {
        'device_id': str(device_id or ''),
        'mode': '',
        'low_pv_cycles': 0,
        'hard_off_release_ready_cycles': 0,
        'hard_off_active': False,
    }


def _normalize_previous_ev_device_state_entry(device_id, state):
    normalized = _default_previous_ev_device_state(device_id)
    state = dict(state or {})
    normalized['device_id'] = str(state.get('device_id') or device_id or '')
    normalized['mode'] = str(state.get('mode') or '')
    normalized['low_pv_cycles'] = int(state.get('low_pv_cycles', 0) or 0)
    normalized['hard_off_release_ready_cycles'] = int(state.get('hard_off_release_ready_cycles', 0) or 0)
    normalized['hard_off_active'] = bool(state.get('hard_off_active', False))
    return normalized


def _normalize_previous_ev_device_states(previous_ev_device_states):
    normalized = {}
    for device_id, state in (previous_ev_device_states or {}).items():
        normalized[str(device_id)] = _normalize_previous_ev_device_state_entry(device_id, state)
    return normalized


def _enforce_device_policy_capabilities(cfg, device_policies):
    sanitized = []
    blocked = []
    for policy in device_policies:
        device_cfg = _capability_device_config_for_id(cfg, policy.device_id)
        clamped_target_w = clamp_target_w_for_capabilities(device_cfg, policy.target_w)
        block_reason = capability_block_reason(device_cfg, policy.target_w)
        enabled = bool(policy.enabled)
        mode = policy.mode
        reason = policy.reason
        if block_reason:
            blocked.append(policy.device_id + ':' + block_reason)
            if policy.device_id == 'HOME_BATTERY':
                enabled = True
                mode = 'power'
            elif str(device_cfg.kind) == 'EV_CHARGER':
                enabled = False
                mode = 'restore_min'
            else:
                enabled = False
                mode = 'relay'
            reason = block_reason
        sanitized.append(
            DevicePolicy(
                device_id=policy.device_id,
                target_w=int(clamped_target_w),
                enabled=enabled,
                mode=mode,
                reason=reason,
            )
        )
    return tuple(sanitized), tuple(blocked)


def _device_policy_payloads(device_policies):
    payloads = []
    for policy in device_policies:
        payloads.append(_device_policy_payload(policy))
    return tuple(payloads)


def _legacy_bridge_metrics(cfg):
    if not hasattr(cfg, 'legacy_device_bridge_count'):
        return 0, {}
    try:
        count = int(cfg.legacy_device_bridge_count())
    except Exception:
        count = 0
    try:
        counts_by_kind = dict(cfg.legacy_device_bridge_counts_by_kind())
    except Exception:
        counts_by_kind = {}
    normalized = {}
    for kind, item_count in counts_by_kind.items():
        normalized[str(kind)] = int(item_count)
    return count, normalized


def _build_device_policies(
    cfg,
    *,
    battery_target_w,
    battery_write_enabled,
    ev_target_w,
    ev_policy_mode,
    adjustable_ev_device_id,
    relay_policies,
):
    policies = [
        DevicePolicy(
            device_id='HOME_BATTERY',
            target_w=int(round(float(battery_target_w))),
            enabled=bool(battery_write_enabled),
            mode='power',
            reason='battery_policy',
        ),
    ]
    selected_ev_device_id = str(adjustable_ev_device_id or _selected_ev_device_id(cfg, ''))
    for ev_device_id in _ev_devices(cfg):
        device_id = str(ev_device_id)
        if device_id == selected_ev_device_id:
            policies.append(
                DevicePolicy(
                    device_id=device_id,
                    target_w=int(round(float(ev_target_w))),
                    enabled=float(ev_target_w) > 0.0,
                    mode=str(ev_policy_mode),
                    reason='ev_policy',
                )
            )
        else:
            policies.append(
                DevicePolicy(
                    device_id=device_id,
                    target_w=0,
                    enabled=False,
                    mode='restore_min',
                    reason='inactive_ev_policy',
                )
            )
    for relay_policy in relay_policies:
        relay_cfg = _capability_device_config_for_id(cfg, relay_policy['device_id'])
        relay_target_w = int(round(float(relay_cfg.max_absorb_w))) if int(relay_policy['command']) > 0 else 0
        policies.append(
            DevicePolicy(
                device_id=str(relay_policy['device_id']),
                target_w=relay_target_w,
                enabled=int(relay_policy['command']) > 0,
                mode='skip' if int(relay_policy['command']) < 0 else 'relay',
                reason='relay_policy',
            )
        )
    return tuple(policies)


def _battery_target_and_authority(
    profiles,
    cfg,
    ev_context,
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
        ev_primary_practical_zero_active = bool(use_ev_primary_mode) and (
            bool(ev_burn_active) or bool(adjustable_surplus_active)
        )
        ev_primary_material_positive_rpnz = bool(use_ev_primary_mode) and float(nz.rpnz_w) > (
            RPNZ_PRACTICAL_ZERO_W if ev_primary_practical_zero_active else 0.0
        )
        adjustable_is_home_battery = _normalized_adjustable_surplus_load(cfg) == 'HOME_BATTERY'
        configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)

        if use_ev_primary_mode:
            # EV primary path does not use legacy battery default floor.
            min_charge_floor_w = float(cfg.nz_battery_floor_ev_active_w)
            battery_min_floor_reason = 'ev_active_floor_override'

            battery_min_floor_w = float(min_charge_floor_w)
            effective_rpnz_w = float(nz.rpnz_w) - float(max(ev_target_w, 0.0))

            ev_max_w = float(ev_max_power_w(ev_context))
            if (
                ev_burn_active
                and (not ev_primary_material_positive_rpnz)
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

        if ev_primary_material_positive_rpnz:
            raw = int(round(min_charge_floor_w))
        else:
            if (
                use_ev_primary_mode
                and ev_burn_active
                and float(nz.rpnz_w) <= RPNZ_PRACTICAL_ZERO_W
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


def _ev_policy_mode_and_target_w(
    profiles, ev_context, haeo, *,
    burn_active,
    force_charge_blocked,
    adjustable_surplus_active,
    ev_release_pending,
    pv_power_kw,
    ev_hard_off_active,
    ev_low_pv_cycles,
    rpc_kw,
    rpnz_w,
    use_ev_adjustable_mode=False,
    use_ev_primary_mode=False,
    use_ev_primary_home_battery_combo=False,
    haeo_nz_plan=None,
):
    target_w = ev_strategy_target_w(
        profiles,
        ev_context,
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
        target_w = float(ev_max_power_w(ev_context))

    if (
        profiles.goal == GoalProfile.NET_ZERO
        and haeo_nz_plan is not None
        and bool(getattr(haeo_nz_plan, 'active', False))
        and target_w > 0
    ):
        limit_w = float(getattr(haeo_nz_plan, 'ev_limit_w', 0))
        target_w = min(float(target_w), limit_w) if limit_w > 0 else 0.0

    if profiles.goal == GoalProfile.MAX_EXPORT and target_w == 0:
        return 'hard_off', 0, 0, False

    if force_charge_blocked:
        target_w = 0.0

    if target_w > 0:
        return 'burn', float(target_w), 0, False

    low_pv_threshold = float(ev_context.hard_off_pv_threshold_kw)
    low_pv = pv_power_kw is not None and float(pv_power_kw) < low_pv_threshold
    next_low_pv_cycles = int(ev_low_pv_cycles) + 1 if low_pv else 0

    hard_off_allowed = (
        profiles.control == ControlProfile.AUTOMATIC
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and not burn_active
    )

    if hard_off_allowed and ev_hard_off_active:
        if use_ev_primary_home_battery_combo:
            return 'hard_off', 0, next_low_pv_cycles, True
        ev_threshold_kw = max((ev_max_power_w(ev_context) - ev_min_power_w(ev_context)) / 1000.0, 0)
        if rpc_kw >= ev_threshold_kw:
            return 'burn', float(ev_max_power_w(ev_context)), next_low_pv_cycles, False
        return 'hard_off', 0, next_low_pv_cycles, True

    if hard_off_allowed and next_low_pv_cycles >= int(ev_context.hard_off_low_pv_cycles):
        return 'hard_off', 0, next_low_pv_cycles, True

    restore_min_w = float(ev_min_power_w(ev_context)) if use_ev_primary_mode else 0.0
    return 'restore_min', restore_min_w, next_low_pv_cycles, False


def _primary_ev_step_target_w(ev_context, envelope_w):
    positive_envelope_w = max(float(envelope_w), 0.0)
    if positive_envelope_w <= 0.0:
        return 0.0

    min_w = float(ev_min_power_w(ev_context))
    max_w = float(ev_max_power_w(ev_context))
    step_w = max(1.0, float(getattr(ev_context, 'power_step_w', 0.0) or 0.0))

    if positive_envelope_w <= min_w:
        quantized_w = min_w
    else:
        # Quantize above minimum using the charger-supported watt resolution.
        offset_w = positive_envelope_w - min_w
        quantized_w = min_w + (offset_w // step_w) * step_w

    return float(min(max(quantized_w, min_w), max_w))


def _primary_power_envelope_w(cfg, ev_context, m, nz):
    current_ev_w = float(
        ev_current_a_to_power_w(
            _ev_runtime_current_a(m, ev_context.device_id),
            ev_context.phases,
            ev_context.voltage_v,
        )
    )
    ev_max_w = float(ev_max_power_w(ev_context))
    return candidate_sp_net_zero(
        rpnz_w=float(nz.rpnz_w),
        grid_actual_w=float(m.grid_power_w),
        current_sp_w=current_ev_w,
        deadband_w=float(cfg.deadband_w),
        ramp_w=float(cfg.ramp_max_w),
        max_sp_w=ev_max_w,
        min_charge_floor_w=0.0,
    )


def _apply_force_rising_edge_freeze_for_devices(
    now_ts,
    freeze_until_ts,
    freeze_s,
    relay_candidates,
    previous_force_on_device_ids=None,
):
    freeze_until = freeze_until_ts
    previous_force_on_device_ids = set(previous_force_on_device_ids or ())
    current_force_on_device_ids = set()
    for relay in relay_candidates:
        if bool(relay.get('force_on', False)):
            current_force_on_device_ids.add(str(relay.get('device_id')))
    rising_edge = False
    for device_id in current_force_on_device_ids:
        if device_id not in previous_force_on_device_ids:
            rising_edge = True
            break
    if rising_edge:
        target_freeze = now_ts + freeze_s
        if freeze_until is None:
            freeze_until = target_freeze
        else:
            freeze_until = max(float(freeze_until), float(target_freeze))
    return freeze_until, tuple(sorted(current_force_on_device_ids))


def _canonical_surplus_freeze_until_ts_for_output(
    dispatch_action,
    dispatch_decision,
    combo_change_freeze_until_ts,
    decision_freeze_until_ts,
    effective_freeze_until_ts,
):
    if combo_change_freeze_until_ts is not None:
        return combo_change_freeze_until_ts
    action = str(dispatch_action or '')
    decision = str(dispatch_decision or '')
    if action == 'CLEAR_ALL' and decision == 'CLEAR_ALL':
        return None
    if action == 'NOOP':
        return effective_freeze_until_ts
    if decision_freeze_until_ts is not None:
        return decision_freeze_until_ts
    return effective_freeze_until_ts


def compute_net_zero_engine_outputs(
    profiles, cfg, m, haeo, nz, now_ts, *,
    freeze_until_ts,
    ev_burn_active,
    adjustable_surplus_active=False,
    pv_power_kw=None,
    ev_hard_off_active=False,
    ev_low_pv_cycles=0,
    ev_hard_off_release_ready_cycles=0,
    relay_device_states=None,
    previous_ev_device_states=None,
    previous_force_on_device_ids=None,
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
            primary_surplus_combo_reason = 'implicit_primary_equals_surplus'
        else:
            adjustable_primary_load = requested_primary_load
            primary_surplus_combo_valid = adjustable_primary_load != adjustable_surplus_load
            primary_surplus_combo_reason = 'supported_cross_combo' if primary_surplus_combo_valid else 'unsupported_same_target_combo'

    if not primary_surplus_combo_valid:
        adjustable_primary_load = 'HOME_BATTERY' if _is_ev_device_id(cfg, adjustable_surplus_load) else _default_ev_device_id(cfg)
        primary_surplus_combo_reason = 'fallback_to_cross_combo'
        primary_surplus_combo_source = 'CONFIG'

    combo_fallback_active = primary_surplus_combo_reason == 'fallback_to_cross_combo'
    combo_fallback_warning = (
        'Unsupported primary/surplus same-target combo detected; '
        'runtime forced fallback_to_cross_combo'
        if combo_fallback_active
        else ''
    )

    has_ev_devices = _has_ev_devices(cfg)
    use_ev_surplus_mode = _is_ev_device_id(cfg, adjustable_surplus_load)
    use_ev_primary_mode = _is_ev_device_id(cfg, adjustable_primary_load)
    use_ev_primary_home_battery_combo = use_ev_primary_mode and (not use_ev_surplus_mode)
    selected_ev_device_id = _selected_ev_device_id_for_roles(
        cfg,
        adjustable_surplus_load,
        adjustable_primary_load,
    )
    selected_ev = _selected_ev_context(cfg, selected_ev_device_id)
    normalized_previous_ev_device_states = _normalize_previous_ev_device_states(previous_ev_device_states)
    selected_previous_ev_state = normalized_previous_ev_device_states.get(selected_ev_device_id)
    if has_ev_devices and selected_previous_ev_state is None:
        selected_previous_ev_state = _normalize_previous_ev_device_state_entry(
            selected_ev_device_id,
            {
                'device_id': selected_ev_device_id,
                'mode': '',
                'low_pv_cycles': ev_low_pv_cycles,
                'hard_off_release_ready_cycles': ev_hard_off_release_ready_cycles,
                'hard_off_active': ev_hard_off_active,
            },
        )
        normalized_previous_ev_device_states[selected_ev_device_id] = selected_previous_ev_state
    if not has_ev_devices:
        selected_previous_ev_state = _default_previous_ev_device_state('')

    configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)
    adjustable_active_current = bool(adjustable_surplus_active or ev_burn_active)
    adjustable_priority = int(getattr(cfg, 'adjustable_surplus_load_priority', 0) or 0)
    adjustable_capable = _device_can_absorb(cfg, adjustable_surplus_load)
    normalized_relay_device_states = {}
    for device_id, state in (relay_device_states or {}).items():
        normalized_relay_device_states[str(device_id)] = dict(state or {})
    relay_devices = _relay_devices(cfg)
    for index, relay in enumerate(relay_devices):
        device_id = str(relay)
        state = normalized_relay_device_states.setdefault(device_id, {})
        if 'surplus_allowed' not in state:
            state['surplus_allowed'] = bool(_device_policy_value(cfg, device_id, 'surplus_allowed', False))
        if 'force_on' not in state:
            state['force_on'] = bool(_device_policy_value(cfg, device_id, 'force_on', False))
        if 'active' not in state:
            state['active'] = False
    relay_runtime_candidates = _relay_runtime_candidates(
        cfg,
        normalized_relay_device_states,
    )
    surplus_device_targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id=adjustable_surplus_load,
        adjustable_priority=adjustable_priority,
        adjustable_active=adjustable_active_current,
        adjustable_enabled=adjustable_capable,
        relay_candidates=relay_runtime_candidates,
    )

    surplus_active = net_zero_surplus_policy_active(profiles, eff_fc, haeo_nz_plan_active=haeo_nz_plan_active)

    effective_freeze_until_ts, current_force_on_device_ids = _apply_force_rising_edge_freeze_for_devices(
        now_ts=now_ts,
        freeze_until_ts=freeze_until_ts,
        freeze_s=cfg.surplus_freeze_s,
        relay_candidates=relay_runtime_candidates,
        previous_force_on_device_ids=previous_force_on_device_ids or (),
    )

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

    relay_active_now = False
    for relay in relay_runtime_candidates:
        if bool(relay.get('active', False)):
            relay_active_now = True
            break
    combo_change_requires_clear = (
        haeo_nz_plan_active
        and bool(getattr(haeo_nz_plan, 'changed', False))
        and (
            bool(adjustable_active_current)
            or relay_active_now
        )
    )
    combo_change_freeze_until_ts = (
        float(now_ts) + float(cfg.surplus_freeze_s)
        if combo_change_requires_clear
        else None
    )
    surplus_state_clear_reason = 'HAEO_COMBO_CHANGED' if combo_change_requires_clear else ''
    surplus_device_decision_text = _decision_text_from_dispatch(surplus_device_targets, surplus_device_decision, combo_change_requires_clear)
    surplus_device_action, surplus_device_target_name = _dispatch_action_and_target(surplus_device_decision_text)
    surplus_device_target_device_id = _device_id_for_decision_name(
        surplus_device_targets,
        surplus_device_target_name,
    ) if surplus_device_target_name else ''
    surplus_device_active_stack = active_device_stack(surplus_device_targets)
    surplus_device_active_device_stack = active_device_stack(surplus_device_targets)
    surplus_device_next_target = surplus_device_next.decision_name if surplus_device_next else 'NONE'
    surplus_device_release_candidate = surplus_device_release.decision_name if surplus_device_release else 'NONE'
    surplus_device_next_device_id = surplus_device_next.device_id if surplus_device_next else ''
    surplus_device_release_device_id = surplus_device_release.device_id if surplus_device_release else ''

    primary_release_target = 'ADJUSTABLE'
    low_pv = False
    battery_to_ev_loop_risk = False
    ev_min_power_kw = 0.0
    hard_off_release_rpc_kw = 0.0
    hard_off_release_cycles_required = 0
    hard_off_release_ready_cycles_next = 0
    ev_primary_burn_active = False
    ev_surplus_burn_active = False
    ev_policy_mode = 'skip'
    next_low_pv_cycles = 0
    ev_hard_off_active_next = False
    primary_envelope_w = None
    ev_target_w = 0.0
    ev_burn_active_for_battery = False
    if has_ev_devices:
        low_pv = (
            pv_power_kw is not None
            and float(pv_power_kw) < float(selected_ev.hard_off_pv_threshold_kw)
        )
        battery_to_ev_loop_risk = (
            low_pv
            and float(m.current_battery_setpoint_w) < 0.0
        )

        ev_min_power_kw = float(ev_min_power_w(selected_ev)) / 1000.0
        hard_off_release_rpc_kw = ev_min_power_kw if use_ev_primary_home_battery_combo else 0.0
        hard_off_release_cycles_required = max(1, int(getattr(selected_ev, 'hard_off_release_cycles', 2) or 2))
        hard_off_release_condition = (
            use_ev_primary_home_battery_combo
            and bool(selected_previous_ev_state['hard_off_active'])
            and (pv_power_kw is not None)
            and float(pv_power_kw) >= float(selected_ev.hard_off_pv_threshold_kw)
            and float(nz.required_power_consumption_kw) >= float(hard_off_release_rpc_kw)
            and (not battery_to_ev_loop_risk)
        )
        hard_off_release_ready_cycles_next = (
            int(selected_previous_ev_state['hard_off_release_ready_cycles']) + 1
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
                            (not bool(selected_previous_ev_state['hard_off_active']))
                            and float(nz.rpnz_w) > 0.0
                        )
                        or (
                            bool(selected_previous_ev_state['hard_off_active'])
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
        ev_policy_mode, ev_target_w, next_low_pv_cycles, ev_hard_off_active_next = _ev_policy_mode_and_target_w(
            profiles,
            selected_ev,
            normalized_haeo,
            burn_active=ev_burn_for_cycle,
            force_charge_blocked=battery_to_ev_loop_risk,
            adjustable_surplus_active=adjustable_active_current,
            ev_release_pending=(surplus_device_decision.release == primary_release_target),
            pv_power_kw=pv_power_kw,
            ev_hard_off_active=bool(selected_previous_ev_state['hard_off_active']),
            ev_low_pv_cycles=int(selected_previous_ev_state['low_pv_cycles']),
            rpc_kw=nz.required_power_consumption_kw,
            rpnz_w=nz.rpnz_w,
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
                    and (surplus_device_decision.clear_all or surplus_device_decision.release == primary_release_target)
                )
            )
            and ev_policy_mode != 'skip'
        ):
            ev_policy_mode = 'restore_min'
            ev_target_w = 0.0

        if use_ev_primary_mode and (not use_ev_surplus_mode) and ev_policy_mode == 'burn':
            primary_envelope_w = _primary_power_envelope_w(cfg, selected_ev, m, nz)
            stepped_primary_w = _primary_ev_step_target_w(selected_ev, primary_envelope_w)
            if haeo_nz_plan_active:
                limit_w = float(getattr(haeo_nz_plan, 'ev_limit_w', 0))
                stepped_primary_w = min(float(stepped_primary_w), limit_w) if limit_w > 0 else 0.0
            ev_target_w = float(stepped_primary_w)
            ev_policy_mode = 'burn' if stepped_primary_w > 0 else 'restore_min'

        ev_burn_active_for_battery = (
            (ev_policy_mode == 'burn' and float(max(ev_target_w, 0.0)) > 0.0)
            or (
                use_ev_primary_mode
                and ev_policy_mode == 'restore_min'
                and _ev_runtime_enabled(m, selected_ev_device_id)
                and float(max(ev_target_w, 0.0)) > 0.0
                and not battery_to_ev_loop_risk
            )
        )
    battery_target_w, battery_write_enabled, battery_min_floor_w, battery_min_floor_reason, adjustable_surplus_active_next = _battery_target_and_authority(
        profiles,
        cfg,
        selected_ev,
        m,
        normalized_haeo,
        nz,
        ev_burn_active=ev_burn_active_for_battery,
        ev_release_pending=(surplus_device_decision.release == primary_release_target),
        ev_target_w=ev_target_w,
        adjustable_surplus_active=adjustable_surplus_active,
        use_ev_primary_mode=use_ev_primary_mode,
        haeo_nz_plan=haeo_nz_plan,
    )
    discharge_limit_w, discharge_limit_sign_mode, configured_discharge_limit_w = _normalized_discharge_limit_w(cfg)
    relay_policy_states = []
    for relay in relay_runtime_candidates:
        relay_policy_states.append(
            {
                'device_id': str(relay['device_id']),
                'command': relay_strategy_command(
                    profiles,
                    bool(relay['enabled']),
                    bool(relay['force_on']),
                    bool(relay['active']),
                ),
            }
        )
    device_policies = _build_device_policies(
        cfg,
        battery_target_w=battery_target_w,
        battery_write_enabled=battery_write_enabled,
        ev_target_w=ev_target_w,
        ev_policy_mode=ev_policy_mode,
        adjustable_ev_device_id=selected_ev_device_id,
        relay_policies=tuple(relay_policy_states),
    )
    device_policies, capability_blocked_devices = _enforce_device_policy_capabilities(cfg, device_policies)
    battery_policy = None
    for policy in device_policies:
        if policy.device_id == 'HOME_BATTERY':
            battery_policy = policy
            break
    if battery_policy is not None:
        battery_target_w = int(battery_policy.target_w)
        battery_write_enabled = bool(battery_policy.enabled)
    updated_previous_ev_device_states = _normalize_previous_ev_device_states(normalized_previous_ev_device_states)
    if has_ev_devices and selected_ev_device_id:
        updated_previous_ev_device_states[selected_ev_device_id] = _normalize_previous_ev_device_state_entry(
            selected_ev_device_id,
            {
                'device_id': selected_ev_device_id,
                'mode': ev_policy_mode,
                'low_pv_cycles': next_low_pv_cycles,
                'hard_off_active': ev_hard_off_active_next,
                'hard_off_release_ready_cycles': hard_off_release_ready_cycles_next,
            },
        )
        selected_previous_ev_state_next = updated_previous_ev_device_states[selected_ev_device_id]
    else:
        selected_previous_ev_state_next = _default_previous_ev_device_state('')

    legacy_device_bridge_count, legacy_device_bridge_counts_by_kind = _legacy_bridge_metrics(cfg)

    return NetZeroOutputs(
        battery_target_w=battery_target_w,
        battery_write_enabled=battery_write_enabled,
        surplus_policy_active=surplus_active,
        surplus_next_target=surplus_device_next_target,
        surplus_next_threshold_kw=round(float(surplus_device_next.threshold_w) / 1000.0, 3) if surplus_device_next else 0,
        surplus_release_candidate=surplus_device_release_candidate,
        surplus_dispatch_decision=surplus_device_decision_text,
        surplus_explanation=surplus_device_decision.explanation,
        effective_forecast=eff_fc,
        dominant_limitation=dominant_limitation(profiles, conf_fc, eff_fc),
        explanation=explain(profiles, conf_fc, eff_fc, haeo_nz_plan_active=haeo_nz_plan_active),
        device_policies=device_policies,
        attrs={
            'configured_forecast': conf_fc,
            'active_stack': surplus_device_active_stack,
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
            'surplus_device_targets': device_targets_payload(surplus_device_targets),
            'relay_device_ids': _relay_device_ids_payload(cfg),
            'ev_device_ids': _ev_device_ids_payload(cfg),
            'device_policies': _device_policy_payloads(device_policies),
            'capability_blocked_devices': capability_blocked_devices,
            'surplus_primary_target': primary_release_target,
            'surplus_freeze_until_ts': _canonical_surplus_freeze_until_ts_for_output(
                surplus_device_action,
                surplus_device_decision_text,
                combo_change_freeze_until_ts,
                surplus_device_decision.freeze_until_ts,
                effective_freeze_until_ts,
            ),
            'surplus_state_clear_reason': surplus_state_clear_reason,
            'surplus_rpc_kw': nz.required_power_consumption_kw,
            'surplus_rpnz_w': nz.rpnz_w,
            'battery_write_enabled': battery_write_enabled,
            'selected_ev_device_id': selected_ev_device_id,
            'ev_policy_mode': ev_policy_mode,
            'ev_low_pv_cycles': next_low_pv_cycles,
            'ev_hard_off_active': ev_hard_off_active_next,
            'ev_hard_off_release_ready_cycles': hard_off_release_ready_cycles_next,
            'previous_device_state': selected_previous_ev_state_next,
            'previous_ev_device_states': updated_previous_ev_device_states,
            'ev_hard_off_release_cycles_required': hard_off_release_cycles_required,
            'ev_hard_off_release_rpc_kw': hard_off_release_rpc_kw,
            'pv_power_kw': pv_power_kw,
            'ev_hard_off_pv_threshold_kw': selected_ev.hard_off_pv_threshold_kw,
            'battery_to_ev_loop_risk': bool(battery_to_ev_loop_risk),
            'ev_adjustable_mode': bool(use_ev_surplus_mode),
            'ev_primary_burn_active': bool(ev_primary_burn_active),
            'ev_surplus_burn_active': bool(ev_surplus_burn_active),
            'ev_current_step_a': int(getattr(selected_ev, 'current_step_a', 1) or 1),
            'ev_force_on': bool(getattr(selected_ev, 'force_on', False)),
            'ev_min_power_w': int(ev_min_power_w(selected_ev)),
            'ev_max_power_w': int(ev_max_power_w(selected_ev)),
            'ev_power_step_w': int(getattr(selected_ev, 'power_step_w', 0) or 0),
            'ev_target_w': int(round(ev_target_w)),
            'primary_power_envelope_w': primary_envelope_w,
            'adjustable_surplus_load_priority': int(getattr(cfg, 'adjustable_surplus_load_priority', 0) or 0),
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
            'haeo_nz_combo_reason': getattr(haeo_nz_plan, 'reason', ''),
            'prev_force_on_device_ids': current_force_on_device_ids,
            'legacy_device_bridge_count': int(legacy_device_bridge_count),
            'legacy_device_bridge_counts_by_kind': legacy_device_bridge_counts_by_kind,
        },
    )
