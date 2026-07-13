from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

from ems_core.domain.models import (
    CorePolicyEngineConfig,
    HaeoTargets,
    Profiles,
)


RUNTIME_SCHEMA_VERSION = 5


class RuntimePacketSchemaError(ValueError):
    """Raised when a required direct-runtime packet field is missing or invalid."""

    def __init__(self, path: str, message: str):
        self.path = str(path or '<root>')
        self.message = str(message or 'invalid value')
        ValueError.__init__(self, f'RUNTIME_PACKET_INVALID: {self.path} {self.message}')


@dataclass
class StaticTopology:
    device_order: tuple[str, ...]
    device_kind_by_id: dict[str, str]
    can_absorb_by_id: dict[str, bool]
    can_produce_by_id: dict[str, bool]
    battery_device_ids: tuple[str, ...]
    ev_device_ids: tuple[str, ...]
    relay_device_ids: tuple[str, ...]
    policy_config_entity_id: str
    measurements_entity_id: str
    policy_state_entity_id: str
    role_constraints: object


@dataclass
class RuntimePolicyConfig:
    revision: int
    profiles: Profiles
    policy_engine: CorePolicyEngineConfig
    role_constraints: object
    global_config: SimpleNamespace
    device_kind_by_id: dict[str, str]
    device_ids_by_kind_map: dict[str, tuple[str, ...]]
    device_capabilities_by_id: dict[str, dict]
    device_policy_by_id: dict[str, dict]
    device_adapter_config_by_id: dict[str, dict]

    def initialize_device_views(self):
        """Build cached device namespaces without scalar compatibility mirrors.

        Global configuration remains authoritative at ``global_config`` and
        device configuration remains authoritative in the per-device maps.
        Runtime schema v5 carries ordered primary-consuming fallback IDs, battery state by device_id, and
        producer membership/order directly in the canonical device maps.
        """
        self.devices = {}
        for device_id in self.device_kind_by_id:
            self.devices[device_id] = self._device_namespace(device_id)

        # Internal immutable-by-convention maps cached with this config revision.
        # The NET_ZERO engine consumes them directly; no per-tick PolicyRuntimeFacts
        # projection or dynamic binding plan is constructed.
        self.direct_policy_maps = {
            'device_ids_by_kind': self.device_ids_by_kind_map,
            'device_kind_by_id': self.device_kind_by_id,
            'device_capabilities_by_id': self.device_capabilities_by_id,
            'device_policy_by_id': self.device_policy_by_id,
            'device_adapter_by_id': self.device_adapter_config_by_id,
        }

    def primary_consuming_device_ids(self):
        return tuple(getattr(self.global_config, 'primary_consuming_device_ids', ()) or ())

    def producing_device_ids(self):
        candidates = []
        for rank, device_id in enumerate(self.device_kind_by_id):
            caps = self.device_capabilities_by_id.get(str(device_id), {}) or {}
            if not bool(caps.get('supports_producing_regulation', False)):
                continue
            policy = self.device_policy_by_id.get(str(device_id), {}) or {}
            candidates.append((
                -int(policy.get('producing_priority', 0) or 0),
                rank,
                str(device_id),
            ))
        candidates.sort()
        result = []
        for item in candidates:
            result.append(item[2])
        return tuple(result)

    def battery_guard_value(self, device_id: str, field: str, default=None):
        guard = self.device_policy_by_id.get(str(device_id), {}).get('_guard', {}) or {}
        return guard.get(str(field), default)

    def _device_namespace(self, device_id: str):
        kind = self.device_kind_by_id.get(device_id, '')
        caps = dict(self.device_capabilities_by_id.get(device_id, {}))
        policy_values = dict(self.device_policy_by_id.get(device_id, {}))
        guard_values = policy_values.pop('_guard', None)
        adapter_values = dict(self.device_adapter_config_by_id.get(device_id, {}))
        return SimpleNamespace(
            device_id=device_id,
            kind=kind,
            capabilities=SimpleNamespace(**caps),
            policy=SimpleNamespace(**policy_values),
            guard=SimpleNamespace(**guard_values) if isinstance(guard_values, dict) else None,
            adapter=SimpleNamespace(**adapter_values),
        )

    def device_by_id(self, device_id: str):
        return self.devices.get(str(device_id))

    def device_kind(self, device_id: str) -> str:
        return str(self.device_kind_by_id.get(str(device_id), '') or '')

    def device_ids_by_kind(self, kind: str) -> tuple[str, ...]:
        return tuple(self.device_ids_by_kind_map.get(str(kind), ()) or ())

    def devices_by_kind(self, kind: str) -> tuple:
        items = []
        for device_id in self.device_ids_by_kind(kind):
            items.append(self.devices[device_id])
        return tuple(items)

    def device_capability(self, device_id: str, field: str, default=None):
        return self.device_capabilities_by_id.get(str(device_id), {}).get(str(field), default)

    def device_policy_value(self, device_id: str, field: str, default=None):
        return self.device_policy_by_id.get(str(device_id), {}).get(str(field), default)

    def device_adapter_value(self, device_id: str, field: str, default=None):
        return self.device_adapter_config_by_id.get(str(device_id), {}).get(str(field), default)


