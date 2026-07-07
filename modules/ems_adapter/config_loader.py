from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from types import MappingProxyType, SimpleNamespace
from typing import Callable, Literal, Optional, Union

from ems_core.domain.models import (
    CoreBatteryAdapterConfig,
    CoreBatteryDeviceConfig,
    CoreBatteryGuardConfig,
    CoreBatteryPolicyConfig,
    CoreConfig,
    CoreDiagnosticsOutputsConfig,
    CoreDeviceCapabilitiesConfig,
    CoreEvAdapterConfig,
    CoreEvChargerDeviceConfig,
    CoreEvPolicyConfig,
    CoreGlobalConfig,
    CoreHaeoConfig,
    CorePolicyEngineConfig,
    CorePolicyOutputsConfig,
    CoreProfilesConfig,
    CoreRelayAdapterConfig,
    CoreRelayDeviceConfig,
    CoreRelayPolicyConfig,
    CoreRoleConstraintsConfig,
    CoreRuntimeConfig,
    CoreStateConfig,
)
from ems_core.domain.constants import (
    CANONICAL_DIAGNOSTICS_OUTPUTS,
    CANONICAL_POLICY_OUTPUTS,
)
from ems_adapter.direct_runtime import (
    RUNTIME_SCHEMA_VERSION,
    StaticTopology,
    build_static_topology,
)

from ems_core.domain.ev_power import (
    ev_current_a_to_power_w,
    ev_max_current_a_from_max_absorb_w,
    ev_max_power_w,
    ev_min_current_a_from_min_absorb_w,
    ev_min_power_w,
    ev_power_step_w,
)


# Production default: no per-run policy-runtime-facts detailed timings.
# Flip to True temporarily together with engine.NET_ZERO_DETAILED_METRICS_ENABLED
# when profiling facts construction.
POLICY_RUNTIME_FACTS_DETAILED_METRICS_ENABLED = True


def set_policy_runtime_facts_detailed_metrics_enabled(enabled):
    global POLICY_RUNTIME_FACTS_DETAILED_METRICS_ENABLED
    POLICY_RUNTIME_FACTS_DETAILED_METRICS_ENABLED = bool(enabled)


def policy_runtime_facts_detailed_metrics_enabled():
    return bool(POLICY_RUNTIME_FACTS_DETAILED_METRICS_ENABLED)


def _policy_runtime_facts_profile_started_ts():
    if not POLICY_RUNTIME_FACTS_DETAILED_METRICS_ENABLED:
        return 0.0
    return time.time()


SEVERITY_ERROR = 'ERROR'
SEVERITY_WARNING = 'WARNING'

REQUIRED_TOP_LEVEL_SECTIONS = (
    'profiles',
    'global_config',
    'devices',
    'runtime',
    'state',
)
OPTIONAL_TOP_LEVEL_SECTIONS = (
    'role_constraints',
    'haeo',
    'policy_engine',
    'runtime_sources',
)
REJECTED_TOP_LEVEL_SECTIONS = frozenset(
    (
        'policy_outputs',
        'diagnostics_outputs',
    )
)
SUPPORTED_DEVICE_KINDS = {
    'BATTERY',
    'EV_CHARGER',
    'RELAY',
}
REQUIRED_DEVICE_IDS = (
    'HOME_BATTERY',
)
EXPECTED_DEVICE_KINDS = {
    'HOME_BATTERY': 'BATTERY',
}
ALLOWED_ROLE_KEYS = {
    'default',
    'EV_PRIMARY',
    'HOME_BATTERY_PRIMARY',
}
ALLOWED_EMS_SECTION_KEYS = frozenset(REQUIRED_TOP_LEVEL_SECTIONS + OPTIONAL_TOP_LEVEL_SECTIONS)
ALLOWED_POLICY_ENGINE_KEYS = frozenset(('interval_seconds', 'diagnostics_interval_seconds'))
ALLOWED_GLOBAL_CONFIG_KEYS = frozenset(
    (
        'deadband_w',
        'ramp_w',
        'strict_limit_w',
        'default_sp_w',
        'surplus_freeze_s',
        'battery_heartbeat_timeout_s',
        'haeo_stale_timeout_s',
        'nz_battery_floor_default_w',
        'nz_battery_floor_ev_active_w',
        'adjustable_primary_load',
    )
)
ALLOWED_RUNTIME_KEYS = frozenset(
    (
        'grid_power_w',
        'quarter_energy_balance_kwh',
        'pv_power_w',
    )
)
LEGACY_RUNTIME_REJECTIONS = {
    'required_power_w': (
        'runtime.required_power_w is no longer accepted; required power is derived inside EMS '
        'from grid_power_w, quarter_energy_balance_kwh, and current quarter time.'
    ),
    'rpnz_w': (
        'runtime.rpnz_w is no longer accepted; RPNZ is derived inside EMS from '
        'quarter_energy_balance_kwh and current quarter time.'
    ),
    'pv_power_kw': 'runtime.pv_power_kw is no longer accepted; use runtime.pv_power_w.',
}
RUNTIME_PACKET_SOURCE_KEYS = frozenset(('policy_config', 'measurements', 'policy_state'))
RUNTIME_PACKET_SCHEMA_VERSION = RUNTIME_SCHEMA_VERSION

PACKET_DEFAULT_PROFILES = {
    'control': 'AUTOMATIC',
    'goal': 'NET_ZERO',
    'forecast': 'NONE',
    'guard': 'NORMAL_LIMITS',
}
PACKET_DEFAULT_GLOBAL_CONFIG = {
    'deadband_w': 50.0,
    'ramp_w': 1000.0,
    'strict_limit_w': 4600.0,
    'default_sp_w': 100.0,
    'surplus_freeze_s': 30.0,
    'battery_heartbeat_timeout_s': 360.0,
    'haeo_stale_timeout_s': 300.0,
    'nz_battery_floor_default_w': 100.0,
    'nz_battery_floor_ev_active_w': 0.0,
    'adjustable_primary_load': '',
}
PACKET_DEFAULT_RUNTIME = {
    'grid_power_w': 0.0,
    'quarter_energy_balance_kwh': 0.0,
    'pv_power_w': 0.0,
}
PACKET_DEFAULT_STATE = {
    'surplus_freeze_until': '',
    'active_surplus_devices': (),
    'previous_device_state': {},
}
PACKET_DEFAULT_HAEO = {
    'battery_power_active': {},
    'ev_power_active': {},
    'battery_fresh_source': False,
    'ev_fresh_source': False,
}

PACKET_STATIC_CAPABILITY_FIELDS = frozenset(('can_absorb_w', 'can_produce_w', 'supports_primary_regulation', 'supports_residual_regulation'))
PACKET_RUNTIME_CAPABILITY_FIELDS_BY_KIND = {
    'BATTERY': {
        'uses_hard_off_lifecycle': False,
        'supports_primary_regulation': True,
        'supports_residual_regulation': True,
        'min_absorb_w': 0.0,
        'max_absorb_w': 0.0,
        'max_produce_w': 0.0,
        'step_w': 1.0,
    },
    'EV_CHARGER': {
        'uses_hard_off_lifecycle': True,
        'supports_primary_regulation': True,
        'supports_residual_regulation': False,
        'min_absorb_w': 0.0,
        'max_absorb_w': 0.0,
        'max_produce_w': 0.0,
        'step_w': 1.0,
    },
    'RELAY': {
        'uses_hard_off_lifecycle': False,
        'supports_primary_regulation': False,
        'supports_residual_regulation': False,
        'min_absorb_w': 0.0,
        'max_absorb_w': 0.0,
        'max_produce_w': 0.0,
        'step_w': 1.0,
    },
}
PACKET_RUNTIME_POLICY_FIELDS_BY_KIND = {
    'BATTERY': {
        'priority': 0,
        'surplus_allowed': False,
        'surplus_dispatch_mode': 'max_absorb',
        'default_min_absorb_w': 0.0,
    },
    'EV_CHARGER': {
        'priority': 0,
        'surplus_allowed': False,
        'surplus_dispatch_mode': 'max_absorb',
        'force_on': False,
        'low_pv_threshold_w': 1600.0,
        'hard_off_low_pv_cycles': 15,
        'hard_off_release_cycles': 100,
    },
    'RELAY': {
        'priority': 0,
        'surplus_allowed': False,
        'surplus_dispatch_mode': 'fixed',
        'force_on': False,
    },
}
PACKET_RUNTIME_GUARD_FIELDS_BY_KIND = {
    'BATTERY': {
        'soc': None,
        'min_cell_voltage_v': None,
        'heartbeat': None,
        'protect_soc': 100.0,
        'protect_soc_recovery_margin': 0.0,
        'protect_min_cell_voltage_v': 99.0,
        'protect_min_absorb_w': 0.0,
    },
}
PACKET_RUNTIME_ADAPTER_FIELDS_BY_KIND = {
    'BATTERY': {
        'target_w': 0.0,
        'measured_power_w': 0.0,
    },
    'EV_CHARGER': {
        'enabled': False,
        'current_a': 0.0,
        'current_step_a': 1.0,
        'phases': 1,
        'voltage_v': 230.0,
    },
    'RELAY': {
        'enabled': False,
    },
}
ALLOWED_DEVICE_KEYS = frozenset(('kind', 'capabilities', 'policy', 'adapter', 'guard'))
ALLOWED_CAPABILITIES_KEYS = frozenset(
    (
        'can_absorb_w',
        'can_produce_w',
        'min_absorb_w',
        'max_absorb_w',
        'step_w',
        'max_produce_w',
        'uses_hard_off_lifecycle',
        'supports_primary_regulation',
        'supports_residual_regulation',
    )
)
ALLOWED_BATTERY_POLICY_KEYS = frozenset(('priority', 'surplus_allowed', 'surplus_dispatch_mode', 'default_min_absorb_w'))
ALLOWED_BATTERY_GUARD_KEYS = frozenset(
    (
        'soc',
        'min_cell_voltage_v',
        'heartbeat',
        'protect_soc',
        'protect_soc_recovery_margin',
        'protect_min_cell_voltage_v',
        'protect_min_absorb_w',
    )
)
ALLOWED_BATTERY_ADAPTER_KEYS = frozenset(('target_w', 'measured_power_w'))
ALLOWED_EV_POLICY_KEYS = frozenset(
    (
        'priority',
        'surplus_allowed',
        'surplus_dispatch_mode',
        'force_on',
        'low_pv_threshold_w',
        'hard_off_low_pv_cycles',
        'hard_off_release_cycles',
    )
)
ALLOWED_EV_ADAPTER_KEYS = frozenset(('enabled', 'current_a', 'current_step_a', 'phases', 'voltage_v'))
ALLOWED_RELAY_POLICY_KEYS = frozenset(('priority', 'surplus_allowed', 'surplus_dispatch_mode', 'force_on'))
ALLOWED_RELAY_ADAPTER_KEYS = frozenset(('enabled',))


@dataclass
class ConfigValidationIssue:
    path: str
    severity: Literal['ERROR', 'WARNING']
    message: str


@dataclass
class ConfigValidationResult:
    ok: bool
    issues: tuple[ConfigValidationIssue, ...]
    errors: Optional[tuple[ConfigValidationIssue, ...]] = None
    warnings: Optional[tuple[ConfigValidationIssue, ...]] = None


@dataclass
class RuntimeAlias:
    runtime_key: str
    config_path: str
    value: str
    unit_transform: str = 'identity'


@dataclass
class DynamicConfigRef:
    path: str
    entity_id: str
    value_type: str
    default: object


@dataclass
class StaticDevicePlan:
    device_id: str
    kind: str
    static_capabilities: object
    static_adapter: object
    static_policy: object
    static_guard: Optional[object]
    dynamic_refs: tuple[DynamicConfigRef, ...]
    grouped_device_plan: dict


@dataclass
class CompiledEMSPlan:
    profiles: dict
    policy_engine: dict
    global_config: dict
    runtime: dict
    state: dict
    devices: dict[str, StaticDevicePlan]
    home_battery: StaticDevicePlan
    haeo: Optional[dict]
    role_constraints: dict
    grouped_config_plan: dict
    policy_runtime_facts_plan: Optional[dict] = None
    static_topology: Optional[StaticTopology] = None


CompiledCoreConfigPlan = CompiledEMSPlan


@dataclass
class DynamicRuntimeSnapshot:
    profiles: dict
    global_config: dict
    runtime: dict
    state: dict
    device_values: dict[str, dict]
    home_battery_values: dict
    haeo_values: Optional[dict]
    role_constraint_values: dict


@dataclass
class PolicyContext:
    plan: CompiledEMSPlan
    snapshot: DynamicRuntimeSnapshot


_MATERIALIZE_CACHE_MISS = object()
_NO_DYNAMIC_SNAPSHOT_VALUE = object()


class CoreConfigDevicesView:
    def __init__(self, cfg_view):
        self._cfg_view = cfg_view
        keys = []
        for device_id in cfg_view._device_order:
            keys.append(str(device_id))
        self._keys = tuple(keys)

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)

    def __contains__(self, device_id):
        return str(device_id) in self._keys

    def __getitem__(self, device_id):
        device = self._cfg_view._materialize_device(str(device_id))
        if device is None:
            raise KeyError(device_id)
        return device

    def get(self, device_id, default=None):
        device = self._cfg_view._materialize_device(str(device_id))
        if device is None:
            return default
        return device

    def keys(self):
        return tuple(self._keys)

    def values(self):
        values = []
        for device_id in self._keys:
            # Pyscript compatibility: avoid routing through __getitem__ here.
            # In Pyscript, dunder dispatch can surface coroutine objects to
            # policy code that expects concrete device objects.
            device = self._cfg_view._materialize_device(str(device_id))
            if device is not None:
                values.append(device)
        return tuple(values)

    def items(self):
        items = []
        for device_id in self._keys:
            # Pyscript compatibility: avoid self[device_id] / __getitem__.
            device = self._cfg_view._materialize_device(str(device_id))
            if device is not None:
                items.append((device_id, device))
        return tuple(items)


class CoreConfigView:
    def __init__(self, context: PolicyContext):
        self._context = context
        self._device_cache = {}
        self._policy_runtime_facts_cache = None
        self._legacy_device_bridge_count = 0
        self._legacy_device_bridge_counts_by_kind = {}
        self._device_order = tuple(context.plan.devices.keys()) + ('HOME_BATTERY',)
        self.profiles = _build_view_profiles(context.snapshot.profiles)
        self.policy_engine = _build_view_policy_engine(context.plan.policy_engine)
        self.global_config = _build_view_global_config(context.snapshot.global_config)
        self.runtime = _build_view_runtime(context.snapshot.runtime)
        self.state = _build_view_state(context.snapshot.state)
        self.haeo = _build_view_haeo(context.snapshot.haeo_values)
        self.role_constraints = _build_view_role_constraints(context.snapshot.role_constraint_values)
        self.policy_outputs = CorePolicyOutputsConfig(
            device_policies=CANONICAL_POLICY_OUTPUTS['device_policies'],
            dispatch_command=CANONICAL_POLICY_OUTPUTS['dispatch_command'],
            policy_state=CANONICAL_POLICY_OUTPUTS['policy_state'],
        )
        self.diagnostics_outputs = CoreDiagnosticsOutputsConfig(
            policy_diagnostics=CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics'],
            actuator_writer_trace=CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace'],
            dispatch_state_applier_trace=CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace'],
        )
        self.devices = CoreConfigDevicesView(self)
        self.deadband_w = self.global_config.deadband_w
        self.ramp_max_w = self.global_config.ramp_w
        self.strict_limits_max_w = self.global_config.strict_limit_w
        self.default_sp_w = self.global_config.default_sp_w
        self.battery_heartbeat_timeout_s = self.global_config.battery_heartbeat_timeout_s
        self.haeo_stale_timeout_s = self.global_config.haeo_stale_timeout_s
        self.max_solar_charge_w = self.home_battery_capability('max_absorb_w')
        self.max_battery_discharge_w = self.home_battery_capability('max_produce_w')
        self.battery_protect_soc = self.home_battery_guard_value('protect_soc')
        self.battery_protect_soc_recovery_margin = self.home_battery_guard_value('protect_soc_recovery_margin')
        self.battery_protect_min_cell_voltage_v = self.home_battery_guard_value('protect_min_cell_voltage_v')
        self.battery_protect_charge_floor_w = self.home_battery_guard_value('protect_min_absorb_w')
        self.nz_battery_floor_default_w = self.global_config.nz_battery_floor_default_w
        self.nz_battery_floor_ev_active_w = self.global_config.nz_battery_floor_ev_active_w
        self.adjustable_primary_load = self.global_config.adjustable_primary_load
        self.surplus_freeze_s = self.global_config.surplus_freeze_s

    def __getattr__(self, name: str):
        if name == 'home_battery':
            return self._materialize_device('HOME_BATTERY')
        if name == 'ev_charger':
            return self.first_device_by_kind('EV_CHARGER')
        raise AttributeError(name)

    def device_by_id(self, device_id: str):
        return self._materialize_device(str(device_id))

    def device_ids_by_kind(self, kind: str) -> tuple[str, ...]:
        matched = []
        kind_text = str(kind)
        for device_id in self._device_order:
            if self.device_kind(device_id) == kind_text:
                matched.append(str(device_id))
        return tuple(matched)

    def device_kind(self, device_id: str) -> str:
        device_plan = self._device_plan(device_id)
        if device_plan is None:
            return ''
        return str(device_plan.kind)

    def device_priority(self, device_id: str):
        return self.device_policy_value(device_id, 'priority')

    def device_surplus_allowed(self, device_id: str):
        return self.device_policy_value(device_id, 'surplus_allowed')

    def device_force_on(self, device_id: str):
        return self.device_policy_value(device_id, 'force_on')

    def device_enabled(self, device_id: str):
        return self.device_adapter_value(device_id, 'enabled')

    def device_capability(self, device_id: str, field: str, default=None):
        return self._device_section_value(device_id, 'capabilities', field, default)

    def device_adapter_value(self, device_id: str, field: str, default=None):
        return self._device_section_value(device_id, 'adapter', field, default)

    def device_policy_value(self, device_id: str, field: str, default=None):
        return self._device_section_value(device_id, 'policy', field, default)

    def home_battery_guard_value(self, field: str, default=None):
        return self._device_section_value('HOME_BATTERY', 'guard', field, default)

    def home_battery_capability(self, field: str, default=None):
        return self.device_capability('HOME_BATTERY', field, default)

    def ev_adapter_value(self, device_id: str, field: str, default=None):
        if self.device_kind(device_id) != 'EV_CHARGER':
            return default
        return self.device_adapter_value(device_id, field, default)

    def legacy_device_bridge_count(self) -> int:
        return int(self._legacy_device_bridge_count)

    def legacy_device_bridge_counts_by_kind(self) -> dict[str, int]:
        counts = {}
        for kind, count in self._legacy_device_bridge_counts_by_kind.items():
            counts[str(kind)] = int(count)
        return counts

    def policy_runtime_facts(self) -> dict:
        cached = self._policy_runtime_facts_cache
        if cached is not None:
            return cached
        facts = build_policy_runtime_facts_from_context(
            self._context.plan,
            self._context.snapshot,
            policy_runtime_facts_plan=self._context.plan.policy_runtime_facts_plan,
        )
        self._policy_runtime_facts_cache = facts
        return facts

    def first_device_by_kind(self, kind: str):
        kind_text = str(kind)
        if kind_text == 'BATTERY':
            return self.home_battery
        for device_id, device_plan in self._context.plan.devices.items():
            if str(device_plan.kind) != kind_text:
                continue
            return self._materialize_device(str(device_id))
        return None

    def devices_by_kind(self, kind: str) -> tuple[object, ...]:
        matched = []
        kind_text = str(kind)
        if kind_text == 'BATTERY':
            matched.append(self.home_battery)
        for device_id, device_plan in self._context.plan.devices.items():
            if str(device_plan.kind) != kind_text:
                continue
            device = self._materialize_device(str(device_id))
            if device is not None:
                matched.append(device)
        return tuple(matched)

    def _device_plan(self, device_id: str) -> Optional[StaticDevicePlan]:
        device_id = str(device_id)
        if device_id == 'HOME_BATTERY':
            return self._context.plan.home_battery
        return self._context.plan.devices.get(device_id)

    def _device_values(self, device_id: str) -> Optional[dict]:
        device_id = str(device_id)
        if device_id == 'HOME_BATTERY':
            return self._context.snapshot.home_battery_values
        return self._context.snapshot.device_values.get(device_id)

    def _device_section_value(self, device_id: str, section: str, field: str, default=None):
        device_plan = self._device_plan(device_id)
        if device_plan is None:
            return default
        values = self._device_values(device_id)
        return _resolve_snapshot_backed_section_value(
            device_plan,
            values,
            str(section),
            str(field),
            default,
        )

    def _note_legacy_device_bridge(self, kind: str):
        kind = str(kind)
        self._legacy_device_bridge_count += 1
        self._legacy_device_bridge_counts_by_kind[kind] = int(
            self._legacy_device_bridge_counts_by_kind.get(kind, 0) or 0
        ) + 1

    def _materialize_device(self, device_id: str):
        if device_id in self._device_cache:
            return self._device_cache[device_id]
        device_plan = self._device_plan(device_id)
        values = self._device_values(device_id)
        if device_plan is None or values is None:
            return None
        kind = str(device_plan.kind)
        if kind == 'EV_CHARGER':
            device = _build_view_ev_device(device_plan, values)
        elif kind == 'RELAY':
            device = _build_view_relay_device(device_plan, values)
        elif kind == 'BATTERY':
            device = _build_view_battery_device(device_plan, values)
        else:
            return None
        self._note_legacy_device_bridge(kind)
        self._device_cache[device_id] = device
        return device


