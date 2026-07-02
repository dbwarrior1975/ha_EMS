from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from types import MappingProxyType
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
from ems_core.domain.ev_power import (
    ev_current_a_to_power_w,
    ev_max_current_a_from_max_absorb_w,
    ev_max_power_w,
    ev_min_current_a_from_min_absorb_w,
    ev_min_power_w,
    ev_power_step_w,
)


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
ALLOWED_DEVICE_KEYS = frozenset(('kind', 'capabilities', 'policy', 'adapter', 'guard'))
ALLOWED_CAPABILITIES_KEYS = frozenset(
    (
        'can_absorb_w',
        'can_produce_w',
        'min_absorb_w',
        'max_absorb_w',
        'step_w',
        'max_produce_w',
    )
)
ALLOWED_BATTERY_POLICY_KEYS = frozenset(('priority', 'default_min_absorb_w'))
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
        'force_on',
        'low_pv_threshold_w',
        'hard_off_low_pv_cycles',
        'hard_off_release_cycles',
    )
)
ALLOWED_EV_ADAPTER_KEYS = frozenset(('enabled', 'current_a', 'current_step_a', 'phases', 'voltage_v'))
ALLOWED_RELAY_POLICY_KEYS = frozenset(('priority', 'surplus_allowed', 'force_on'))
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

    def __post_init__(self):
        errors = []
        warnings = []
        for issue in self.issues:
            if issue.severity == SEVERITY_ERROR:
                errors.append(issue)
            if issue.severity == SEVERITY_WARNING:
                warnings.append(issue)
        if self.errors is None:
            self.errors = tuple(errors)
        if self.warnings is None:
            self.warnings = tuple(warnings)


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
        self.adjustable_surplus_load = self.global_config.adjustable_surplus_load
        self.adjustable_primary_load = self.global_config.adjustable_primary_load
        self.adjustable_surplus_activation = self.global_config.adjustable_surplus_activation_w
        self.surplus_freeze_s = self.global_config.surplus_freeze_s
        self.adjustable_surplus_load_priority = self.device_policy_value('HOME_BATTERY', 'priority', 0)

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
        values = self._device_values(device_id)
        if not isinstance(values, dict):
            return default
        section_values = values.get(str(section))
        if not isinstance(section_values, dict):
            return default
        return section_values.get(str(field), default)

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


def load_and_validate_grouped_ems_config(path: Union[str, Path]) -> tuple[dict, ConfigValidationResult]:
    config = load_grouped_ems_config(path)
    return config, validate_grouped_ems_config(config)