@dataclass
class TickFrame:
    now_ts: float
    grid_power_w: float
    quarter_energy_balance_kwh: float
    pv_power_w: float
    battery_states: dict[str, dict]
    relay_states: dict[str, dict]
    ev_states: dict[str, dict]
    surplus_freeze_until_ts: Optional[float]
    active_surplus_device_ids: tuple[str, ...]
    previous_device_states: dict[str, dict]
    haeo_device_state_kw_by_id: dict[str, float]
    haeo_device_age_s_by_id: dict[str, float]
    previous_quarter_key: str
    previous_primary_consuming_device_id: str
    previous_force_on_device_ids: tuple[str, ...]
    policy_config_revision: int

    def battery_state(self, device_id: str) -> dict:
        return dict((self.battery_states or {}).get(str(device_id), {}) or {})

    def haeo_targets(self, profiles: Profiles, runtime_config: RuntimePolicyConfig) -> HaeoTargets:
        from ems_core.net_zero.engine import configured_forecast, effective_forecast

        configured = configured_forecast(profiles.control, profiles.forecast)
        timeout_s = float(runtime_config.global_config.haeo_stale_timeout_s)
        fresh_targets = {}
        fresh_ages = {}
        for device_id, target_kw in (self.haeo_device_state_kw_by_id or {}).items():
            age_s = float((self.haeo_device_age_s_by_id or {}).get(str(device_id), float('inf')))
            if age_s < timeout_s:
                fresh_targets[str(device_id)] = float(target_kw)
                fresh_ages[str(device_id)] = age_s
        fresh = bool(fresh_targets)
        return HaeoTargets(
            effective_forecast=effective_forecast(configured, fresh),
            configured_forecast=configured,
            fresh=fresh,
            device_target_kw_by_id=fresh_targets,
            device_age_s_by_id=fresh_ages,
        )


@dataclass
class PolicyResult:
    outputs: object
    attrs: dict


_POLICY_CONFIG_CACHE = {
    'entity_id': None,
    'revision': None,
    'config': None,
}


def reset_direct_runtime_cache() -> None:
    _POLICY_CONFIG_CACHE.clear()
    _POLICY_CONFIG_CACHE.update({'entity_id': None, 'revision': None, 'config': None})


def _fail(path: str, message: str):
    raise RuntimePacketSchemaError(path, message)


def _mapping(value, path: str) -> dict:
    if not isinstance(value, dict):
        _fail(path, 'must be a mapping')
    return value


def _required(mapping: dict, key: str, path: str):
    if key not in mapping:
        _fail(f'{path}.{key}' if path else key, 'missing')
    return mapping[key]


def _number(value, path: str) -> float:
    if isinstance(value, bool):
        _fail(path, 'must be numeric')
    try:
        return float(value)
    except (TypeError, ValueError):
        _fail(path, 'must be numeric')


def _integer(value, path: str) -> int:
    number = _number(value, path)
    if int(number) != number:
        _fail(path, 'must be an integer')
    return int(number)