def load_grouped_ems_config(path: Union[str, Path]) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f'Grouped EMS config not found: {config_path}')

    yaml = _load_yaml_module()
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        raise ValueError(f'Invalid YAML in {config_path}: {exc}') from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValueError(f'Grouped EMS config root must be a mapping: {config_path}')
    return loaded


def _load_yaml_module():
    import yaml

    return yaml


def _runtime_packet_sources_from_ems(ems: object) -> Optional[dict[str, str]]:
    if not isinstance(ems, dict):
        return None
    sources = ems.get('runtime_sources')
    if not isinstance(sources, dict):
        return None
    resolved = {}
    for key in RUNTIME_PACKET_SOURCE_KEYS:
        source = sources.get(key)
        entity_id = None
        if isinstance(source, dict):
            entity_id = source.get('entity_id')
        elif isinstance(source, str):
            entity_id = source
        if not _is_valid_entity_id(entity_id):
            return None
        resolved[str(key)] = str(entity_id)
    return resolved


def _ems_uses_runtime_packets(ems: object) -> bool:
    return _runtime_packet_sources_from_ems(ems) is not None


def _config_uses_runtime_packets(config: object) -> bool:
    if not isinstance(config, dict):
        return False
    return _ems_uses_runtime_packets(config.get('ems'))


def _deep_mutable_copy(value: object) -> object:
    if isinstance(value, dict):
        copied = {}
        for key, item in value.items():
            copied[key] = _deep_mutable_copy(item)
        return copied
    if isinstance(value, list):
        copied = []
        for item in value:
            copied.append(_deep_mutable_copy(item))
        return copied
    if isinstance(value, tuple):
        copied = []
        for item in value:
            copied.append(_deep_mutable_copy(item))
        return tuple(copied)
    return value


def _ensure_dict(parent: dict, key: str) -> dict:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _setdefault_fields(section: dict, defaults: dict) -> None:
    for key, value in defaults.items():
        if key not in section:
            section[key] = _deep_mutable_copy(value)


def _normalize_runtime_packet_config_for_compile(config: dict) -> dict:
    if not _config_uses_runtime_packets(config):
        return config
    normalized = _deep_mutable_copy(config)
    if not isinstance(normalized, dict):
        return config
    ems = _ensure_dict(normalized, 'ems')
    _setdefault_fields(_ensure_dict(ems, 'profiles'), PACKET_DEFAULT_PROFILES)
    _setdefault_fields(_ensure_dict(ems, 'global_config'), PACKET_DEFAULT_GLOBAL_CONFIG)
    _setdefault_fields(_ensure_dict(ems, 'runtime'), PACKET_DEFAULT_RUNTIME)
    _setdefault_fields(_ensure_dict(ems, 'state'), PACKET_DEFAULT_STATE)
    _setdefault_fields(_ensure_dict(ems, 'haeo'), PACKET_DEFAULT_HAEO)

    devices = _ensure_dict(ems, 'devices')
    for _device_id, device in devices.items():
        if not isinstance(device, dict):
            continue
        kind = str(device.get('kind') or '')
        capabilities = _ensure_dict(device, 'capabilities')
        _setdefault_fields(capabilities, PACKET_RUNTIME_CAPABILITY_FIELDS_BY_KIND.get(kind, {}))
        policy = _ensure_dict(device, 'policy')
        _setdefault_fields(policy, PACKET_RUNTIME_POLICY_FIELDS_BY_KIND.get(kind, {}))
        guard_defaults = PACKET_RUNTIME_GUARD_FIELDS_BY_KIND.get(kind, {})
        if guard_defaults:
            guard = _ensure_dict(device, 'guard')
            _setdefault_fields(guard, guard_defaults)
        adapter = _ensure_dict(device, 'adapter')
        _setdefault_fields(adapter, PACKET_RUNTIME_ADAPTER_FIELDS_BY_KIND.get(kind, {}))
    return normalized


def _validate_runtime_sources(runtime_sources: object, issues: list[ConfigValidationIssue]) -> None:
    if not isinstance(runtime_sources, dict):
        issues.append(_issue('ems.runtime_sources', SEVERITY_ERROR, 'missing or not a mapping'))
        return
    _validate_unknown_fields(runtime_sources, 'ems.runtime_sources', RUNTIME_PACKET_SOURCE_KEYS, issues)
    for key in RUNTIME_PACKET_SOURCE_KEYS:
        source = runtime_sources.get(key)
        entity_id = None
        if isinstance(source, dict):
            _validate_unknown_fields(source, f'ems.runtime_sources.{key}', frozenset(('entity_id',)), issues)
            entity_id = source.get('entity_id')
        elif isinstance(source, str):
            entity_id = source
        else:
            issues.append(_issue(f'ems.runtime_sources.{key}', SEVERITY_ERROR, 'must be a mapping with entity_id'))
            continue
        if not _is_valid_entity_id(entity_id):
            issues.append(_issue(f'ems.runtime_sources.{key}.entity_id', SEVERITY_ERROR, 'must be a non-empty entity id string'))


def load_and_validate_grouped_ems_config(path: Union[str, Path]) -> tuple[dict, ConfigValidationResult]:
    config = load_grouped_ems_config(path)
    return config, validate_grouped_ems_config(config)


def validate_grouped_ems_config(config: dict) -> ConfigValidationResult:
    issues: list[ConfigValidationIssue] = []

    ems = config.get('ems')
    if not isinstance(ems, dict):
        issues.append(_issue('ems', SEVERITY_ERROR, 'missing or not a mapping'))
        return _validation_result(False, issues)

    runtime_packet_mode = 'runtime_sources' in ems
    _validate_unknown_fields(
        ems,
        'ems',
        frozenset(tuple(ALLOWED_EMS_SECTION_KEYS) + tuple(REJECTED_TOP_LEVEL_SECTIONS)),
        issues,
    )
    _validate_rejected_top_level_sections(ems, issues)

    if runtime_packet_mode:
        required_sections = ('runtime_sources', 'devices')
    else:
        required_sections = REQUIRED_TOP_LEVEL_SECTIONS
    for section in required_sections:
        if section not in ems:
            issues.append(_issue(f'ems.{section}', SEVERITY_ERROR, 'missing required section'))
        elif not isinstance(ems.get(section), dict):
            issues.append(_issue(f'ems.{section}', SEVERITY_ERROR, 'must be a mapping'))

    for section in OPTIONAL_TOP_LEVEL_SECTIONS:
        if section in ems and not isinstance(ems.get(section), dict):
            issues.append(_issue(f'ems.{section}', SEVERITY_ERROR, 'must be a mapping'))

    if runtime_packet_mode:
        _validate_runtime_sources(ems.get('runtime_sources'), issues)

    devices = ems.get('devices', {})
    if isinstance(devices, dict):
        _validate_devices(devices, issues, runtime_packet_mode=runtime_packet_mode)
        _validate_device_capability_semantics(ems, devices, issues)
    else:
        devices = {}

    if isinstance(ems.get('profiles'), dict) and not runtime_packet_mode:
        _validate_required_entities(
            ems['profiles'],
            'ems.profiles',
            ('control', 'goal', 'forecast', 'guard'),
            issues,
        )

    if runtime_packet_mode and 'global_config' in ems:
        issues.append(
            _issue(
                'ems.global_config',
                SEVERITY_ERROR,
                'runtime-packet mode owns global policy config via '
                'sensor.ems_policy_config_runtime attribute config; remove static ems.global_config',
            )
        )
    elif isinstance(ems.get('global_config'), dict):
        _validate_unknown_fields(
            ems['global_config'],
            'ems.global_config',
            ALLOWED_GLOBAL_CONFIG_KEYS,
            issues,
        )
        _validate_required_entities(
            ems['global_config'],
            'ems.global_config',
            ('deadband_w', 'ramp_w', 'strict_limit_w', 'surplus_freeze_s', 'haeo_stale_timeout_s', 'adjustable_primary_load'),
            issues,
        )

    if isinstance(ems.get('runtime'), dict):
        _validate_legacy_runtime_fields(ems['runtime'], issues)
        _validate_unknown_fields(
            ems['runtime'],
            'ems.runtime',
            frozenset(tuple(ALLOWED_RUNTIME_KEYS) + tuple(LEGACY_RUNTIME_REJECTIONS)),
            issues,
        )
        if not runtime_packet_mode:
            _validate_required_entities(
                ems['runtime'],
                'ems.runtime',
                ('grid_power_w', 'quarter_energy_balance_kwh', 'pv_power_w'),
                issues,
            )

    if isinstance(ems.get('policy_engine'), dict):
        _validate_unknown_fields(
            ems['policy_engine'],
            'ems.policy_engine',
            ALLOWED_POLICY_ENGINE_KEYS,
            issues,
        )
        raw_interval = ems['policy_engine'].get('interval_seconds', 5.0)
        try:
            _parse_policy_engine_interval_seconds(raw_interval)
        except ValueError as exc:
            issues.append(_issue('ems.policy_engine.interval_seconds', SEVERITY_ERROR, str(exc)))
        raw_diagnostics_interval = ems['policy_engine'].get('diagnostics_interval_seconds', 30.0)
        try:
            _parse_policy_engine_diagnostics_interval_seconds(raw_diagnostics_interval)
        except ValueError as exc:
            issues.append(_issue('ems.policy_engine.diagnostics_interval_seconds', SEVERITY_ERROR, str(exc)))

    if isinstance(ems.get('state'), dict) and not runtime_packet_mode:
        _validate_required_entities(
            ems['state'],
            'ems.state',
            ('surplus_freeze_until', 'active_surplus_devices', 'previous_device_state'),
            issues,
        )

    if isinstance(ems.get('haeo'), dict) and not runtime_packet_mode:
        _validate_required_entities(
            ems['haeo'],
            'ems.haeo',
            ('battery_power_active', 'ev_power_active', 'battery_fresh_source', 'ev_fresh_source'),
            issues,
        )

    if isinstance(ems.get('role_constraints'), dict) and not runtime_packet_mode:
        _validate_role_constraints(ems['role_constraints'], devices, issues)

    has_error = False
    for issue in issues:
        if issue.severity == SEVERITY_ERROR:
            has_error = True
            break
    return _validation_result(not has_error, issues)


def _validation_result(ok: bool, issues: list[ConfigValidationIssue]) -> ConfigValidationResult:
    errors = []
    warnings = []
    for issue in issues:
        if issue.severity == SEVERITY_ERROR:
            errors.append(issue)
        if issue.severity == SEVERITY_WARNING:
            warnings.append(issue)
    return ConfigValidationResult(
        ok=ok,
        issues=tuple(issues),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _validate_rejected_top_level_sections(
    ems: dict,
    issues: list[ConfigValidationIssue],
) -> None:
    if 'policy_outputs' in ems:
        issues.append(
            _issue(
                'ems.policy_outputs',
                SEVERITY_ERROR,
                'ems.policy_outputs is no longer user config. EMS canonical policy output entity IDs are fixed in code.',
            )
        )
    if 'diagnostics_outputs' in ems:
        issues.append(
            _issue(
                'ems.diagnostics_outputs',
                SEVERITY_ERROR,
                'ems.diagnostics_outputs is no longer user config. EMS diagnostics output entity IDs are fixed in code.',
            )
        )


def _validate_legacy_runtime_fields(
    runtime: dict,
    issues: list[ConfigValidationIssue],
) -> None:
    for field_name, message in LEGACY_RUNTIME_REJECTIONS.items():
        if field_name in runtime:
            issues.append(_issue(f'ems.runtime.{field_name}', SEVERITY_ERROR, message))


def build_runtime_aliases(config: dict) -> tuple[RuntimeAlias, ...]:
    ems = config.get('ems', {})
    profiles = ems.get('profiles', {})
    global_config = ems.get('global_config', {})
    runtime = ems.get('runtime', {})
    devices = ems.get('devices', {})

    aliases = [
        _alias('control_profile', 'ems.profiles.control', profiles.get('control')),
        _alias('goal_profile', 'ems.profiles.goal', profiles.get('goal')),
        _alias('forecast_profile', 'ems.profiles.forecast', profiles.get('forecast')),
        _alias('guard_profile', 'ems.profiles.guard', profiles.get('guard')),
    ]
    if not _ems_uses_runtime_packets(ems):
        aliases.extend(
            [
                _alias('deadband_w', 'ems.global_config.deadband_w', global_config.get('deadband_w')),
                _alias('ramp_max_w', 'ems.global_config.ramp_w', global_config.get('ramp_w')),
                _alias('strict_limits_max_w', 'ems.global_config.strict_limit_w', global_config.get('strict_limit_w')),
                _alias('surplus_freeze_s', 'ems.global_config.surplus_freeze_s', global_config.get('surplus_freeze_s')),
                _alias('haeo_stale_timeout_s', 'ems.global_config.haeo_stale_timeout_s', global_config.get('haeo_stale_timeout_s')),
                _alias('nz_battery_floor_default_w', 'ems.global_config.nz_battery_floor_default_w', global_config.get('nz_battery_floor_default_w')),
                _alias('nz_battery_floor_ev_active_w', 'ems.global_config.nz_battery_floor_ev_active_w', global_config.get('nz_battery_floor_ev_active_w')),
                _alias('adjustable_primary_load', 'ems.global_config.adjustable_primary_load', global_config.get('adjustable_primary_load')),
            ]
        )

    home_battery = devices.get('HOME_BATTERY', {})
    battery_guard = home_battery.get('guard', {}) if isinstance(home_battery, dict) else {}
    battery_capabilities = home_battery.get('capabilities', {}) if isinstance(home_battery, dict) else {}
    battery_policy = home_battery.get('policy', {}) if isinstance(home_battery, dict) else {}
    battery_adapter = home_battery.get('adapter', {}) if isinstance(home_battery, dict) else {}
    aliases.extend(
        [
            _alias('max_solar_charge_w', 'ems.devices.HOME_BATTERY.capabilities.max_absorb_w', battery_capabilities.get('max_absorb_w')),
            _alias('max_battery_discharge_w', 'ems.devices.HOME_BATTERY.capabilities.max_produce_w', battery_capabilities.get('max_produce_w')),
            _alias('battery_protect_soc', 'ems.devices.HOME_BATTERY.guard.protect_soc', battery_guard.get('protect_soc')),
            _alias('battery_protect_soc_recovery_margin', 'ems.devices.HOME_BATTERY.guard.protect_soc_recovery_margin', battery_guard.get('protect_soc_recovery_margin')),
            _alias('battery_protect_min_cell_voltage_v', 'ems.devices.HOME_BATTERY.guard.protect_min_cell_voltage_v', battery_guard.get('protect_min_cell_voltage_v')),
            _alias('battery_protect_charge_floor_w', 'ems.devices.HOME_BATTERY.guard.protect_min_absorb_w', battery_guard.get('protect_min_absorb_w')),
            _alias('soc', 'ems.devices.HOME_BATTERY.guard.soc', battery_guard.get('soc')),
            _alias('min_cell_voltage_v', 'ems.devices.HOME_BATTERY.guard.min_cell_voltage_v', battery_guard.get('min_cell_voltage_v')),
            _alias('battery_heartbeat', 'ems.devices.HOME_BATTERY.guard.heartbeat', battery_guard.get('heartbeat')),
            _alias('current_battery_sp', 'ems.devices.HOME_BATTERY.adapter.target_w', battery_adapter.get('target_w')),
            _alias('actuator_battery_setpoint_w', 'ems.devices.HOME_BATTERY.adapter.target_w', battery_adapter.get('target_w')),
        ]
    )

    ev = _first_device_of_kind(devices, 'EV_CHARGER')
    ev_capabilities = ev.get('capabilities', {}) if isinstance(ev, dict) else {}
    ev_policy = ev.get('policy', {}) if isinstance(ev, dict) else {}
    ev_adapter = ev.get('adapter', {}) if isinstance(ev, dict) else {}
    ev_id = _device_id_of(ev, 'EV_CHARGER')
    aliases.extend(
        [
            _alias('ev_hard_off_pv_threshold_kw', f'ems.devices.{ev_id}.policy.low_pv_threshold_w', ev_policy.get('low_pv_threshold_w'), unit_transform='W_TO_KW'),
            _alias('ev_hard_off_low_pv_cycles', f'ems.devices.{ev_id}.policy.hard_off_low_pv_cycles', ev_policy.get('hard_off_low_pv_cycles')),
            _alias('ev_hard_off_release_cycles', f'ems.devices.{ev_id}.policy.hard_off_release_cycles', ev_policy.get('hard_off_release_cycles')),
            _alias('charger_control', f'ems.devices.{ev_id}.adapter.enabled', ev_adapter.get('enabled')),
            _alias('actuator_ev_enabled', f'ems.devices.{ev_id}.adapter.enabled', ev_adapter.get('enabled')),
            _alias('charger_current', f'ems.devices.{ev_id}.adapter.current_a', ev_adapter.get('current_a')),
            _alias('actuator_ev_current_a', f'ems.devices.{ev_id}.adapter.current_a', ev_adapter.get('current_a')),
            _alias('ev_min_absorb_w', f'ems.devices.{ev_id}.capabilities.min_absorb_w', ev_capabilities.get('min_absorb_w')),
            _alias('ev_max_absorb_w', f'ems.devices.{ev_id}.capabilities.max_absorb_w', ev_capabilities.get('max_absorb_w')),
            _alias('ev_power_step_w', f'ems.devices.{ev_id}.capabilities.step_w', ev_capabilities.get('step_w')),
            _alias('ev_current_step_a', f'ems.devices.{ev_id}.adapter.current_step_a', ev_adapter.get('current_step_a')),
            _alias('ev_charger_phases', f'ems.devices.{ev_id}.adapter.phases', ev_adapter.get('phases')),
            _alias('ev_force_on', f'ems.devices.{ev_id}.policy.force_on', ev_policy.get('force_on')),
        ]
    )

    relay1 = _relay_device_by_index(devices, 0)
    relay1_capabilities = relay1.get('capabilities', {}) if isinstance(relay1, dict) else {}
    relay1_policy = relay1.get('policy', {}) if isinstance(relay1, dict) else {}
    relay1_adapter = relay1.get('adapter', {}) if isinstance(relay1, dict) else {}
    relay1_id = _device_id_of(relay1, 'RELAY1')
    aliases.extend(
        [
            _alias('actuator_relay1', f'ems.devices.{relay1_id}.adapter.enabled', relay1_adapter.get('enabled')),
        ]
    )

    relay2 = _relay_device_by_index(devices, 1)
    relay2_capabilities = relay2.get('capabilities', {}) if isinstance(relay2, dict) else {}
    relay2_policy = relay2.get('policy', {}) if isinstance(relay2, dict) else {}
    relay2_adapter = relay2.get('adapter', {}) if isinstance(relay2, dict) else {}
    relay2_id = _device_id_of(relay2, 'RELAY2')
    aliases.extend(
        [
            _alias('actuator_relay2', f'ems.devices.{relay2_id}.adapter.enabled', relay2_adapter.get('enabled')),
        ]
    )

    active_aliases = []
    for alias in aliases:
        if alias.value:
            active_aliases.append(alias)
    return tuple(active_aliases)


def runtime_alias_index(config: dict) -> dict[str, RuntimeAlias]:
    index = {}
    for alias in build_runtime_aliases(config):
        index[alias.runtime_key] = alias
    return index


def _first_device_of_kind(devices: dict, kind: str) -> dict:
    if not isinstance(devices, dict):
        return {}
    for device_id, device in devices.items():
        if isinstance(device, dict) and str(device.get('kind')) == str(kind):
            mapped = dict(device)
            mapped['_device_id'] = str(device_id)
            return mapped
    return {}


def _relay_device_by_index(devices: dict, index: int) -> dict:
    if not isinstance(devices, dict):
        return {}
    preferred_id = f'RELAY{index + 1}'
    preferred = devices.get(preferred_id)
    if isinstance(preferred, dict) and str(preferred.get('kind')) == 'RELAY':
        mapped = dict(preferred)
        mapped['_device_id'] = preferred_id
        return mapped
    relays = []
    for device_id, device in devices.items():
        if isinstance(device, dict) and str(device.get('kind')) == 'RELAY':
            mapped = dict(device)
            mapped['_device_id'] = str(device_id)
            relays.append(mapped)
    if index < len(relays):
        return relays[index]
    return {}


def _device_id_of(device: dict, default: str) -> str:
    if not isinstance(device, dict):
        return default
    resolved = device.get('device_id') or device.get('_device_id')
    if resolved not in (None, ''):
        return str(resolved)
    return default


def _entity_values_reader(entity_values: dict[str, object]):
    def read_entity(entity_id, default):
        return entity_values.get(entity_id, default)

    return read_entity


def build_core_config_from_grouped_config(config: dict, entity_values: Optional[dict[str, object]] = None) -> CoreConfig:
    return build_core_config_from_grouped_reader(config, _entity_values_reader(entity_values or {}))


def _dynamic_value_type_for_default(default: object) -> str:
    if isinstance(default, bool):
        return 'bool'
    if isinstance(default, int) and not isinstance(default, bool):
        return 'int'
    if isinstance(default, float):
        return 'float'
    return 'str'


def _compile_dynamic_value(value: object, path: str, default: object) -> object:
    if value in (None, 'unknown', 'unavailable', 'none', ''):
        return default
    if _is_valid_entity_id(value):
        return DynamicConfigRef(
            path=path,
            entity_id=str(value),
            value_type=_dynamic_value_type_for_default(default),
            default=default,
        )
    return value


def _materialize_dynamic_value(value: object, read_entity: Callable[[str, object], object]) -> object:
    if isinstance(value, DynamicConfigRef):
        raw_value = read_entity(value.entity_id, value.default)
        if raw_value in (None, 'unknown', 'unavailable', 'none', ''):
            return value.default
        return raw_value
    if isinstance(value, dict):
        materialized = {}
        for key, item in value.items():
            materialized[key] = _materialize_dynamic_value(item, read_entity)
        return materialized
    if isinstance(value, list):
        materialized = []
        for item in value:
            materialized.append(_materialize_dynamic_value(item, read_entity))
        return materialized
    if isinstance(value, tuple):
        materialized = []
        for item in value:
            materialized.append(_materialize_dynamic_value(item, read_entity))
        return tuple(materialized)
    return value



def _compile_core_capabilities_plan(
    device: object,
    *,
    device_path: str,
    default_min_absorb_w: object = 0,
    default_max_absorb_w: object = 0,
    default_step_w: object = 1,
    default_max_produce_w: Optional[object] = None,
) -> dict[str, object]:
    capabilities = _require_mapping_value(device, 'capabilities')
    compiled = {
        'can_absorb_w': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'can_absorb_w'),
            f'{device_path}.capabilities.can_absorb_w',
            False,
        ),
        'can_produce_w': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'can_produce_w'),
            f'{device_path}.capabilities.can_produce_w',
            False,
        ),
        'uses_hard_off_lifecycle': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'uses_hard_off_lifecycle'),
            f'{device_path}.capabilities.uses_hard_off_lifecycle',
            False,
        ),
        'supports_primary_regulation': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'supports_primary_regulation'),
            f'{device_path}.capabilities.supports_primary_regulation',
            False,
        ),
        'supports_residual_regulation': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'supports_residual_regulation'),
            f'{device_path}.capabilities.supports_residual_regulation',
            False,
        ),
        'min_absorb_w': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'min_absorb_w'),
            f'{device_path}.capabilities.min_absorb_w',
            default_min_absorb_w,
        ),
        'max_absorb_w': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'max_absorb_w'),
            f'{device_path}.capabilities.max_absorb_w',
            default_max_absorb_w,
        ),
        'step_w': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'step_w'),
            f'{device_path}.capabilities.step_w',
            default_step_w,
        ) if 'step_w' in capabilities else default_step_w,
        'max_produce_w': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'max_produce_w'),
            f'{device_path}.capabilities.max_produce_w',
            default_max_produce_w,
        ) if 'max_produce_w' in capabilities else None,
    }
    return compiled