def validate_grouped_ems_config(config: dict) -> ConfigValidationResult:
    issues: list[ConfigValidationIssue] = []

    ems = config.get('ems')
    if not isinstance(ems, dict):
        issues.append(_issue('ems', SEVERITY_ERROR, 'missing or not a mapping'))
        return _validation_result(False, issues)

    _validate_unknown_fields(
        ems,
        'ems',
        frozenset(tuple(ALLOWED_EMS_SECTION_KEYS) + tuple(REJECTED_TOP_LEVEL_SECTIONS)),
        issues,
    )
    _validate_rejected_top_level_sections(ems, issues)

    for section in REQUIRED_TOP_LEVEL_SECTIONS:
        if section not in ems:
            issues.append(_issue(f'ems.{section}', SEVERITY_ERROR, 'missing required section'))
        elif not isinstance(ems.get(section), dict):
            issues.append(_issue(f'ems.{section}', SEVERITY_ERROR, 'must be a mapping'))

    for section in OPTIONAL_TOP_LEVEL_SECTIONS:
        if section in ems and not isinstance(ems.get(section), dict):
            issues.append(_issue(f'ems.{section}', SEVERITY_ERROR, 'must be a mapping'))

    devices = ems.get('devices', {})
    if isinstance(devices, dict):
        _validate_devices(devices, issues)
        _validate_device_capability_semantics(ems, devices, issues)
    else:
        devices = {}

    if isinstance(ems.get('profiles'), dict):
        _validate_required_entities(
            ems['profiles'],
            'ems.profiles',
            ('control', 'goal', 'forecast', 'guard'),
            issues,
        )

    if isinstance(ems.get('global_config'), dict):
        _validate_required_entities(
            ems['global_config'],
            'ems.global_config',
            ('deadband_w', 'ramp_w', 'strict_limit_w', 'surplus_freeze_s', 'haeo_stale_timeout_s'),
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

    if isinstance(ems.get('state'), dict):
        _validate_required_entities(
            ems['state'],
            'ems.state',
            ('surplus_freeze_until', 'active_surplus_devices', 'previous_device_state'),
            issues,
        )

    if isinstance(ems.get('haeo'), dict):
        _validate_required_entities(
            ems['haeo'],
            'ems.haeo',
            ('battery_power_active', 'ev_power_active', 'battery_fresh_source', 'ev_fresh_source'),
            issues,
        )

    if isinstance(ems.get('role_constraints'), dict):
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
        _alias('deadband_w', 'ems.global_config.deadband_w', global_config.get('deadband_w')),
        _alias('ramp_max_w', 'ems.global_config.ramp_w', global_config.get('ramp_w')),
        _alias('strict_limits_max_w', 'ems.global_config.strict_limit_w', global_config.get('strict_limit_w')),
        _alias('surplus_freeze_s', 'ems.global_config.surplus_freeze_s', global_config.get('surplus_freeze_s')),
        _alias('haeo_stale_timeout_s', 'ems.global_config.haeo_stale_timeout_s', global_config.get('haeo_stale_timeout_s')),
        _alias('nz_battery_floor_default_w', 'ems.global_config.nz_battery_floor_default_w', global_config.get('nz_battery_floor_default_w')),
        _alias('nz_battery_floor_ev_active_w', 'ems.global_config.nz_battery_floor_ev_active_w', global_config.get('nz_battery_floor_ev_active_w')),
        _alias('adjustable_surplus_load', 'ems.global_config.adjustable_surplus_load', global_config.get('adjustable_surplus_load')),
        _alias('adjustable_primary_load', 'ems.global_config.adjustable_primary_load', global_config.get('adjustable_primary_load')),
        _alias('adjustable_surplus_activation', 'ems.global_config.adjustable_surplus_activation_w', global_config.get('adjustable_surplus_activation_w')),
    ]

    home_battery = devices.get('HOME_BATTERY', {})
    battery_guard = home_battery.get('guard', {}) if isinstance(home_battery, dict) else {}
    battery_capabilities = home_battery.get('capabilities', {}) if isinstance(home_battery, dict) else {}
    battery_policy = home_battery.get('policy', {}) if isinstance(home_battery, dict) else {}
    battery_adapter = home_battery.get('adapter', {}) if isinstance(home_battery, dict) else {}
    aliases.extend(
        [
            _alias('max_solar_charge_w', 'ems.devices.HOME_BATTERY.capabilities.max_absorb_w', battery_capabilities.get('max_absorb_w')),
            _alias('max_battery_discharge_w', 'ems.devices.HOME_BATTERY.capabilities.max_produce_w', battery_capabilities.get('max_produce_w')),
            _alias('adjustable_surplus_load_priority', 'ems.devices.HOME_BATTERY.policy.priority', battery_policy.get('priority')),
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


def _resolved_first_ev_priority(materialized_config: dict) -> object:
    devices = (((materialized_config.get('ems') or {}).get('devices')) or {})
    for device in devices.values():
        if not isinstance(device, dict):
            continue
        if str(device.get('kind') or '') != 'EV_CHARGER':
            continue
        policy = device.get('policy') or {}
        return policy.get('priority', 3)
    return 3


def _apply_dynamic_default_overrides(
    materialized_config: dict,
    grouped_config_plan: dict,
) -> dict:
    plan_devices = (((grouped_config_plan.get('ems') or {}).get('devices')) or {})
    materialized_devices = (((materialized_config.get('ems') or {}).get('devices')) or {})
    battery_plan = (plan_devices.get('HOME_BATTERY') or {}).get('policy', {})
    battery_ref = battery_plan.get('priority')
    if isinstance(battery_ref, DynamicConfigRef):
        battery_policy = (materialized_devices.get('HOME_BATTERY') or {}).get('policy', {})
        if battery_policy.get('priority') == battery_ref.default:
            battery_policy['priority'] = _resolved_first_ev_priority(materialized_config)
    return materialized_config


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
    ems = config.get('ems', {})
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
                'adjustable_surplus_load': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'adjustable_surplus_load'), 'ems.global_config.adjustable_surplus_load', 'HOME_BATTERY'),
                'adjustable_primary_load': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'adjustable_primary_load'), 'ems.global_config.adjustable_primary_load', ''),
                'adjustable_surplus_activation_w': _compile_dynamic_value(_require_mapping_value(ems.get('global_config'), 'adjustable_surplus_activation_w'), 'ems.global_config.adjustable_surplus_activation_w', 0.0),
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
    return CompiledEMSPlan(
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
    )


