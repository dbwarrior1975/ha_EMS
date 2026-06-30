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
    adjustable_surplus_load: EntityRef
    adjustable_primary_load: EntityRef
    adjustable_surplus_activation_w: ScalarRef


@dataclass
class CoreDeviceCapabilitiesConfig:
    can_absorb_w: bool
    can_produce_w: bool
    min_absorb_w: ScalarRef
    max_absorb_w: ScalarRef
    step_w: ScalarRef
    max_produce_w: Optional[ScalarRef] = None


@dataclass
class CoreBatteryPolicyConfig:
    priority: ScalarRef
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
    required_power_w: EntityRef
    rpnz_w: EntityRef
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
    decision_trace: EntityRef
    device_policies: EntityRef
    surplus_policy_active: EntityRef


@dataclass
class CoreRoleConstraintsConfig:
    default: Optional[dict[str, ScalarRef]] = None
    by_role: Optional[dict[str, dict[str, dict[str, ScalarRef]]]] = None

    def __post_init__(self):
        if self.default is None:
            self.default = {}
        if self.by_role is None:
            self.by_role = {}


CoreDeviceConfig = Union[
    'CoreBatteryDeviceConfig',
    'CoreEvChargerDeviceConfig',
    'CoreRelayDeviceConfig',
]


@dataclass
class CoreConfig:
    profiles: CoreProfilesConfig
    global_config: CoreGlobalConfig
    home_battery: CoreBatteryDeviceConfig
    runtime: CoreRuntimeConfig
    state: CoreStateConfig
    policy_outputs: CorePolicyOutputsConfig
    haeo: Optional[CoreHaeoConfig] = None
    role_constraints: Optional[CoreRoleConstraintsConfig] = None
    devices: Optional[dict[str, CoreDeviceConfig]] = None
    ev_charger: Optional[CoreEvChargerDeviceConfig] = None
    deadband_w: Optional[ScalarRef] = None
    ramp_max_w: Optional[ScalarRef] = None
    strict_limits_max_w: Optional[ScalarRef] = None
    default_sp_w: Optional[ScalarRef] = None
    battery_heartbeat_timeout_s: Optional[ScalarRef] = None
    haeo_stale_timeout_s: Optional[ScalarRef] = None
    max_solar_charge_w: Optional[ScalarRef] = None
    max_battery_discharge_w: Optional[ScalarRef] = None
    battery_protect_soc: Optional[ScalarRef] = None
    battery_protect_soc_recovery_margin: Optional[ScalarRef] = None
    battery_protect_min_cell_voltage_v: Optional[ScalarRef] = None
    battery_protect_charge_floor_w: Optional[ScalarRef] = None
    nz_battery_floor_default_w: Optional[ScalarRef] = None
    nz_battery_floor_ev_active_w: Optional[ScalarRef] = None
    adjustable_surplus_load: Optional[EntityRef] = None
    adjustable_primary_load: Optional[EntityRef] = None
    adjustable_surplus_activation: Optional[ScalarRef] = None
    surplus_freeze_s: Optional[ScalarRef] = None
    adjustable_surplus_load_priority: Optional[ScalarRef] = None

    def __post_init__(self):
        if self.role_constraints is None:
            self.role_constraints = CoreRoleConstraintsConfig()
        if self.devices is None:
            self.devices = {}
        if 'HOME_BATTERY' not in self.devices:
            self.devices['HOME_BATTERY'] = self.home_battery
        self.home_battery = self._resolve_home_battery_device()
        self.ev_charger = self._resolve_ev_compat_device()
        if self.deadband_w is None:
            self.deadband_w = self.global_config.deadband_w
        if self.ramp_max_w is None:
            self.ramp_max_w = self.global_config.ramp_w
        if self.strict_limits_max_w is None:
            self.strict_limits_max_w = self.global_config.strict_limit_w
        if self.default_sp_w is None:
            self.default_sp_w = self.global_config.default_sp_w
        if self.battery_heartbeat_timeout_s is None:
            self.battery_heartbeat_timeout_s = self.global_config.battery_heartbeat_timeout_s
        if self.haeo_stale_timeout_s is None:
            self.haeo_stale_timeout_s = self.global_config.haeo_stale_timeout_s
        if self.max_solar_charge_w is None:
            self.max_solar_charge_w = self.home_battery.capabilities.max_absorb_w
        if self.max_battery_discharge_w is None:
            self.max_battery_discharge_w = self.home_battery.capabilities.max_produce_w
        if self.battery_protect_soc is None:
            self.battery_protect_soc = self.home_battery.guard.protect_soc
        if self.battery_protect_soc_recovery_margin is None:
            self.battery_protect_soc_recovery_margin = self.home_battery.guard.protect_soc_recovery_margin
        if self.battery_protect_min_cell_voltage_v is None:
            self.battery_protect_min_cell_voltage_v = self.home_battery.guard.protect_min_cell_voltage_v
        if self.battery_protect_charge_floor_w is None:
            self.battery_protect_charge_floor_w = self.home_battery.guard.protect_min_absorb_w
        if self.nz_battery_floor_default_w is None:
            self.nz_battery_floor_default_w = self.global_config.nz_battery_floor_default_w
        if self.nz_battery_floor_ev_active_w is None:
            self.nz_battery_floor_ev_active_w = self.global_config.nz_battery_floor_ev_active_w
        if self.adjustable_surplus_load is None:
            self.adjustable_surplus_load = self.global_config.adjustable_surplus_load
        if self.adjustable_primary_load is None:
            self.adjustable_primary_load = self.global_config.adjustable_primary_load
        if self.adjustable_surplus_activation is None:
            self.adjustable_surplus_activation = self.global_config.adjustable_surplus_activation_w
        if self.surplus_freeze_s is None:
            self.surplus_freeze_s = self.global_config.surplus_freeze_s
        if self.adjustable_surplus_load_priority is None:
            self.adjustable_surplus_load_priority = self.home_battery.policy.priority
    def device_by_id(self, device_id: str) -> Optional[CoreDeviceConfig]:
        if self.devices is None:
            return None
        return self.devices.get(device_id)

    def _resolve_home_battery_device(self) -> CoreBatteryDeviceConfig:
        device = self.device_by_id('HOME_BATTERY')
        if device is not None and str(device.kind) == 'BATTERY':
            return device
        return self.home_battery

    def first_device_by_kind(self, kind: str) -> Optional[CoreDeviceConfig]:
        devices = self.devices_by_kind(kind)
        if not devices:
            return None
        return devices[0]

    def nth_device_by_kind(self, kind: str, index: int) -> Optional[CoreDeviceConfig]:
        devices = self.devices_by_kind(kind)
        if index < 0 or index >= len(devices):
            return None
        return devices[index]

    def _resolve_ev_compat_device(self) -> Optional[CoreEvChargerDeviceConfig]:
        device = self.device_by_id('EV_CHARGER')
        if device is not None and str(device.kind) == 'EV_CHARGER':
            return device
        return self.first_device_by_kind('EV_CHARGER')

    def devices_by_kind(self, kind: str) -> tuple[CoreDeviceConfig, ...]:
        if self.devices is None:
            return ()
        items = []
        for device in self.devices.values():
            if str(device.kind) == str(kind):
                items.append(device)
        return tuple(items)

    def surplus_capable_devices(self) -> tuple[CoreDeviceConfig, ...]:
        if self.devices is None:
            return ()
        items = []
        for device in self.devices.values():
            if str(device.kind) == 'BATTERY':
                continue
            if bool(device.capabilities.can_absorb_w):
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
    adjustable_surplus_load: str = ''
    primary_device_id: str = ''
    adjustable_device_id: str = ''
    device_limits_w: Optional[dict] = None
    battery_limit_w: int = 0
    ev_limit_w: int = 0
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
    decision_name: str
    priority: int
    rank: int
    threshold_w: int
    enabled: bool = True
    force_on: bool = False
    active: bool = False
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
    surplus_next_target: str
    surplus_next_threshold_kw: float
    surplus_release_candidate: str
    surplus_dispatch_decision: str
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