def _compile_core_battery_device_plan(
    device_id: str,
    device: object,
    *,
    default_priority: object = 3,
) -> dict[str, object]:
    device_path = f'ems.devices.{device_id}'
    policy = _require_mapping_value(device, 'policy')
    guard = _require_mapping_value(device, 'guard')
    adapter = _require_mapping_value(device, 'adapter')
    return {
        'device_id': str(device_id),
        'kind': _compile_dynamic_value(_require_mapping_value(device, 'kind'), f'{device_path}.kind', 'BATTERY'),
        'capabilities': _compile_core_capabilities_plan(
            device,
            device_path=device_path,
            default_min_absorb_w=0,
            default_max_absorb_w=3700,
            default_step_w=50,
            default_max_produce_w=4600,
        ),
        'policy': {
            'priority': _compile_dynamic_value(
                _require_mapping_value(policy, 'priority'),
                f'{device_path}.policy.priority',
                default_priority,
            ),
            'surplus_allowed': _compile_dynamic_value(policy.get('surplus_allowed', False), f'{device_path}.policy.surplus_allowed', False),
            'surplus_dispatch_mode': _compile_dynamic_value(policy.get('surplus_dispatch_mode', 'max_absorb'), f'{device_path}.policy.surplus_dispatch_mode', 'max_absorb'),
            'default_min_absorb_w': _compile_dynamic_value(
                _require_mapping_value(policy, 'default_min_absorb_w'),
                f'{device_path}.policy.default_min_absorb_w',
                0.0,
            ) if 'default_min_absorb_w' in policy else None,
        },
        'guard': {
            'soc': _compile_dynamic_value(_require_mapping_value(guard, 'soc'), f'{device_path}.guard.soc', ''),
            'min_cell_voltage_v': _compile_dynamic_value(_require_mapping_value(guard, 'min_cell_voltage_v'), f'{device_path}.guard.min_cell_voltage_v', ''),
            'heartbeat': _compile_dynamic_value(_require_mapping_value(guard, 'heartbeat'), f'{device_path}.guard.heartbeat', ''),
            'protect_soc': _compile_dynamic_value(_require_mapping_value(guard, 'protect_soc'), f'{device_path}.guard.protect_soc', 2),
            'protect_soc_recovery_margin': _compile_dynamic_value(_require_mapping_value(guard, 'protect_soc_recovery_margin'), f'{device_path}.guard.protect_soc_recovery_margin', 1),
            'protect_min_cell_voltage_v': _compile_dynamic_value(_require_mapping_value(guard, 'protect_min_cell_voltage_v'), f'{device_path}.guard.protect_min_cell_voltage_v', 3.030),
            'protect_min_absorb_w': _compile_dynamic_value(_require_mapping_value(guard, 'protect_min_absorb_w'), f'{device_path}.guard.protect_min_absorb_w', 0),
        },
        'adapter': {
            'target_w': _compile_dynamic_value(_require_mapping_value(adapter, 'target_w'), f'{device_path}.adapter.target_w', ''),
            'measured_power_w': _compile_dynamic_value(_require_mapping_value(adapter, 'measured_power_w'), f'{device_path}.adapter.measured_power_w', ''),
        },
    }


def _compile_core_ev_device_plan(device_id: str, device: object) -> dict[str, object]:
    device_path = f'ems.devices.{device_id}'
    policy = _require_mapping_value(device, 'policy')
    adapter = _require_mapping_value(device, 'adapter')
    return {
        'device_id': str(device_id),
        'kind': _compile_dynamic_value(_require_mapping_value(device, 'kind'), f'{device_path}.kind', 'EV_CHARGER'),
        'capabilities': _compile_core_capabilities_plan(
            device,
            device_path=device_path,
            default_min_absorb_w=0,
            default_max_absorb_w=0,
            default_step_w=1,
            default_max_produce_w=None,
        ),
        'policy': {
            'priority': _compile_dynamic_value(_require_mapping_value(policy, 'priority'), f'{device_path}.policy.priority', 3),
            'surplus_allowed': _compile_dynamic_value(_require_mapping_value(policy, 'surplus_allowed'), f'{device_path}.policy.surplus_allowed', ''),
            'surplus_dispatch_mode': _compile_dynamic_value(_require_mapping_value(policy, 'surplus_dispatch_mode'), f'{device_path}.policy.surplus_dispatch_mode', 'max_absorb'),
            'force_on': _compile_dynamic_value(_require_mapping_value(policy, 'force_on'), f'{device_path}.policy.force_on', ''),
            'low_pv_threshold_w': _compile_dynamic_value(_require_mapping_value(policy, 'low_pv_threshold_w'), f'{device_path}.policy.low_pv_threshold_w', 1.6),
            'hard_off_low_pv_cycles': _compile_dynamic_value(_require_mapping_value(policy, 'hard_off_low_pv_cycles'), f'{device_path}.policy.hard_off_low_pv_cycles', 2),
            'hard_off_release_cycles': _compile_dynamic_value(_require_mapping_value(policy, 'hard_off_release_cycles'), f'{device_path}.policy.hard_off_release_cycles', 2),
        },
        'adapter': {
            'enabled': _compile_dynamic_value(_require_mapping_value(adapter, 'enabled'), f'{device_path}.adapter.enabled', False),
            'current_a': _compile_dynamic_value(_require_mapping_value(adapter, 'current_a'), f'{device_path}.adapter.current_a', 0),
            'current_step_a': _compile_dynamic_value(_require_mapping_value(adapter, 'current_step_a'), f'{device_path}.adapter.current_step_a', 4),
            'phases': _compile_dynamic_value(_require_mapping_value(adapter, 'phases'), f'{device_path}.adapter.phases', 1),
            'voltage_v': _compile_dynamic_value(_require_mapping_value(adapter, 'voltage_v'), f'{device_path}.adapter.voltage_v', 230),
        },
    }


def _compile_core_relay_device_plan(device_id: str, device: object) -> dict[str, object]:
    device_path = f'ems.devices.{device_id}'
    policy = _require_mapping_value(device, 'policy')
    adapter = _require_mapping_value(device, 'adapter')
    relay_default = 2 if device_id == 'RELAY1' else 1
    relay_power_default = 2.5 if device_id == 'RELAY1' else 5.0
    return {
        'device_id': str(device_id),
        'kind': _compile_dynamic_value(_require_mapping_value(device, 'kind'), f'{device_path}.kind', 'RELAY'),
        'capabilities': _compile_core_capabilities_plan(
            device,
            device_path=device_path,
            default_min_absorb_w=relay_power_default,
            default_max_absorb_w=relay_power_default,
            default_step_w=relay_power_default,
            default_max_produce_w=None,
        ),
        'policy': {
            'priority': _compile_dynamic_value(_require_mapping_value(policy, 'priority'), f'{device_path}.policy.priority', relay_default),
            'surplus_allowed': _compile_dynamic_value(_require_mapping_value(policy, 'surplus_allowed'), f'{device_path}.policy.surplus_allowed', ''),
            'surplus_dispatch_mode': _compile_dynamic_value(_require_mapping_value(policy, 'surplus_dispatch_mode'), f'{device_path}.policy.surplus_dispatch_mode', 'fixed'),
            'force_on': _compile_dynamic_value(_require_mapping_value(policy, 'force_on'), f'{device_path}.policy.force_on', ''),
        },
        'adapter': {
            'enabled': _compile_dynamic_value(_require_mapping_value(adapter, 'enabled'), f'{device_path}.adapter.enabled', ''),
        },
    }


def _compile_core_devices_plan(devices: object) -> dict[str, dict[str, object]]:
    if not isinstance(devices, dict):
        return {}
    compiled = {}
    for device_id, device in devices.items():
        if not isinstance(device, dict):
            continue
        kind = str(device.get('kind') or '')
        if kind == 'BATTERY':
            compiled[str(device_id)] = _compile_core_battery_device_plan(str(device_id), device)
        elif kind == 'EV_CHARGER':
            compiled[str(device_id)] = _compile_core_ev_device_plan(str(device_id), device)
        elif kind == 'RELAY':
            compiled[str(device_id)] = _compile_core_relay_device_plan(str(device_id), device)
    return compiled


def _compile_core_haeo_plan(haeo: object) -> Optional[dict[str, object]]:
    if not isinstance(haeo, dict):
        return None
    return {
        'battery_power_active': _compile_dynamic_value(_require_mapping_value(haeo, 'battery_power_active'), 'ems.haeo.battery_power_active', ''),
        'ev_power_active': _compile_dynamic_value(_require_mapping_value(haeo, 'ev_power_active'), 'ems.haeo.ev_power_active', ''),
        'battery_fresh_source': _compile_dynamic_value(_require_mapping_value(haeo, 'battery_fresh_source'), 'ems.haeo.battery_fresh_source', ''),
        'ev_fresh_source': _compile_dynamic_value(_require_mapping_value(haeo, 'ev_fresh_source'), 'ems.haeo.ev_fresh_source', ''),
    }


def _compile_core_role_constraints_plan(role_constraints: object) -> dict[str, object]:
    if not isinstance(role_constraints, dict):
        return {}
    compiled_default = {}
    raw_default = role_constraints.get('default', {})
    if isinstance(raw_default, dict):
        for key, value in raw_default.items():
            compiled_default[str(key)] = _compile_dynamic_value(value, f'ems.role_constraints.default.{key}', value)
    compiled = {}
    if compiled_default:
        compiled['default'] = compiled_default
    for role_key, role_value in role_constraints.items():
        if role_key == 'default' or not isinstance(role_value, dict):
            continue
        role_devices = {}
        for device_id, device_fields in role_value.items():
            if not isinstance(device_fields, dict):
                continue
            compiled_fields = {}
            for field_name, field_value in device_fields.items():
                compiled_fields[str(field_name)] = _compile_dynamic_value(
                    field_value,
                    f'ems.role_constraints.{role_key}.{device_id}.{field_name}',
                    field_value,
                )
            role_devices[str(device_id)] = compiled_fields
        compiled[str(role_key)] = role_devices
    return compiled


def _collect_dynamic_refs(value: object) -> tuple[DynamicConfigRef, ...]:
    refs = []
    if isinstance(value, DynamicConfigRef):
        refs.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            refs.extend(_collect_dynamic_refs(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            refs.extend(_collect_dynamic_refs(item))
    return tuple(refs)


def _deep_freeze(value: object) -> object:
    if isinstance(value, dict):
        frozen = {}
        for key, item in value.items():
            frozen[str(key)] = _deep_freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, list):
        frozen_items = []
        for item in value:
            frozen_items.append(_deep_freeze(item))
        return tuple(frozen_items)
    if isinstance(value, tuple):
        frozen_items = []
        for item in value:
            frozen_items.append(_deep_freeze(item))
        return tuple(frozen_items)
    return value


def _build_static_device_plan(compiled_device: dict[str, object]) -> StaticDevicePlan:
    return StaticDevicePlan(
        device_id=str(compiled_device.get('device_id', '')),
        kind=str(compiled_device.get('kind', '')),
        static_capabilities=_deep_freeze(_require_mapping_value(compiled_device, 'capabilities')),
        static_adapter=_deep_freeze(_require_mapping_value(compiled_device, 'adapter')),
        static_policy=_deep_freeze(_require_mapping_value(compiled_device, 'policy')),
        static_guard=_deep_freeze(compiled_device.get('guard', {})) if isinstance(compiled_device.get('guard'), dict) else None,
        dynamic_refs=_collect_dynamic_refs(compiled_device),
        grouped_device_plan=_deep_freeze(compiled_device),
    )


def compile_core_config_plan_from_grouped_config(config: dict) -> CompiledCoreConfigPlan:
    static_topology = build_static_topology(config) if _config_uses_runtime_packets(config) else None
    config_for_compile = _normalize_runtime_packet_config_for_compile(config)
    ems = config_for_compile.get('ems', {})
    devices = ems.get('devices', {})
    role_constraints = ems.get('role_constraints', {})
    policy_engine = ems.get('policy_engine', {})
    compiled = {
        'ems': {
            'profiles': {
                'control': _compile_dynamic_value(_require_mapping_value(ems.get('profiles'), 'control'), 'ems.profiles.control', ''),
                'goal': _compile_dynamic_value(_require_mapping_value(ems.get('profiles'), 'goal'), 'ems.profiles.goal', ''),
                'forecast': _compile_dynamic_value(_require_mapping_value(ems.get('profiles'), 'forecast'), 'ems.profiles.forecast', ''),
                'guard': _compile_dynamic_value(_require_mapping_value(ems.get('profiles'), 'guard'), 'ems.profiles.guard', ''),
            },
            'policy_engine': {
                'interval_seconds': _parse_policy_engine_interval_seconds(
                    policy_engine.get('interval_seconds', 5.0) if isinstance(policy_engine, dict) else 5.0
                ),
                'diagnostics_interval_seconds': _parse_policy_engine_diagnostics_interval_seconds(
                    policy_engine.get('diagnostics_interval_seconds', 30.0) if isinstance(policy_engine, dict) else 30.0
                ),
            },
            'global_config': {
                'deadband_w': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'deadband_w'), 'ems.global_config.deadband_w', 50),
                'ramp_w': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'ramp_w'), 'ems.global_config.ramp_w', 1000),
                'strict_limit_w': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'strict_limit_w'), 'ems.global_config.strict_limit_w', 4600),
                'default_sp_w': _compile_dynamic_value(ems.get('global_config', {}).get('default_sp_w', 100.0), 'ems.global_config.default_sp_w', 100.0),
                'surplus_freeze_s': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'surplus_freeze_s'), 'ems.global_config.surplus_freeze_s', 30),
                'battery_heartbeat_timeout_s': _compile_dynamic_value(ems.get('global_config', {}).get('battery_heartbeat_timeout_s', 360.0), 'ems.global_config.battery_heartbeat_timeout_s', 360.0),
                'haeo_stale_timeout_s': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'haeo_stale_timeout_s'), 'ems.global_config.haeo_stale_timeout_s', 300),
                'nz_battery_floor_default_w': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'nz_battery_floor_default_w'), 'ems.global_config.nz_battery_floor_default_w', 100.0),
                'nz_battery_floor_ev_active_w': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'nz_battery_floor_ev_active_w'), 'ems.global_config.nz_battery_floor_ev_active_w', 0.0),
                'adjustable_primary_load': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'adjustable_primary_load'), 'ems.global_config.adjustable_primary_load', ''),
            },
            'runtime': {
                'grid_power_w': _compile_dynamic_value(_require_mapping_value(ems.get('runtime'), 'grid_power_w'), 'ems.runtime.grid_power_w', 0),
                'quarter_energy_balance_kwh': _compile_dynamic_value(_require_mapping_value(ems.get('runtime'), 'quarter_energy_balance_kwh'), 'ems.runtime.quarter_energy_balance_kwh', 0),
                'pv_power_w': _compile_dynamic_value(_require_mapping_value(ems.get('runtime'), 'pv_power_w'), 'ems.runtime.pv_power_w', 0),
            },
            'state': {
                'surplus_freeze_until': _compile_dynamic_value(_require_mapping_value(ems.get('state'), 'surplus_freeze_until'), 'ems.state.surplus_freeze_until', ''),
                'active_surplus_devices': _compile_dynamic_value(_require_mapping_value(ems.get('state'), 'active_surplus_devices'), 'ems.state.active_surplus_devices', ''),
                'previous_device_state': _compile_dynamic_value(_require_mapping_value(ems.get('state'), 'previous_device_state'), 'ems.state.previous_device_state', ''),
            },
            'devices': _compile_core_devices_plan(devices),
            'haeo': _compile_core_haeo_plan(ems.get('haeo')),
            'role_constraints': _compile_core_role_constraints_plan(role_constraints),
        }
    }
    compiled_devices = _compile_core_devices_plan(devices)
    home_battery_plan = _build_static_device_plan(_require_mapping_value(compiled_devices, 'HOME_BATTERY'))
    static_devices = {}
    for device_id, device_plan in compiled_devices.items():
        if str(device_id) == 'HOME_BATTERY':
            continue
        static_devices[str(device_id)] = _build_static_device_plan(device_plan)
    compiled_plan = CompiledEMSPlan(
        profiles=dict(_require_mapping_value(compiled['ems'], 'profiles')),
        policy_engine=dict(_require_mapping_value(compiled['ems'], 'policy_engine')),
        global_config=dict(_require_mapping_value(compiled['ems'], 'global_config')),
        runtime=dict(_require_mapping_value(compiled['ems'], 'runtime')),
        state=dict(_require_mapping_value(compiled['ems'], 'state')),
        devices=static_devices,
        home_battery=home_battery_plan,
        haeo=dict(compiled['ems']['haeo']) if isinstance(compiled['ems'].get('haeo'), dict) else None,
        role_constraints=dict(_require_mapping_value(compiled['ems'], 'role_constraints')),
        grouped_config_plan=compiled,
        static_topology=static_topology,
    )
    if static_topology is None:
        compiled_plan.policy_runtime_facts_plan = compile_policy_runtime_facts_plan(compiled_plan)
    return compiled_plan


def materialize_core_config_from_plan(
    plan: CompiledCoreConfigPlan,
    read_entity: Callable[[str, object], object],
    metrics: Optional[dict[str, int]] = None,
) -> CoreConfig:
    return _materialize_core_config_direct(plan, read_entity, metrics=metrics)


def _runtime_materialization_ref_key(value: DynamicConfigRef) -> tuple[object, ...]:
    return (str(value.entity_id), str(value.value_type), value.default)


def _resolve_dynamic_config_ref_value(
    value: DynamicConfigRef,
    read_entity: Callable[[str, object], object],
    *,
    resolved_dynamic_values: Optional[dict[tuple[object, ...], object]] = None,
    stats: Optional[dict[str, int]] = None,
) -> object:
    if stats is not None:
        stats['dynamic_refs_seen'] = int(stats.get('dynamic_refs_seen', 0) or 0) + 1
    if resolved_dynamic_values is None:
        return _resolve_core_config_value(value, read_entity, value.default)
    cache_key = _runtime_materialization_ref_key(value)
    cached_value = resolved_dynamic_values.get(cache_key, _MATERIALIZE_CACHE_MISS)
    if cached_value is not _MATERIALIZE_CACHE_MISS:
        if stats is not None:
            stats['dynamic_ref_cache_hits'] = int(stats.get('dynamic_ref_cache_hits', 0) or 0) + 1
        note_cached_dynamic_read = getattr(read_entity, 'note_cached_dynamic_read', None)
        if callable(note_cached_dynamic_read):
            note_cached_dynamic_read(value.entity_id, value.default)
        return cached_value
    resolved_value = _resolve_core_config_value(value, read_entity, value.default)
    resolved_dynamic_values[cache_key] = resolved_value
    if stats is not None:
        stats['dynamic_refs_unique'] = int(stats.get('dynamic_refs_unique', 0) or 0) + 1
    return resolved_value


