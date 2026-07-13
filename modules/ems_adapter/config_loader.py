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
from ems_adapter.direct_runtime import (
    RUNTIME_SCHEMA_VERSION,
    StaticTopology,
    build_static_topology,
)

try:
    pyscript_executor
except NameError:
    def pyscript_executor(func):
        return func


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
REQUIRED_DEVICE_IDS = ()
EXPECTED_DEVICE_KINDS = {}
ALLOWED_ROLE_KEYS = {
    'default',
    'EV_PRIMARY',
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
        'primary_consuming_device_ids',
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
    'primary_consuming_device_ids': (),
}
PACKET_DEFAULT_RUNTIME = {
    'grid_power_w': 0.0,
    'quarter_energy_balance_kwh': 0.0,
    'pv_power_w': 0.0,
}
PACKET_DEFAULT_STATE = {
    'surplus_freeze_until': '',
    'active_surplus_devices': (),
}
PACKET_DEFAULT_HAEO = {
    'devices': {},
}

PACKET_STATIC_CAPABILITY_FIELDS = frozenset(('can_absorb_w', 'can_produce_w', 'supports_primary_consuming_regulation', 'supports_producing_regulation'))
PACKET_RUNTIME_CAPABILITY_FIELDS_BY_KIND = {
    'BATTERY': {
        'uses_hard_off_lifecycle': False,
        'supports_primary_consuming_regulation': True,
        'supports_producing_regulation': True,
        'min_produce_w': 0.0,
        'min_absorb_w': 0.0,
        'max_absorb_w': 0.0,
        'max_produce_w': 0.0,
        'step_w': 1.0,
    },
    'EV_CHARGER': {
        'uses_hard_off_lifecycle': True,
        'supports_primary_consuming_regulation': True,
        'supports_producing_regulation': False,
        'min_produce_w': 0.0,
        'min_absorb_w': 0.0,
        'max_absorb_w': 0.0,
        'max_produce_w': 0.0,
        'step_w': 1.0,
    },
    'RELAY': {
        'uses_hard_off_lifecycle': False,
        'supports_primary_consuming_regulation': False,
        'supports_producing_regulation': False,
        'min_produce_w': 0.0,
        'min_absorb_w': 0.0,
        'max_absorb_w': 0.0,
        'max_produce_w': 0.0,
        'step_w': 1.0,
    },
}
PACKET_RUNTIME_POLICY_FIELDS_BY_KIND = {
    'BATTERY': {
        'priority': 0,
        'producing_priority': 0,
        'surplus_allowed': False,
        'surplus_dispatch_mode': 'max_absorb',
        'default_min_absorb_w': 0.0,
    },
    'EV_CHARGER': {
        'priority': 0,
        'producing_priority': 0,
        'surplus_allowed': False,
        'surplus_dispatch_mode': 'max_absorb',
        'force_on': False,
        'low_pv_threshold_w': 1600.0,
        'hard_off_low_pv_cycles': 15,
        'hard_off_release_cycles': 100,
    },
    'RELAY': {
        'priority': 0,
        'producing_priority': 0,
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
        'min_produce_w',
        'max_produce_w',
        'uses_hard_off_lifecycle',
        'supports_primary_consuming_regulation',
        'supports_producing_regulation',
    )
)
ALLOWED_BATTERY_POLICY_KEYS = frozenset(('priority', 'producing_priority', 'surplus_allowed', 'surplus_dispatch_mode', 'default_min_absorb_w'))
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
ALLOWED_BATTERY_ADAPTER_KEYS = frozenset(('target_w',))
ALLOWED_EV_POLICY_KEYS = frozenset(
    (
        'priority',
        'producing_priority',
        'surplus_allowed',
        'surplus_dispatch_mode',
        'force_on',
        'low_pv_threshold_w',
        'hard_off_low_pv_cycles',
        'hard_off_release_cycles',
    )
)
ALLOWED_EV_ADAPTER_KEYS = frozenset(('enabled', 'current_a', 'current_step_a', 'phases', 'voltage_v'))
ALLOWED_RELAY_POLICY_KEYS = frozenset(('priority', 'producing_priority', 'surplus_allowed', 'surplus_dispatch_mode', 'force_on'))
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
    haeo: Optional[dict]
    role_constraints: dict
    grouped_config_plan: dict
    static_topology: Optional[StaticTopology] = None






