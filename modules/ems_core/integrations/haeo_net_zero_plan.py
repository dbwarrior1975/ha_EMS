from ems_core.domain.models import (
    ControlProfile,
    ForecastProfile,
    GoalProfile,
    GuardProfile,
    HaeoNetZeroPlan,
)


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
    return str(getattr(device, 'kind', '') or '') if device is not None else ''


def _device_capability(cfg, device_id, field, default=None):
    if hasattr(cfg, 'device_capability'):
        return cfg.device_capability(device_id, field, default)
    device = _device_by_id(cfg, device_id)
    capabilities = getattr(device, 'capabilities', None) if device is not None else None
    return getattr(capabilities, field, default) if capabilities is not None else default


def _device_policy_value(cfg, device_id, field, default=None):
    if hasattr(cfg, 'device_policy_value'):
        return cfg.device_policy_value(device_id, field, default)
    device = _device_by_id(cfg, device_id)
    policy = getattr(device, 'policy', None) if device is not None else None
    return getattr(policy, field, default) if policy is not None else default


def _ordered_device_ids(cfg):
    result = []
    if hasattr(cfg, 'ordered_device_ids'):
        for value in (cfg.ordered_device_ids() or ()):
            result.append(str(value))
        return tuple(result)
    devices = getattr(cfg, 'devices', {}) or {}
    if isinstance(devices, dict):
        for value in devices.keys():
            result.append(str(value))
        return tuple(result)
    for kind in ('BATTERY', 'EV_CHARGER', 'RELAY'):
        if hasattr(cfg, 'device_ids_by_kind'):
            for value in (cfg.device_ids_by_kind(kind) or ()):
                value = str(value)
                if value not in result:
                    result.append(value)
    return tuple(result)


def _target_kw(haeo, device_id):
    if hasattr(haeo, 'target_kw'):
        return float(haeo.target_kw(device_id, 0.0) or 0.0)
    return float((getattr(haeo, 'device_target_kw_by_id', {}) or {}).get(str(device_id), 0.0) or 0.0)


def compute_haeo_net_zero_plan(
    profiles,
    cfg,
    haeo,
    now_ts,
    *,
    previous_quarter_key='',
    previous_primary_consuming_device_id='',
):
    """Build a device-owned HAEO NET_ZERO plan.

    Only explicit per-device HAEO targets participate. Missing device entries mean
    no HAEO authority for that device. No implicit device fallback is permitted
    at this boundary.
    """
    quarter_key = quarter_key_for_ts(now_ts)

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

    ordered_ids = _ordered_device_ids(cfg)
    device_limits_w = {}
    primary_candidates = []
    for rank, device_id in enumerate(ordered_ids):
        requested_w = _positive_w(_target_kw(haeo, device_id))
        if requested_w <= 0:
            continue
        max_absorb_w = max(
            int(round(float(_device_capability(cfg, device_id, 'max_absorb_w', 0) or 0))),
            0,
        )
        limit_w = min(requested_w, max_absorb_w)
        if limit_w <= 0:
            continue
        device_limits_w[str(device_id)] = int(limit_w)
        if (
            bool(_device_capability(cfg, device_id, 'can_absorb_w', False))
            and bool(_device_capability(cfg, device_id, 'supports_primary_consuming_regulation', False))
        ):
            primary_candidates.append((int(limit_w), -rank, str(device_id)))

    if not device_limits_w:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='zero_forecast')
    if not primary_candidates:
        return HaeoNetZeroPlan(False, quarter_key=quarter_key, device_limits_w={}, reason='no_primary_consuming_candidate')

    max_limit = 0
    for item in primary_candidates:
        if item[0] > max_limit:
            max_limit = item[0]
    tied_ids = []
    for item in primary_candidates:
        if item[0] == max_limit:
            tied_ids.append(item[2])
    previous_primary = str(previous_primary_consuming_device_id or '')
    if previous_primary in tied_ids:
        primary_consuming_device_id = previous_primary
        reason = 'tie_keep_previous' if len(tied_ids) > 1 else 'largest_explicit_device_target'
    else:
        primary_consuming_device_id = max(primary_candidates)[2]
        reason = 'largest_explicit_device_target'

    surplus_candidates = []
    for rank, device_id in enumerate(ordered_ids):
        device_id = str(device_id)
        if device_id == primary_consuming_device_id or device_id not in device_limits_w:
            continue
        if not bool(_device_policy_value(cfg, device_id, 'surplus_allowed', False)):
            continue
        try:
            priority = int(_device_policy_value(cfg, device_id, 'priority', 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        surplus_candidates.append((priority, -rank, device_id))
    preferred_surplus_device_id = max(surplus_candidates)[2] if surplus_candidates else ''

    changed = (
        quarter_key != str(previous_quarter_key or '')
        or primary_consuming_device_id != previous_primary
    )
    return HaeoNetZeroPlan(
        active=True,
        quarter_key=quarter_key,
        primary_consuming_device_id=primary_consuming_device_id,
        preferred_surplus_device_id=preferred_surplus_device_id,
        device_limits_w=device_limits_w,
        reason=reason,
        changed=bool(changed),
    )
