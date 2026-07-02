from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
    'policy_outputs',
    'diagnostics_outputs',
)
OPTIONAL_TOP_LEVEL_SECTIONS = (
    'role_constraints',
    'haeo',
    'policy_engine',
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
ALLOWED_POLICY_OUTPUT_KEYS = frozenset(
    (
        'device_policies',
        'dispatch_command',
        'policy_state',
    )
)
ALLOWED_DIAGNOSTICS_OUTPUT_KEYS = frozenset(
    (
        'policy_diagnostics',
        'actuator_writer_trace',
        'dispatch_state_applier_trace',
    )
)
ALLOWED_POLICY_ENGINE_KEYS = frozenset(('interval_seconds',))
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
LEGACY_POLICY_OUTPUT_REJECTIONS = {
    'decision_trace': 'Unsupported legacy policy_outputs field: decision_trace. Use diagnostics_outputs.policy_diagnostics instead.',
    'actuator_writer_trace': 'Unsupported legacy policy_outputs field: actuator_writer_trace. Use diagnostics_outputs.actuator_writer_trace instead.',
    'dispatch_state_applier_trace': 'Unsupported legacy policy_outputs field: dispatch_state_applier_trace. Use diagnostics_outputs.dispatch_state_applier_trace instead.',
    'surplus_policy_active': 'Unsupported legacy policy_outputs field: surplus_policy_active. Standalone surplus summary sensors were removed.',
    'surplus_next_target': 'Unsupported legacy policy_outputs field: surplus_next_target. Standalone surplus summary sensors were removed.',
    'surplus_next_threshold': 'Unsupported legacy policy_outputs field: surplus_next_threshold. Standalone surplus summary sensors were removed.',
    'surplus_release_candidate': 'Unsupported legacy policy_outputs field: surplus_release_candidate. Standalone surplus summary sensors were removed.',
    'surplus_explanation': 'Unsupported legacy policy_outputs field: surplus_explanation. Standalone surplus summary sensors were removed.',
}
KNOWN_POLICY_OUTPUT_KEYS = frozenset(tuple(ALLOWED_POLICY_OUTPUT_KEYS) + tuple(LEGACY_POLICY_OUTPUT_REJECTIONS))
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

    _validate_unknown_fields(ems, 'ems', ALLOWED_EMS_SECTION_KEYS, issues)

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

    if isinstance(ems.get('state'), dict):
        _validate_required_entities(
            ems['state'],
            'ems.state',
            ('surplus_freeze_until', 'active_surplus_devices', 'previous_device_state'),
            issues,
        )

    if isinstance(ems.get('policy_outputs'), dict):
        _validate_legacy_policy_output_fields(ems['policy_outputs'], issues)
        _validate_unknown_fields(
            ems['policy_outputs'],
            'ems.policy_outputs',
            KNOWN_POLICY_OUTPUT_KEYS,
            issues,
        )
        _validate_required_entities(
            ems['policy_outputs'],
            'ems.policy_outputs',
            (
                'device_policies',
                'dispatch_command',
                'policy_state',
            ),
            issues,
        )
    if isinstance(ems.get('diagnostics_outputs'), dict):
        _validate_unknown_fields(
            ems['diagnostics_outputs'],
            'ems.diagnostics_outputs',
            ALLOWED_DIAGNOSTICS_OUTPUT_KEYS,
            issues,
        )
        _validate_required_entities(
            ems['diagnostics_outputs'],
            'ems.diagnostics_outputs',
            (
                'policy_diagnostics',
                'actuator_writer_trace',
                'dispatch_state_applier_trace',
            ),
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


def _validate_legacy_policy_output_fields(
    policy_outputs: dict,
    issues: list[ConfigValidationIssue],
) -> None:
    for field_name, message in LEGACY_POLICY_OUTPUT_REJECTIONS.items():
        if field_name in policy_outputs:
            issues.append(_issue(f'ems.policy_outputs.{field_name}', SEVERITY_ERROR, message))


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


def _build_core_devices_map(
    devices: object,
    read_entity: Callable[[str, object], object],
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
    ems = config.get('ems', {})
    devices = ems.get('devices', {})
    role_constraints = ems.get('role_constraints', {})
    policy_engine = ems.get('policy_engine', {})
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
            device_policies=_resolve_core_config_value(_require_mapping_value(ems.get('policy_outputs'), 'device_policies'), read_entity, ''),
            dispatch_command=_resolve_core_config_value(_require_mapping_value(ems.get('policy_outputs'), 'dispatch_command'), read_entity, ''),
            policy_state=_resolve_core_config_value(_require_mapping_value(ems.get('policy_outputs'), 'policy_state'), read_entity, ''),
        ),
        diagnostics_outputs=CoreDiagnosticsOutputsConfig(
            policy_diagnostics=_resolve_core_config_value(_require_mapping_value(ems.get('diagnostics_outputs'), 'policy_diagnostics'), read_entity, ''),
            actuator_writer_trace=_resolve_core_config_value(_require_mapping_value(ems.get('diagnostics_outputs'), 'actuator_writer_trace'), read_entity, ''),
            dispatch_state_applier_trace=_resolve_core_config_value(_require_mapping_value(ems.get('diagnostics_outputs'), 'dispatch_state_applier_trace'), read_entity, ''),
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
    read_entity: Callable[[str, object], object],
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
    read_entity: Callable[[str, object], object],
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


def _build_core_ev_device(device_id: str, device: object, read_entity: Callable[[str, object], object]) -> CoreEvChargerDeviceConfig:
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


def _build_core_relay_device(device_id: str, device: object, read_entity: Callable[[str, object], object]) -> CoreRelayDeviceConfig:
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


def _build_core_haeo_config(haeo: object, read_entity: Callable[[str, object], object]) -> Optional[CoreHaeoConfig]:
    if not isinstance(haeo, dict):
        return None
    return CoreHaeoConfig(
        battery_power_active=_resolve_core_config_value(_require_mapping_value(haeo, 'battery_power_active'), read_entity, ''),
        ev_power_active=_resolve_core_config_value(_require_mapping_value(haeo, 'ev_power_active'), read_entity, ''),
        battery_fresh_source=_resolve_core_config_value(_require_mapping_value(haeo, 'battery_fresh_source'), read_entity, ''),
        ev_fresh_source=_resolve_core_config_value(_require_mapping_value(haeo, 'ev_fresh_source'), read_entity, ''),
    )


def _build_core_role_constraints(role_constraints: object, read_entity: Callable[[str, object], object]) -> CoreRoleConstraintsConfig:
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
    read_entity: Callable[[str, object], object],
    default: object,
) -> object:
    if value in (None, 'unknown', 'unavailable', 'none', ''):
        return default
    if _is_valid_entity_id(value):
        entity_value = read_entity(value, default)
        if entity_value in (None, 'unknown', 'unavailable', 'none', ''):
            return default
        return entity_value
    return value
