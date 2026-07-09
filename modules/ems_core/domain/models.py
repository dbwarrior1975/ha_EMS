from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Union


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


ScalarRef = Union[str, int, float]
EntityRef = str


@dataclass
class Profiles:
    control: str
    goal: str
    forecast: str
    guard: str


@dataclass
class CoreProfilesConfig:
    control: EntityRef
    goal: EntityRef
    forecast: EntityRef
    guard: EntityRef


@dataclass
class CoreGlobalConfig:
    deadband_w: ScalarRef
    ramp_w: ScalarRef
    strict_limit_w: ScalarRef
    default_sp_w: ScalarRef
    surplus_freeze_s: ScalarRef
    battery_heartbeat_timeout_s: ScalarRef
    haeo_stale_timeout_s: ScalarRef
    nz_battery_floor_default_w: ScalarRef
    nz_battery_floor_ev_active_w: ScalarRef
    primary_device_id: EntityRef


@dataclass
class CoreDeviceCapabilitiesConfig:
    can_absorb_w: bool
    can_produce_w: bool
    supports_primary_regulation: bool
    supports_residual_regulation: bool
    min_absorb_w: ScalarRef
    max_absorb_w: ScalarRef
    step_w: ScalarRef
    max_produce_w: Optional[ScalarRef] = None
    uses_hard_off_lifecycle: bool = False


@dataclass
class DeviceControlContext:
    device_id: str
    kind: str
    can_absorb_w: bool
    can_produce_w: bool
    min_absorb_w: float
    max_absorb_w: float
    max_produce_w: float
    step_w: float
    supports_primary_regulation: bool
    supports_residual_regulation: bool
    uses_hard_off_lifecycle: bool
    priority: int
    current_measured_power_w: float = 0.0


@dataclass
class HardOffLifecycleTransition:
    low_pv_cycles: int
    hard_off_release_ready_cycles: int
    hard_off_active: bool
    activation_allowed: bool
    release_allowed: bool
    recovery_condition: bool
    mode: str


@dataclass
class CoreBatteryPolicyConfig:
    priority: ScalarRef
    surplus_allowed: bool = False
    surplus_dispatch_mode: str = 'max_absorb'
    default_min_absorb_w: Optional[ScalarRef] = None


@dataclass
class CoreBatteryGuardConfig:
    soc: EntityRef
    min_cell_voltage_v: EntityRef
    heartbeat: EntityRef
    protect_soc: ScalarRef
    protect_soc_recovery_margin: ScalarRef
    protect_min_cell_voltage_v: ScalarRef
    protect_min_absorb_w: ScalarRef


@dataclass
class CoreBatteryAdapterConfig:
    target_w: EntityRef
    measured_power_w: EntityRef


@dataclass
class CoreBatteryDeviceConfig:
    device_id: str
    kind: str
    capabilities: CoreDeviceCapabilitiesConfig
    policy: CoreBatteryPolicyConfig
    guard: CoreBatteryGuardConfig
    adapter: CoreBatteryAdapterConfig


@dataclass
class CoreEvPolicyConfig:
    priority: ScalarRef
    surplus_allowed: EntityRef
    force_on: EntityRef
    low_pv_threshold_w: ScalarRef
    hard_off_low_pv_cycles: ScalarRef
    hard_off_release_cycles: ScalarRef
    surplus_dispatch_mode: str = 'max_absorb'


@dataclass
class CoreEvAdapterConfig:
    enabled: EntityRef
    current_a: EntityRef
    current_step_a: ScalarRef
    phases: ScalarRef
    voltage_v: ScalarRef


@dataclass
class CoreEvChargerDeviceConfig:
    device_id: str
    kind: str
    capabilities: CoreDeviceCapabilitiesConfig
    policy: CoreEvPolicyConfig
    adapter: CoreEvAdapterConfig


@dataclass
class CoreRelayPolicyConfig:
    priority: ScalarRef
    surplus_allowed: EntityRef
    force_on: EntityRef
    surplus_dispatch_mode: str = 'fixed'


@dataclass
class CoreRelayAdapterConfig:
    enabled: EntityRef


@dataclass
class CoreRelayDeviceConfig:
    device_id: str
    kind: str
    capabilities: CoreDeviceCapabilitiesConfig
    policy: CoreRelayPolicyConfig
    adapter: CoreRelayAdapterConfig


@dataclass
class CoreRuntimeConfig:
    grid_power_w: EntityRef
    quarter_energy_balance_kwh: EntityRef
    pv_power_w: EntityRef


@dataclass
class CoreHaeoConfig:
    battery_power_active: EntityRef
    ev_power_active: EntityRef
    battery_fresh_source: EntityRef
    ev_fresh_source: EntityRef


@dataclass
class CoreStateConfig:
    surplus_freeze_until: EntityRef
    active_surplus_devices: EntityRef


@dataclass
class CorePolicyOutputsConfig:
    device_policies: EntityRef
    dispatch_command: EntityRef
    policy_state: EntityRef


@dataclass
class CoreDiagnosticsOutputsConfig:
    policy_diagnostics: EntityRef
    actuator_writer_trace: EntityRef
    dispatch_state_applier_trace: EntityRef


@dataclass
class CoreRoleConstraintsConfig:
    default: Optional[dict[str, ScalarRef]] = None
    by_role: Optional[dict[str, dict[str, dict[str, ScalarRef]]]] = None

    def __post_init__(self):
        if self.default is None:
            self.default = {}
        if self.by_role is None:
            self.by_role = {}


