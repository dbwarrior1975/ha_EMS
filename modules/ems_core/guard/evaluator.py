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


def _v3_battery_guard_value(cfg, field_name, default=None):
    if hasattr(cfg, 'v3_battery_guard_value'):
        return cfg.v3_battery_guard_value(field_name, default)
    battery = None
    if hasattr(cfg, 'device_ids_by_kind') and hasattr(cfg, 'device_by_id'):
        battery_ids = tuple(cfg.device_ids_by_kind('BATTERY') or ())
        battery = cfg.device_by_id(battery_ids[0]) if battery_ids else None
    elif hasattr(cfg, 'devices_by_kind'):
        batteries = tuple(cfg.devices_by_kind('BATTERY') or ())
        battery = batteries[0] if batteries else None
    guard = getattr(battery, 'guard', None) if battery is not None else None
    return getattr(guard, field_name, default) if guard is not None else default


def evaluate_guard(current_guard: str, m: RuntimeMeasurements, cfg: CoreConfig) -> GuardDecision:
    transport_ok = m.battery_heartbeat_age_s <= float(_global_config_value(cfg, 'battery_heartbeat_timeout_s', 360.0))
    soc_valid = m.soc is not None and 0 <= m.soc <= 100
    soc_stale = (not transport_ok) or (not soc_valid)
    min_cell_voltage_valid = m.min_cell_voltage_v is not None and m.min_cell_voltage_v > 0

    if current_guard == GuardProfile.STRICT_LIMITS:
        return GuardDecision(current_guard, soc_stale, transport_ok, soc_valid, 'STRICT_LIMITS is user selected; EMS will not override')

    if soc_stale:
        return GuardDecision(GuardProfile.DEGRADED, soc_stale, transport_ok, soc_valid, 'battery inverter/SOC data is stale or invalid')

    soc_low = m.soc is not None and m.soc < float(_v3_battery_guard_value(cfg, 'protect_soc', 2.0))
    min_cell_low = min_cell_voltage_valid and m.min_cell_voltage_v < float(_v3_battery_guard_value(cfg, 'protect_min_cell_voltage_v', 3.03))

    if soc_low and min_cell_low:
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, 'Battery protect active: SOC and minimum cell voltage below thresholds')
    if soc_low:
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, 'Battery protect active: SOC below threshold')
    if min_cell_low:
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, 'Battery protect active: minimum cell voltage below threshold')

    if current_guard == GuardProfile.BATTERY_PROTECT:
        soc_recovered = m.soc is not None and m.soc >= (float(_v3_battery_guard_value(cfg, 'protect_soc', 2.0)) + float(_v3_battery_guard_value(cfg, 'protect_soc_recovery_margin', 1.0)))
        min_cell_recovered = min_cell_voltage_valid and m.min_cell_voltage_v >= float(_v3_battery_guard_value(cfg, 'protect_min_cell_voltage_v', 3.03))
        if soc_recovered and min_cell_recovered:
            return GuardDecision(GuardProfile.NORMAL_LIMITS, soc_stale, transport_ok, soc_valid, 'Guard recovered: SOC recovery margin reached and minimum cell voltage threshold restored')
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, 'Battery protect persists until SOC recovery margin and minimum cell voltage threshold are both satisfied')

    if current_guard == GuardProfile.DEGRADED:
        return GuardDecision(GuardProfile.NORMAL_LIMITS, soc_stale, transport_ok, soc_valid, 'Guard recovered: data fresh and SOC OK')

    return GuardDecision(current_guard, soc_stale, transport_ok, soc_valid, 'Guard unchanged')