def _materialize_runtime_mapping(
    value: object,
    read_entity: Callable[[str, object], object],
    *,
    resolved_dynamic_values: Optional[dict[tuple[object, ...], object]] = None,
    stats: Optional[dict[str, int]] = None,
) -> object:
    if isinstance(value, DynamicConfigRef):
        return _resolve_dynamic_config_ref_value(
            value,
            read_entity,
            resolved_dynamic_values=resolved_dynamic_values,
            stats=stats,
        )
    if isinstance(value, MappingProxyType):
        if stats is not None:
            stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
        materialized = {}
        for key, item in value.items():
            materialized[str(key)] = _materialize_runtime_mapping(
                item,
                read_entity,
                resolved_dynamic_values=resolved_dynamic_values,
                stats=stats,
            )
        return materialized
    if isinstance(value, dict):
        if stats is not None:
            stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
        materialized = {}
        for key, item in value.items():
            materialized[str(key)] = _materialize_runtime_mapping(
                item,
                read_entity,
                resolved_dynamic_values=resolved_dynamic_values,
                stats=stats,
            )
        return materialized
    if isinstance(value, tuple):
        if stats is not None:
            stats['tuple_nodes'] = int(stats.get('tuple_nodes', 0) or 0) + 1
        materialized = []
        for item in value:
            materialized.append(
                _materialize_runtime_mapping(
                    item,
                    read_entity,
                    resolved_dynamic_values=resolved_dynamic_values,
                    stats=stats,
                )
            )
        return tuple(materialized)
    return value


def _materialize_runtime_dynamic_mapping(
    value: object,
    read_entity: Callable[[str, object], object],
    *,
    resolved_dynamic_values: Optional[dict[tuple[object, ...], object]] = None,
    stats: Optional[dict[str, int]] = None,
) -> object:
    if isinstance(value, DynamicConfigRef):
        return _resolve_dynamic_config_ref_value(
            value,
            read_entity,
            resolved_dynamic_values=resolved_dynamic_values,
            stats=stats,
        )
    if isinstance(value, MappingProxyType):
        materialized = {}
        for key, item in value.items():
            resolved_item = _materialize_runtime_dynamic_mapping(
                item,
                read_entity,
                resolved_dynamic_values=resolved_dynamic_values,
                stats=stats,
            )
            if resolved_item is _NO_DYNAMIC_SNAPSHOT_VALUE:
                continue
            materialized[str(key)] = resolved_item
        if not materialized:
            return _NO_DYNAMIC_SNAPSHOT_VALUE
        if stats is not None:
            stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
        return materialized
    if isinstance(value, dict):
        materialized = {}
        for key, item in value.items():
            resolved_item = _materialize_runtime_dynamic_mapping(
                item,
                read_entity,
                resolved_dynamic_values=resolved_dynamic_values,
                stats=stats,
            )
            if resolved_item is _NO_DYNAMIC_SNAPSHOT_VALUE:
                continue
            materialized[str(key)] = resolved_item
        if not materialized:
            return _NO_DYNAMIC_SNAPSHOT_VALUE
        if stats is not None:
            stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
        return materialized
    if isinstance(value, tuple):
        materialized = []
        saw_dynamic = False
        for item in value:
            resolved_item = _materialize_runtime_dynamic_mapping(
                item,
                read_entity,
                resolved_dynamic_values=resolved_dynamic_values,
                stats=stats,
            )
            if resolved_item is _NO_DYNAMIC_SNAPSHOT_VALUE:
                materialized.append(item)
                continue
            saw_dynamic = True
            materialized.append(resolved_item)
        if not saw_dynamic:
            return _NO_DYNAMIC_SNAPSHOT_VALUE
        if stats is not None:
            stats['tuple_nodes'] = int(stats.get('tuple_nodes', 0) or 0) + 1
        return tuple(materialized)
    return _NO_DYNAMIC_SNAPSHOT_VALUE


def _snapshot_dynamic_section_values(
    section_value: object,
    read_entity: Callable[[str, object], object],
    *,
    resolved_dynamic_values: Optional[dict[tuple[object, ...], object]] = None,
    stats: Optional[dict[str, int]] = None,
) -> Optional[dict]:
    resolved = _materialize_runtime_dynamic_mapping(
        section_value,
        read_entity,
        resolved_dynamic_values=resolved_dynamic_values,
        stats=stats,
    )
    if resolved is _NO_DYNAMIC_SNAPSHOT_VALUE or not isinstance(resolved, dict):
        return None
    return resolved


def _materialize_device_snapshot_values(
    device_plan: StaticDevicePlan,
    read_entity: Callable[[str, object], object],
    *,
    resolved_dynamic_values: Optional[dict[tuple[object, ...], object]] = None,
    stats: Optional[dict[str, int]] = None,
) -> dict:
    materialized = {}
    capabilities = _snapshot_dynamic_section_values(
        device_plan.static_capabilities,
        read_entity,
        resolved_dynamic_values=resolved_dynamic_values,
        stats=stats,
    )
    if capabilities is not None:
        materialized['capabilities'] = capabilities
    adapter = _snapshot_dynamic_section_values(
        device_plan.static_adapter,
        read_entity,
        resolved_dynamic_values=resolved_dynamic_values,
        stats=stats,
    )
    if adapter is not None:
        materialized['adapter'] = adapter
    policy = _snapshot_dynamic_section_values(
        device_plan.static_policy,
        read_entity,
        resolved_dynamic_values=resolved_dynamic_values,
        stats=stats,
    )
    if policy is not None:
        materialized['policy'] = policy
    if device_plan.static_guard is not None:
        guard = _snapshot_dynamic_section_values(
            device_plan.static_guard,
            read_entity,
            resolved_dynamic_values=resolved_dynamic_values,
            stats=stats,
        )
        if guard is not None:
            materialized['guard'] = guard
    return materialized


def _resolve_snapshot_backed_value(
    static_value: object,
    dynamic_values: Optional[dict],
    field: str,
    default=None,
):
    if isinstance(dynamic_values, dict) and str(field) in dynamic_values:
        return dynamic_values[str(field)]
    if isinstance(static_value, DynamicConfigRef):
        return static_value.default
    if static_value is None:
        return default
    return static_value


def _resolve_snapshot_backed_section_value(
    device_plan: StaticDevicePlan,
    dynamic_values: Optional[dict],
    section: str,
    field: str,
    default=None,
):
    section_name = str(section)
    if section_name == 'capabilities':
        static_section = device_plan.static_capabilities
    elif section_name == 'adapter':
        static_section = device_plan.static_adapter
    elif section_name == 'policy':
        static_section = device_plan.static_policy
    elif section_name == 'guard':
        static_section = device_plan.static_guard
    else:
        return default
    if not hasattr(static_section, 'get'):
        return default
    static_value = static_section.get(str(field))
    section_dynamic_values = dynamic_values.get(section_name) if isinstance(dynamic_values, dict) else None
    return _resolve_snapshot_backed_value(static_value, section_dynamic_values, str(field), default)


def _register_dynamic_runtime_read(
    unique_reads: list[dict[str, object]],
    unique_slots: dict[tuple[object, ...], int],
    logical_read_counts: list[int],
    value: DynamicConfigRef,
) -> int:
    cache_key = _runtime_materialization_ref_key(value)
    slot = unique_slots.get(cache_key)
    if slot is None:
        slot = len(unique_reads)
        unique_slots[cache_key] = slot
        unique_reads.append(
            {
                'entity_id': str(value.entity_id),
                'default': value.default,
                'value_type': str(value.value_type),
            }
        )
        logical_read_counts.append(0)
    logical_read_counts[slot] = int(logical_read_counts[slot]) + 1
    return slot


def _compile_flat_runtime_section_fields(
    section: object,
    unique_reads: list[dict[str, object]],
    unique_slots: dict[tuple[object, ...], int],
    logical_read_counts: list[int],
) -> tuple[tuple[str, Optional[int], object], ...]:
    if not hasattr(section, 'items'):
        return ()
    bindings = []
    for field_name, field_value in section.items():
        if isinstance(field_value, DynamicConfigRef):
            slot = _register_dynamic_runtime_read(unique_reads, unique_slots, logical_read_counts, field_value)
            bindings.append((str(field_name), slot, field_value.default))
        else:
            bindings.append((str(field_name), None, field_value))
    return tuple(bindings)


def _compile_flat_runtime_role_constraint_fields(
    role_constraints: object,
    unique_reads: list[dict[str, object]],
    unique_slots: dict[tuple[object, ...], int],
    logical_read_counts: list[int],
) -> tuple[tuple[str, str, str, Optional[int], object], ...]:
    if not hasattr(role_constraints, 'items'):
        return ()
    bindings = []
    default_fields = role_constraints.get('default', {}) if hasattr(role_constraints, 'get') else {}
    if hasattr(default_fields, 'items'):
        for field_name, field_value in default_fields.items():
            if isinstance(field_value, DynamicConfigRef):
                slot = _register_dynamic_runtime_read(unique_reads, unique_slots, logical_read_counts, field_value)
                bindings.append(('default', '', str(field_name), slot, field_value.default))
            else:
                bindings.append(('default', '', str(field_name), None, field_value))
    for role_key, role_devices in role_constraints.items():
        if str(role_key) == 'default' or not hasattr(role_devices, 'items'):
            continue
        for device_id, device_fields in role_devices.items():
            if not hasattr(device_fields, 'items'):
                continue
            for field_name, field_value in device_fields.items():
                if isinstance(field_value, DynamicConfigRef):
                    slot = _register_dynamic_runtime_read(unique_reads, unique_slots, logical_read_counts, field_value)
                    bindings.append((str(role_key), str(device_id), str(field_name), slot, field_value.default))
                else:
                    bindings.append((str(role_key), str(device_id), str(field_name), None, field_value))
    return tuple(bindings)


def _compile_flat_runtime_device_dynamic_fields(
    device_plan: StaticDevicePlan,
    unique_reads: list[dict[str, object]],
    unique_slots: dict[tuple[object, ...], int],
    logical_read_counts: list[int],
) -> tuple[tuple[str, str, int], ...]:
    bindings = []
    for section_name, section_value in (
        ('capabilities', device_plan.static_capabilities),
        ('adapter', device_plan.static_adapter),
        ('policy', device_plan.static_policy),
        ('guard', device_plan.static_guard),
    ):
        if not hasattr(section_value, 'items'):
            continue
        for field_name, field_value in section_value.items():
            if not isinstance(field_value, DynamicConfigRef):
                continue
            slot = _register_dynamic_runtime_read(unique_reads, unique_slots, logical_read_counts, field_value)
            bindings.append((str(section_name), str(field_name), slot))
    return tuple(bindings)



def _policy_runtime_static_section(device_plan: StaticDevicePlan, section: str):
    section_name = str(section)
    if section_name == 'capabilities':
        return device_plan.static_capabilities
    if section_name == 'adapter':
        return device_plan.static_adapter
    if section_name == 'policy':
        return device_plan.static_policy
    if section_name == 'guard':
        return device_plan.static_guard
    return None


def _policy_runtime_static_fact_value(device_plan: StaticDevicePlan, section: str, field: str, default=None):
    static_section = _policy_runtime_static_section(device_plan, section)
    if not hasattr(static_section, 'get'):
        return default, False
    static_value = static_section.get(str(field))
    if isinstance(static_value, DynamicConfigRef):
        return static_value.default, True
    if static_value is None:
        return default, False
    return static_value, False



def _policy_runtime_positive_float(value, default):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if parsed > 0 else float(default)


