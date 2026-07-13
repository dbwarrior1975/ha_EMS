from dataclasses import dataclass

from ems_core.domain.models import CoreConfig, GuardProfile, RuntimeMeasurements


@dataclass
class GuardDecision:
    guard: str
    soc_stale: bool
    transport_ok: bool
    soc_valid: bool
    reason: str


def _global_config_value(cfg, field_name, default=None):
    global_config = getattr(cfg, 'global_config', None)
    return getattr(global_config, field_name, default) if global_config is not None else default


def _device_by_id(cfg, device_id):
    if hasattr(cfg, 'device_by_id'):
        return cfg.device_by_id(str(device_id))
    return (getattr(cfg, 'devices', {}) or {}).get(str(device_id))


def _device_kind(cfg, device_id):
    if hasattr(cfg, 'device_kind'):
        return str(cfg.device_kind(str(device_id)) or '')
    device = _device_by_id(cfg, device_id)
    return str(getattr(device, 'kind', '') or '') if device is not None else ''


def _device_capability(cfg, device_id, field, default=None):
    if hasattr(cfg, 'device_capability'):
        return cfg.device_capability(str(device_id), str(field), default)
    device = _device_by_id(cfg, device_id)
    caps = getattr(device, 'capabilities', None) if device is not None else None
    return getattr(caps, field, default) if caps is not None else default


def _battery_guard_value(cfg, device_id, field_name, default=None):
    if hasattr(cfg, 'battery_guard_value'):
        return cfg.battery_guard_value(str(device_id), field_name, default)
    device = _device_by_id(cfg, device_id)
    guard = getattr(device, 'guard', None) if device is not None else None
    return getattr(guard, field_name, default) if guard is not None else default


def _guard_battery_device_ids(cfg):
    ids = []
    primary_ids = tuple(
        getattr(getattr(cfg, 'global_config', None), 'primary_consuming_device_ids', ()) or ()
    )
    for primary_id in primary_ids:
        primary_id = str(primary_id or '')
        if primary_id and _device_kind(cfg, primary_id) == 'BATTERY' and primary_id not in ids:
            ids.append(primary_id)
    devices = getattr(cfg, 'device_kind_by_id', None)
    if isinstance(devices, dict):
        ordered_ids = tuple(devices)
    else:
        ordered_ids = tuple((getattr(cfg, 'devices', {}) or {}).keys())
    for device_id in ordered_ids:
        device_id = str(device_id)
        if _device_kind(cfg, device_id) != 'BATTERY':
            continue
        if not bool(_device_capability(cfg, device_id, 'supports_producing_regulation', False)):
            continue
        if device_id not in ids:
            ids.append(device_id)
    return tuple(ids)


def evaluate_guard(current_guard: str, m: RuntimeMeasurements, cfg: CoreConfig) -> GuardDecision:
    battery_ids = _guard_battery_device_ids(cfg)
    if not battery_ids:
        return GuardDecision(current_guard, False, True, True, 'No guarded battery regulator configured')

    timeout_s = float(_global_config_value(cfg, 'battery_heartbeat_timeout_s', 360.0))
    states = []
    for device_id in battery_ids:
        state = dict((getattr(m, 'battery_states', {}) or {}).get(device_id, {}) or {})
        heartbeat_age_s = float(state.get('heartbeat_age_s', float('inf')))
        soc = state.get('soc')
        min_cell = state.get('min_cell_voltage_v')
        transport_ok = heartbeat_age_s <= timeout_s
        soc_valid = soc is not None and 0 <= float(soc) <= 100
        min_cell_valid = min_cell is not None and float(min_cell) > 0
        states.append((device_id, state, transport_ok, soc_valid, min_cell_valid))

    transport_ok = True
    soc_valid = True
    for item in states:
        transport_ok = transport_ok and bool(item[2])
        soc_valid = soc_valid and bool(item[3])
    soc_stale = (not transport_ok) or (not soc_valid)

    if current_guard == GuardProfile.STRICT_LIMITS:
        return GuardDecision(current_guard, soc_stale, transport_ok, soc_valid, 'STRICT_LIMITS is user selected; EMS will not override')

    if soc_stale:
        return GuardDecision(GuardProfile.DEGRADED, soc_stale, transport_ok, soc_valid, 'battery regulator inverter/SOC data is stale or invalid')

    low_reasons = []
    any_soc_low = False
    any_min_cell_low = False
    for device_id, state, _transport_ok, _soc_valid, min_cell_valid in states:
        soc = float(state['soc'])
        min_cell = state.get('min_cell_voltage_v')
        soc_low = soc < float(_battery_guard_value(cfg, device_id, 'protect_soc', 2.0))
        min_cell_low = min_cell_valid and float(min_cell) < float(
            _battery_guard_value(cfg, device_id, 'protect_min_cell_voltage_v', 3.03)
        )
        any_soc_low = any_soc_low or soc_low
        any_min_cell_low = any_min_cell_low or min_cell_low
        if soc_low:
            low_reasons.append(f'{device_id}:SOC')
        if min_cell_low:
            low_reasons.append(f'{device_id}:MIN_CELL')
    if low_reasons:
        if len(states) == 1:
            if any_soc_low and any_min_cell_low:
                reason = 'Battery protect active: SOC and minimum cell voltage below thresholds'
            elif any_soc_low:
                reason = 'Battery protect active: SOC below threshold'
            else:
                reason = 'Battery protect active: minimum cell voltage below threshold'
        else:
            reason = 'Battery protect active: ' + ','.join(low_reasons)
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, reason)

    if current_guard == GuardProfile.BATTERY_PROTECT:
        for device_id, state, _transport_ok, _soc_valid, min_cell_valid in states:
            soc_recovered = float(state['soc']) >= (
                float(_battery_guard_value(cfg, device_id, 'protect_soc', 2.0))
                + float(_battery_guard_value(cfg, device_id, 'protect_soc_recovery_margin', 1.0))
            )
            min_cell_recovered = min_cell_valid and float(state['min_cell_voltage_v']) >= float(
                _battery_guard_value(cfg, device_id, 'protect_min_cell_voltage_v', 3.03)
            )
            if not (soc_recovered and min_cell_recovered):
                reason = (
                    'Battery protect persists until SOC recovery margin and minimum cell voltage threshold are both satisfied'
                    if len(states) == 1
                    else 'Battery protect persists until all guarded battery regulators recover'
                )
                return GuardDecision(
                    GuardProfile.BATTERY_PROTECT,
                    soc_stale,
                    transport_ok,
                    soc_valid,
                    reason,
                )
        reason = (
            'Guard recovered: SOC recovery margin reached and minimum cell voltage threshold restored'
            if len(states) == 1
            else 'Guard recovered: all guarded battery regulators recovered'
        )
        return GuardDecision(GuardProfile.NORMAL_LIMITS, soc_stale, transport_ok, soc_valid, reason)

    if current_guard == GuardProfile.DEGRADED:
        reason = 'Guard recovered: data fresh and SOC OK' if len(states) == 1 else 'Guard recovered: regulator data fresh and SOC OK'
        return GuardDecision(GuardProfile.NORMAL_LIMITS, soc_stale, transport_ok, soc_valid, reason)

    return GuardDecision(current_guard, soc_stale, transport_ok, soc_valid, 'Guard unchanged')