@dataclass
class CorePolicyEngineConfig:
    interval_seconds: float = 5.0
    diagnostics_interval_seconds: float = 30.0


CoreDeviceConfig = Union[
    'CoreBatteryDeviceConfig',
    'CoreEvChargerDeviceConfig',
    'CoreRelayDeviceConfig',
]


@dataclass
class CoreConfig:
    profiles: CoreProfilesConfig
    policy_engine: Optional[CorePolicyEngineConfig]
    global_config: CoreGlobalConfig
    runtime: CoreRuntimeConfig
    state: CoreStateConfig
    policy_outputs: CorePolicyOutputsConfig
    diagnostics_outputs: CoreDiagnosticsOutputsConfig
    haeo: Optional[CoreHaeoConfig] = None
    role_constraints: Optional[CoreRoleConstraintsConfig] = None
    devices: Optional[dict[str, CoreDeviceConfig]] = None

    def __post_init__(self):
        if self.policy_engine is None:
            self.policy_engine = CorePolicyEngineConfig()
        if self.role_constraints is None:
            self.role_constraints = CoreRoleConstraintsConfig()
        if self.devices is None:
            self.devices = {}

    def device_by_id(self, device_id: str) -> Optional[CoreDeviceConfig]:
        if self.devices is None:
            return None
        return self.devices.get(str(device_id))

    def device_ids_by_kind(self, kind: str) -> tuple[str, ...]:
        ids = []
        kind_text = str(kind)
        if self.devices is None:
            return ()
        for device_id, device in self.devices.items():
            if str(device.kind) == kind_text:
                ids.append(str(device_id))
        return tuple(ids)

    def devices_by_kind(self, kind: str) -> tuple[CoreDeviceConfig, ...]:
        if self.devices is None:
            return ()
        items = []
        kind_text = str(kind)
        for device in self.devices.values():
            if str(device.kind) == kind_text:
                items.append(device)
        return tuple(items)


@dataclass
class RuntimeMeasurements:
    now_ts: float
    soc: Optional[float]
    min_cell_voltage_v: Optional[float]
    battery_heartbeat_age_s: float
    grid_power_w: float
    current_battery_setpoint_w: float
    quarter_energy_balance_kwh: float
    pv_power_w: Optional[float] = None
    relay_states: Optional[dict[str, dict]] = None
    ev_states: Optional[dict[str, dict]] = None

    def __post_init__(self):
        if self.relay_states is None:
            self.relay_states = {}
        if self.ev_states is None:
            self.ev_states = {}


@dataclass
class HaeoTargets:
    effective_forecast: str
    configured_forecast: str
    fresh: bool
    battery_target_kw: float = 0.0
    ev_target_kw: float = 0.0


@dataclass
class HaeoNetZeroPlan:
    active: bool
    quarter_key: str = ''
    primary_load: str = ''
    primary_device_id: str = ''
    preferred_surplus_device_id: str = ''
    device_limits_w: Optional[dict] = None
    reason: str = ''
    changed: bool = False

    def __post_init__(self):
        if self.device_limits_w is None:
            self.device_limits_w = {}


@dataclass
class NetZeroState:
    rpnz_w: float
    required_power_consumption_kw: float


@dataclass
class EmsDeviceConfig:
    device_id: str
    kind: str
    response_kind: str
    can_absorb_w: bool
    can_produce_w: bool
    min_absorb_w: int
    max_absorb_w: int
    max_produce_w: int
    step_w: int
    priority: int
    enabled: bool = True


@dataclass
class EmsDeviceState:
    device_id: str
    available: bool
    active: bool
    measured_power_w: int
    current_target_w: int
    guard_state: str = 'OK'


@dataclass
class EmsDevice:
    config: EmsDeviceConfig
    state: EmsDeviceState


@dataclass
class DevicePolicy:
    device_id: str
    target_w: int
    enabled: bool
    mode: str
    reason: str = ''


@dataclass
class SurplusDeviceTarget:
    device_id: str
    priority: int
    rank: int
    threshold_w: int
    enabled: bool = True
    force_on: bool = False
    active: bool = False
    activation_allowed: bool = True
    surplus_dispatch_mode: str = ''
    threshold_source: str = ''
    incremental_surplus_threshold_w: Optional[int] = None


@dataclass
class SurplusDispatchInput:
    policy_active: bool
    freeze_until_ts: Optional[float]
    rpc_kw: float
    rpnz_w: float
    targets: tuple[SurplusDeviceTarget, ...]


@dataclass
class SurplusDispatchDecision:
    activate: Optional[str] = None
    release: Optional[str] = None
    clear_all: bool = False
    freeze_until_ts: Optional[float] = None
    explanation: str = ''


@dataclass
class NetZeroOutputs:
    battery_write_enabled: bool
    battery_target_w: int
    surplus_policy_active: bool
    surplus_next_threshold_kw: float
    surplus_explanation: str
    effective_forecast: str
    dominant_limitation: str
    explanation: str
    device_policies: Optional[tuple[DevicePolicy, ...]] = None
    attrs: Optional[dict] = None

    def __post_init__(self):
        if self.device_policies is None:
            self.device_policies = ()
        if self.attrs is None:
            self.attrs = {}