def _policy_runtime_non_negative_float(value, default=0.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if parsed >= 0 else float(default)


def _policy_runtime_int_or_default(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return int(default)


def _policy_runtime_ev_context_from_facts(facts: dict, device_id: str):
    device_id = str(device_id or '')
    kind = str((facts.get('device_kind_by_id', {}) or {}).get(device_id, '') or '')
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

    capabilities = (facts.get('device_capabilities_by_id', {}) or {}).get(device_id, {}) or {}
    policy = (facts.get('device_policy_by_id', {}) or {}).get(device_id, {}) or {}
    adapter = (facts.get('device_adapter_by_id', {}) or {}).get(device_id, {}) or {}

    current_step_a = _policy_runtime_positive_float(adapter.get('current_step_a'), 1.0)
    phases = _policy_runtime_positive_float(adapter.get('phases'), 1.0)
    voltage_v = _policy_runtime_positive_float(adapter.get('voltage_v'), 230.0)

    raw_force_on = policy.get('force_on', False)
    if isinstance(raw_force_on, str):
        text = raw_force_on.strip().lower()
        if text in ('true', 'on', '1', 'yes'):
            force_on = True
        elif text in ('false', 'off', '0', 'no', '', 'unknown', 'unavailable', 'none'):
            force_on = False
        else:
            force_on = False
    else:
        force_on = bool(raw_force_on)

    low_pv_threshold = _policy_runtime_non_negative_float(policy.get('low_pv_threshold_w', 0), 0.0)
    hard_off_pv_threshold_kw = low_pv_threshold / 1000.0 if low_pv_threshold > 50.0 else low_pv_threshold
    min_absorb_w = _policy_runtime_non_negative_float(capabilities.get('min_absorb_w', None), 0.0)
    max_absorb_w = _policy_runtime_non_negative_float(capabilities.get('max_absorb_w', None), 0.0)
    configured_step_w = _policy_runtime_non_negative_float(capabilities.get('step_w', 0), 0.0)
    power_step_w = configured_step_w if configured_step_w > 0 else float(
        ev_current_a_to_power_w(current_step_a, phases, voltage_v)
    )

    return SimpleNamespace(
        device_id=device_id,
        device=None,
        adapter=None,
        capabilities=None,
        policy=None,
        current_step_a=int(round(current_step_a)),
        phases=int(round(phases)),
        voltage_v=float(voltage_v),
        min_absorb_w=min_absorb_w,
        max_absorb_w=max_absorb_w,
        power_step_w=float(power_step_w),
        force_on=force_on,
        hard_off_pv_threshold_kw=hard_off_pv_threshold_kw,
        hard_off_low_pv_cycles=_policy_runtime_int_or_default(policy.get('hard_off_low_pv_cycles', 0), 0),
        hard_off_release_cycles=_policy_runtime_int_or_default(policy.get('hard_off_release_cycles', 0), 0),
        priority=_policy_runtime_int_or_default(policy.get('priority', 0), 0),
    )


def _policy_runtime_selected_ev_contexts(facts: dict) -> dict:
    selected_ev_context_by_id = {}
    device_ids_by_kind = facts.get('device_ids_by_kind', {}) or {}
    for device_id in tuple(device_ids_by_kind.get('EV_CHARGER', ()) or ()):
        selected_ev_context_by_id[str(device_id)] = _policy_runtime_ev_context_from_facts(facts, str(device_id))
    return selected_ev_context_by_id

def compile_policy_runtime_facts_plan(compiled_plan: CompiledEMSPlan) -> dict[str, object]:
    battery_device_ids = ['HOME_BATTERY']
    device_ids_by_kind = {
        'BATTERY': (),
        'EV_CHARGER': (),
        'RELAY': (),
    }
    ev_device_ids = []
    relay_device_ids = []
    devices = {}
    static_device_kind_by_id = {}
    static_capabilities_by_id = {}
    static_policy_by_id = {}
    static_adapter_by_id = {}
    dynamic_fact_bindings = []
    dynamic_fact_binding_groups = {}

    def add_dynamic_fact_binding(target_map_name, device_id_text, target_field, section_name, source_field):
        binding = (str(target_map_name), str(device_id_text), str(target_field), str(section_name), str(source_field))
        dynamic_fact_bindings.append(binding)
        group_key = (binding[0], binding[1], binding[3])
        field_pairs = dynamic_fact_binding_groups.get(group_key)
        if field_pairs is None:
            field_pairs = []
            dynamic_fact_binding_groups[group_key] = field_pairs
        field_pairs.append((binding[2], binding[4]))

    def add_device(device_id_text, device_plan, kind):
        capabilities_fields = (
            'min_absorb_w',
            'max_absorb_w',
            'max_produce_w',
            'step_w',
            'can_absorb_w',
            'can_produce_w',
            'uses_hard_off_lifecycle',
            'supports_primary_regulation',
            'supports_residual_regulation',
        )
        policy_fields = (
            'priority',
            'surplus_allowed',
                'surplus_dispatch_mode',
            'default_min_absorb_w',
        ) if kind == 'BATTERY' else ('priority',)
        adapter_fields = ()
        if kind == 'EV_CHARGER':
            policy_fields = (
                'priority',
                'surplus_allowed',
                        'surplus_dispatch_mode',
                'force_on',
                'low_pv_threshold_w',
                'hard_off_low_pv_cycles',
                'hard_off_release_cycles',
            )
            adapter_fields = (
                'enabled',
                'current_a',
                'current_step_a',
                'phases',
                'voltage_v',
            )
        elif kind == 'RELAY':
            policy_fields = (
                'priority',
                'surplus_allowed',
                        'surplus_dispatch_mode',
                'force_on',
            )
            adapter_fields = (
                'enabled',
            )

        devices[device_id_text] = {
            'kind': kind,
            'capabilities_fields': capabilities_fields,
            'policy_fields': policy_fields,
            'adapter_fields': adapter_fields,
        }
        static_device_kind_by_id[device_id_text] = kind

        capability_values = {}
        for field_name in capabilities_fields:
            default = False if str(field_name) in ('can_absorb_w', 'can_produce_w', 'uses_hard_off_lifecycle', 'supports_primary_regulation', 'supports_residual_regulation') else 0
            value, is_dynamic = _policy_runtime_static_fact_value(device_plan, 'capabilities', str(field_name), default)
            capability_values[str(field_name)] = value
            if is_dynamic:
                add_dynamic_fact_binding('device_capabilities_by_id', device_id_text, str(field_name), 'capabilities', str(field_name))
        static_capabilities_by_id[device_id_text] = capability_values

        policy_values = {}
        for field_name in policy_fields:
            default = 0 if str(field_name) == 'priority' else False
            value, is_dynamic = _policy_runtime_static_fact_value(device_plan, 'policy', str(field_name), default)
            policy_values[str(field_name)] = value
            if is_dynamic:
                add_dynamic_fact_binding('device_policy_by_id', device_id_text, str(field_name), 'policy', str(field_name))
        static_policy_by_id[device_id_text] = policy_values

        adapter_values = {}
        for field_name in adapter_fields:
            value, is_dynamic = _policy_runtime_static_fact_value(device_plan, 'adapter', str(field_name), None)
            adapter_values[str(field_name)] = value
            if is_dynamic:
                add_dynamic_fact_binding('device_adapter_by_id', device_id_text, str(field_name), 'adapter', str(field_name))
        if adapter_values:
            static_adapter_by_id[device_id_text] = adapter_values

    add_device('HOME_BATTERY', compiled_plan.home_battery, 'BATTERY')

    for device_id, device_plan in compiled_plan.devices.items():
        kind = str(device_plan.kind)
        device_id_text = str(device_id)
        if kind == 'EV_CHARGER':
            ev_device_ids.append(device_id_text)
        elif kind == 'RELAY':
            relay_device_ids.append(device_id_text)
        elif kind == 'BATTERY':
            battery_device_ids.append(device_id_text)
        add_device(device_id_text, device_plan, kind)

    device_ids_by_kind['BATTERY'] = tuple(battery_device_ids)
    device_ids_by_kind['EV_CHARGER'] = tuple(ev_device_ids)
    device_ids_by_kind['RELAY'] = tuple(relay_device_ids)
    static_base = {
        'device_ids_by_kind': device_ids_by_kind,
        'device_kind_by_id': static_device_kind_by_id,
        'device_capabilities_by_id': static_capabilities_by_id,
        'device_policy_by_id': static_policy_by_id,
        'device_adapter_by_id': static_adapter_by_id,
    }
    dynamic_fact_binding_group_entries = []
    for group_key, field_pairs in dynamic_fact_binding_groups.items():
        dynamic_fact_binding_group_entries.append(
            (
                str(group_key[0]),
                str(group_key[1]),
                str(group_key[2]),
                tuple(field_pairs),
            )
        )
    facts_plan_metrics = {
        'device_count': int(len(static_device_kind_by_id)),
        'capability_fields': 0,
        'policy_fields': 0,
        'adapter_fields': 0,
        'dynamic_bindings': int(len(dynamic_fact_bindings)),
        'dynamic_binding_groups': int(len(dynamic_fact_binding_group_entries)),
    }
    for descriptor in devices.values():
        facts_plan_metrics['capability_fields'] += len(tuple(descriptor.get('capabilities_fields', ()) or ()))
        facts_plan_metrics['policy_fields'] += len(tuple(descriptor.get('policy_fields', ()) or ()))
        facts_plan_metrics['adapter_fields'] += len(tuple(descriptor.get('adapter_fields', ()) or ()))
    return {
        'device_ids_by_kind': device_ids_by_kind,
        'devices': devices,
        'static_base': static_base,
        'dynamic_fact_bindings': tuple(dynamic_fact_bindings),
        'dynamic_fact_binding_groups': tuple(dynamic_fact_binding_group_entries),
        'facts_plan_metrics': facts_plan_metrics,
    }


def compile_dynamic_runtime_read_plan(compiled_plan: CompiledEMSPlan) -> dict[str, object]:
    unique_reads: list[dict[str, object]] = []
    unique_slots: dict[tuple[object, ...], int] = {}
    logical_read_counts: list[int] = []

    profiles_fields = _compile_flat_runtime_section_fields(
        compiled_plan.profiles, unique_reads, unique_slots, logical_read_counts
    )
    if compiled_plan.static_topology is not None:
        global_config_fields = ()
    else:
        global_config_fields = _compile_flat_runtime_section_fields(
            compiled_plan.global_config, unique_reads, unique_slots, logical_read_counts
        )
    runtime_fields = _compile_flat_runtime_section_fields(
        compiled_plan.runtime, unique_reads, unique_slots, logical_read_counts
    )
    state_fields = _compile_flat_runtime_section_fields(
        compiled_plan.state, unique_reads, unique_slots, logical_read_counts
    )
    haeo_fields = None
    if compiled_plan.haeo is not None:
        haeo_fields = _compile_flat_runtime_section_fields(
            compiled_plan.haeo, unique_reads, unique_slots, logical_read_counts
        )
    role_constraint_fields = _compile_flat_runtime_role_constraint_fields(
        compiled_plan.role_constraints, unique_reads, unique_slots, logical_read_counts
    )

    device_dynamic_fields = {}
    for device_id, device_plan in compiled_plan.devices.items():
        device_dynamic_fields[str(device_id)] = _compile_flat_runtime_device_dynamic_fields(
            device_plan,
            unique_reads,
            unique_slots,
            logical_read_counts,
        )
    home_battery_dynamic_fields = _compile_flat_runtime_device_dynamic_fields(
        compiled_plan.home_battery,
        unique_reads,
        unique_slots,
        logical_read_counts,
    )

    battery_priority_static = None
    battery_priority_slot = None
    battery_priority_value = (
        compiled_plan.home_battery.static_policy.get('priority')
        if hasattr(compiled_plan.home_battery.static_policy, 'get')
        else None
    )
    if isinstance(battery_priority_value, DynamicConfigRef):
        battery_priority_slot = unique_slots.get(_runtime_materialization_ref_key(battery_priority_value))
        if battery_priority_slot is None:
            battery_priority_slot = _register_dynamic_runtime_read(
                unique_reads,
                unique_slots,
                logical_read_counts,
                battery_priority_value,
            )
        battery_priority_static = battery_priority_value.default
    else:
        battery_priority_static = battery_priority_value

    dynamic_refs_seen = 0
    for count in logical_read_counts:
        dynamic_refs_seen += int(count)
    dynamic_refs_unique = len(unique_reads)
    compiled_logical_read_counts = []
    for count in logical_read_counts:
        compiled_logical_read_counts.append(int(count))
    return {
        'unique_reads': tuple(unique_reads),
        'logical_read_counts': tuple(compiled_logical_read_counts),
        'profiles_fields': profiles_fields,
        'global_config_fields': global_config_fields,
        'runtime_fields': runtime_fields,
        'state_fields': state_fields,
        'haeo_fields': haeo_fields,
        'role_constraint_fields': role_constraint_fields,
        'device_dynamic_fields': device_dynamic_fields,
        'home_battery_dynamic_fields': home_battery_dynamic_fields,
        'home_battery_priority_slot': battery_priority_slot,
        'home_battery_priority_static': battery_priority_static,
        'dynamic_refs_seen': int(dynamic_refs_seen),
        'dynamic_refs_unique': int(dynamic_refs_unique),
        'dynamic_ref_cache_hits': max(0, int(dynamic_refs_seen) - int(dynamic_refs_unique)),
    }


def _assemble_flat_runtime_section(
    field_bindings: tuple[tuple[str, Optional[int], object], ...],
    dynamic_values: tuple[object, ...],
    stats: Optional[dict[str, int]] = None,
) -> dict:
    assembled = {}
    if stats is not None:
        stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
    for field_name, slot, static_value in field_bindings:
        if slot is None:
            assembled[str(field_name)] = static_value
        else:
            assembled[str(field_name)] = dynamic_values[int(slot)]
    return assembled


def _assemble_flat_runtime_role_constraints(
    field_bindings: tuple[tuple[str, str, str, Optional[int], object], ...],
    dynamic_values: tuple[object, ...],
    stats: Optional[dict[str, int]] = None,
) -> dict:
    assembled = {'default': {}}
    if stats is not None:
        stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 2
    for role_key, device_id, field_name, slot, static_value in field_bindings:
        resolved_value = static_value if slot is None else dynamic_values[int(slot)]
        if role_key == 'default':
            assembled['default'][str(field_name)] = resolved_value
            continue
        role_devices = assembled.get(str(role_key))
        if role_devices is None:
            role_devices = {}
            assembled[str(role_key)] = role_devices
            if stats is not None:
                stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
        device_fields = role_devices.get(str(device_id))
        if device_fields is None:
            device_fields = {}
            role_devices[str(device_id)] = device_fields
            if stats is not None:
                stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
        device_fields[str(field_name)] = resolved_value
    return assembled


def _assemble_flat_runtime_device_dynamic_values(
    device_bindings: tuple[tuple[str, str, int], ...],
    dynamic_values: tuple[object, ...],
    stats: Optional[dict[str, int]] = None,
) -> dict:
    assembled = {}
    if stats is not None:
        stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
    for section_name, field_name, slot in device_bindings:
        section_values = assembled.get(str(section_name))
        if section_values is None:
            section_values = {}
            assembled[str(section_name)] = section_values
            if stats is not None:
                stats['dict_nodes'] = int(stats.get('dict_nodes', 0) or 0) + 1
        section_values[str(field_name)] = dynamic_values[int(slot)]
    return assembled


def _resolve_home_battery_priority_from_snapshot(
    battery_plan: StaticDevicePlan,
    battery_values: dict,
    compiled_plan: CompiledEMSPlan,
    device_values: dict[str, dict],
) -> object:
    # Device-owned surplus priority: HOME_BATTERY never inherits EV priority.
    return _resolve_snapshot_backed_section_value(
        battery_plan,
        battery_values,
        'policy',
        'priority',
        3,
    )


def _policy_runtime_device_plan(compiled_plan: CompiledEMSPlan, device_id: str) -> Optional[StaticDevicePlan]:
    device_id = str(device_id)
    if device_id == 'HOME_BATTERY':
        return compiled_plan.home_battery
    return compiled_plan.devices.get(device_id)



def _policy_runtime_device_values(snapshot: DynamicRuntimeSnapshot, device_id: str) -> dict:
    device_id = str(device_id)
    if device_id == 'HOME_BATTERY':
        return snapshot.home_battery_values or {}
    return snapshot.device_values.get(device_id, {}) or {}



def build_policy_runtime_facts_from_context(
    compiled_plan: CompiledEMSPlan,
    snapshot: DynamicRuntimeSnapshot,
    *,
    policy_runtime_facts_plan: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    facts_started_ts = _policy_runtime_facts_profile_started_ts()
    fact_dict_copies = 0
    fact_device_count = 0
    fact_capability_fields = 0
    fact_policy_fields = 0
    fact_adapter_fields = 0

    facts_plan = policy_runtime_facts_plan or compiled_plan.policy_runtime_facts_plan or compile_policy_runtime_facts_plan(compiled_plan)
    static_base = facts_plan.get('static_base') if isinstance(facts_plan, dict) else None
    if isinstance(static_base, dict):
        device_ids_by_kind = static_base.get('device_ids_by_kind', {}) or {}
        device_kind_by_id = static_base.get('device_kind_by_id', {}) or {}
        base_capabilities_by_id = static_base.get('device_capabilities_by_id', {}) or {}
        base_policy_by_id = static_base.get('device_policy_by_id', {}) or {}
        base_adapter_by_id = static_base.get('device_adapter_by_id', {}) or {}
        device_capabilities_by_id = base_capabilities_by_id
        device_policy_by_id = base_policy_by_id
        device_adapter_by_id = base_adapter_by_id
        copied_capability_devices = {}
        copied_policy_devices = {}
        copied_adapter_devices = {}

        dynamic_fact_bindings = tuple(facts_plan.get('dynamic_fact_bindings', ()) or ())
        dynamic_fact_binding_groups = tuple(facts_plan.get('dynamic_fact_binding_groups', ()) or ())
        if not dynamic_fact_binding_groups and dynamic_fact_bindings:
            grouped = {}
            for binding in dynamic_fact_bindings:
                if len(tuple(binding)) < 5:
                    continue
                group_key = (str(binding[0]), str(binding[1]), str(binding[3]))
                field_pairs = grouped.get(group_key)
                if field_pairs is None:
                    field_pairs = []
                    grouped[group_key] = field_pairs
                field_pairs.append((str(binding[2]), str(binding[4])))
            group_entries = []
            for group_key, field_pairs in grouped.items():
                group_entries.append((str(group_key[0]), str(group_key[1]), str(group_key[2]), tuple(field_pairs)))
            dynamic_fact_binding_groups = tuple(group_entries)

        dynamic_values_by_device = {}
        for group in dynamic_fact_binding_groups:
            if len(tuple(group)) < 4:
                continue
            target_map_name = str(group[0])
            device_id = str(group[1])
            section_name = str(group[2])
            field_pairs = tuple(group[3] or ())
            dynamic_values = dynamic_values_by_device.get(device_id)
            if dynamic_values is None:
                dynamic_values = _policy_runtime_device_values(snapshot, device_id)
                dynamic_values_by_device[device_id] = dynamic_values
            section_dynamic_values = dynamic_values.get(section_name) if isinstance(dynamic_values, dict) else None
            if not isinstance(section_dynamic_values, dict):
                continue
            has_override = False
            for target_field, source_field in field_pairs:
                if str(source_field) in section_dynamic_values:
                    has_override = True
                    break
            if not has_override:
                continue

            if target_map_name == 'device_capabilities_by_id':
                if not isinstance(device_capabilities_by_id, dict) or device_capabilities_by_id is base_capabilities_by_id:
                    device_capabilities_by_id = dict(base_capabilities_by_id)
                    fact_dict_copies += 1
                section_values_map = copied_capability_devices.get(device_id)
                if section_values_map is None:
                    section_values_map = dict(device_capabilities_by_id.get(device_id, {}) or {})
                    copied_capability_devices[device_id] = section_values_map
                    device_capabilities_by_id[device_id] = section_values_map
                    fact_dict_copies += 1
            elif target_map_name == 'device_policy_by_id':
                if not isinstance(device_policy_by_id, dict) or device_policy_by_id is base_policy_by_id:
                    device_policy_by_id = dict(base_policy_by_id)
                    fact_dict_copies += 1
                section_values_map = copied_policy_devices.get(device_id)
                if section_values_map is None:
                    section_values_map = dict(device_policy_by_id.get(device_id, {}) or {})
                    copied_policy_devices[device_id] = section_values_map
                    device_policy_by_id[device_id] = section_values_map
                    fact_dict_copies += 1
            elif target_map_name == 'device_adapter_by_id':
                if not isinstance(device_adapter_by_id, dict) or device_adapter_by_id is base_adapter_by_id:
                    device_adapter_by_id = dict(base_adapter_by_id)
                    fact_dict_copies += 1
                section_values_map = copied_adapter_devices.get(device_id)
                if section_values_map is None:
                    section_values_map = dict(device_adapter_by_id.get(device_id, {}) or {})
                    copied_adapter_devices[device_id] = section_values_map
                    device_adapter_by_id[device_id] = section_values_map
                    fact_dict_copies += 1
            else:
                continue

            for target_field, source_field in field_pairs:
                source_field = str(source_field)
                if source_field in section_dynamic_values:
                    section_values_map[str(target_field)] = section_dynamic_values[source_field]

        facts_plan_metrics = facts_plan.get('facts_plan_metrics', {}) or {}
        fact_device_count = int(facts_plan_metrics.get('device_count', len(device_kind_by_id) if hasattr(device_kind_by_id, '__len__') else 0) or 0)
        fact_capability_fields = int(facts_plan_metrics.get('capability_fields', 0) or 0)
        fact_policy_fields = int(facts_plan_metrics.get('policy_fields', 0) or 0)
        fact_adapter_fields = int(facts_plan_metrics.get('adapter_fields', 0) or 0)

        facts_without_metrics = {
            'device_ids_by_kind': device_ids_by_kind,
            'device_kind_by_id': device_kind_by_id,
            'device_capabilities_by_id': device_capabilities_by_id,
            'device_policy_by_id': device_policy_by_id,
            'device_adapter_by_id': device_adapter_by_id,
        }
        selected_ev_context_by_id = _policy_runtime_selected_ev_contexts(facts_without_metrics)

        facts_without_metrics['selected_ev_context_by_id'] = selected_ev_context_by_id
        if POLICY_RUNTIME_FACTS_DETAILED_METRICS_ENABLED:
            metrics = {
                'policy_runtime_facts_context_build_ms': int(round(max(0.0, time.time() - facts_started_ts) * 1000.0)),
                'policy_runtime_facts_device_count': int(fact_device_count),
                'policy_runtime_facts_capability_fields': int(fact_capability_fields),
                'policy_runtime_facts_policy_fields': int(fact_policy_fields),
                'policy_runtime_facts_adapter_fields': int(fact_adapter_fields),
                'policy_runtime_fact_dict_copies': int(fact_dict_copies),
                'policy_runtime_facts_dynamic_bindings': int(len(dynamic_fact_bindings)),
                'policy_runtime_facts_dynamic_binding_groups': int(len(dynamic_fact_binding_groups)),
                'policy_runtime_selected_ev_contexts': int(len(selected_ev_context_by_id)),
            }
            facts_without_metrics['_metrics'] = metrics
        return facts_without_metrics

    device_ids_by_kind = dict(facts_plan.get('device_ids_by_kind', {}) or {})
    device_descriptors = dict(facts_plan.get('devices', {}) or {})
    fact_dict_copies += 2
    device_kind_by_id = {}
    device_capabilities_by_id = {}
    device_policy_by_id = {}
    device_adapter_by_id = {}
    fact_dict_copies += 4

    for device_id, descriptor in device_descriptors.items():
        device_plan = _policy_runtime_device_plan(compiled_plan, str(device_id))
        if device_plan is None:
            continue
        fact_device_count += 1
        dynamic_values = _policy_runtime_device_values(snapshot, str(device_id))
        kind = str(descriptor.get('kind', '') or '')
        device_kind_by_id[str(device_id)] = kind

        capability_values = {}
        fact_dict_copies += 1
        for field_name in tuple(descriptor.get('capabilities_fields', ()) or ()):
            fact_capability_fields += 1
            default = False if str(field_name) in ('can_absorb_w', 'can_produce_w', 'uses_hard_off_lifecycle', 'supports_primary_regulation', 'supports_residual_regulation') else 0
            capability_values[str(field_name)] = _resolve_snapshot_backed_section_value(
                device_plan,
                dynamic_values,
                'capabilities',
                str(field_name),
                default,
            )
        device_capabilities_by_id[str(device_id)] = capability_values

        policy_values = {}
        fact_dict_copies += 1
        for field_name in tuple(descriptor.get('policy_fields', ()) or ()):
            fact_policy_fields += 1
            policy_values[str(field_name)] = _resolve_snapshot_backed_section_value(
                device_plan,
                dynamic_values,
                'policy',
                str(field_name),
                0 if str(field_name) == 'priority' else False,
            )
        device_policy_by_id[str(device_id)] = policy_values

        adapter_values = {}
        fact_dict_copies += 1
        for field_name in tuple(descriptor.get('adapter_fields', ()) or ()):
            fact_adapter_fields += 1
            adapter_values[str(field_name)] = _resolve_snapshot_backed_section_value(
                device_plan,
                dynamic_values,
                'adapter',
                str(field_name),
                None,
            )
        if adapter_values:
            device_adapter_by_id[str(device_id)] = adapter_values

    normalized_ids_by_kind = {}
    fact_dict_copies += 1
    for kind, ids in device_ids_by_kind.items():
        normalized_ids = []
        for device_id in tuple(ids or ()):
            normalized_ids.append(str(device_id))
        normalized_ids_by_kind[str(kind)] = tuple(normalized_ids)

    facts = {
        'device_ids_by_kind': normalized_ids_by_kind,
        'device_kind_by_id': device_kind_by_id,
        'device_capabilities_by_id': device_capabilities_by_id,
        'device_policy_by_id': device_policy_by_id,
        'device_adapter_by_id': device_adapter_by_id,
    }
    if POLICY_RUNTIME_FACTS_DETAILED_METRICS_ENABLED:
        metrics = {
            'policy_runtime_facts_context_build_ms': int(round(max(0.0, time.time() - facts_started_ts) * 1000.0)),
            'policy_runtime_facts_device_count': int(fact_device_count),
            'policy_runtime_facts_capability_fields': int(fact_capability_fields),
            'policy_runtime_facts_policy_fields': int(fact_policy_fields),
            'policy_runtime_facts_adapter_fields': int(fact_adapter_fields),
            'policy_runtime_fact_dict_copies': int(fact_dict_copies),
        }
        facts['_metrics'] = metrics
    return facts


def _static_snapshot_value(value: object) -> object:
    if isinstance(value, DynamicConfigRef):
        return value.default
    if isinstance(value, MappingProxyType):
        materialized = {}
        for key, item in value.items():
            materialized[str(key)] = _static_snapshot_value(item)
        return materialized
    if isinstance(value, dict):
        materialized = {}
        for key, item in value.items():
            materialized[str(key)] = _static_snapshot_value(item)
        return materialized
    if isinstance(value, tuple):
        materialized = []
        for item in value:
            materialized.append(_static_snapshot_value(item))
        return tuple(materialized)
    return value


def _packet_missing(value: object) -> bool:
    return value in (None, 'unknown', 'unavailable', 'none', '')


def _coerce_packet_value(value: object, default: object) -> object:
    if _packet_missing(value):
        return default
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        return text in ('1', 'true', 'yes', 'on')
    if isinstance(default, int) and not isinstance(default, bool):
        if isinstance(value, bool):
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        if isinstance(value, bool):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return value


def build_dynamic_runtime_snapshot(
    compiled_plan: CompiledEMSPlan,
    read_entity: Callable[[str, object], object],
    metrics: Optional[dict[str, int]] = None,
    dynamic_runtime_read_plan: Optional[dict[str, object]] = None,
    dynamic_runtime_read_values: Optional[tuple[object, ...]] = None,
) -> DynamicRuntimeSnapshot:
    materialize_started_ts = time.time()
    runtime_read_plan = dynamic_runtime_read_plan or compile_dynamic_runtime_read_plan(compiled_plan)

    if dynamic_runtime_read_values is None:
        resolved_values_list = []
        for index, read_entry in enumerate(runtime_read_plan.get('unique_reads', ())):
            resolved_values_list.append(read_entity(str(read_entry['entity_id']), read_entry.get('default')))
            logical_count = int(tuple(runtime_read_plan.get('logical_read_counts', ()))[index])
            note_cached_dynamic_read = getattr(read_entity, 'note_cached_dynamic_read', None)
            if callable(note_cached_dynamic_read):
                duplicate_count = max(0, logical_count - 1)
                while duplicate_count > 0:
                    note_cached_dynamic_read(str(read_entry['entity_id']), read_entry.get('default'))
                    duplicate_count -= 1
        dynamic_runtime_read_values = tuple(resolved_values_list)

    snapshot_stats = {
        'dict_nodes': 0,
        'tuple_nodes': 0,
        'dynamic_refs_seen': int(runtime_read_plan.get('dynamic_refs_seen', 0) or 0),
        'dynamic_refs_unique': int(runtime_read_plan.get('dynamic_refs_unique', 0) or 0),
        'dynamic_ref_cache_hits': int(runtime_read_plan.get('dynamic_ref_cache_hits', 0) or 0),
    }

    profiles_started_ts = time.time()
    profiles = _assemble_flat_runtime_section(
        tuple(runtime_read_plan.get('profiles_fields', ()) or ()),
        dynamic_runtime_read_values,
        stats=snapshot_stats,
    )
    global_config = _assemble_flat_runtime_section(
        tuple(runtime_read_plan.get('global_config_fields', ()) or ()),
        dynamic_runtime_read_values,
        stats=snapshot_stats,
    )
    runtime = _assemble_flat_runtime_section(
        tuple(runtime_read_plan.get('runtime_fields', ()) or ()),
        dynamic_runtime_read_values,
        stats=snapshot_stats,
    )
    state = _assemble_flat_runtime_section(
        tuple(runtime_read_plan.get('state_fields', ()) or ()),
        dynamic_runtime_read_values,
        stats=snapshot_stats,
    )
    _record_core_config_metric(metrics, 'policy_engine_core_config_profiles_global_runtime_state_ms', profiles_started_ts)

    devices_started_ts = time.time()
    device_values = {}
    for device_id, device_plan in compiled_plan.devices.items():
        device_values[str(device_id)] = _assemble_flat_runtime_device_dynamic_values(
            tuple(runtime_read_plan.get('device_dynamic_fields', {}).get(str(device_id), ()) or ()),
            dynamic_runtime_read_values,
            stats=snapshot_stats,
        )
    _record_core_config_metric(metrics, 'policy_engine_core_config_devices_ms', devices_started_ts)

    home_battery_started_ts = time.time()
    home_battery_values = _assemble_flat_runtime_device_dynamic_values(
        tuple(runtime_read_plan.get('home_battery_dynamic_fields', ()) or ()),
        dynamic_runtime_read_values,
        stats=snapshot_stats,
    )
    battery_priority_slot = runtime_read_plan.get('home_battery_priority_slot')
    battery_priority_static = runtime_read_plan.get('home_battery_priority_static', 3)
    resolved_battery_priority = battery_priority_static
    if battery_priority_slot is not None:
        resolved_battery_priority = dynamic_runtime_read_values[int(battery_priority_slot)]
        home_battery_values.setdefault('policy', {})
        home_battery_values['policy']['priority'] = resolved_battery_priority
    _record_core_config_metric(metrics, 'policy_engine_core_config_home_battery_ms', home_battery_started_ts)

    haeo_started_ts = time.time()
    haeo_values = None
    if compiled_plan.haeo is not None:
        haeo_values = _assemble_flat_runtime_section(
            tuple(runtime_read_plan.get('haeo_fields', ()) or ()),
            dynamic_runtime_read_values,
            stats=snapshot_stats,
        )
    _record_core_config_metric(metrics, 'policy_engine_core_config_haeo_ms', haeo_started_ts)

    role_constraints_started_ts = time.time()
    role_constraint_values = _assemble_flat_runtime_role_constraints(
        tuple(runtime_read_plan.get('role_constraint_fields', ()) or ()),
        dynamic_runtime_read_values,
        stats=snapshot_stats,
    )
    _record_core_config_metric(metrics, 'policy_engine_core_config_role_constraints_ms', role_constraints_started_ts)

    derived_fields_started_ts = time.time()
    if metrics is not None:
        metrics['policy_engine_dynamic_runtime_snapshot_dict_nodes'] = int(snapshot_stats['dict_nodes'])
        metrics['policy_engine_dynamic_runtime_snapshot_tuple_nodes'] = int(snapshot_stats['tuple_nodes'])
        metrics['policy_engine_dynamic_runtime_snapshot_dynamic_refs_seen'] = int(snapshot_stats['dynamic_refs_seen'])
        metrics['policy_engine_dynamic_runtime_snapshot_dynamic_refs_unique'] = int(snapshot_stats['dynamic_refs_unique'])
        metrics['policy_engine_dynamic_runtime_snapshot_dynamic_ref_cache_hits'] = int(snapshot_stats['dynamic_ref_cache_hits'])
    _record_core_config_metric(metrics, 'policy_engine_core_config_derived_fields_ms', derived_fields_started_ts)
    _record_core_config_metric(metrics, 'policy_engine_core_config_materialize_total_ms', materialize_started_ts)
    return DynamicRuntimeSnapshot(
        profiles=profiles,
        global_config=global_config,
        runtime=runtime,
        state=state,
        device_values=device_values,
        home_battery_values=home_battery_values,
        haeo_values=haeo_values,
        role_constraint_values=role_constraint_values,
    )


def build_policy_context_view(
    compiled_plan: CompiledEMSPlan,
    read_entity: Callable[[str, object], object],
    metrics: Optional[dict[str, int]] = None,
    dynamic_runtime_read_plan: Optional[dict[str, object]] = None,
    dynamic_runtime_read_values: Optional[tuple[object, ...]] = None,
) -> CoreConfigView:
    snapshot_started_ts = time.time()
    snapshot = build_dynamic_runtime_snapshot(
        compiled_plan,
        read_entity,
        metrics=metrics,
        dynamic_runtime_read_plan=dynamic_runtime_read_plan,
        dynamic_runtime_read_values=dynamic_runtime_read_values,
    )
    _record_core_config_metric(metrics, 'policy_engine_dynamic_runtime_snapshot_ms', snapshot_started_ts)
    view_started_ts = time.time()
    cfg_view = CoreConfigView(PolicyContext(plan=compiled_plan, snapshot=snapshot))
    _record_core_config_metric(metrics, 'policy_engine_policy_context_view_ms', view_started_ts)
    return cfg_view


def _materialize_core_config_via_resolved_config_for_tests(
    plan: CompiledCoreConfigPlan,
    read_entity: Callable[[str, object], object],
) -> CoreConfig:
    resolved_config = _materialize_dynamic_value(plan.grouped_config_plan, read_entity)
    return _build_core_config_from_grouped_value_config(resolved_config)


def _materialize_core_config_direct(
    plan: CompiledCoreConfigPlan,
    read_entity: Callable[[str, object], object],
    metrics: Optional[dict[str, int]] = None,
) -> CoreConfig:
    materialize_started_ts = time.time()
    ems_plan = _require_mapping_value(plan.grouped_config_plan, 'ems')
    profiles_started_ts = time.time()
    profiles = _materialize_core_profiles_from_plan(ems_plan, read_entity)
    global_config = _materialize_core_global_from_plan(ems_plan, read_entity)
    runtime = _materialize_core_runtime_from_plan(ems_plan, read_entity)
    state = _materialize_core_state_from_plan(ems_plan, read_entity)
    _record_core_config_metric(
        metrics,
        'policy_engine_core_config_profiles_global_runtime_state_ms',
        profiles_started_ts,
    )

    devices_started_ts = time.time()
    core_devices = _materialize_core_devices_from_plan(ems_plan, read_entity)
    _record_core_config_metric(metrics, 'policy_engine_core_config_devices_ms', devices_started_ts)

    home_battery_started_ts = time.time()
    home_battery = _materialize_home_battery_from_plan(ems_plan, core_devices, read_entity)
    core_devices['HOME_BATTERY'] = home_battery
    _record_core_config_metric(metrics, 'policy_engine_core_config_home_battery_ms', home_battery_started_ts)

    haeo_started_ts = time.time()
    haeo = _materialize_core_haeo_from_plan(ems_plan, read_entity)
    _record_core_config_metric(metrics, 'policy_engine_core_config_haeo_ms', haeo_started_ts)

    role_constraints_started_ts = time.time()
    role_constraints = _materialize_core_role_constraints_from_plan(ems_plan, read_entity)
    _record_core_config_metric(metrics, 'policy_engine_core_config_role_constraints_ms', role_constraints_started_ts)

    core_config = CoreConfig(
        profiles=profiles,
        policy_engine=_materialize_core_policy_engine_from_plan(ems_plan),
        global_config=global_config,
        home_battery=home_battery,
        runtime=runtime,
        state=state,
        policy_outputs=CorePolicyOutputsConfig(
            device_policies=CANONICAL_POLICY_OUTPUTS['device_policies'],
            dispatch_command=CANONICAL_POLICY_OUTPUTS['dispatch_command'],
            policy_state=CANONICAL_POLICY_OUTPUTS['policy_state'],
        ),
        diagnostics_outputs=CoreDiagnosticsOutputsConfig(
            policy_diagnostics=CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics'],
            actuator_writer_trace=CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace'],
            dispatch_state_applier_trace=CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace'],
        ),
        haeo=haeo,
        role_constraints=role_constraints,
        devices=core_devices,
    )
    derived_fields_started_ts = time.time()
    materialized_core_config = _populate_core_config_derived_fields(core_config)
    _record_core_config_metric(metrics, 'policy_engine_core_config_derived_fields_ms', derived_fields_started_ts)
    _record_core_config_metric(metrics, 'policy_engine_core_config_materialize_total_ms', materialize_started_ts)
    return materialized_core_config


def _record_core_config_metric(metrics: Optional[dict[str, int]], key: str, started_ts: float) -> None:
    if metrics is None:
        return
    metrics[key] = max(0, int(round((time.time() - started_ts) * 1000.0)))


def _build_view_profiles(values: dict) -> CoreProfilesConfig:
    return CoreProfilesConfig(
        control=values['control'],
        goal=values['goal'],
        forecast=values['forecast'],
        guard=values['guard'],
    )


def _build_view_policy_engine(values: dict) -> CorePolicyEngineConfig:
    return CorePolicyEngineConfig(
        interval_seconds=_parse_policy_engine_interval_seconds(values.get('interval_seconds', 5.0)),
        diagnostics_interval_seconds=_parse_policy_engine_diagnostics_interval_seconds(
            values.get('diagnostics_interval_seconds', 30.0)
        ),
    )


def _build_view_global_config(values: dict) -> CoreGlobalConfig:
    return CoreGlobalConfig(
        deadband_w=values['deadband_w'],
        ramp_w=values['ramp_w'],
        strict_limit_w=values['strict_limit_w'],
        default_sp_w=values['default_sp_w'],
        surplus_freeze_s=values['surplus_freeze_s'],
        battery_heartbeat_timeout_s=values['battery_heartbeat_timeout_s'],
        haeo_stale_timeout_s=values['haeo_stale_timeout_s'],
        nz_battery_floor_default_w=values['nz_battery_floor_default_w'],
        nz_battery_floor_ev_active_w=values['nz_battery_floor_ev_active_w'],
        adjustable_primary_load=values['adjustable_primary_load'],
    )


def _build_view_runtime(values: dict) -> CoreRuntimeConfig:
    return CoreRuntimeConfig(
        grid_power_w=values['grid_power_w'],
        quarter_energy_balance_kwh=values['quarter_energy_balance_kwh'],
        pv_power_w=values['pv_power_w'],
    )


def _build_view_state(values: dict) -> CoreStateConfig:
    return CoreStateConfig(
        surplus_freeze_until=values['surplus_freeze_until'],
        active_surplus_devices=values['active_surplus_devices'],
        previous_device_state=values['previous_device_state'],
    )


def _build_view_haeo(values: Optional[dict]) -> Optional[CoreHaeoConfig]:
    if values is None:
        return None
    return CoreHaeoConfig(
        battery_power_active=values['battery_power_active'],
        ev_power_active=values['ev_power_active'],
        battery_fresh_source=values['battery_fresh_source'],
        ev_fresh_source=values['ev_fresh_source'],
    )


def _build_view_role_constraints(values: dict) -> CoreRoleConstraintsConfig:
    by_role = {}
    for role_key, role_devices in (values or {}).items():
        if role_key == 'default' or not isinstance(role_devices, dict):
            continue
        copied_role_devices = {}
        for device_id, device_fields in role_devices.items():
            copied_role_devices[str(device_id)] = dict(device_fields)
        by_role[str(role_key)] = copied_role_devices
    return CoreRoleConstraintsConfig(
        default=dict((values or {}).get('default', {})),
        by_role=by_role,
    )


def _build_view_capabilities(values: dict) -> CoreDeviceCapabilitiesConfig:
    caps = values['capabilities']
    return CoreDeviceCapabilitiesConfig(
        can_absorb_w=bool(caps['can_absorb_w']),
        can_produce_w=bool(caps['can_produce_w']),
        supports_primary_regulation=bool(caps['supports_primary_regulation']),
        supports_residual_regulation=bool(caps['supports_residual_regulation']),
        min_absorb_w=caps['min_absorb_w'],
        max_absorb_w=caps['max_absorb_w'],
        step_w=caps['step_w'],
        max_produce_w=caps.get('max_produce_w'),
        uses_hard_off_lifecycle=bool(caps.get('uses_hard_off_lifecycle', False)),
    )


def _build_view_battery_device(plan: StaticDevicePlan, values: dict) -> CoreBatteryDeviceConfig:
    capabilities = {
        'capabilities': {
            'can_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'can_absorb_w', False),
            'can_produce_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'can_produce_w', False),
            'uses_hard_off_lifecycle': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'uses_hard_off_lifecycle', False),
            'supports_primary_regulation': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'supports_primary_regulation', False),
            'supports_residual_regulation': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'supports_residual_regulation', False),
            'min_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'min_absorb_w', 0),
            'max_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'max_absorb_w', 0),
            'step_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'step_w', 1),
            'max_produce_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'max_produce_w'),
        }
    }
    return CoreBatteryDeviceConfig(
        device_id=plan.device_id,
        kind=str(plan.kind),
        capabilities=_build_view_capabilities(capabilities),
        policy=CoreBatteryPolicyConfig(
            priority=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'priority', 3),
            surplus_allowed=bool(_resolve_snapshot_backed_section_value(plan, values, 'policy', 'surplus_allowed', False)),
            surplus_dispatch_mode=str(_resolve_snapshot_backed_section_value(plan, values, 'policy', 'surplus_dispatch_mode', 'max_absorb')),
            default_min_absorb_w=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'default_min_absorb_w'),
        ),
        guard=CoreBatteryGuardConfig(
            soc=_resolve_snapshot_backed_section_value(plan, values, 'guard', 'soc', ''),
            min_cell_voltage_v=_resolve_snapshot_backed_section_value(plan, values, 'guard', 'min_cell_voltage_v', ''),
            heartbeat=_resolve_snapshot_backed_section_value(plan, values, 'guard', 'heartbeat', ''),
            protect_soc=_resolve_snapshot_backed_section_value(plan, values, 'guard', 'protect_soc', 2),
            protect_soc_recovery_margin=_resolve_snapshot_backed_section_value(plan, values, 'guard', 'protect_soc_recovery_margin', 1),
            protect_min_cell_voltage_v=_resolve_snapshot_backed_section_value(plan, values, 'guard', 'protect_min_cell_voltage_v', 3.030),
            protect_min_absorb_w=_resolve_snapshot_backed_section_value(plan, values, 'guard', 'protect_min_absorb_w', 0),
        ),
        adapter=CoreBatteryAdapterConfig(
            target_w=_resolve_snapshot_backed_section_value(plan, values, 'adapter', 'target_w', ''),
            measured_power_w=_resolve_snapshot_backed_section_value(plan, values, 'adapter', 'measured_power_w', ''),
        ),
    )


