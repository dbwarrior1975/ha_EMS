from dataclasses import dataclass
from ems_core.domain.models import GuardProfile, RuntimeMeasurements, EmsConfig

@dataclass(frozen=True)
class GuardDecision:
    guard: str
    soc_stale: bool
    transport_ok: bool
    soc_valid: bool
    reason: str

def evaluate_guard(current_guard: str, m: RuntimeMeasurements, cfg: EmsConfig) -> GuardDecision:
    transport_ok = m.battery_heartbeat_age_s <= cfg.battery_heartbeat_timeout_s
    soc_valid = m.soc is not None and 0 <= m.soc <= 100
    soc_stale = (not transport_ok) or (not soc_valid)
    min_cell_voltage_valid = m.min_cell_voltage_v is not None and m.min_cell_voltage_v > 0

    if current_guard == GuardProfile.STRICT_LIMITS:
        return GuardDecision(current_guard, soc_stale, transport_ok, soc_valid, 'STRICT_LIMITS is user selected; EMS will not override')

    if soc_stale:
        return GuardDecision(GuardProfile.DEGRADED, soc_stale, transport_ok, soc_valid, 'battery inverter/SOC data is stale or invalid')

    soc_low = m.soc is not None and m.soc < cfg.battery_protect_soc
    min_cell_low = min_cell_voltage_valid and m.min_cell_voltage_v < cfg.battery_protect_min_cell_voltage_v

    if soc_low and min_cell_low:
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, 'Battery protect active: SOC and minimum cell voltage below thresholds')
    if soc_low:
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, 'Battery protect active: SOC below threshold')
    if min_cell_low:
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, 'Battery protect active: minimum cell voltage below threshold')

    if current_guard == GuardProfile.BATTERY_PROTECT:
        soc_recovered = m.soc is not None and m.soc >= (cfg.battery_protect_soc + cfg.battery_protect_soc_recovery_margin)
        min_cell_recovered = min_cell_voltage_valid and m.min_cell_voltage_v >= cfg.battery_protect_min_cell_voltage_v
        if soc_recovered and min_cell_recovered:
            return GuardDecision(GuardProfile.NORMAL_LIMITS, soc_stale, transport_ok, soc_valid, 'Guard recovered: SOC recovery margin reached and minimum cell voltage threshold restored')
        return GuardDecision(GuardProfile.BATTERY_PROTECT, soc_stale, transport_ok, soc_valid, 'Battery protect persists until SOC recovery margin and minimum cell voltage threshold are both satisfied')

    if current_guard == GuardProfile.DEGRADED:
        return GuardDecision(GuardProfile.NORMAL_LIMITS, soc_stale, transport_ok, soc_valid, 'Guard recovered: data fresh and SOC OK')

    return GuardDecision(current_guard, soc_stale, transport_ok, soc_valid, 'Guard unchanged')