def materialize_core_config_from_plan(
    plan: CompiledCoreConfigPlan,
    read_entity: Callable[[str, object], object],
    metrics: Optional[dict[str, int]] = None,
) -> CoreConfig:
    return _materialize_core_config_direct(plan, read_entity, metrics=metrics)


def _materialize_runtime_mapping(value: object, read_entity: Callable[[str, object], object]) -> object:
    if isinstance(value, DynamicConfigRef):
        return _resolve_core_config_value(value, read_entity, value.default)
    if isinstance(value, MappingProxyType):
        materialized = {}
        for key, item in value.items():
            materialized[str(key)] = _materialize_runtime_mapping(item, read_entity)
        return materialized
    if isinstance(value, dict):
        materialized = {}
        for key, item in value.items():
            materialized[str(key)] = _materialize_runtime_mapping(item, read_entity)
        return materialized
    if isinstance(value, tuple):
        materialized = []
        for item in value:
            materialized.append(_materialize_runtime_mapping(item, read_entity))
        return tuple(materialized)
    return value


def _materialize_device_snapshot_values(
    device_plan: StaticDevicePlan,
    read_entity: Callable[[str, object], object],
) -> dict:
    materialized = {
        'kind': str(device_plan.kind),
        'capabilities': _materialize_runtime_mapping(device_plan.static_capabilities, read_entity),
        'adapter': _materialize_runtime_mapping(device_plan.static_adapter, read_entity),
        'policy': _materialize_runtime_mapping(device_plan.static_policy, read_entity),
    }
    if device_plan.static_guard is not None:
        materialized['guard'] = _materialize_runtime_mapping(device_plan.static_guard, read_entity)
    return materialized


def _resolve_home_battery_priority_from_snapshot(
    battery_plan: StaticDevicePlan,
    battery_values: dict,
    device_values: dict[str, dict],
) -> object:
    policy_priority = (
        battery_plan.grouped_device_plan.get('policy', {}).get('priority')
        if hasattr(battery_plan.grouped_device_plan, 'get')
        else None
    )
    resolved_priority = battery_values.get('policy', {}).get('priority', 3)
    if isinstance(policy_priority, DynamicConfigRef) and resolved_priority == policy_priority.default:
        for device in device_values.values():
            if str(device.get('kind', '')) == 'EV_CHARGER':
                return device.get('policy', {}).get('priority', 3)
    return resolved_priority


def build_dynamic_runtime_snapshot(
    compiled_plan: CompiledEMSPlan,
    read_entity: Callable[[str, object], object],
    metrics: Optional[dict[str, int]] = None,
) -> DynamicRuntimeSnapshot:
    materialize_started_ts = time.time()

    profiles_started_ts = time.time()
    profiles = _materialize_runtime_mapping(compiled_plan.profiles, read_entity)
    global_config = _materialize_runtime_mapping(compiled_plan.global_config, read_entity)
    runtime = _materialize_runtime_mapping(compiled_plan.runtime, read_entity)
    state = _materialize_runtime_mapping(compiled_plan.state, read_entity)
    _record_core_config_metric(metrics, 'policy_engine_core_config_profiles_global_runtime_state_ms', profiles_started_ts)

    devices_started_ts = time.time()
    device_values = {}
    for device_id, device_plan in compiled_plan.devices.items():
        device_values[str(device_id)] = _materialize_device_snapshot_values(device_plan, read_entity)
    _record_core_config_metric(metrics, 'policy_engine_core_config_devices_ms', devices_started_ts)

    home_battery_started_ts = time.time()
    home_battery_values = _materialize_device_snapshot_values(compiled_plan.home_battery, read_entity)
    home_battery_values.setdefault('policy', {})
    home_battery_values['policy']['priority'] = _resolve_home_battery_priority_from_snapshot(
        compiled_plan.home_battery,
        home_battery_values,
        device_values,
    )
    _record_core_config_metric(metrics, 'policy_engine_core_config_home_battery_ms', home_battery_started_ts)

    haeo_started_ts = time.time()
    haeo_values = None if compiled_plan.haeo is None else _materialize_runtime_mapping(compiled_plan.haeo, read_entity)
    _record_core_config_metric(metrics, 'policy_engine_core_config_haeo_ms', haeo_started_ts)

    role_constraints_started_ts = time.time()
    role_constraint_values = _materialize_runtime_mapping(compiled_plan.role_constraints, read_entity)
    _record_core_config_metric(metrics, 'policy_engine_core_config_role_constraints_ms', role_constraints_started_ts)

    derived_fields_started_ts = time.time()
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
) -> CoreConfigView:
    snapshot_started_ts = time.time()
    snapshot = build_dynamic_runtime_snapshot(compiled_plan, read_entity, metrics=metrics)
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
    resolved_config = _apply_dynamic_default_overrides(resolved_config, plan.grouped_config_plan)
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
        adjustable_surplus_load=values['adjustable_surplus_load'],
        adjustable_primary_load=values['adjustable_primary_load'],
        adjustable_surplus_activation_w=values['adjustable_surplus_activation_w'],
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
        min_absorb_w=caps['min_absorb_w'],
        max_absorb_w=caps['max_absorb_w'],
        step_w=caps['step_w'],
        max_produce_w=caps.get('max_produce_w'),
    )