def _boolean(value, path: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ('true', 'on', 'yes', '1'):
            return True
        if text in ('false', 'off', 'no', '0'):
            return False
    _fail(path, 'must be boolean')


def _strict_boolean(value, path: str) -> bool:
    if type(value) is not bool:
        _fail(path, 'must be a boolean')
    return value


def _text(value, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        _fail(path, 'must be a string')
    text = value.strip()
    if not text and not allow_empty:
        _fail(path, 'must be non-empty')
    return text


def _string_tuple(value, path: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _fail(path, 'must be a list')
    items = []
    for index, item in enumerate(value):
        items.append(_text(item, f'{path}[{index}]'))
    return tuple(items)


def _require_runtime_schema(packet: dict, packet_name: str) -> None:
    version = _integer(_required(packet, 'schema_version', packet_name), f'{packet_name}.schema_version')
    if version != RUNTIME_SCHEMA_VERSION:
        _fail(
            f'{packet_name}.schema_version',
            f'must equal {RUNTIME_SCHEMA_VERSION}, got {version}',
        )


def build_static_topology(config: dict) -> StaticTopology:
    ems = _mapping(config.get('ems'), 'ems')
    sources = _mapping(ems.get('runtime_sources'), 'ems.runtime_sources')

    source_ids = {}
    for key in ('policy_config', 'measurements', 'policy_state'):
        source = _mapping(_required(sources, key, 'ems.runtime_sources'), f'ems.runtime_sources.{key}')
        source_ids[key] = _text(
            _required(source, 'entity_id', f'ems.runtime_sources.{key}'),
            f'ems.runtime_sources.{key}.entity_id',
        )

    devices = _mapping(ems.get('devices'), 'ems.devices')
    device_order = []
    kind_by_id = {}
    can_absorb_by_id = {}
    can_produce_by_id = {}
    ids_by_kind = {'BATTERY': [], 'EV_CHARGER': [], 'RELAY': []}
    for raw_device_id, raw_device in devices.items():
        device_id = str(raw_device_id)
        device = _mapping(raw_device, f'ems.devices.{device_id}')
        kind = _text(_required(device, 'kind', f'ems.devices.{device_id}'), f'ems.devices.{device_id}.kind')
        if kind not in ids_by_kind:
            _fail(f'ems.devices.{device_id}.kind', f'unsupported kind {kind}')
        capabilities = _mapping(
            _required(device, 'capabilities', f'ems.devices.{device_id}'),
            f'ems.devices.{device_id}.capabilities',
        )
        device_order.append(device_id)
        kind_by_id[device_id] = kind
        can_absorb_by_id[device_id] = _boolean(
            _required(capabilities, 'can_absorb_w', f'ems.devices.{device_id}.capabilities'),
            f'ems.devices.{device_id}.capabilities.can_absorb_w',
        )
        can_produce_by_id[device_id] = _boolean(
            _required(capabilities, 'can_produce_w', f'ems.devices.{device_id}.capabilities'),
            f'ems.devices.{device_id}.capabilities.can_produce_w',
        )
        ids_by_kind[kind].append(device_id)

    if not ids_by_kind['BATTERY']:
        _fail('ems.devices', 'must contain a BATTERY device')

    role_constraints_raw = ems.get('role_constraints', {})
    role_constraints_raw = role_constraints_raw if isinstance(role_constraints_raw, dict) else {}
    default_roles = role_constraints_raw.get('default', {})
    by_role = {}
    for key, value in role_constraints_raw.items():
        if key == 'default':
            continue
        by_role[str(key)] = value if isinstance(value, dict) else {}
    # Avoid constructing a local dataclass with __post_init__ on the Pyscript
    # evaluator path. A dataclass-generated native __init__ cannot await a
    # Pyscript-interpreted bound __post_init__ method.
    role_constraints = SimpleNamespace(
        default=dict(default_roles) if isinstance(default_roles, dict) else {},
        by_role=by_role,
    )

    return StaticTopology(
        device_order=tuple(device_order),
        device_kind_by_id=kind_by_id,
        can_absorb_by_id=can_absorb_by_id,
        can_produce_by_id=can_produce_by_id,
        battery_device_ids=tuple(ids_by_kind['BATTERY']),
        ev_device_ids=tuple(ids_by_kind['EV_CHARGER']),
        relay_device_ids=tuple(ids_by_kind['RELAY']),
        policy_config_entity_id=source_ids['policy_config'],
        measurements_entity_id=source_ids['measurements'],
        policy_state_entity_id=source_ids['policy_state'],
        role_constraints=role_constraints,
    )


def _tuple_values_by_key(mapping: dict) -> dict:
    result = {}
    for key, value in mapping.items():
        result[str(key)] = tuple(value)
    return result


def _profile_value(profiles: dict, key: str, allowed: tuple[str, ...]) -> str:
    value = _text(_required(profiles, key, 'policy_config.profiles'), f'policy_config.profiles.{key}')
    if value not in allowed:
        _fail(f'policy_config.profiles.{key}', f'unsupported value {value}')
    return value


def _parse_policy_config_v5(
    topology: StaticTopology,
    packet: dict,
    policy_engine: Optional[CorePolicyEngineConfig],
) -> RuntimePolicyConfig:
    _require_runtime_schema(packet, 'policy_config')
    revision = _integer(_required(packet, 'revision', 'policy_config'), 'policy_config.revision')
    if revision < 0:
        _fail('policy_config.revision', 'must be non-negative')

    profiles_raw = _mapping(_required(packet, 'profiles', 'policy_config'), 'policy_config.profiles')
    profiles = Profiles(
        control=_profile_value(profiles_raw, 'control', ('MANUAL', 'MANUAL_SAFE', 'AUTOMATIC', 'HORIZON_BY_HAEO')),
        goal=_profile_value(profiles_raw, 'goal', ('NET_ZERO', 'MAX_EXPORT', 'CHEAP_GRID_CHARGE')),
        forecast=_profile_value(profiles_raw, 'forecast', ('NONE', 'HAEO')),
        guard=_profile_value(profiles_raw, 'guard', ('NORMAL_LIMITS', 'STRICT_LIMITS', 'BATTERY_PROTECT', 'DEGRADED')),
    )

    cfg_raw = _mapping(_required(packet, 'config', 'policy_config'), 'policy_config.config')
    for removed_field in ('adjustable_surplus_load', 'adjustable_surplus_activation_w'):
        if removed_field in cfg_raw:
            _fail(
                f'policy_config.config.{removed_field}',
                'field removed; surplus eligibility is device-owned and activation threshold derives from capabilities.max_absorb_w',
            )
    number_fields = (
        'deadband_w',
        'ramp_w',
        'strict_limit_w',
        'default_sp_w',
        'surplus_freeze_s',
        'battery_heartbeat_timeout_s',
        'haeo_stale_timeout_s',
        'nz_battery_floor_default_w',
        'nz_battery_floor_ev_active_w',
    )
    cfg_values = {}
    for field in number_fields:
        cfg_values[field] = _number(_required(cfg_raw, field, 'policy_config.config'), f'policy_config.config.{field}')
    cfg_values['primary_consuming_device_ids'] = _string_tuple(
        _required(cfg_raw, 'primary_consuming_device_ids', 'policy_config.config'),
        'policy_config.config.primary_consuming_device_ids',
    )
    seen_primary_ids = set()
    for index, device_id in enumerate(cfg_values['primary_consuming_device_ids']):
        if device_id not in topology.device_kind_by_id:
            _fail(
                f'policy_config.config.primary_consuming_device_ids[{index}]',
                f'unknown device id {device_id}',
            )
        if device_id in seen_primary_ids:
            _fail(
                f'policy_config.config.primary_consuming_device_ids[{index}]',
                f'duplicate device id {device_id}',
            )
        seen_primary_ids.add(device_id)

    devices_raw = _mapping(_required(packet, 'devices', 'policy_config'), 'policy_config.devices')
    packet_device_ids = set()
    for key in devices_raw:
        packet_device_ids.add(str(key))
    unknown_devices = packet_device_ids - set(topology.device_order)
    if unknown_devices:
        _fail('policy_config.devices', f'unknown device ids {sorted(unknown_devices)}')

    capabilities_by_id = {}
    policy_by_id = {}
    adapter_by_id = {}
    ids_by_kind = {'BATTERY': [], 'EV_CHARGER': [], 'RELAY': []}

    for device_id in topology.device_order:
        kind = topology.device_kind_by_id[device_id]
        ids_by_kind[kind].append(device_id)
        device_path = f'policy_config.devices.{device_id}'
        device = _mapping(_required(devices_raw, device_id, 'policy_config.devices'), device_path)
        caps_raw = _mapping(_required(device, 'capabilities', device_path), f'{device_path}.capabilities')
        caps = {
            'can_absorb_w': bool(topology.can_absorb_by_id[device_id]),
            'can_produce_w': bool(topology.can_produce_by_id[device_id]),
            'uses_hard_off_lifecycle': _strict_boolean(
                _required(caps_raw, 'uses_hard_off_lifecycle', f'{device_path}.capabilities'),
                f'{device_path}.capabilities.uses_hard_off_lifecycle',
            ),
            'supports_primary_consuming_regulation': _strict_boolean(
                _required(caps_raw, 'supports_primary_consuming_regulation', f'{device_path}.capabilities'),
                f'{device_path}.capabilities.supports_primary_consuming_regulation',
            ),
            'supports_producing_regulation': _strict_boolean(
                _required(caps_raw, 'supports_producing_regulation', f'{device_path}.capabilities'),
                f'{device_path}.capabilities.supports_producing_regulation',
            ),
        }
        for field in ('min_absorb_w', 'max_absorb_w', 'min_produce_w', 'max_produce_w', 'step_w'):
            caps[field] = _number(_required(caps_raw, field, f'{device_path}.capabilities'), f'{device_path}.capabilities.{field}')
        capabilities_by_id[device_id] = caps

        policy_raw = _mapping(_required(device, 'policy', device_path), f'{device_path}.policy')
        if 'activation_threshold_w' in policy_raw:
            _fail(
                f'{device_path}.policy.activation_threshold_w',
                'field removed; surplus activation threshold derives from capabilities.max_absorb_w',
            )
        policy = {
            'priority': _integer(_required(policy_raw, 'priority', f'{device_path}.policy'), f'{device_path}.policy.priority'),
            'producing_priority': _integer(_required(policy_raw, 'producing_priority', f'{device_path}.policy'), f'{device_path}.policy.producing_priority'),
        }
        policy['surplus_allowed'] = _strict_boolean(
            _required(policy_raw, 'surplus_allowed', f'{device_path}.policy'),
            f'{device_path}.policy.surplus_allowed',
        )
        policy['surplus_dispatch_mode'] = _text(
            _required(policy_raw, 'surplus_dispatch_mode', f'{device_path}.policy'),
            f'{device_path}.policy.surplus_dispatch_mode',
        )
        if policy['surplus_dispatch_mode'] not in ('max_absorb', 'fixed'):
            _fail(f'{device_path}.policy.surplus_dispatch_mode', 'must be max_absorb or fixed')
        adapter = {}
        if kind == 'BATTERY':
            policy['default_min_absorb_w'] = _number(
                _required(policy_raw, 'default_min_absorb_w', f'{device_path}.policy'),
                f'{device_path}.policy.default_min_absorb_w',
            )
            guard_raw = _mapping(_required(device, 'guard', device_path), f'{device_path}.guard')
            guard_values = {}
            for field in (
                'protect_soc',
                'protect_soc_recovery_margin',
                'protect_min_cell_voltage_v',
                'protect_min_absorb_w',
            ):
                guard_values[field] = _number(
                    _required(guard_raw, field, f'{device_path}.guard'),
                    f'{device_path}.guard.{field}',
                )
            policy['_guard'] = guard_values
        elif kind == 'EV_CHARGER':
            policy['force_on'] = _boolean(
                _required(policy_raw, 'force_on', f'{device_path}.policy'),
                f'{device_path}.policy.force_on',
            )
            policy['low_pv_threshold_w'] = _number(
                _required(policy_raw, 'low_pv_threshold_w', f'{device_path}.policy'),
                f'{device_path}.policy.low_pv_threshold_w',
            )
            policy['hard_off_low_pv_cycles'] = _integer(
                _required(policy_raw, 'hard_off_low_pv_cycles', f'{device_path}.policy'),
                f'{device_path}.policy.hard_off_low_pv_cycles',
            )
            policy['hard_off_release_cycles'] = _integer(
                _required(policy_raw, 'hard_off_release_cycles', f'{device_path}.policy'),
                f'{device_path}.policy.hard_off_release_cycles',
            )
            adapter_raw = _mapping(_required(device, 'adapter_config', device_path), f'{device_path}.adapter_config')
            adapter = {
                'current_step_a': _number(_required(adapter_raw, 'current_step_a', f'{device_path}.adapter_config'), f'{device_path}.adapter_config.current_step_a'),
                'phases': _integer(_required(adapter_raw, 'phases', f'{device_path}.adapter_config'), f'{device_path}.adapter_config.phases'),
                'voltage_v': _number(_required(adapter_raw, 'voltage_v', f'{device_path}.adapter_config'), f'{device_path}.adapter_config.voltage_v'),
            }
        elif kind == 'RELAY':
            policy['force_on'] = _boolean(
                _required(policy_raw, 'force_on', f'{device_path}.policy'),
                f'{device_path}.policy.force_on',
            )
        policy_by_id[device_id] = policy
        adapter_by_id[device_id] = adapter

    primary_consuming_device_ids = tuple(cfg_values['primary_consuming_device_ids'])
    for index, primary_consuming_device_id in enumerate(primary_consuming_device_ids):
        primary_caps = capabilities_by_id.get(primary_consuming_device_id, {}) or {}
        if not bool(primary_caps.get('supports_primary_consuming_regulation', False)):
            _fail(
                f'policy_config.config.primary_consuming_device_ids[{index}]',
                f'{primary_consuming_device_id} does not support primary consuming regulation',
            )
        if not bool(primary_caps.get('can_absorb_w', False)):
            _fail(
                f'policy_config.config.primary_consuming_device_ids[{index}]',
                f'{primary_consuming_device_id} cannot absorb power',
            )

    for device_id, caps in capabilities_by_id.items():
        if bool(caps.get('supports_producing_regulation', False)) and not bool(caps.get('can_produce_w', False)):
            _fail(
                f'policy_config.devices.{device_id}.capabilities.supports_producing_regulation',
                'requires can_produce_w=true',
            )
        min_produce_w = float(caps.get('min_produce_w', 0.0) or 0.0)
        max_produce_w = float(caps.get('max_produce_w', 0.0) or 0.0)
        if min_produce_w < 0.0 or max_produce_w < min_produce_w:
            _fail(
                f'policy_config.devices.{device_id}.capabilities.max_produce_w',
                'must be >= min_produce_w >= 0',
            )

    parsed = RuntimePolicyConfig(
        revision=revision,
        profiles=profiles,
        policy_engine=policy_engine or CorePolicyEngineConfig(),
        role_constraints=topology.role_constraints,
        global_config=SimpleNamespace(**cfg_values),
        device_kind_by_id=dict(topology.device_kind_by_id),
        device_ids_by_kind_map=_tuple_values_by_key(ids_by_kind),
        device_capabilities_by_id=capabilities_by_id,
        device_policy_by_id=policy_by_id,
        device_adapter_config_by_id=adapter_by_id,
    )
    # Call from interpreted code instead of relying on dataclass __init__ to
    # invoke a Pyscript-interpreted __post_init__ coroutine wrapper.
    parsed.initialize_device_views()
    return parsed


def parse_policy_config_cached(
    topology: StaticTopology,
    packet: dict,
    policy_engine: Optional[CorePolicyEngineConfig] = None,
) -> tuple[RuntimePolicyConfig, bool]:
    packet = _mapping(packet, 'policy_config')
    _require_runtime_schema(packet, 'policy_config')
    revision = _integer(_required(packet, 'revision', 'policy_config'), 'policy_config.revision')
    if (
        _POLICY_CONFIG_CACHE.get('entity_id') == topology.policy_config_entity_id
        and _POLICY_CONFIG_CACHE.get('revision') == revision
        and isinstance(_POLICY_CONFIG_CACHE.get('config'), RuntimePolicyConfig)
    ):
        return _POLICY_CONFIG_CACHE['config'], True

    parsed = _parse_policy_config_v5(topology, packet, policy_engine)
    _POLICY_CONFIG_CACHE.update(
        {
            'entity_id': topology.policy_config_entity_id,
            'revision': parsed.revision,
            'config': parsed,
        }
    )
    return parsed, False


def _normalize_previous_device_state(value: dict, path: str) -> dict:
    state = _mapping(value, path)
    return {
        'device_id': _text(_required(state, 'device_id', path), f'{path}.device_id', allow_empty=True),
        'mode': _text(_required(state, 'mode', path), f'{path}.mode', allow_empty=True),
        'low_pv_cycles': _integer(_required(state, 'low_pv_cycles', path), f'{path}.low_pv_cycles'),
        'hard_off_release_ready_cycles': _integer(
            _required(state, 'hard_off_release_ready_cycles', path),
            f'{path}.hard_off_release_ready_cycles',
        ),
        'hard_off_active': _boolean(_required(state, 'hard_off_active', path), f'{path}.hard_off_active'),
    }


def parse_tick_frame_v5(
    topology: StaticTopology,
    runtime_config: RuntimePolicyConfig,
    measurements_packet: dict,
    policy_state_packet: dict,
    now_ts: float,
) -> TickFrame:
    measurements = _mapping(measurements_packet, 'measurements')
    state_packet = _mapping(policy_state_packet, 'policy_state')
    _require_runtime_schema(measurements, 'measurements')
    _require_runtime_schema(state_packet, 'policy_state')

    grid_power_w = _number(_required(measurements, 'grid_power_w', 'measurements'), 'measurements.grid_power_w')
    quarter_balance = _number(
        _required(measurements, 'quarter_energy_balance_kwh', 'measurements'),
        'measurements.quarter_energy_balance_kwh',
    )
    pv_power_w = _number(_required(measurements, 'pv_power_w', 'measurements'), 'measurements.pv_power_w')

    batteries_packet = _mapping(_required(measurements, 'batteries', 'measurements'), 'measurements.batteries')
    battery_states = {}
    for device_id in topology.battery_device_ids:
        path = f'measurements.batteries.{device_id}'
        item = _mapping(_required(batteries_packet, device_id, 'measurements.batteries'), path)
        heartbeat = _required(item, 'heartbeat', path)
        if heartbeat in (None, '', 'unknown', 'unavailable', 'none'):
            _fail(f'{path}.heartbeat', 'must be available')
        heartbeat_age_s = _number(_required(item, 'heartbeat_age_s', path), f'{path}.heartbeat_age_s')
        if heartbeat_age_s < 0:
            _fail(f'{path}.heartbeat_age_s', 'must be non-negative')
        battery_states[device_id] = {
            'soc': _number(_required(item, 'soc', path), f'{path}.soc'),
            'min_cell_voltage_v': _number(
                _required(item, 'min_cell_voltage_v', path),
                f'{path}.min_cell_voltage_v',
            ),
            'heartbeat': heartbeat,
            'heartbeat_age_s': heartbeat_age_s,
            'current_setpoint_w': _number(
                _required(item, 'current_setpoint_w', path),
                f'{path}.current_setpoint_w',
            ),
        }

    surplus = _mapping(_required(state_packet, 'surplus', 'policy_state'), 'policy_state.surplus')
    active_ids = _string_tuple(
        _required(surplus, 'active_device_ids', 'policy_state.surplus'),
        'policy_state.surplus.active_device_ids',
    )
    for device_id in active_ids:
        if device_id not in topology.device_kind_by_id:
            _fail('policy_state.surplus.active_device_ids', f'unknown device id {device_id}')
    freeze_raw = _required(surplus, 'freeze_until', 'policy_state.surplus')
    freeze_until = None if freeze_raw in (None, '') else _number(freeze_raw, 'policy_state.surplus.freeze_until')
    previous_device_states = {}
    raw_device_states = surplus.get('previous_device_states', {})
    if raw_device_states is not None:
        raw_device_states = _mapping(raw_device_states, 'policy_state.surplus.previous_device_states')
        for device_id, raw_state in raw_device_states.items():
            text_id = str(device_id)
            previous_device_states[text_id] = _normalize_previous_device_state(
                raw_state,
                f'policy_state.surplus.previous_device_states.{text_id}',
            )

    haeo = _mapping(_required(state_packet, 'haeo', 'policy_state'), 'policy_state.haeo')
    haeo_devices = _mapping(_required(haeo, 'devices', 'policy_state.haeo'), 'policy_state.haeo.devices')
    haeo_device_state_kw_by_id = {}
    haeo_device_age_s_by_id = {}
    for raw_device_id, raw_item in haeo_devices.items():
        device_id = str(raw_device_id)
        if device_id not in topology.device_kind_by_id:
            _fail(f'policy_state.haeo.devices.{device_id}', 'unknown device id')
        path = f'policy_state.haeo.devices.{device_id}'
        item = _mapping(raw_item, path)
        age_s = _number(_required(item, 'age_s', path), f'{path}.age_s')
        if age_s < 0:
            _fail(f'{path}.age_s', 'must be non-negative')
        haeo_device_state_kw_by_id[device_id] = _number(
            _required(item, 'state_kw', path),
            f'{path}.state_kw',
        )
        haeo_device_age_s_by_id[device_id] = age_s

    policy_state = _mapping(_required(state_packet, 'policy', 'policy_state'), 'policy_state.policy')
    previous_quarter_key = _text(
        _required(policy_state, 'haeo_nz_quarter_key', 'policy_state.policy'),
        'policy_state.policy.haeo_nz_quarter_key',
        allow_empty=True,
    )
    previous_primary_consuming_device_id = _text(
        _required(policy_state, 'haeo_nz_primary_consuming_device_id', 'policy_state.policy'),
        'policy_state.policy.haeo_nz_primary_consuming_device_id',
        allow_empty=True,
    )
    previous_force_on_ids = _string_tuple(
        _required(policy_state, 'prev_force_on_device_ids', 'policy_state.policy'),
        'policy_state.policy.prev_force_on_device_ids',
    )

    ev_packet = _mapping(_required(measurements, 'ev', 'measurements'), 'measurements.ev')
    ev_states = {}
    for device_id in topology.ev_device_ids:
        item = _mapping(_required(ev_packet, device_id, 'measurements.ev'), f'measurements.ev.{device_id}')
        enabled = _boolean(_required(item, 'enabled', f'measurements.ev.{device_id}'), f'measurements.ev.{device_id}.enabled')
        current_a = _number(_required(item, 'current_a', f'measurements.ev.{device_id}'), f'measurements.ev.{device_id}.current_a')
        policy = runtime_config.device_policy_by_id[device_id]
        ev_states[device_id] = {
            'enabled': enabled,
            'current_a': current_a,
            'surplus_allowed': bool(policy.get('surplus_allowed', False)),
            'active': bool(enabled and current_a > 0),
        }

    relay_packet = _mapping(_required(measurements, 'relays', 'measurements'), 'measurements.relays')
    relay_states = {}
    active_set = set(active_ids)
    for device_id in topology.relay_device_ids:
        item = _mapping(_required(relay_packet, device_id, 'measurements.relays'), f'measurements.relays.{device_id}')
        enabled = _boolean(
            _required(item, 'enabled', f'measurements.relays.{device_id}'),
            f'measurements.relays.{device_id}.enabled',
        )
        policy = runtime_config.device_policy_by_id[device_id]
        relay_states[device_id] = {
            'enabled': enabled,
            'surplus_allowed': bool(policy.get('surplus_allowed', False)),
            'force_on': bool(policy.get('force_on', False)),
            'active': device_id in active_set,
        }

    return TickFrame(
        now_ts=float(now_ts),
        grid_power_w=grid_power_w,
        quarter_energy_balance_kwh=quarter_balance,
        pv_power_w=pv_power_w,
        battery_states=battery_states,
        relay_states=relay_states,
        ev_states=ev_states,
        surplus_freeze_until_ts=freeze_until,
        active_surplus_device_ids=active_ids,
        previous_device_states=previous_device_states,
        haeo_device_state_kw_by_id=haeo_device_state_kw_by_id,
        haeo_device_age_s_by_id=haeo_device_age_s_by_id,
        previous_quarter_key=previous_quarter_key,
        previous_primary_consuming_device_id=previous_primary_consuming_device_id,
        previous_force_on_device_ids=previous_force_on_ids,
        policy_config_revision=runtime_config.revision,
    )
