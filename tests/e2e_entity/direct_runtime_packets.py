from __future__ import annotations

import json
from datetime import datetime
from dataclasses import dataclass
from types import SimpleNamespace

from ems_adapter.direct_runtime import (
    RUNTIME_SCHEMA_VERSION,
    build_static_topology,
    parse_policy_config_cached,
    parse_tick_frame_v5,
    reset_direct_runtime_cache,
)
from ems_adapter.runtime_context import build_runtime_entities_from_policy_config_packet
from ems_core.domain.models import CorePolicyEngineConfig


_PACKET_ENTITY_IDS = {
    'policy_config': 'sensor.ems_policy_config_runtime',
    'measurements': 'sensor.ems_measurements_runtime',
    'policy_state': 'sensor.ems_policy_state_runtime',
}


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _entity_id(value):
    if not isinstance(value, str):
        return ''
    text = value.strip()
    return text if '.' in text else ''


def _timestamp_or_none(value):
    if value in (None, '', 'unknown', 'unavailable', 'none'):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def _parse_ids(value):
    if value in (None, '', 'unknown', 'unavailable', 'none'):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return [part.strip() for part in str(value).split(',') if part.strip()]


@dataclass
class ScenarioPacketSnapshot:
    policy_config: dict
    measurements: dict
    policy_state: dict
    runtime_config: object
    tick_frame: object
    runtime_entities: dict


