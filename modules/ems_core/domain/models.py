from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal


class ControlProfile:
    MANUAL = 'MANUAL'
    MANUAL_SAFE = 'MANUAL_SAFE'
    AUTOMATIC = 'AUTOMATIC'
    HORIZON_BY_HAEO = 'HORIZON_BY_HAEO'


class GoalProfile:
    NET_ZERO = 'NET_ZERO'
    MAX_EXPORT = 'MAX_EXPORT'
    CHEAP_GRID_CHARGE = 'CHEAP_GRID_CHARGE'


class ForecastProfile:
    NONE = 'NONE'
    HAEO = 'HAEO'


class GuardProfile:
    NORMAL_LIMITS = 'NORMAL_LIMITS'
    STRICT_LIMITS = 'STRICT_LIMITS'
    BATTERY_PROTECT = 'BATTERY_PROTECT'
    DEGRADED = 'DEGRADED'


class DominantLimitation:
    SYSTEM_DEGRADED = 'SYSTEM_DEGRADED'
    BATTERY_SOC_LIMIT = 'BATTERY_SOC_LIMIT'
    USER_MANUAL_OVERRIDE = 'USER_MANUAL_OVERRIDE'
    MANUAL_SAFE_ACTIVE = 'MANUAL_SAFE_ACTIVE'
    STRICT_POWER_LIMITS = 'STRICT_POWER_LIMITS'
    FORECAST_FALLBACK_LOCAL = 'FORECAST_FALLBACK_LOCAL'
    OPTIMIZATION_ACTIVE = 'OPTIMIZATION_ACTIVE'


@dataclass(frozen=True)
class Profiles:
    control: str
    goal: str
    forecast: str
    guard: str


@dataclass(frozen=True)
class EmsConfig:
    deadband_w: float = 50.0
    ramp_max_w: float = 1000.0
    strict_limits_max_w: float = 4600.0
    max_battery_discharge_w: float = 4600.0
    default_sp_w: float = 100.0
    max_solar_charge_w: float = 3700.0
    battery_protect_soc: float = 2.0
    battery_protect_soc_recovery_margin: float = 1.0
    battery_protect_min_cell_voltage_v: float = 3.030
    battery_protect_charge_floor_w: float = 0.0
    battery_heartbeat_timeout_s: float = 360.0
    haeo_stale_timeout_s: float = 300.0
    ev_min_current_a: int = 6
    ev_max_current_a: int = 28
    ev_charger_phases: int = 1
    ev_force_current_a: int = 0
    ev_hard_off_pv_threshold_kw: float = 1.6
    ev_hard_off_low_pv_cycles: int = 2
    ev_hard_off_release_cycles: int = 2
    ev_current_step_a: int = 4
    nz_battery_floor_default_w: float = 100.0
    nz_battery_floor_ev_active_w: float = 0.0
    adjustable_surplus_load: str = 'HOME_BATTERY'
    adjustable_primary_load: str = ''
    adjustable_surplus_activation: float = 0.0
    adjustable_surplus_load_priority: int = 3
    relay1_power_kw: float = 2.5
    relay2_power_kw: float = 5.0
    relay1_priority: int = 2
    relay2_priority: int = 1
    ev_priority: int = 3
    surplus_freeze_s: int = 30


@dataclass(frozen=True)
class RuntimeMeasurements:
    now_ts: float
    soc: Optional[float]
    min_cell_voltage_v: Optional[float]
    battery_heartbeat_age_s: float
    grid_power_w: float
    current_battery_setpoint_w: float
    hourly_energy_balance_kwh: float
    charger_on: bool
    charger_current_a: int
    relay1_on: bool
    relay2_on: bool


@dataclass(frozen=True)
class HaeoTargets:
    effective_forecast: str
    configured_forecast: str
    fresh: bool
    battery_target_kw: float = 0.0
    ev_target_kw: float = 0.0


@dataclass(frozen=True)
class NetZeroState:
    rpnz_w: float
    required_power_consumption_kw: float


@dataclass(frozen=True)
class SurplusTargetConfig:
    name: Literal['EV', 'BATTERY', 'ADJUSTABLE', 'RELAY1', 'RELAY2']
    priority: int
    rank: int
    threshold_kw: float
    enabled: bool = True
    force_on: bool = False
    active: bool = False


@dataclass(frozen=True)
class SurplusDispatchInput:
    policy_active: bool
    freeze_until_ts: Optional[float]
    rpc_kw: float
    rpnz_w: float
    targets: tuple[SurplusTargetConfig, ...]


@dataclass(frozen=True)
class SurplusDispatchDecision:
    activate: Optional[str] = None
    release: Optional[str] = None
    clear_all: bool = False
    freeze_until_ts: Optional[float] = None
    explanation: str = ''


@dataclass(frozen=True)
class NetZeroOutputs:
    battery_write_enabled: bool
    battery_target_w: int
    ev_current_a: int
    relay1_command: int
    relay2_command: int
    surplus_policy_active: bool
    surplus_next_target: str
    surplus_next_threshold_kw: float
    surplus_release_candidate: str
    surplus_dispatch_decision: str
    surplus_explanation: str
    effective_forecast: str
    dominant_limitation: str
    explanation: str
    attrs: dict = field(default_factory=dict)