def _build_view_ev_device(plan: StaticDevicePlan, values: dict) -> CoreEvChargerDeviceConfig:
    capabilities = {
        'capabilities': {
            'can_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'can_absorb_w', False),
            'can_produce_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'can_produce_w', False),
            'uses_hard_off_lifecycle': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'uses_hard_off_lifecycle', False),
            'supports_primary_regulation': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'supports_primary_regulation', False),
            'supports_residual_regulation': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'supports_residual_regulation', False),
            'min_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'min_absorb_w', 0),
            'max_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'max_absorb_w', 0),
            'step_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'step_w', 1),
            'max_produce_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'max_produce_w'),
        }
    }
    return CoreEvChargerDeviceConfig(
        device_id=plan.device_id,
        kind=str(plan.kind),
        capabilities=_build_view_capabilities(capabilities),
        policy=CoreEvPolicyConfig(
            priority=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'priority', 3),
            surplus_allowed=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'surplus_allowed', ''),
            surplus_dispatch_mode=str(_resolve_snapshot_backed_section_value(plan, values, 'policy', 'surplus_dispatch_mode', 'max_absorb')),
            force_on=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'force_on', ''),
            low_pv_threshold_w=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'low_pv_threshold_w', 1.6),
            hard_off_low_pv_cycles=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'hard_off_low_pv_cycles', 2),
            hard_off_release_cycles=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'hard_off_release_cycles', 2),
        ),
        adapter=CoreEvAdapterConfig(
            enabled=_resolve_snapshot_backed_section_value(plan, values, 'adapter', 'enabled', False),
            current_a=_resolve_snapshot_backed_section_value(plan, values, 'adapter', 'current_a', 0),
            current_step_a=_resolve_snapshot_backed_section_value(plan, values, 'adapter', 'current_step_a', 4),
            phases=_resolve_snapshot_backed_section_value(plan, values, 'adapter', 'phases', 1),
            voltage_v=_resolve_snapshot_backed_section_value(plan, values, 'adapter', 'voltage_v', 230),
        ),
    )


def _build_view_relay_device(plan: StaticDevicePlan, values: dict) -> CoreRelayDeviceConfig:
    capabilities = {
        'capabilities': {
            'can_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'can_absorb_w', False),
            'can_produce_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'can_produce_w', False),
            'uses_hard_off_lifecycle': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'uses_hard_off_lifecycle', False),
            'supports_primary_regulation': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'supports_primary_regulation', False),
            'supports_residual_regulation': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'supports_residual_regulation', False),
            'min_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'min_absorb_w', 0),
            'max_absorb_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'max_absorb_w', 0),
            'step_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'step_w', 1),
            'max_produce_w': _resolve_snapshot_backed_section_value(plan, values, 'capabilities', 'max_produce_w'),
        }
    }
    return CoreRelayDeviceConfig(
        device_id=plan.device_id,
        kind=str(plan.kind),
        capabilities=_build_view_capabilities(capabilities),
        policy=CoreRelayPolicyConfig(
            priority=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'priority', 0),
            surplus_allowed=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'surplus_allowed', ''),
            surplus_dispatch_mode=str(_resolve_snapshot_backed_section_value(plan, values, 'policy', 'surplus_dispatch_mode', 'fixed')),
            force_on=_resolve_snapshot_backed_section_value(plan, values, 'policy', 'force_on', ''),
        ),
        adapter=CoreRelayAdapterConfig(
            enabled=_resolve_snapshot_backed_section_value(plan, values, 'adapter', 'enabled', '')
        ),
    )




def _materialize_core_profiles_from_plan(
    ems_plan: dict,
    read_entity: Callable[[str, object], object],
) -> CoreProfilesConfig:
    profiles = _require_mapping_value(ems_plan, 'profiles')
    return CoreProfilesConfig(
        control=_resolve_core_config_value(_require_mapping_value(profiles, 'control'), read_entity, ''),
        goal=_resolve_core_config_value(_require_mapping_value(profiles, 'goal'), read_entity, ''),
        forecast=_resolve_core_config_value(_require_mapping_value(profiles, 'forecast'), read_entity, ''),
        guard=_resolve_core_config_value(_require_mapping_value(profiles, 'guard'), read_entity, ''),
    )


def _materialize_core_policy_engine_from_plan(ems_plan: dict) -> CorePolicyEngineConfig:
    policy_engine = ems_plan.get('policy_engine', {})
    return CorePolicyEngineConfig(
        interval_seconds=_parse_policy_engine_interval_seconds(
            policy_engine.get('interval_seconds', 5.0) if isinstance(policy_engine, dict) else 5.0
        ),
        diagnostics_interval_seconds=_parse_policy_engine_diagnostics_interval_seconds(
            policy_engine.get('diagnostics_interval_seconds', 30.0) if isinstance(policy_engine, dict) else 30.0
        ),
    )


def _materialize_core_global_from_plan(
    ems_plan: dict,
    read_entity: Callable[[str, object], object],
) -> CoreGlobalConfig:
    global_config = _require_mapping_value(ems_plan, 'global_config')
    return CoreGlobalConfig(
        deadband_w=_resolve_core_config_value(_require_mapping_value(global_config, 'deadband_w'), read_entity, 50),
        ramp_w=_resolve_core_config_value(_require_mapping_value(global_config, 'ramp_w'), read_entity, 1000),
        strict_limit_w=_resolve_core_config_value(_require_mapping_value(global_config, 'strict_limit_w'), read_entity, 4600),
        default_sp_w=_resolve_core_config_value(global_config.get('default_sp_w', 100.0), read_entity, 100.0),
        surplus_freeze_s=_resolve_core_config_value(_require_mapping_value(global_config, 'surplus_freeze_s'), read_entity, 30),
        battery_heartbeat_timeout_s=_resolve_core_config_value(global_config.get('battery_heartbeat_timeout_s', 360.0), read_entity, 360.0),
        haeo_stale_timeout_s=_resolve_core_config_value(_require_mapping_value(global_config, 'haeo_stale_timeout_s'), read_entity, 300),
        nz_battery_floor_default_w=_resolve_core_config_value(_require_mapping_value(global_config, 'nz_battery_floor_default_w'), read_entity, 100.0),
        nz_battery_floor_ev_active_w=_resolve_core_config_value(_require_mapping_value(global_config, 'nz_battery_floor_ev_active_w'), read_entity, 0.0),
        adjustable_primary_load=_resolve_core_config_value(_require_mapping_value(global_config, 'adjustable_primary_load'), read_entity, ''),
    )


def _materialize_core_runtime_from_plan(
    ems_plan: dict,
    read_entity: Callable[[str, object], object],
) -> CoreRuntimeConfig:
    runtime = _require_mapping_value(ems_plan, 'runtime')
    return CoreRuntimeConfig(
        grid_power_w=_resolve_core_config_value(_require_mapping_value(runtime, 'grid_power_w'), read_entity, 0),
        quarter_energy_balance_kwh=_resolve_core_config_value(_require_mapping_value(runtime, 'quarter_energy_balance_kwh'), read_entity, 0),
        pv_power_w=_resolve_core_config_value(_require_mapping_value(runtime, 'pv_power_w'), read_entity, 0),
    )


def _materialize_core_state_from_plan(
    ems_plan: dict,
    read_entity: Callable[[str, object], object],
) -> CoreStateConfig:
    state = _require_mapping_value(ems_plan, 'state')
    return CoreStateConfig(
        surplus_freeze_until=_resolve_core_config_value(_require_mapping_value(state, 'surplus_freeze_until'), read_entity, ''),
        active_surplus_devices=_resolve_core_config_value(_require_mapping_value(state, 'active_surplus_devices'), read_entity, ''),
        previous_device_state=_resolve_core_config_value(_require_mapping_value(state, 'previous_device_state'), read_entity, ''),
    )