def _build_view_battery_device(plan: StaticDevicePlan, values: dict) -> CoreBatteryDeviceConfig:
    return CoreBatteryDeviceConfig(
        device_id=plan.device_id,
        kind=str(values.get('kind', plan.kind)),
        capabilities=_build_view_capabilities(values),
        policy=CoreBatteryPolicyConfig(
            priority=values['policy']['priority'],
            default_min_absorb_w=values['policy'].get('default_min_absorb_w'),
        ),
        guard=CoreBatteryGuardConfig(
            soc=values['guard']['soc'],
            min_cell_voltage_v=values['guard']['min_cell_voltage_v'],
            heartbeat=values['guard']['heartbeat'],
            protect_soc=values['guard']['protect_soc'],
            protect_soc_recovery_margin=values['guard']['protect_soc_recovery_margin'],
            protect_min_cell_voltage_v=values['guard']['protect_min_cell_voltage_v'],
            protect_min_absorb_w=values['guard']['protect_min_absorb_w'],
        ),
        adapter=CoreBatteryAdapterConfig(
            target_w=values['adapter']['target_w'],
            measured_power_w=values['adapter']['measured_power_w'],
        ),
    )


def _build_view_ev_device(plan: StaticDevicePlan, values: dict) -> CoreEvChargerDeviceConfig:
    return CoreEvChargerDeviceConfig(
        device_id=plan.device_id,
        kind=str(values.get('kind', plan.kind)),
        capabilities=_build_view_capabilities(values),
        policy=CoreEvPolicyConfig(
            priority=values['policy']['priority'],
            surplus_allowed=values['policy']['surplus_allowed'],
            force_on=values['policy']['force_on'],
            low_pv_threshold_w=values['policy']['low_pv_threshold_w'],
            hard_off_low_pv_cycles=values['policy']['hard_off_low_pv_cycles'],
            hard_off_release_cycles=values['policy']['hard_off_release_cycles'],
        ),
        adapter=CoreEvAdapterConfig(
            enabled=values['adapter']['enabled'],
            current_a=values['adapter']['current_a'],
            current_step_a=values['adapter']['current_step_a'],
            phases=values['adapter']['phases'],
            voltage_v=values['adapter']['voltage_v'],
        ),
    )