_MATERIALIZE_CACHE_MISS = object()
_NO_DYNAMIC_SNAPSHOT_VALUE = object()


@pyscript_executor
def load_grouped_ems_config(path: Union[str, Path]) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f'Grouped EMS config not found: {config_path}')

    import yaml

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

    if runtime_packet_mode and 'state' in ems:
        issues.append(
            _issue(
                'ems.state',
                SEVERITY_ERROR,
                'runtime-packet mode owns state entity mappings via '
                'sensor.ems_policy_config_runtime attribute entity_registry; '
                'remove static ems.state from EMS_config.yaml',
            )
        )
    if isinstance(ems.get('state'), dict) and not runtime_packet_mode:
        _validate_required_entities(
            ems['state'],
            'ems.state',
            ('surplus_freeze_until', 'active_surplus_devices'),
            issues,
        )

    if isinstance(ems.get('haeo'), dict) and not runtime_packet_mode:
        haeo_devices = ems['haeo'].get('devices')
        if not isinstance(haeo_devices, dict):
            issues.append(_issue('ems.haeo.devices', SEVERITY_ERROR, 'missing or not a mapping'))
        else:
            for device_id, mapping in haeo_devices.items():
                path = f'ems.haeo.devices.{device_id}'
                if str(device_id) not in devices:
                    issues.append(_issue(path, SEVERITY_ERROR, 'references unknown device id'))
                    continue
                if not isinstance(mapping, dict):
                    issues.append(_issue(path, SEVERITY_ERROR, 'must be a mapping'))
                    continue
                _validate_required_entities(mapping, path, ('power_active', 'fresh_source'), issues)

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
        'supports_primary_consuming_regulation': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'supports_primary_consuming_regulation'),
            f'{device_path}.capabilities.supports_primary_consuming_regulation',
            False,
        ),
        'supports_producing_regulation': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'supports_producing_regulation'),
            f'{device_path}.capabilities.supports_producing_regulation',
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
        'min_produce_w': _compile_dynamic_value(
            _require_mapping_value(capabilities, 'min_produce_w'),
            f'{device_path}.capabilities.min_produce_w',
            0.0,
        ) if 'min_produce_w' in capabilities else 0.0,
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
            'producing_priority': _compile_dynamic_value(
                _require_mapping_value(policy, 'producing_priority'),
                f'{device_path}.policy.producing_priority',
                0,
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
            'producing_priority': _compile_dynamic_value(_require_mapping_value(policy, 'producing_priority'), f'{device_path}.policy.producing_priority', 0),
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
            'producing_priority': _compile_dynamic_value(_require_mapping_value(policy, 'producing_priority'), f'{device_path}.policy.producing_priority', 0),
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
    raw_devices = haeo.get('devices', {})
    if not isinstance(raw_devices, dict):
        return {'devices': {}}
    devices = {}
    for device_id, raw_mapping in raw_devices.items():
        if not isinstance(raw_mapping, dict):
            continue
        path = f'ems.haeo.devices.{device_id}'
        devices[str(device_id)] = {
            'power_active': _compile_dynamic_value(_require_mapping_value(raw_mapping, 'power_active'), f'{path}.power_active', ''),
            'fresh_source': _compile_dynamic_value(_require_mapping_value(raw_mapping, 'fresh_source'), f'{path}.fresh_source', ''),
        }
    return {'devices': devices}


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




def _compile_primary_consuming_device_ids(items):
    compiled_items = []
    for index, item in enumerate(items or ()):
        compiled_items.append(
            _compile_dynamic_value(
                item,
                f'ems.global_config.primary_consuming_device_ids[{index}]',
                '',
            )
        )
    return tuple(compiled_items)


def _materialize_primary_consuming_device_ids(items, read_entity):
    materialized = _materialize_dynamic_value(items, read_entity)
    ordered = []
    for item in materialized or ():
        device_id = str(item or '')
        if device_id and device_id not in ordered:
            ordered.append(device_id)
    return tuple(ordered)


def compile_core_config_plan_from_grouped_config(config: dict) -> CompiledEMSPlan:
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
                'primary_consuming_device_ids': _compile_primary_consuming_device_ids(
                    _require_mapping_value(ems.get('global_config'), 'primary_consuming_device_ids')
                ),
            },
            'runtime': {
                'grid_power_w': _compile_dynamic_value(_require_mapping_value(ems.get('runtime'), 'grid_power_w'), 'ems.runtime.grid_power_w', 0),
                'quarter_energy_balance_kwh': _compile_dynamic_value(_require_mapping_value(ems.get('runtime'), 'quarter_energy_balance_kwh'), 'ems.runtime.quarter_energy_balance_kwh', 0),
                'pv_power_w': _compile_dynamic_value(_require_mapping_value(ems.get('runtime'), 'pv_power_w'), 'ems.runtime.pv_power_w', 0),
            },
            'state': {
                'surplus_freeze_until': _compile_dynamic_value(_require_mapping_value(ems.get('state'), 'surplus_freeze_until'), 'ems.state.surplus_freeze_until', ''),
                'active_surplus_devices': _compile_dynamic_value(_require_mapping_value(ems.get('state'), 'active_surplus_devices'), 'ems.state.active_surplus_devices', ''),
            },
            'devices': _compile_core_devices_plan(devices),
            'haeo': _compile_core_haeo_plan(ems.get('haeo')),
            'role_constraints': _compile_core_role_constraints_plan(role_constraints),
        }
    }
    compiled_devices = _compile_core_devices_plan(devices)
    static_devices = {}
    for device_id, device_plan in compiled_devices.items():
        static_devices[str(device_id)] = _build_static_device_plan(device_plan)
    compiled_plan = CompiledEMSPlan(
        profiles=dict(_require_mapping_value(compiled['ems'], 'profiles')),
        policy_engine=dict(_require_mapping_value(compiled['ems'], 'policy_engine')),
        global_config=dict(_require_mapping_value(compiled['ems'], 'global_config')),
        runtime=dict(_require_mapping_value(compiled['ems'], 'runtime')),
        state=dict(_require_mapping_value(compiled['ems'], 'state')),
        devices=static_devices,
        haeo=dict(compiled['ems']['haeo']) if isinstance(compiled['ems'].get('haeo'), dict) else None,
        role_constraints=dict(_require_mapping_value(compiled['ems'], 'role_constraints')),
        grouped_config_plan=compiled,
        static_topology=static_topology,
    )
    return compiled_plan