def _materialize_core_haeo_from_plan(
    ems_plan: dict,
    read_entity: Callable[[str, object], object],
) -> Optional[CoreHaeoConfig]:
    return _build_core_haeo_config(ems_plan.get('haeo'), read_entity)


def _materialize_core_role_constraints_from_plan(
    ems_plan: dict,
    read_entity: Callable[[str, object], object],
) -> CoreRoleConstraintsConfig:
    return _build_core_role_constraints(ems_plan.get('role_constraints'), read_entity)


def _materialize_core_devices_from_plan(
    ems_plan: dict,
    read_entity: Callable[[str, object], object],
) -> dict[str, object]:
    devices = ems_plan.get('devices', {})
    if not isinstance(devices, dict):
        return {}

    materialized = {}
    for device_id, device in devices.items():
        if str(device_id) == 'HOME_BATTERY' or not isinstance(device, dict):
            continue
        kind = str(_resolve_core_config_value(device.get('kind'), read_entity, ''))
        if kind == 'BATTERY':
            materialized[str(device_id)] = _build_core_battery_device(str(device_id), device, read_entity)
        elif kind == 'EV_CHARGER':
            materialized[str(device_id)] = _build_core_ev_device(str(device_id), device, read_entity)
        elif kind == 'RELAY':
            materialized[str(device_id)] = _build_core_relay_device(str(device_id), device, read_entity)
    return materialized


def _resolve_home_battery_priority_from_plan(
    battery_device_plan: object,
    core_devices: dict[str, object],
    read_entity: Callable[[str, object], object],
) -> object:
    policy = _require_mapping_value(_require_mapping_value(battery_device_plan, 'policy'), 'priority')
    return _resolve_core_config_value(policy, read_entity, 3)


def _materialize_home_battery_from_plan(
    ems_plan: dict,
    core_devices: dict[str, object],
    read_entity: Callable[[str, object], object],
) -> CoreBatteryDeviceConfig:
    devices = _require_mapping_value(ems_plan, 'devices')
    device = _require_mapping_value(devices, 'HOME_BATTERY')
    policy = _require_mapping_value(device, 'policy')
    guard = _require_mapping_value(device, 'guard')
    adapter = _require_mapping_value(device, 'adapter')
    return CoreBatteryDeviceConfig(
        device_id='HOME_BATTERY',
        kind=str(_resolve_core_config_value(_require_mapping_value(device, 'kind'), read_entity, 'BATTERY')),
        capabilities=_build_core_capabilities(
            device,
            read_entity,
            default_min_absorb_w=0,
            default_max_absorb_w=3700,
            default_step_w=50,
            default_max_produce_w=4600,
        ),
        policy=CoreBatteryPolicyConfig(
            priority=_resolve_home_battery_priority_from_plan(device, core_devices, read_entity),
            surplus_allowed=bool(
                _resolve_core_config_value(policy.get('surplus_allowed', False), read_entity, False)
            ),
            surplus_dispatch_mode=str(
                _resolve_core_config_value(policy.get('surplus_dispatch_mode', 'max_absorb'), read_entity, 'max_absorb')
            ),
            default_min_absorb_w=_resolve_core_config_value(_require_mapping_value(policy, 'default_min_absorb_w'), read_entity, 0.0)
            if 'default_min_absorb_w' in policy
            else None,
        ),
        guard=CoreBatteryGuardConfig(
            soc=_resolve_core_config_value(_require_mapping_value(guard, 'soc'), read_entity, ''),
            min_cell_voltage_v=_resolve_core_config_value(_require_mapping_value(guard, 'min_cell_voltage_v'), read_entity, ''),
            heartbeat=_resolve_core_config_value(_require_mapping_value(guard, 'heartbeat'), read_entity, ''),
            protect_soc=_resolve_core_config_value(_require_mapping_value(guard, 'protect_soc'), read_entity, 2),
            protect_soc_recovery_margin=_resolve_core_config_value(_require_mapping_value(guard, 'protect_soc_recovery_margin'), read_entity, 1),
            protect_min_cell_voltage_v=_resolve_core_config_value(_require_mapping_value(guard, 'protect_min_cell_voltage_v'), read_entity, 3.030),
            protect_min_absorb_w=_resolve_core_config_value(_require_mapping_value(guard, 'protect_min_absorb_w'), read_entity, 0),
        ),
        adapter=CoreBatteryAdapterConfig(
            target_w=_resolve_core_config_value(_require_mapping_value(adapter, 'target_w'), read_entity, ''),
            measured_power_w=_resolve_core_config_value(_require_mapping_value(adapter, 'measured_power_w'), read_entity, ''),
        ),
    )


def _build_core_devices_map(
    devices: object,
    read_entity: Optional[Callable[[str, object], object]],
) -> dict[str, object]:
    if not isinstance(devices, dict):
        return {}

    mapped = {}
    for device_id, device in devices.items():
        if not isinstance(device, dict):
            continue
        device = dict(device)
        device['_device_id'] = str(device_id)
        kind = str(_resolve_core_config_value(device.get('kind'), read_entity, ''))
        if kind == 'BATTERY':
            mapped[str(device_id)] = _build_core_battery_device(str(device_id), device, read_entity)
        elif kind == 'EV_CHARGER':
            mapped[str(device_id)] = _build_core_ev_device(str(device_id), device, read_entity)
        elif kind == 'RELAY':
            mapped[str(device_id)] = _build_core_relay_device(str(device_id), device, read_entity)
    return mapped


def build_core_config_from_grouped_reader(
    config: dict,
    read_entity: Callable[[str, object], object],
) -> CoreConfig:
    plan = compile_core_config_plan_from_grouped_config(config)
    return materialize_core_config_from_plan(plan, read_entity)


def _build_core_config_from_grouped_value_config(config: dict) -> CoreConfig:
    ems = config.get('ems', {})
    devices = ems.get('devices', {})
    role_constraints = ems.get('role_constraints', {})
    policy_engine = ems.get('policy_engine', {})
    read_entity = None
    core_devices = _build_core_devices_map(devices, read_entity)
    home_battery = _build_core_battery_device(
        'HOME_BATTERY',
        devices.get('HOME_BATTERY'),
        read_entity,
        default_priority=3,
    )
    core_devices['HOME_BATTERY'] = home_battery
    core_config = CoreConfig(
        profiles=CoreProfilesConfig(
            control=_resolve_core_config_value(_require_mapping_value(ems.get('profiles'), 'control'), read_entity, ''),
            goal=_resolve_core_config_value(_require_mapping_value(ems.get('profiles'), 'goal'), read_entity, ''),
            forecast=_resolve_core_config_value(_require_mapping_value(ems.get('profiles'), 'forecast'), read_entity, ''),
            guard=_resolve_core_config_value(_require_mapping_value(ems.get('profiles'), 'guard'), read_entity, ''),
        ),
        policy_engine=CorePolicyEngineConfig(
            interval_seconds=_parse_policy_engine_interval_seconds(
                policy_engine.get('interval_seconds', 5.0) if isinstance(policy_engine, dict) else 5.0
            ),
            diagnostics_interval_seconds=_parse_policy_engine_diagnostics_interval_seconds(
                policy_engine.get('diagnostics_interval_seconds', 30.0) if isinstance(policy_engine, dict) else 30.0
            ),
        ),
        global_config=CoreGlobalConfig(
            deadband_w=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'deadband_w'), read_entity, 50),
            ramp_w=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'ramp_w'), read_entity, 1000),
            strict_limit_w=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'strict_limit_w'), read_entity, 4600),
            default_sp_w=_resolve_core_config_value(ems.get('global_config', {}).get('default_sp_w', 100.0), read_entity, 100.0),
            surplus_freeze_s=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'surplus_freeze_s'), read_entity, 30),
            battery_heartbeat_timeout_s=_resolve_core_config_value(ems.get('global_config', {}).get('battery_heartbeat_timeout_s', 360.0), read_entity, 360.0),
            haeo_stale_timeout_s=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'haeo_stale_timeout_s'), read_entity, 300),
            nz_battery_floor_default_w=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'nz_battery_floor_default_w'), read_entity, 100.0),
            nz_battery_floor_ev_active_w=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'nz_battery_floor_ev_active_w'), read_entity, 0.0),
            adjustable_primary_load=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'adjustable_primary_load'), read_entity, ''),
        ),
        home_battery=home_battery,
        runtime=CoreRuntimeConfig(
            grid_power_w=_resolve_core_config_value(_require_mapping_value(ems.get('runtime'), 'grid_power_w'), read_entity, 0),
            quarter_energy_balance_kwh=_resolve_core_config_value(_require_mapping_value(ems.get('runtime'), 'quarter_energy_balance_kwh'), read_entity, 0),
            pv_power_w=_resolve_core_config_value(_require_mapping_value(ems.get('runtime'), 'pv_power_w'), read_entity, 0),
        ),
        state=CoreStateConfig(
            surplus_freeze_until=_resolve_core_config_value(_require_mapping_value(ems.get('state'), 'surplus_freeze_until'), read_entity, ''),
            active_surplus_devices=_resolve_core_config_value(_require_mapping_value(ems.get('state'), 'active_surplus_devices'), read_entity, ''),
            previous_device_state=_resolve_core_config_value(_require_mapping_value(ems.get('state'), 'previous_device_state'), read_entity, ''),
        ),
        policy_outputs=CorePolicyOutputsConfig(
            device_policies=CANONICAL_POLICY_OUTPUTS['device_policies'],
            dispatch_command=CANONICAL_POLICY_OUTPUTS['dispatch_command'],
            policy_state=CANONICAL_POLICY_OUTPUTS['policy_state'],
        ),
        diagnostics_outputs=CoreDiagnosticsOutputsConfig(
            policy_diagnostics=CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics'],
            actuator_writer_trace=CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace'],
            dispatch_state_applier_trace=CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace'],
        ),
        haeo=_build_core_haeo_config(ems.get('haeo'), read_entity),
        role_constraints=_build_core_role_constraints(role_constraints, read_entity),
        devices=core_devices,
    )
    return _populate_core_config_derived_fields(core_config)


def _populate_core_config_derived_fields(core_config: CoreConfig) -> CoreConfig:
    if core_config.role_constraints is None:
        core_config.role_constraints = CoreRoleConstraintsConfig()
    if core_config.deadband_w is None:
        core_config.deadband_w = core_config.global_config.deadband_w
    if core_config.ramp_max_w is None:
        core_config.ramp_max_w = core_config.global_config.ramp_w
    if core_config.strict_limits_max_w is None:
        core_config.strict_limits_max_w = core_config.global_config.strict_limit_w
    if core_config.default_sp_w is None:
        core_config.default_sp_w = core_config.global_config.default_sp_w
    if core_config.battery_heartbeat_timeout_s is None:
        core_config.battery_heartbeat_timeout_s = core_config.global_config.battery_heartbeat_timeout_s
    if core_config.haeo_stale_timeout_s is None:
        core_config.haeo_stale_timeout_s = core_config.global_config.haeo_stale_timeout_s
    if core_config.max_solar_charge_w is None:
        core_config.max_solar_charge_w = core_config.home_battery.capabilities.max_absorb_w
    if core_config.max_battery_discharge_w is None:
        core_config.max_battery_discharge_w = core_config.home_battery.capabilities.max_produce_w
    if core_config.battery_protect_soc is None:
        core_config.battery_protect_soc = core_config.home_battery.guard.protect_soc
    if core_config.battery_protect_soc_recovery_margin is None:
        core_config.battery_protect_soc_recovery_margin = core_config.home_battery.guard.protect_soc_recovery_margin
    if core_config.battery_protect_min_cell_voltage_v is None:
        core_config.battery_protect_min_cell_voltage_v = core_config.home_battery.guard.protect_min_cell_voltage_v
    if core_config.battery_protect_charge_floor_w is None:
        core_config.battery_protect_charge_floor_w = core_config.home_battery.guard.protect_min_absorb_w
    if core_config.nz_battery_floor_default_w is None:
        core_config.nz_battery_floor_default_w = core_config.global_config.nz_battery_floor_default_w
    if core_config.nz_battery_floor_ev_active_w is None:
        core_config.nz_battery_floor_ev_active_w = core_config.global_config.nz_battery_floor_ev_active_w
    if core_config.adjustable_primary_load is None:
        core_config.adjustable_primary_load = core_config.global_config.adjustable_primary_load
    if core_config.surplus_freeze_s is None:
        core_config.surplus_freeze_s = core_config.global_config.surplus_freeze_s
    return core_config



def _parse_policy_engine_interval_seconds(raw_value):
    if raw_value is None:
        return 5.0
    if isinstance(raw_value, bool):
        raise ValueError('policy_engine.interval_seconds must be numeric')
    if not isinstance(raw_value, (int, float)):
        raise ValueError('policy_engine.interval_seconds must be numeric')
    interval_seconds = float(raw_value)
    if interval_seconds < 2.0:
        raise ValueError('policy_engine.interval_seconds must be >= 2 seconds')
    return interval_seconds


def _parse_policy_engine_diagnostics_interval_seconds(raw_value):
    if raw_value is None:
        return 30.0
    if isinstance(raw_value, bool):
        raise ValueError('policy_engine.diagnostics_interval_seconds must be a numeric config constant')
    if not isinstance(raw_value, (int, float)):
        raise ValueError('policy_engine.diagnostics_interval_seconds must be a numeric config constant')
    interval_seconds = float(raw_value)
    if interval_seconds < 5.0:
        raise ValueError('policy_engine.diagnostics_interval_seconds must be >= 5 seconds')
    return interval_seconds


def _validate_devices(devices: dict, issues: list[ConfigValidationIssue], runtime_packet_mode: bool = False) -> None:
    for device_id in REQUIRED_DEVICE_IDS:
        if device_id not in devices:
            issues.append(_issue(f'ems.devices.{device_id}', SEVERITY_ERROR, 'missing required device'))
    battery_ids = []
    for device_id, device in devices.items():
        if not isinstance(device, dict):
            issues.append(_issue(f'ems.devices.{device_id}', SEVERITY_ERROR, 'must be a mapping'))
            continue
        kind = device.get('kind')
        if kind == 'BATTERY':
            battery_ids.append(str(device_id))
        expected_kind = EXPECTED_DEVICE_KINDS.get(device_id)
        _validate_device(device_id, device, expected_kind, issues, runtime_packet_mode=runtime_packet_mode)

    if len(battery_ids) != 1 or battery_ids[0] != 'HOME_BATTERY':
        issues.append(_issue('ems.devices', SEVERITY_ERROR, 'phase-1 flexible loader supports exactly one battery device id: HOME_BATTERY'))


def _validate_device(device_id: str, device: dict, expected_kind: Optional[str], issues: list[ConfigValidationIssue], runtime_packet_mode: bool = False) -> None:
    device_path = f'ems.devices.{device_id}'
    kind = device.get('kind')
    _validate_unknown_fields(device, device_path, ALLOWED_DEVICE_KEYS, issues)
    if kind not in SUPPORTED_DEVICE_KINDS:
        issues.append(_issue(f'{device_path}.kind', SEVERITY_ERROR, f'unsupported kind {kind!r}'))
    elif expected_kind is not None and kind != expected_kind:
        issues.append(_issue(f'{device_path}.kind', SEVERITY_ERROR, f'expected {expected_kind}'))

    capabilities = device.get('capabilities')
    if not isinstance(capabilities, dict):
        issues.append(_issue(f'{device_path}.capabilities', SEVERITY_ERROR, 'missing or not a mapping'))
    elif runtime_packet_mode:
        _validate_packet_static_capabilities(device_path, capabilities, issues)
    else:
        _validate_capabilities(device_path, capabilities, issues)

    if runtime_packet_mode:
        required_sections = ['capabilities']
    else:
        required_sections = ['capabilities', 'policy', 'adapter']
        if device_id == 'HOME_BATTERY':
            required_sections.append('guard')
    for section in required_sections:
        if section not in device:
            issues.append(_issue(f'{device_path}.{section}', SEVERITY_ERROR, 'missing required section'))
        elif not isinstance(device.get(section), dict):
            issues.append(_issue(f'{device_path}.{section}', SEVERITY_ERROR, 'must be a mapping'))

    if runtime_packet_mode:
        for runtime_owned_section in ('policy', 'guard', 'adapter'):
            if runtime_owned_section in device:
                issues.append(
                    _issue(
                        f'{device_path}.{runtime_owned_section}',
                        SEVERITY_ERROR,
                        'runtime packet-owned section must not be defined in EMS_config.yaml',
                    )
                )
        if kind == 'RELAY':
            capabilities = device.get('capabilities')
            if isinstance(capabilities, dict):
                if capabilities.get('can_produce_w') is not False:
                    issues.append(_issue(f'{device_path}.capabilities.can_produce_w', SEVERITY_ERROR, 'relay must define can_produce_w=false'))
                if capabilities.get('can_absorb_w') is not True:
                    issues.append(_issue(f'{device_path}.capabilities.can_absorb_w', SEVERITY_ERROR, 'relay must define can_absorb_w=true'))
        return

    if device_id == 'HOME_BATTERY' and isinstance(device.get('guard'), dict):
        _validate_unknown_fields(
            device['guard'],
            f'{device_path}.guard',
            ALLOWED_BATTERY_GUARD_KEYS,
            issues,
        )
        _validate_required_entities(
            device['guard'],
            f'{device_path}.guard',
            ('soc', 'min_cell_voltage_v', 'heartbeat', 'protect_soc', 'protect_soc_recovery_margin', 'protect_min_cell_voltage_v', 'protect_min_absorb_w'),
            issues,
        )

    if device_id == 'HOME_BATTERY' and isinstance(device.get('policy'), dict):
        _validate_unknown_fields(
            device['policy'],
            f'{device_path}.policy',
            ALLOWED_BATTERY_POLICY_KEYS,
            issues,
        )
        if 'surplus_allowed' in device['policy']:
            _validate_entity_or_bool(device['policy'], f'{device_path}.policy.surplus_allowed', 'surplus_allowed', issues)
        if bool(device['policy'].get('surplus_allowed', False)):
            if device['policy'].get('surplus_dispatch_mode') not in ('max_absorb', 'fixed'):
                issues.append(_issue(f'{device_path}.policy.surplus_dispatch_mode', SEVERITY_ERROR, 'must be max_absorb or fixed'))

    if device_id == 'HOME_BATTERY' and isinstance(device.get('adapter'), dict):
        _validate_unknown_fields(
            device['adapter'],
            f'{device_path}.adapter',
            ALLOWED_BATTERY_ADAPTER_KEYS,
            issues,
        )
        _validate_required_entities(
            device['adapter'],
            f'{device_path}.adapter',
            ('target_w', 'measured_power_w'),
            issues,
        )

    if kind == 'EV_CHARGER' and isinstance(device.get('policy'), dict):
        _validate_unknown_fields(
            device['policy'],
            f'{device_path}.policy',
            ALLOWED_EV_POLICY_KEYS,
            issues,
        )
        _validate_required_entities(
            device['policy'],
            f'{device_path}.policy',
            ('priority', 'force_on', 'low_pv_threshold_w', 'hard_off_low_pv_cycles', 'hard_off_release_cycles'),
            issues,
        )
        _validate_entity_or_bool(device['policy'], f'{device_path}.policy.surplus_allowed', 'surplus_allowed', issues)
        dispatch_mode = device['policy'].get('surplus_dispatch_mode')
        if dispatch_mode not in ('max_absorb', 'fixed'):
            issues.append(_issue(f'{device_path}.policy.surplus_dispatch_mode', SEVERITY_ERROR, 'must be max_absorb or fixed'))

    if kind == 'EV_CHARGER' and isinstance(device.get('adapter'), dict):
        _validate_unknown_fields(
            device['adapter'],
            f'{device_path}.adapter',
            ALLOWED_EV_ADAPTER_KEYS,
            issues,
        )
        _validate_required_entities(
            device['adapter'],
            f'{device_path}.adapter',
            ('enabled', 'current_a', 'current_step_a', 'phases', 'voltage_v'),
            issues,
        )
        _validate_entity_or_number(device['adapter'], f'{device_path}.adapter.current_step_a', 'current_step_a', issues, min_value=1)
        _validate_entity_or_number(device['adapter'], f'{device_path}.adapter.phases', 'phases', issues, min_value=1)
        _validate_entity_or_number(device['adapter'], f'{device_path}.adapter.voltage_v', 'voltage_v', issues, min_value=1)
        _validate_ev_watt_limits_match_adapter_resolution(device_path, device, issues)

    if kind == 'RELAY':
        if isinstance(device.get('policy'), dict):
            _validate_unknown_fields(
                device['policy'],
                f'{device_path}.policy',
                ALLOWED_RELAY_POLICY_KEYS,
                issues,
            )
            _validate_required_entities(
                device['policy'],
                f'{device_path}.policy',
                ('priority', 'force_on'),
                issues,
            )
            _validate_entity_or_bool(device['policy'], f'{device_path}.policy.surplus_allowed', 'surplus_allowed', issues)
            dispatch_mode = device['policy'].get('surplus_dispatch_mode')
            if dispatch_mode not in ('max_absorb', 'fixed'):
                issues.append(_issue(f'{device_path}.policy.surplus_dispatch_mode', SEVERITY_ERROR, 'must be max_absorb or fixed'))
        if isinstance(device.get('adapter'), dict):
            _validate_unknown_fields(
                device['adapter'],
                f'{device_path}.adapter',
                ALLOWED_RELAY_ADAPTER_KEYS,
                issues,
            )
            _validate_required_entities(
                device['adapter'],
                f'{device_path}.adapter',
                ('enabled',),
                issues,
            )
        capabilities = device.get('capabilities')
        if isinstance(capabilities, dict):
            if capabilities.get('can_produce_w') is not False:
                issues.append(_issue(f'{device_path}.capabilities.can_produce_w', SEVERITY_ERROR, 'relay must define can_produce_w=false'))
            if capabilities.get('can_absorb_w') is not True:
                issues.append(_issue(f'{device_path}.capabilities.can_absorb_w', SEVERITY_ERROR, 'relay must define can_absorb_w=true'))