class ScenarioDirectRuntimeV5:
    """Test-only materializer for production-parity direct_tick_frame_v5 E2E execution.

    Scenario YAML is only a human-readable fixture definition. Runtime execution never
    builds a PolicyContext/CoreConfigView from it. Every policy tick is materialized as
    the same three strict v5 packets used by production and parsed by the real direct
    runtime parser.
    """

    def __init__(self, scenario_config: dict, store, now_provider):
        reset_direct_runtime_cache()
        self.scenario_config = scenario_config
        self.store = store
        self._now_provider = now_provider
        self.ems = _mapping(scenario_config.get('ems'))
        self.devices = _mapping(self.ems.get('devices'))
        self.static_config = self._build_static_config()
        self.topology = build_static_topology(self.static_config)
        policy_engine = _mapping(self.ems.get('policy_engine'))
        self.policy_engine_config = CorePolicyEngineConfig(
            interval_seconds=float(policy_engine.get('interval_seconds', 5.0) or 5.0),
            diagnostics_interval_seconds=float(policy_engine.get('diagnostics_interval_seconds', 30.0) or 30.0),
        )
        self._last_policy_key = None
        self._revision = 0

    @property
    def now(self):
        return float(self._now_provider())

    def _read(self, value, default=None):
        entity_id = _entity_id(value)
        if entity_id:
            raw = self.store.get_value(entity_id, default)
            if raw in (None, 'unknown', 'unavailable', 'none', ''):
                return default
            return raw
        return default if value is None else value

    def _age(self, entity_ref, fallback=999999.0):
        entity_id = _entity_id(entity_ref)
        if not entity_id:
            return float(fallback)
        last = self.store.last_update_ts.get(entity_id)
        if last is None:
            return float(fallback)
        return max(0.0, self.now - float(last))

    def _build_static_config(self):
        static_devices = {}
        for raw_device_id, raw_device in self.devices.items():
            device_id = str(raw_device_id)
            device = _mapping(raw_device)
            caps = _mapping(device.get('capabilities'))
            static_devices[device_id] = {
                'kind': str(device.get('kind') or ''),
                'capabilities': {
                    'can_absorb_w': bool(caps.get('can_absorb_w', False)),
                    'can_produce_w': bool(caps.get('can_produce_w', False)),
                    'supports_primary_consuming_regulation': bool(caps.get('supports_primary_consuming_regulation', False)),
                    'supports_producing_regulation': bool(caps.get('supports_producing_regulation', False)),
                },
            }
        return {
            'ems': {
                'runtime_sources': {
                    key: {'entity_id': entity_id}
                    for key, entity_id in _PACKET_ENTITY_IDS.items()
                },
                'policy_engine': dict(_mapping(self.ems.get('policy_engine'))),
                'role_constraints': dict(_mapping(self.ems.get('role_constraints'))),
                'devices': static_devices,
            }
        }

    def _profiles(self):
        profiles = _mapping(self.ems.get('profiles'))
        return {
            'control': str(self._read(profiles.get('control'), 'AUTOMATIC')),
            'goal': str(self._read(profiles.get('goal'), 'NET_ZERO')),
            'forecast': str(self._read(profiles.get('forecast'), 'NONE')),
            'guard': str(self._read(profiles.get('guard'), 'NORMAL_LIMITS')),
        }

    def _global_config(self):
        cfg = _mapping(self.ems.get('global_config'))
        return {
            'deadband_w': self._read(cfg.get('deadband_w'), 50.0),
            'ramp_w': self._read(cfg.get('ramp_w'), 1000.0),
            'strict_limit_w': self._read(cfg.get('strict_limit_w'), 4600.0),
            'default_sp_w': self._read(cfg.get('default_sp_w'), 100.0),
            'surplus_freeze_s': self._read(cfg.get('surplus_freeze_s'), 30.0),
            'battery_heartbeat_timeout_s': self._read(cfg.get('battery_heartbeat_timeout_s'), 360.0),
            'haeo_stale_timeout_s': self._read(cfg.get('haeo_stale_timeout_s'), 300.0),
            'nz_battery_floor_default_w': self._read(cfg.get('nz_battery_floor_default_w'), 100.0),
            'nz_battery_floor_ev_active_w': self._read(cfg.get('nz_battery_floor_ev_active_w'), 0.0),
            'primary_consuming_device_ids': tuple(
                dict.fromkeys(
                    str(self._read(item, '') or '')
                    for item in tuple(cfg.get('primary_consuming_device_ids') or ())
                    if str(self._read(item, '') or '')
                )
            ),
        }

    def _device_policy_packet(self):
        result = {}
        for device_id in self.topology.device_order:
            device = _mapping(self.devices.get(device_id))
            kind = str(device.get('kind') or '')
            caps = _mapping(device.get('capabilities'))
            policy = _mapping(device.get('policy'))
            adapter = _mapping(device.get('adapter'))
            packet_device = {
                'capabilities': {
                    'uses_hard_off_lifecycle': bool(self._read(caps.get('uses_hard_off_lifecycle'), kind == 'EV_CHARGER')),
                    'supports_primary_consuming_regulation': bool(self._read(caps.get('supports_primary_consuming_regulation'), False)),
                    'supports_producing_regulation': bool(self._read(caps.get('supports_producing_regulation'), False)),
                    'min_absorb_w': self._read(caps.get('min_absorb_w'), 0.0),
                    'max_absorb_w': self._read(caps.get('max_absorb_w'), 0.0),
                    'min_produce_w': self._read(caps.get('min_produce_w'), 0.0),
                    'max_produce_w': self._read(caps.get('max_produce_w'), 0.0),
                    'step_w': self._read(caps.get('step_w'), 1.0),
                },
                'policy': {
                    'priority': self._read(policy.get('priority'), 0),
                    'producing_priority': self._read(policy.get('producing_priority'), 0),
                    'surplus_allowed': bool(self._read(policy.get('surplus_allowed'), False)),
                    'surplus_dispatch_mode': str(self._read(policy.get('surplus_dispatch_mode'), 'fixed' if kind == 'RELAY' else 'max_absorb')),
                },
            }
            if kind == 'BATTERY':
                guard = _mapping(device.get('guard'))
                packet_device['policy']['default_min_absorb_w'] = self._read(policy.get('default_min_absorb_w'), 0.0)
                packet_device['guard'] = {
                    'protect_soc': self._read(guard.get('protect_soc'), 100.0),
                    'protect_soc_recovery_margin': self._read(guard.get('protect_soc_recovery_margin'), 0.0),
                    'protect_min_cell_voltage_v': self._read(guard.get('protect_min_cell_voltage_v'), 99.0),
                    'protect_min_absorb_w': self._read(guard.get('protect_min_absorb_w'), 0.0),
                }
            elif kind == 'EV_CHARGER':
                packet_device['policy'].update({
                    'force_on': bool(self._read(policy.get('force_on'), False)),
                    'low_pv_threshold_w': self._read(policy.get('low_pv_threshold_w'), 1600.0),
                    'hard_off_low_pv_cycles': self._read(policy.get('hard_off_low_pv_cycles'), 15),
                    'hard_off_release_cycles': self._read(policy.get('hard_off_release_cycles'), 100),
                })
                packet_device['adapter_config'] = {
                    'current_step_a': self._read(adapter.get('current_step_a'), 1.0),
                    'phases': self._read(adapter.get('phases'), 1),
                    'voltage_v': self._read(adapter.get('voltage_v'), 230.0),
                }
            elif kind == 'RELAY':
                packet_device['policy']['force_on'] = bool(self._read(policy.get('force_on'), False))
            result[device_id] = packet_device
        return result

    def _entity_registry(self):
        state = _mapping(self.ems.get('state'))
        state_registry = {}
        for key in ('surplus_freeze_until', 'active_surplus_devices'):
            entity_id = _entity_id(state.get(key))
            if entity_id:
                state_registry[key] = entity_id
        device_registry = {}
        for device_id in self.topology.device_order:
            device = _mapping(self.devices.get(device_id))
            kind = str(device.get('kind') or '')
            adapter = _mapping(device.get('adapter'))
            fields = ('target_w',) if kind == 'BATTERY' else ('enabled', 'current_a') if kind == 'EV_CHARGER' else ('enabled',) if kind == 'RELAY' else ()
            mapped = {}
            for field in fields:
                entity_id = _entity_id(adapter.get(field))
                if entity_id:
                    mapped[field] = entity_id
            device_registry[device_id] = mapped
        return {'state': state_registry, 'devices': device_registry}

    def build_policy_config_packet(self):
        content = {
            'schema_version': RUNTIME_SCHEMA_VERSION,
            'profiles': self._profiles(),
            'config': self._global_config(),
            'devices': self._device_policy_packet(),
            'entity_registry': self._entity_registry(),
        }
        key = json.dumps(content, sort_keys=True, separators=(',', ':'), default=str)
        if key != self._last_policy_key:
            self._revision += 1
            self._last_policy_key = key
        packet = dict(content)
        packet['revision'] = self._revision
        return packet

    def build_measurements_packet(self):
        runtime = _mapping(self.ems.get('runtime'))
        batteries = {}
        ev = {}
        relays = {}
        for device_id in self.topology.battery_device_ids:
            battery = _mapping(self.devices.get(device_id))
            guard = _mapping(battery.get('guard'))
            adapter = _mapping(battery.get('adapter'))
            batteries[device_id] = {
                'soc': self._read(guard.get('soc'), 50.0),
                'min_cell_voltage_v': self._read(guard.get('min_cell_voltage_v'), 3.2),
                'heartbeat': self._read(guard.get('heartbeat'), 0.0),
                'heartbeat_age_s': self._age(guard.get('heartbeat')),
                'current_setpoint_w': self._read(adapter.get('target_w'), 100.0),
            }
        for device_id in self.topology.ev_device_ids:
            dev_adapter = _mapping(_mapping(self.devices.get(device_id)).get('adapter'))
            ev[device_id] = {
                'enabled': bool(self._read(dev_adapter.get('enabled'), False)),
                'current_a': self._read(dev_adapter.get('current_a'), 0.0),
            }
        for device_id in self.topology.relay_device_ids:
            dev_adapter = _mapping(_mapping(self.devices.get(device_id)).get('adapter'))
            relays[device_id] = {'enabled': bool(self._read(dev_adapter.get('enabled'), False))}
        return {
            'schema_version': RUNTIME_SCHEMA_VERSION,
            'grid_power_w': self._read(runtime.get('grid_power_w'), 0.0),
            'quarter_energy_balance_kwh': self._read(runtime.get('quarter_energy_balance_kwh'), 0.0),
            'pv_power_w': self._read(runtime.get('pv_power_w'), 0.0),
            'batteries': batteries,
            'ev': ev,
            'relays': relays,
        }

    def build_policy_state_packet(self):
        state = _mapping(self.ems.get('state'))
        active_entity = _entity_id(state.get('active_surplus_devices'))
        active_ids = []
        if active_entity:
            active_ids = _parse_ids(self.store.get_attr(active_entity, 'device_ids', None))
            if not active_ids:
                active_ids = _parse_ids(self.store.get_value(active_entity, None))
        freeze_value = _timestamp_or_none(self._read(state.get('surplus_freeze_until'), None))
        policy_state_entity = 'sensor.ems_policy_state_pyscript'
        policy_attrs = self.store.get_attr(policy_state_entity, None, {}) or {}
        haeo = _mapping(self.ems.get('haeo'))
        haeo_devices = {}
        for device_id, mapping in _mapping(haeo.get('devices')).items():
            mapping = _mapping(mapping)
            haeo_devices[str(device_id)] = {
                'state_kw': self._read(mapping.get('power_active'), 0.0),
                'age_s': self._age(mapping.get('fresh_source')),
            }
        return {
            'schema_version': RUNTIME_SCHEMA_VERSION,
            'surplus': {
                'freeze_until': freeze_value,
                'active_device_ids': active_ids,
                'previous_device_states': policy_attrs.get('previous_device_states', {}) or {},
            },
            'haeo': {
                'devices': haeo_devices,
            },
            'policy': {
                'haeo_nz_quarter_key': str(policy_attrs.get('haeo_nz_quarter_key', '') or ''),
                'haeo_nz_primary_consuming_device_id': str(policy_attrs.get('haeo_nz_primary_consuming_device_id', '') or ''),
                'prev_force_on_device_ids': list(policy_attrs.get('prev_force_on_device_ids', []) or []),
            },
        }


    def snapshot(self):
        policy = self.build_policy_config_packet()
        measurements = self.build_measurements_packet()
        state = self.build_policy_state_packet()
        runtime_config, _cache_hit = parse_policy_config_cached(
            self.topology,
            policy,
            self.policy_engine_config,
        )
        frame = parse_tick_frame_v5(
            self.topology,
            runtime_config,
            measurements,
            state,
            self.now,
        )
        runtime_entities = build_runtime_entities_from_policy_config_packet(policy, self.topology)
        runtime_entities['_direct_tick_frame'] = frame
        return ScenarioPacketSnapshot(
            policy_config=policy,
            measurements=measurements,
            policy_state=state,
            runtime_config=runtime_config,
            tick_frame=frame,
            runtime_entities=runtime_entities,
        )

    def read_runtime_context(self, *args, **kwargs):
        snap = self.snapshot()
        return snap.runtime_config, snap.runtime_entities

    def read_runtime_entities(self, *args, **kwargs):
        policy = self.build_policy_config_packet()
        return build_runtime_entities_from_policy_config_packet(policy, self.topology)

    @staticmethod
    def config_trace_attrs():
        return {
            'config_source': 'direct_tick_frame_v5_e2e',
            'config_runtime_enabled': True,
            'config_runtime_ok': True,
            'config_runtime_reason': 'e2e_direct_packet_fixture',
            'config_runtime_mismatches': [],
        }