def materialize_core_config_from_plan(
    plan: CompiledEMSPlan,
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


def _materialize_core_config_via_resolved_config_for_tests(
    plan: CompiledEMSPlan,
    read_entity: Callable[[str, object], object],
) -> CoreConfig:
    resolved_config = _materialize_dynamic_value(plan.grouped_config_plan, read_entity)
    return _build_core_config_from_grouped_value_config(resolved_config)


def _materialize_core_config_direct(
    plan: CompiledEMSPlan,
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
    _record_core_config_metric(metrics, 'policy_engine_core_config_materialize_total_ms', materialize_started_ts)
    return core_config


def _record_core_config_metric(metrics: Optional[dict[str, int]], key: str, started_ts: float) -> None:
    if metrics is None:
        return
    metrics[key] = max(0, int(round((time.time() - started_ts) * 1000.0)))


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
        primary_consuming_device_ids=_materialize_primary_consuming_device_ids(
            _require_mapping_value(global_config, 'primary_consuming_device_ids'),
            read_entity,
        ),
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
        if not isinstance(device, dict):
            continue
        kind = str(_resolve_core_config_value(device.get('kind'), read_entity, ''))
        if kind == 'BATTERY':
            materialized[str(device_id)] = _build_core_battery_device(str(device_id), device, read_entity)
        elif kind == 'EV_CHARGER':
            materialized[str(device_id)] = _build_core_ev_device(str(device_id), device, read_entity)
        elif kind == 'RELAY':
            materialized[str(device_id)] = _build_core_relay_device(str(device_id), device, read_entity)
    return materialized


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
            primary_consuming_device_ids=_materialize_primary_consuming_device_ids(
                _require_mapping_value(ems.get('global_config'), 'primary_consuming_device_ids'),
                read_entity,
            ),
        ),
        runtime=CoreRuntimeConfig(
            grid_power_w=_resolve_core_config_value(_require_mapping_value(ems.get('runtime'), 'grid_power_w'), read_entity, 0),
            quarter_energy_balance_kwh=_resolve_core_config_value(_require_mapping_value(ems.get('runtime'), 'quarter_energy_balance_kwh'), read_entity, 0),
            pv_power_w=_resolve_core_config_value(_require_mapping_value(ems.get('runtime'), 'pv_power_w'), read_entity, 0),
        ),
        state=CoreStateConfig(
            surplus_freeze_until=_resolve_core_config_value(_require_mapping_value(ems.get('state'), 'surplus_freeze_until'), read_entity, ''),
            active_surplus_devices=_resolve_core_config_value(_require_mapping_value(ems.get('state'), 'active_surplus_devices'), read_entity, ''),
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
    battery_ids = []
    for device_id, device in devices.items():
        if not isinstance(device, dict):
            issues.append(_issue(f'ems.devices.{device_id}', SEVERITY_ERROR, 'must be a mapping'))
            continue
        kind = device.get('kind')
        if kind == 'BATTERY':
            battery_ids.append(str(device_id))
        _validate_device(device_id, device, None, issues, runtime_packet_mode=runtime_packet_mode)

    if not battery_ids:
        issues.append(_issue('ems.devices', SEVERITY_ERROR, 'at least one BATTERY device is required by direct_tick_frame_v5'))


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
        if kind == 'BATTERY':
            required_sections.append('guard')
    for section in required_sections:
        if section not in device:
            issues.append(_issue(f'{device_path}.{section}', SEVERITY_ERROR, 'missing required section'))
        elif not isinstance(device.get(section), dict):
            issues.append(_issue(f'{device_path}.{section}', SEVERITY_ERROR, 'must be a mapping'))

    if runtime_packet_mode:
        for runtime_owned_section in ('policy', 'guard'):
            if runtime_owned_section in device:
                issues.append(
                    _issue(
                        f'{device_path}.{runtime_owned_section}',
                        SEVERITY_ERROR,
                        'runtime packet-owned section must not be defined in EMS_config.yaml',
                    )
                )
        if 'adapter' in device:
            issues.append(
                _issue(
                    f'{device_path}.adapter',
                    SEVERITY_ERROR,
                    'runtime-packet mode owns actuator entity mappings via '
                    'sensor.ems_policy_config_runtime attribute entity_registry; '
                    'remove static device adapter mapping from EMS_config.yaml',
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

    if kind == 'BATTERY' and isinstance(device.get('guard'), dict):
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

    if kind == 'BATTERY' and isinstance(device.get('policy'), dict):
        _validate_unknown_fields(
            device['policy'],
            f'{device_path}.policy',
            ALLOWED_BATTERY_POLICY_KEYS,
            issues,
        )
        if 'producing_priority' not in device['policy']:
            issues.append(_issue(f'{device_path}.policy.producing_priority', SEVERITY_ERROR, 'missing required field'))
        else:
            _validate_entity_or_number(
                device['policy'], f'{device_path}.policy.producing_priority',
                'producing_priority', issues, min_value=0,
            )
        if 'surplus_allowed' in device['policy']:
            _validate_entity_or_bool(
                device['policy'], f'{device_path}.policy.surplus_allowed',
                'surplus_allowed', issues,
            )
        if bool(device['policy'].get('surplus_allowed', False)):
            if device['policy'].get('surplus_dispatch_mode') not in ('max_absorb', 'fixed'):
                issues.append(_issue(f'{device_path}.policy.surplus_dispatch_mode', SEVERITY_ERROR, 'must be max_absorb or fixed'))

    if kind == 'BATTERY' and isinstance(device.get('adapter'), dict):
        _validate_unknown_fields(
            device['adapter'],
            f'{device_path}.adapter',
            ALLOWED_BATTERY_ADAPTER_KEYS,
            issues,
        )
        _validate_required_entities(
            device['adapter'],
            f'{device_path}.adapter',
            ('target_w',),
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
        if 'producing_priority' not in device['policy']:
            issues.append(_issue(f'{device_path}.policy.producing_priority', SEVERITY_ERROR, 'missing required field'))
        else:
            _validate_entity_or_number(device['policy'], f'{device_path}.policy.producing_priority', 'producing_priority', issues, min_value=0)
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
            if 'producing_priority' not in device['policy']:
                issues.append(_issue(f'{device_path}.policy.producing_priority', SEVERITY_ERROR, 'missing required field'))
            else:
                _validate_entity_or_number(device['policy'], f'{device_path}.policy.producing_priority', 'producing_priority', issues, min_value=0)
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
    for field in ('can_absorb_w', 'can_produce_w', 'supports_primary_consuming_regulation', 'supports_producing_regulation'):
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
    bool_fields = ('can_absorb_w', 'can_produce_w', 'uses_hard_off_lifecycle', 'supports_primary_consuming_regulation', 'supports_producing_regulation')
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

    if capabilities.get('supports_producing_regulation') is True and capabilities.get('can_produce_w') is not True:
        issues.append(_issue(f'{device_path}.capabilities.supports_producing_regulation', SEVERITY_ERROR, 'requires can_produce_w=true'))
    if capabilities.get('can_produce_w') is True and 'max_produce_w' not in capabilities:
        issues.append(_issue(f'{device_path}.capabilities.max_produce_w', SEVERITY_ERROR, 'required when can_produce_w=true'))
    if 'min_produce_w' in capabilities:
        _validate_entity_or_number(capabilities, f'{device_path}.capabilities.min_produce_w', 'min_produce_w', issues, min_value=0)
    if 'max_produce_w' in capabilities:
        _validate_entity_or_number(capabilities, f'{device_path}.capabilities.max_produce_w', 'max_produce_w', issues, min_value=0)
    min_produce = capabilities.get('min_produce_w', 0)
    max_produce = capabilities.get('max_produce_w')
    if _is_number(min_produce) and _is_number(max_produce) and float(max_produce) < float(min_produce):
        issues.append(_issue(f'{device_path}.capabilities.max_produce_w', SEVERITY_ERROR, 'must be >= min_produce_w'))

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
    for device_id, battery in devices.items():
        if not isinstance(battery, dict) or str(battery.get('kind') or '') != 'BATTERY':
            continue
        battery_caps = battery.get('capabilities')
        if isinstance(battery_caps, dict):
            if battery_caps.get('can_absorb_w') is False and battery_caps.get('can_produce_w') is False:
                issues.append(
                    _issue(
                        f'ems.devices.{device_id}.capabilities',
                        SEVERITY_ERROR,
                        f'{device_id} must define at least one enabled direction: can_absorb_w=true or can_produce_w=true',
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
        supports_primary_consuming_regulation=bool(_resolve_core_config_value(
            _require_mapping_value(_require_mapping_value(device, 'capabilities'), 'supports_primary_consuming_regulation'),
            read_entity,
            False,
        )),
        supports_producing_regulation=bool(_resolve_core_config_value(
            _require_mapping_value(_require_mapping_value(device, 'capabilities'), 'supports_producing_regulation'),
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
        min_produce_w=_resolve_core_config_value(_require_mapping_value(_require_mapping_value(device, 'capabilities'), 'min_produce_w'), read_entity, 0.0)
        if 'min_produce_w' in _require_mapping_value(device, 'capabilities')
        else 0.0,
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
            producing_priority=_resolve_core_config_value(
                _require_mapping_value(_require_mapping_value(device, 'policy'), 'producing_priority'),
                read_entity,
                0,
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
            producing_priority=_resolve_core_config_value(_require_mapping_value(policy_section, 'producing_priority'), read_entity, 0),
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
            producing_priority=_resolve_core_config_value(
                _require_mapping_value(_require_mapping_value(device, 'policy'), 'producing_priority'),
                read_entity,
                0,
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
    raw_devices = haeo.get('devices', {})
    devices = {}
    if isinstance(raw_devices, dict):
        for device_id, raw_mapping in raw_devices.items():
            if not isinstance(raw_mapping, dict):
                continue
            devices[str(device_id)] = {
                'power_active': _resolve_core_config_value(_require_mapping_value(raw_mapping, 'power_active'), read_entity, ''),
                'fresh_source': _resolve_core_config_value(_require_mapping_value(raw_mapping, 'fresh_source'), read_entity, ''),
            }
    return CoreHaeoConfig(devices=devices)


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