def _validate_packet_static_capabilities(device_path: str, capabilities: dict, issues: list[ConfigValidationIssue]) -> None:
    _validate_unknown_fields(
        capabilities,
        f'{device_path}.capabilities',
        PACKET_STATIC_CAPABILITY_FIELDS,
        issues,
    )
    for field in ('can_absorb_w', 'can_produce_w', 'supports_primary_regulation', 'supports_residual_regulation'):
        if field not in capabilities:
            issues.append(_issue(f'{device_path}.capabilities.{field}', SEVERITY_ERROR, 'missing required field'))
        elif type(capabilities[field]) is not bool:
            issues.append(_issue(f'{device_path}.capabilities.{field}', SEVERITY_ERROR, 'must be a boolean'))


def _validate_capabilities(device_path: str, capabilities: dict, issues: list[ConfigValidationIssue]) -> None:
    _validate_unknown_fields(
        capabilities,
        f'{device_path}.capabilities',
        ALLOWED_CAPABILITIES_KEYS,
        issues,
    )
    bool_fields = ('can_absorb_w', 'can_produce_w', 'uses_hard_off_lifecycle', 'supports_primary_regulation', 'supports_residual_regulation')
    entity_or_number_fields = ('min_absorb_w', 'max_absorb_w')
    if not device_path.endswith('.EV_CHARGER'):
        entity_or_number_fields = entity_or_number_fields + ('step_w',)

    for field in bool_fields:
        if field not in capabilities:
            issues.append(_issue(f'{device_path}.capabilities.{field}', SEVERITY_ERROR, 'missing required field'))
        elif type(capabilities[field]) is not bool:
            issues.append(_issue(f'{device_path}.capabilities.{field}', SEVERITY_ERROR, 'must be a boolean'))

    for field in entity_or_number_fields:
        _validate_entity_or_number(capabilities, f'{device_path}.capabilities.{field}', field, issues, min_value=1 if field == 'step_w' else None)

    if capabilities.get('can_produce_w') is True and 'max_produce_w' not in capabilities:
        issues.append(_issue(f'{device_path}.capabilities.max_produce_w', SEVERITY_ERROR, 'required when can_produce_w=true'))
    if 'max_produce_w' in capabilities:
        _validate_entity_or_number(capabilities, f'{device_path}.capabilities.max_produce_w', 'max_produce_w', issues, min_value=0)

    min_absorb = capabilities.get('min_absorb_w')
    max_absorb = capabilities.get('max_absorb_w')
    if _is_number(min_absorb) and _is_number(max_absorb) and float(max_absorb) < float(min_absorb):
        issues.append(_issue(f'{device_path}.capabilities.max_absorb_w', SEVERITY_ERROR, 'must be >= min_absorb_w'))
    if capabilities.get('can_absorb_w') is False and 'max_absorb_w' in capabilities:
        issues.append(_issue(f'{device_path}.capabilities.max_absorb_w', SEVERITY_WARNING, 'max_absorb_w is ignored when can_absorb_w=false'))
    max_produce = capabilities.get('max_produce_w')
    if capabilities.get('can_produce_w') is False and 'max_produce_w' in capabilities:
        issues.append(_issue(f'{device_path}.capabilities.max_produce_w', SEVERITY_WARNING, 'max_produce_w is ignored when can_produce_w=false'))


def _validate_ev_watt_limits_match_adapter_resolution(
    device_path: str,
    device: dict,
    issues: list[ConfigValidationIssue],
) -> None:
    capabilities = device.get('capabilities')
    adapter = device.get('adapter')
    if not isinstance(capabilities, dict) or not isinstance(adapter, dict):
        return

    numeric_values = (
        capabilities.get('min_absorb_w'),
        capabilities.get('max_absorb_w'),
        adapter.get('current_step_a'),
        adapter.get('phases'),
        adapter.get('voltage_v'),
    )
    for value in numeric_values:
        if not _is_number(value):
            return

    min_absorb_w = capabilities.get('min_absorb_w')
    max_absorb_w = capabilities.get('max_absorb_w')
    current_step_a = adapter.get('current_step_a')
    phases = adapter.get('phases')
    voltage_v = adapter.get('voltage_v')

    if float(min_absorb_w) <= 0:
        issues.append(_issue(f'{device_path}.capabilities.min_absorb_w', SEVERITY_ERROR, 'must be > 0'))
        return

    try:
        derived_min_current_a = ev_min_current_a_from_min_absorb_w(
            min_absorb_w,
            phases=phases,
            voltage_v=voltage_v,
            current_step_a=current_step_a,
        )
        derived_max_current_a = ev_max_current_a_from_max_absorb_w(
            max_absorb_w,
            phases=phases,
            voltage_v=voltage_v,
            current_step_a=current_step_a,
        )
    except ValueError as exc:
        issues.append(_issue(f'{device_path}.adapter', SEVERITY_ERROR, str(exc)))
        return

    if float(derived_min_current_a) > float(derived_max_current_a):
        issues.append(
            _issue(
                f'{device_path}.adapter.current_step_a',
                SEVERITY_ERROR,
                'derived_min_current_a must be <= derived_max_current_a',
            )
        )


def _validate_device_capability_semantics(ems: dict, devices: dict, issues: list[ConfigValidationIssue]) -> None:
    battery = devices.get('HOME_BATTERY')
    if isinstance(battery, dict):
        battery_caps = battery.get('capabilities')
        if isinstance(battery_caps, dict):
            if battery_caps.get('can_absorb_w') is False and battery_caps.get('can_produce_w') is False:
                issues.append(
                    _issue(
                        'ems.devices.HOME_BATTERY.capabilities',
                        SEVERITY_ERROR,
                        'HOME_BATTERY must define at least one enabled direction: can_absorb_w=true or can_produce_w=true',
                    )
                )

    global_config = ems.get('global_config')
    if not isinstance(global_config, dict):
        return


def _validate_role_constraints(role_constraints: dict, devices: dict, issues: list[ConfigValidationIssue]) -> None:
    for role_key, value in role_constraints.items():
        role_path = f'ems.role_constraints.{role_key}'
        if role_key not in ALLOWED_ROLE_KEYS:
            issues.append(_issue(role_path, SEVERITY_ERROR, 'unsupported role constraint key'))
            continue
        if not isinstance(value, dict):
            issues.append(_issue(role_path, SEVERITY_ERROR, 'must be a mapping'))
            continue

        if role_key == 'default':
            for field in value:
                _validate_entity_or_number(value, f'{role_path}.{field}', field, issues, min_value=0)
            continue

        for device_id, fields in value.items():
            device_path = f'{role_path}.{device_id}'
            if device_id not in devices:
                issues.append(_issue(device_path, SEVERITY_ERROR, 'references unknown device id'))
                continue
            if not isinstance(fields, dict):
                issues.append(_issue(device_path, SEVERITY_ERROR, 'must be a mapping'))
                continue
            for field in fields:
                _validate_entity_or_number(fields, f'{device_path}.{field}', field, issues, min_value=0)


def _validate_required_entities(section: dict, section_path: str, fields: tuple[str, ...], issues: list[ConfigValidationIssue]) -> None:
    for field in fields:
        if field not in section:
            issues.append(_issue(f'{section_path}.{field}', SEVERITY_ERROR, 'missing required field'))
            continue
        if not _is_valid_entity_id(section[field]):
            issues.append(_issue(f'{section_path}.{field}', SEVERITY_ERROR, 'must be a non-empty entity id string'))


def _validate_entity_or_bool(
    container: dict,
    path: str,
    field: str,
    issues: list[ConfigValidationIssue],
) -> None:
    if field not in container:
        issues.append(_issue(path, SEVERITY_ERROR, 'missing required field'))
        return
    value = container[field]
    if isinstance(value, bool) or _is_valid_entity_id(value):
        return
    issues.append(_issue(path, SEVERITY_ERROR, 'must be an entity id string or boolean constant'))


def _validate_entity_or_number(
    container: dict,
    path: str,
    field: str,
    issues: list[ConfigValidationIssue],
    min_value: Optional[Union[int, float]] = None,
    allowed_numbers: Optional[tuple[Union[int, float], ...]] = None,
) -> None:
    if field not in container:
        issues.append(_issue(path, SEVERITY_ERROR, 'missing required field'))
        return

    value = container[field]
    if _is_valid_entity_id(value):
        return
    if _is_number(value):
        numeric_value = float(value)
        if min_value is not None and numeric_value < float(min_value):
            issues.append(_issue(path, SEVERITY_ERROR, f'must be >= {min_value}'))
        if allowed_numbers is not None:
            allowed_values = []
            allowed_text_values = []
            for item in allowed_numbers:
                allowed_values.append(float(item))
                allowed_text_values.append(str(item))
            if numeric_value not in tuple(allowed_values):
                allowed_text = ', '.join(allowed_text_values)
                issues.append(_issue(path, SEVERITY_ERROR, f'must be one of: {allowed_text}'))
        return

    issues.append(_issue(path, SEVERITY_ERROR, 'must be an entity id string or numeric constant'))


def _validate_unknown_fields(
    section: dict,
    section_path: str,
    allowed_fields: frozenset[str],
    issues: list[ConfigValidationIssue],
) -> None:
    for field in section:
        if field not in allowed_fields:
            issues.append(_issue(f'{section_path}.{field}', SEVERITY_ERROR, f'Unknown config field: {section_path}.{field}'))


def _is_valid_entity_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped or '.' not in stripped:
        return False
    domain, object_id = stripped.split('.', 1)
    return bool(domain) and bool(object_id)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _issue(path: str, severity: Literal['ERROR', 'WARNING'], message: str) -> ConfigValidationIssue:
    return ConfigValidationIssue(path=path, severity=severity, message=message)


def _require_mapping_value(section: object, field: str) -> object:
    if not isinstance(section, dict):
        raise ValueError(f'Missing mapping section for field {field!r}')
    if field not in section:
        raise ValueError(f'Missing required field {field!r}')
    return section[field]


def _build_core_capabilities(
    device: object,
    read_entity: Optional[Callable[[str, object], object]],
    *,
    default_min_absorb_w: object = 0,
    default_max_absorb_w: object = 0,
    default_step_w: object = 1,
    default_max_produce_w: Optional[object] = None,
) -> CoreDeviceCapabilitiesConfig:
    return CoreDeviceCapabilitiesConfig(
        can_absorb_w=bool(_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'capabilities'), 'can_absorb_w'), read_entity, False)),
        can_produce_w=bool(_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'capabilities'), 'can_produce_w'), read_entity, False)),
        supports_primary_regulation=bool(_resolve_core_config_value(
            _require_mapping_value(_require_mapping_value(device, 'capabilities'), 'supports_primary_regulation'),
            read_entity,
            False,
        )),
        supports_residual_regulation=bool(_resolve_core_config_value(
            _require_mapping_value(_require_mapping_value(device, 'capabilities'), 'supports_residual_regulation'),
            read_entity,
            False,
        )),
        uses_hard_off_lifecycle=bool(_resolve_core_config_value(
            _require_mapping_value(_require_mapping_value(device, 'capabilities'), 'uses_hard_off_lifecycle'),
            read_entity,
            False,
        )),
        min_absorb_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'capabilities'), 'min_absorb_w'), read_entity, default_min_absorb_w),
        max_absorb_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'capabilities'), 'max_absorb_w'), read_entity, default_max_absorb_w),
        step_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'capabilities'), 'step_w'), read_entity, default_step_w)
        if 'step_w' in _require_mapping_value(device, 'capabilities')
        else default_step_w,
        max_produce_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'capabilities'), 'max_produce_w'), read_entity, default_max_produce_w)
        if 'max_produce_w' in _require_mapping_value(device, 'capabilities')
        else None,
    )


def _build_core_battery_device(
    device_id: str,
    device: object,
    read_entity: Optional[Callable[[str, object], object]],
    default_priority: object = 3,
) -> CoreBatteryDeviceConfig:
    return CoreBatteryDeviceConfig(
        device_id=device_id,
        kind=str(_resolve_core_config_value(_require_mapping_value(device, 'kind'), read_entity, 'BATTERY')),
        capabilities=_build_core_capabilities(
            device,
            read_entity,
            default_min_absorb_w=0,
            default_max_absorb_w=3700,
            default_step_w=50,
            default_max_produce_w=4600,
        ),
        policy=CoreBatteryPolicyConfig(
            priority=_resolve_core_config_value(
                _require_mapping_value(_require_mapping_value(device, 'policy'), 'priority'),
                read_entity,
                default_priority,
            ),
            surplus_allowed=bool(_resolve_core_config_value(_require_mapping_value(device, 'policy').get('surplus_allowed', False), read_entity, False)),
            surplus_dispatch_mode=str(_resolve_core_config_value(_require_mapping_value(device, 'policy').get('surplus_dispatch_mode', 'max_absorb'), read_entity, 'max_absorb')),
            default_min_absorb_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'policy'), 'default_min_absorb_w'), read_entity, 0.0)
            if 'default_min_absorb_w' in _require_mapping_value(device, 'policy')
            else None,
        ),
        guard=CoreBatteryGuardConfig(
            soc=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'guard'), 'soc'), read_entity, ''),
            min_cell_voltage_v=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'guard'), 'min_cell_voltage_v'), read_entity, ''),
            heartbeat=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'guard'), 'heartbeat'), read_entity, ''),
            protect_soc=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'guard'), 'protect_soc'), read_entity, 2),
            protect_soc_recovery_margin=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'guard'), 'protect_soc_recovery_margin'), read_entity, 1),
            protect_min_cell_voltage_v=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'guard'), 'protect_min_cell_voltage_v'), read_entity, 3.030),
            protect_min_absorb_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'guard'), 'protect_min_absorb_w'), read_entity, 0),
        ),
        adapter=CoreBatteryAdapterConfig(
            target_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'adapter'), 'target_w'), read_entity, ''),
            measured_power_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'adapter'), 'measured_power_w'), read_entity, ''),
        ),
    )


def _build_core_ev_device(device_id: str, device: object, read_entity: Optional[Callable[[str, object], object]]) -> CoreEvChargerDeviceConfig:
    policy_section = _require_mapping_value(device, 'policy')
    adapter_section = _require_mapping_value(device, 'adapter')
    return CoreEvChargerDeviceConfig(
        device_id=device_id,
        kind=str(_resolve_core_config_value(_require_mapping_value(device, 'kind'), read_entity, 'EV_CHARGER')),
        capabilities=_build_core_capabilities(
            device,
            read_entity,
            default_min_absorb_w=0,
            default_max_absorb_w=0,
            default_step_w=1,
            default_max_produce_w=None,
        ),
        policy=CoreEvPolicyConfig(
            priority=_resolve_core_config_value(_require_mapping_value(policy_section, 'priority'), read_entity, 3),
            surplus_allowed=_resolve_core_config_value(_require_mapping_value(policy_section, 'surplus_allowed'), read_entity, ''),
            surplus_dispatch_mode=str(_resolve_core_config_value(_require_mapping_value(policy_section, 'surplus_dispatch_mode'), read_entity, 'max_absorb')),
            force_on=_resolve_core_config_value(_require_mapping_value(policy_section, 'force_on'), read_entity, ''),
            low_pv_threshold_w=_resolve_core_config_value(_require_mapping_value(policy_section, 'low_pv_threshold_w'), read_entity, 1.6),
            hard_off_low_pv_cycles=_resolve_core_config_value(_require_mapping_value(policy_section, 'hard_off_low_pv_cycles'), read_entity, 2),
            hard_off_release_cycles=_resolve_core_config_value(_require_mapping_value(policy_section, 'hard_off_release_cycles'), read_entity, 2),
        ),
        adapter=CoreEvAdapterConfig(
            enabled=_resolve_core_config_value(_require_mapping_value(adapter_section, 'enabled'), read_entity, False),
            current_a=_resolve_core_config_value(_require_mapping_value(adapter_section, 'current_a'), read_entity, 0),
            current_step_a=_resolve_core_config_value(_require_mapping_value(adapter_section, 'current_step_a'), read_entity, 4),
            phases=_resolve_core_config_value(_require_mapping_value(adapter_section, 'phases'), read_entity, 1),
            voltage_v=_resolve_core_config_value(_require_mapping_value(adapter_section, 'voltage_v'), read_entity, 230),
        ),
    )


def _build_core_relay_device(device_id: str, device: object, read_entity: Optional[Callable[[str, object], object]]) -> CoreRelayDeviceConfig:
    return CoreRelayDeviceConfig(
        device_id=device_id,
        kind=str(_resolve_core_config_value(_require_mapping_value(device, 'kind'), read_entity, 'RELAY')),
        capabilities=_build_core_capabilities(
            device,
            read_entity,
            default_min_absorb_w=2.5 if device_id == 'RELAY1' else 5.0,
            default_max_absorb_w=2.5 if device_id == 'RELAY1' else 5.0,
            default_step_w=2.5 if device_id == 'RELAY1' else 5.0,
            default_max_produce_w=None,
        ),
        policy=CoreRelayPolicyConfig(
            priority=_resolve_core_config_value(
                _require_mapping_value(_require_mapping_value(device, 'policy'), 'priority'),
                read_entity,
                2 if device_id == 'RELAY1' else 1,
            ),
            surplus_allowed=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'policy'), 'surplus_allowed'), read_entity, ''),
            surplus_dispatch_mode=str(_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'policy'), 'surplus_dispatch_mode'), read_entity, 'fixed')),
            force_on=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'policy'), 'force_on'), read_entity, ''),
        ),
        adapter=CoreRelayAdapterConfig(
            enabled=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'adapter'), 'enabled'), read_entity, ''),
        ),
    )


def _build_core_haeo_config(haeo: object, read_entity: Optional[Callable[[str, object], object]]) -> Optional[CoreHaeoConfig]:
    if not isinstance(haeo, dict):
        return None
    return CoreHaeoConfig(
        battery_power_active=_resolve_core_config_value(_require_mapping_value(haeo, 'battery_power_active'), read_entity, ''),
        ev_power_active=_resolve_core_config_value(_require_mapping_value(haeo, 'ev_power_active'), read_entity, ''),
        battery_fresh_source=_resolve_core_config_value(_require_mapping_value(haeo, 'battery_fresh_source'), read_entity, ''),
        ev_fresh_source=_resolve_core_config_value(_require_mapping_value(haeo, 'ev_fresh_source'), read_entity, ''),
    )


def _build_core_role_constraints(role_constraints: object, read_entity: Optional[Callable[[str, object], object]]) -> CoreRoleConstraintsConfig:
    if not isinstance(role_constraints, dict):
        return CoreRoleConstraintsConfig(default={}, by_role={})

    default_constraints = {}
    raw_default = role_constraints.get('default', {})
    if isinstance(raw_default, dict):
        for key, value in raw_default.items():
            default_constraints[str(key)] = _resolve_core_config_value(value, read_entity, value)

    by_role = {}
    for role_key, role_value in role_constraints.items():
        if role_key == 'default' or not isinstance(role_value, dict):
            continue
        role_devices = {}
        for device_id, device_fields in role_value.items():
            if not isinstance(device_fields, dict):
                continue
            copied_fields = {}
            for field_name, field_value in device_fields.items():
                copied_fields[str(field_name)] = _resolve_core_config_value(field_value, read_entity, field_value)
            role_devices[str(device_id)] = copied_fields
        by_role[str(role_key)] = role_devices

    return CoreRoleConstraintsConfig(
        default=default_constraints,
        by_role=by_role,
    )


def _alias(runtime_key: str, config_path: str, value: object, unit_transform: str = 'identity') -> RuntimeAlias:
    return RuntimeAlias(
        runtime_key=runtime_key,
        config_path=config_path,
        value='' if value is None else str(value),
        unit_transform=unit_transform,
    )


def _read_grouped_value(
    aliases: dict[str, RuntimeAlias],
    read_entity: Callable[[str, object], object],
    runtime_key: str,
    default: object,
) -> object:
    alias = aliases.get(runtime_key)
    if alias is None:
        return default
    raw_value = read_entity(alias.value, default)
    if raw_value in (None, 'unknown', 'unavailable', 'none', ''):
        return default
    return raw_value


def _resolve_core_config_value(
    value: object,
    read_entity: Optional[Callable[[str, object], object]],
    default: object,
) -> object:
    if value in (None, 'unknown', 'unavailable', 'none', ''):
        return default
    if isinstance(value, DynamicConfigRef):
        if read_entity is None:
            return value.default
        entity_value = read_entity(value.entity_id, value.default)
        if entity_value in (None, 'unknown', 'unavailable', 'none', ''):
            return value.default
        return entity_value
    if _is_valid_entity_id(value):
        if read_entity is None:
            return value
        entity_value = read_entity(value, default)
        if entity_value in (None, 'unknown', 'unavailable', 'none', ''):
            return default
        return entity_value
    return value