def _build_view_relay_device(plan: StaticDevicePlan, values: dict) -> CoreRelayDeviceConfig:
    return CoreRelayDeviceConfig(
        device_id=plan.device_id,
        kind=str(values.get('kind', plan.kind)),
        capabilities=_build_view_capabilities(values),
        policy=CoreRelayPolicyConfig(
            priority=values['policy']['priority'],
            surplus_allowed=values['policy']['surplus_allowed'],
            force_on=values['policy']['force_on'],
        ),
        adapter=CoreRelayAdapterConfig(enabled=values['adapter']['enabled']),
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
        adjustable_surplus_load=_resolve_core_config_value(_require_mapping_value(global_config, 'adjustable_surplus_load'), read_entity, 'HOME_BATTERY'),
        adjustable_primary_load=_resolve_core_config_value(_require_mapping_value(global_config, 'adjustable_primary_load'), read_entity, ''),
        adjustable_surplus_activation_w=_resolve_core_config_value(_require_mapping_value(global_config, 'adjustable_surplus_activation_w'), read_entity, 0.0),
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
    resolved_priority = _resolve_core_config_value(policy, read_entity, 3)
    if isinstance(policy, DynamicConfigRef) and resolved_priority == policy.default:
        return _first_ev_priority(core_devices)
    return resolved_priority


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
        default_priority=_first_ev_priority(core_devices),
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
            adjustable_surplus_load=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'adjustable_surplus_load'), read_entity, 'HOME_BATTERY'),
            adjustable_primary_load=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'adjustable_primary_load'), read_entity, ''),
            adjustable_surplus_activation_w=_resolve_core_config_value(_require_mapping_value(ems.get('global_config'), 'adjustable_surplus_activation_w'), read_entity, 0.0),
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
    if core_config.adjustable_surplus_load is None:
        core_config.adjustable_surplus_load = core_config.global_config.adjustable_surplus_load
    if core_config.adjustable_primary_load is None:
        core_config.adjustable_primary_load = core_config.global_config.adjustable_primary_load
    if core_config.adjustable_surplus_activation is None:
        core_config.adjustable_surplus_activation = core_config.global_config.adjustable_surplus_activation_w
    if core_config.surplus_freeze_s is None:
        core_config.surplus_freeze_s = core_config.global_config.surplus_freeze_s
    if core_config.adjustable_surplus_load_priority is None:
        core_config.adjustable_surplus_load_priority = core_config.home_battery.policy.priority
    return core_config


def _first_ev_priority(core_devices: dict[str, object]) -> object:
    for device in core_devices.values():
        if str(getattr(device, 'kind', '')) == 'EV_CHARGER':
            return getattr(getattr(device, 'policy', None), 'priority', 3)
    return 3


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


def _validate_devices(devices: dict, issues: list[ConfigValidationIssue]) -> None:
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
        _validate_device(device_id, device, expected_kind, issues)

    if len(battery_ids) != 1 or battery_ids[0] != 'HOME_BATTERY':
        issues.append(_issue('ems.devices', SEVERITY_ERROR, 'phase-1 flexible loader supports exactly one battery device id: HOME_BATTERY'))


def _validate_device(device_id: str, device: dict, expected_kind: Optional[str], issues: list[ConfigValidationIssue]) -> None:
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
    else:
        _validate_capabilities(device_path, capabilities, issues)

    required_sections = ['capabilities', 'policy', 'adapter']
    if device_id == 'HOME_BATTERY':
        required_sections.append('guard')
    for section in required_sections:
        if section not in device:
            issues.append(_issue(f'{device_path}.{section}', SEVERITY_ERROR, 'missing required section'))
        elif not isinstance(device.get(section), dict):
            issues.append(_issue(f'{device_path}.{section}', SEVERITY_ERROR, 'must be a mapping'))

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
            ('priority', 'surplus_allowed', 'force_on', 'low_pv_threshold_w', 'hard_off_low_pv_cycles', 'hard_off_release_cycles'),
            issues,
        )

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
                ('priority', 'surplus_allowed', 'force_on'),
                issues,
            )
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


def _validate_capabilities(device_path: str, capabilities: dict, issues: list[ConfigValidationIssue]) -> None:
    _validate_unknown_fields(
        capabilities,
        f'{device_path}.capabilities',
        ALLOWED_CAPABILITIES_KEYS,
        issues,
    )
    bool_fields = ('can_absorb_w', 'can_produce_w')
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

    adjustable_surplus_load = global_config.get('adjustable_surplus_load')
    if isinstance(adjustable_surplus_load, str) and adjustable_surplus_load in devices:
        adjustable_caps = devices.get(adjustable_surplus_load, {}).get('capabilities')
        if isinstance(adjustable_caps, dict) and adjustable_caps.get('can_absorb_w') is False:
            issues.append(
                _issue(
                    'ems.global_config.adjustable_surplus_load',
                    SEVERITY_ERROR,
                    'adjustable_surplus_load must reference a device with can_absorb_w=true',
                )
            )


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
