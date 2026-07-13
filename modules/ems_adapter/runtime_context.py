import os
import time

try:
    pyscript_executor
except NameError:
    def pyscript_executor(func):
        return func


from ems_adapter.config_loader import load_and_validate_grouped_ems_config
from ems_adapter.direct_runtime import (
    RUNTIME_SCHEMA_VERSION,
    RuntimePacketSchemaError,
    build_static_topology,
    parse_policy_config_cached,
    parse_tick_frame_v5,
    reset_direct_runtime_cache,
)
from ems_core.domain.models import CorePolicyEngineConfig
from ems_adapter.ha_adapter import get_bool as _get_bool
from ems_adapter.ha_adapter import get_float as _get_float
from ems_adapter.ha_adapter import get_int as _get_int
from ems_adapter.ha_adapter import get_str as _get_str
from ems_adapter.ha_adapter import get_attrs as _get_attrs
from ems_core.domain.ev_power import (
    ev_current_a_to_power_w,
    ev_max_current_a_from_max_absorb_w,
    ev_min_current_a_from_min_absorb_w,
    ev_per_amp_w,
)
from ems_core.domain.constants import (
    CANONICAL_DIAGNOSTICS_OUTPUTS,
    CANONICAL_POLICY_OUTPUTS,
)


# Production default: keep runtime-context detailed timings/audit off.
# The policy runner can still measure total tick duration around this call.
RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED = True


def set_runtime_context_detailed_metrics_enabled(enabled):
    global RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED
    RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED = bool(enabled)


def runtime_context_detailed_metrics_enabled():
    return bool(RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED)


def _runtime_context_profile_started_ts():
    if not RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED:
        return 0.0
    return time.time()


_GROUPED_CONFIG_STATUS = {
    'enabled': False,
    'ok': None,
    'source': 'grouped_config',
}

_DEFAULT_GROUPED_CONFIG_PATH = '/config/EMS_config.yaml'
_MAX_VALIDATION_ISSUES_IN_ERROR = 8
_RUNTIME_CONTEXT_CONFIG_CACHE = {
    'path': None,
    'mtime_ns': None,
    'size': None,
    'config': None,
    'validation': None,
    'static_topology': None,
    'policy_engine_config': None,
    'hits': 0,
    'misses': 0,
}
_RUNTIME_CONTEXT_LAST_METRICS = {
    'policy_engine_config_signature_ms': 0,
    'policy_engine_static_context_cache_hit': False,
    'policy_engine_static_context_cache_hits': 0,
    'policy_engine_static_context_cache_misses': 0,
    'policy_engine_static_context_build_ms': 0,
    'policy_engine_runtime_entity_registry_ms': 0,
    'policy_engine_runtime_packet_reads': 0,
    'policy_engine_runtime_packet_read_ms': 0,
    'policy_engine_runtime_packet_parse_ms': 0,
    'policy_engine_runtime_packet_missing_fields': 0,
    'policy_engine_runtime_packet_schema_version': 0,
    'policy_engine_runtime_policy_config_revision': 0,
    'policy_engine_runtime_policy_config_cache_hit': False,
    'policy_engine_runtime_policy_config_parse_ms': 0,
    'policy_engine_runtime_tick_frame_parse_ms': 0,
    'policy_engine_direct_runtime_total_ms': 0,
}

def _reset_runtime_context_config_cache():
    reset_direct_runtime_cache()
    _RUNTIME_CONTEXT_CONFIG_CACHE.clear()
    _RUNTIME_CONTEXT_CONFIG_CACHE.update(
        {
            'path': None,
            'mtime_ns': None,
            'size': None,
            'config': None,
            'validation': None,
            'static_topology': None,
            'policy_engine_config': None,
            'hits': 0,
            'misses': 0,
        }
    )
    _reset_runtime_context_metrics()


def _reset_runtime_context_metrics():
    _RUNTIME_CONTEXT_LAST_METRICS.clear()
    _RUNTIME_CONTEXT_LAST_METRICS.update(
        {
            'policy_engine_config_signature_ms': 0,
            'policy_engine_static_context_cache_hit': False,
            'policy_engine_static_context_cache_hits': 0,
            'policy_engine_static_context_cache_misses': 0,
            'policy_engine_static_context_build_ms': 0,
            'policy_engine_runtime_entity_registry_ms': 0,
            'policy_engine_runtime_packet_reads': 0,
            'policy_engine_runtime_packet_read_ms': 0,
            'policy_engine_runtime_packet_parse_ms': 0,
            'policy_engine_runtime_packet_missing_fields': 0,
            'policy_engine_runtime_packet_schema_version': 0,
            'policy_engine_runtime_policy_config_revision': 0,
            'policy_engine_runtime_policy_config_cache_hit': False,
            'policy_engine_runtime_policy_config_parse_ms': 0,
            'policy_engine_runtime_tick_frame_parse_ms': 0,
            'policy_engine_direct_runtime_total_ms': 0,
        }
    )


@pyscript_executor
def _grouped_config_file_signature(path):
    stat_result = os.stat(path)
    return stat_result.st_mtime_ns, stat_result.st_size


def _policy_engine_config_from_grouped_config(grouped_config):
    ems = grouped_config.get('ems', {}) if isinstance(grouped_config, dict) else {}
    values = ems.get('policy_engine', {}) if isinstance(ems, dict) else {}
    values = values if isinstance(values, dict) else {}
    return CorePolicyEngineConfig(
        interval_seconds=float(values.get('interval_seconds', 5.0) or 5.0),
        diagnostics_interval_seconds=float(values.get('diagnostics_interval_seconds', 30.0) or 30.0),
    )


def _load_grouped_config_cached(path):
    mtime_ns, size = _grouped_config_file_signature(path)
    if (
        _RUNTIME_CONTEXT_CONFIG_CACHE.get('path') == path
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('mtime_ns') == mtime_ns
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('size') == size
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('config') is not None
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('validation') is not None
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('static_topology') is not None
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('policy_engine_config') is not None
    ):
        _RUNTIME_CONTEXT_CONFIG_CACHE['hits'] = int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('hits', 0) or 0) + 1
        return (
            _RUNTIME_CONTEXT_CONFIG_CACHE['config'],
            _RUNTIME_CONTEXT_CONFIG_CACHE['validation'],
            _RUNTIME_CONTEXT_CONFIG_CACHE['static_topology'],
            _RUNTIME_CONTEXT_CONFIG_CACHE['policy_engine_config'],
            True,
            0,
        )

    build_started_ts = time.time()
    grouped_config, validation = load_and_validate_grouped_ems_config(path)
    static_topology = None
    policy_engine_config = None
    if validation.ok:
        ems = grouped_config.get('ems', {}) if isinstance(grouped_config, dict) else {}
        if isinstance(ems, dict) and isinstance(ems.get('runtime_sources'), dict):
            static_topology = build_static_topology(grouped_config)
        policy_engine_config = _policy_engine_config_from_grouped_config(grouped_config)
    static_context_build_ms = _elapsed_ms(build_started_ts, time.time())
    _RUNTIME_CONTEXT_CONFIG_CACHE['misses'] = int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('misses', 0) or 0) + 1
    _RUNTIME_CONTEXT_CONFIG_CACHE.update(
        {
            'path': path,
            'mtime_ns': mtime_ns,
            'size': size,
            'config': grouped_config,
            'validation': validation,
            'static_topology': static_topology,
            'policy_engine_config': policy_engine_config,
        }
    )
    return (
        grouped_config,
        validation,
        static_topology,
        policy_engine_config,
        False,
        static_context_build_ms,
    )


def _elapsed_ms(started_ts, ended_ts):
    return int(round((ended_ts - started_ts) * 1000.0))


def runtime_context_metrics_attrs():
    if not RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED:
        return {}
    return dict(_RUNTIME_CONTEXT_LAST_METRICS)


def _read_runtime_packet_attrs(read_attrs, entity_id, source_name):
    source_path = str(source_name) + '.source_entity'
    if not callable(read_attrs):
        raise RuntimePacketSchemaError(
            source_path,
            'attribute reader unavailable for ' + str(entity_id),
        )
    attrs = read_attrs(str(entity_id), {})
    if not isinstance(attrs, dict):
        raise RuntimePacketSchemaError(
            source_path,
            'source ' + str(entity_id) + ' did not return an attribute mapping',
        )
    if 'schema_version' not in attrs:
        raise RuntimePacketSchemaError(
            str(source_name) + '.schema_version',
            'missing from source entity ' + str(entity_id),
        )
    return attrs


def read_runtime_packets(read_attrs, static_topology):
    started_ts = time.time()
    packets = {}
    sources = (
        ('policy_config', static_topology.policy_config_entity_id),
        ('measurements', static_topology.measurements_entity_id),
        ('policy_state', static_topology.policy_state_entity_id),
    )
    for source_name, entity_id in sources:
        packets[source_name] = _read_runtime_packet_attrs(read_attrs, entity_id, source_name)
    return packets, {
        'reads': 3,
        'read_ms': _elapsed_ms(started_ts, time.time()),
        'schema_version': RUNTIME_SCHEMA_VERSION,
    }


def _set_grouped_config_status(status):
    _GROUPED_CONFIG_STATUS.clear()
    _GROUPED_CONFIG_STATUS.update(status)


def _format_validation_issues(issues, limit=_MAX_VALIDATION_ISSUES_IN_ERROR):
    formatted = []
    for issue in tuple(issues or ())[:limit]:
        path = getattr(issue, 'path', '') or '<unknown>'
        message = getattr(issue, 'message', '') or 'validation error'
        formatted.append(f'{path}: {message}')
    remaining = max(0, len(tuple(issues or ())) - len(formatted))
    if remaining:
        formatted.append(f'... and {remaining} more')
    return tuple(formatted)


def _config_mismatches(left_cfg, right_cfg):
    fields = getattr(left_cfg, '__dataclass_fields__', {})
    mismatches = []
    for field_name in fields:
        if getattr(left_cfg, field_name) != getattr(right_cfg, field_name):
            mismatches.append(field_name)
    return tuple(mismatches)


def _grouped_config_production_ready(status):
    if not bool(status.get('enabled', False)):
        return False, 'not_configured'
    if status.get('ok') is not True:
        return False, status.get('reason', 'not_matched') or 'not_matched'
    if status.get('source') != 'grouped_config':
        return False, 'source_not_grouped'
    return True, 'ready'


def config_trace_attrs():
    status = dict(_GROUPED_CONFIG_STATUS)
    production_ready, production_ready_reason = _grouped_config_production_ready(status)
    attrs = {
        'config_source': status.get('source', 'grouped_config'),
        'config_runtime_enabled': bool(status.get('enabled', False)),
        'config_runtime_ok': status.get('ok'),
        'config_runtime_reason': status.get('reason', ''),
        'config_grouped_production_ready': production_ready,
        'config_grouped_production_ready_reason': production_ready_reason,
    }
    if 'path' in status:
        attrs['config_grouped_path'] = status['path']
    if 'default_path' in status:
        attrs['config_grouped_default_path'] = status['default_path']
    if 'issues' in status:
        attrs['config_runtime_issues'] = status['issues']
    if 'mismatches' in status:
        attrs['config_runtime_mismatches'] = status['mismatches']
    return attrs


def _read_grouped_runtime_candidate(read_bool, read_float, read_int, read_str, read_attrs=None):
    path = os.environ.get('EMS_GROUPED_CONFIG_PATH', '').strip() or _DEFAULT_GROUPED_CONFIG_PATH
    try:
        signature_started_ts = _runtime_context_profile_started_ts()
        (
            grouped_config,
            validation,
            static_topology,
            policy_engine_cfg,
            cache_hit,
            static_context_build_ms,
        ) = _load_grouped_config_cached(path)
        if RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED:
            config_signature_ms = _elapsed_ms(signature_started_ts, time.time()) - max(0, int(static_context_build_ms))
            config_signature_ms = max(0, config_signature_ms)
        else:
            config_signature_ms = 0
    except Exception as exc:
        if RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED:
            _RUNTIME_CONTEXT_LAST_METRICS.update(
                {
                    'policy_engine_static_context_cache_hit': False,
                    'policy_engine_static_context_cache_hits': int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('hits', 0) or 0),
                    'policy_engine_static_context_cache_misses': int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('misses', 0) or 0),
                }
            )
        _set_grouped_config_status(
            {
                'enabled': True,
                'ok': False,
                'source': 'grouped_config',
                'path': path,
                'reason': type(exc).__name__,
            }
        )
        raise

    if not validation.ok:
        issue_path_values = []
        for issue in validation.errors:
            issue_path_values.append(issue.path)
        issue_paths = tuple(issue_path_values)
        issue_details = _format_validation_issues(validation.errors)
        _set_grouped_config_status(
            {
                'enabled': True,
                'ok': False,
                'source': 'grouped_config',
                'path': path,
                'reason': 'validation_failed',
                'issues': issue_paths,
                'issue_details': issue_details,
            }
        )
        detail_text = '; '.join(issue_details) if issue_details else 'unknown validation error'
        raise ValueError(f'Grouped EMS config validation failed: {detail_text}')

    if static_topology is None:
        _set_grouped_config_status(
            {
                'enabled': True,
                'ok': False,
                'source': 'grouped_config',
                'path': path,
                'reason': 'direct_runtime_packets_required',
            }
        )
        raise ValueError(
            'Direct runtime packet configuration required: ems.runtime_sources must define '
            'policy_config, measurements and policy_state.'
        )

    direct_started_ts = _runtime_context_profile_started_ts()
    runtime_packets, packet_read_metrics = read_runtime_packets(read_attrs, static_topology)
    registry_started_ts = _runtime_context_profile_started_ts()
    direct_entities = build_runtime_entities_from_policy_config_packet(
        runtime_packets.get('policy_config', {}),
        static_topology,
    )
    runtime_entity_registry_ms = _elapsed_ms(registry_started_ts, time.time())

    config_parse_started_ts = _runtime_context_profile_started_ts()
    runtime_cfg, config_cache_hit = parse_policy_config_cached(
        static_topology,
        runtime_packets.get('policy_config', {}),
        policy_engine_cfg,
    )
    config_parse_ms = _elapsed_ms(config_parse_started_ts, time.time())

    frame_parse_started_ts = _runtime_context_profile_started_ts()
    tick_frame = parse_tick_frame_v5(
        static_topology,
        runtime_cfg,
        runtime_packets.get('measurements', {}),
        runtime_packets.get('policy_state', {}),
        time.time(),
    )
    frame_parse_ms = _elapsed_ms(frame_parse_started_ts, time.time())
    direct_total_ms = _elapsed_ms(direct_started_ts, time.time())

    packet_reads = int(packet_read_metrics.get('reads', 0) or 0)
    packet_read_ms = int(packet_read_metrics.get('read_ms', 0) or 0)
    if RUNTIME_CONTEXT_DETAILED_METRICS_ENABLED:
        _RUNTIME_CONTEXT_LAST_METRICS.update(
            {
                'policy_engine_config_signature_ms': config_signature_ms,
                'policy_engine_static_context_cache_hit': bool(cache_hit),
                'policy_engine_static_context_cache_hits': int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('hits', 0) or 0),
                'policy_engine_static_context_cache_misses': int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('misses', 0) or 0),
                'policy_engine_static_context_build_ms': max(0, int(static_context_build_ms)),
                'policy_engine_runtime_packet_reads': packet_reads,
                'policy_engine_runtime_packet_read_ms': max(0, packet_read_ms),
                'policy_engine_runtime_packet_schema_version': RUNTIME_SCHEMA_VERSION,
                'policy_engine_runtime_packet_parse_ms': max(0, config_parse_ms + frame_parse_ms),
                'policy_engine_runtime_packet_missing_fields': 0,
                'policy_engine_runtime_policy_config_revision': int(runtime_cfg.revision),
                'policy_engine_runtime_policy_config_cache_hit': bool(config_cache_hit),
                'policy_engine_runtime_policy_config_parse_ms': max(0, config_parse_ms),
                'policy_engine_runtime_tick_frame_parse_ms': max(0, frame_parse_ms),
                'policy_engine_runtime_entity_registry_ms': max(0, int(runtime_entity_registry_ms)),
                'policy_engine_direct_runtime_total_ms': max(0, direct_total_ms),
            }
        )
    else:
        _RUNTIME_CONTEXT_LAST_METRICS.clear()

    direct_entities['_direct_tick_frame'] = tick_frame
    return runtime_cfg, direct_entities, {
        'enabled': True,
        'ok': None,
        'source': 'grouped_config',
        'path': path,
        'reason': 'loaded',
        'config_cache_hit': cache_hit,
        'runtime_packet_mode': True,
        'runtime_schema_version': RUNTIME_SCHEMA_VERSION,
        'policy_config_revision': int(runtime_cfg.revision),
    }, grouped_config


def _runtime_entity_id(value):
    if not isinstance(value, str):
        return None
    entity_id = value.strip()
    if not entity_id or '.' not in entity_id:
        return None
    return entity_id


def build_runtime_entities_from_policy_config_packet(packet, static_topology):
    """Build the writer/applier registry from the template-owned policy-config packet.

    EMS_config.yaml remains static topology only. Missing or invalid packet mappings
    are deliberately omitted so writer/applier callers fail closed without falling
    back to ENT globals or hardcoded actuator entities.
    """
    packet = packet if isinstance(packet, dict) else {}
    registry = packet.get('entity_registry', {})
    registry = registry if isinstance(registry, dict) else {}
    state_registry = registry.get('state', {})
    state_registry = state_registry if isinstance(state_registry, dict) else {}
    device_registry = registry.get('devices', {})
    device_registry = device_registry if isinstance(device_registry, dict) else {}

    ent = {
        'device_policies': CANONICAL_POLICY_OUTPUTS['device_policies'],
        'dispatch_command': CANONICAL_POLICY_OUTPUTS['dispatch_command'],
        'policy_state': CANONICAL_POLICY_OUTPUTS['policy_state'],
        'policy_diagnostics': CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics'],
        'actuator_writer_trace': CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace'],
        'dispatch_state_applier_trace': CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace'],
    }
    for key in ('surplus_freeze_until', 'active_surplus_devices'):
        entity_id = _runtime_entity_id(state_registry.get(key))
        if entity_id:
            ent[key] = entity_id

    devices = {}
    device_order = tuple(getattr(static_topology, 'device_order', ()) or ())
    kind_by_id = dict(getattr(static_topology, 'device_kind_by_id', {}) or {})
    for raw_device_id in device_order:
        device_id = str(raw_device_id)
        kind = str(kind_by_id.get(device_id, '') or '')
        mapped = device_registry.get(device_id, {})
        mapped = mapped if isinstance(mapped, dict) else {}
        entry = {'device_id': device_id, 'kind': kind}
        expected_fields = ()
        if kind == 'BATTERY':
            expected_fields = ('target_w',)
        elif kind == 'EV_CHARGER':
            expected_fields = ('enabled', 'current_a')
        elif kind == 'RELAY':
            expected_fields = ('enabled',)
        for field_name in expected_fields:
            entity_id = _runtime_entity_id(mapped.get(field_name))
            if entity_id:
                entry[field_name] = entity_id
        devices[device_id] = entry

    ent['devices'] = devices
    ent['relay_device_ids'] = tuple(getattr(static_topology, 'relay_device_ids', ()) or ())
    ent['ev_device_ids'] = tuple(getattr(static_topology, 'ev_device_ids', ()) or ())
    return ent

def read_runtime_context(read_bool=None, read_float=None, read_int=None, read_str=None, read_attrs=None):
    read_bool = read_bool or _get_bool
    read_float = read_float or _get_float
    read_int = read_int or _get_int
    read_str = read_str or _get_str
    read_attrs = read_attrs or _get_attrs
    grouped_cfg, grouped_entities, status, _grouped_config = _read_grouped_runtime_candidate(read_bool, read_float, read_int, read_str, read_attrs)
    status['ok'] = True
    status['mismatches'] = ()
    status['strict'] = True
    status['source'] = 'grouped_config'
    status['reason'] = 'loaded'
    _set_grouped_config_status(status)
    return grouped_cfg, grouped_entities


def read_core_config(read_bool=None, read_float=None, read_int=None, read_str=None):
    cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    return cfg


def read_runtime_entities(read_bool=None, read_float=None, read_int=None, read_str=None, read_attrs=None):
    del read_bool, read_float, read_int, read_str
    read_attrs = read_attrs or _get_attrs
    path = os.environ.get('EMS_GROUPED_CONFIG_PATH', '').strip() or _DEFAULT_GROUPED_CONFIG_PATH
    _grouped_config, validation, static_topology, _policy_engine_cfg, _cache_hit, _build_ms = _load_grouped_config_cached(path)
    if not validation.ok:
        detail_text = '; '.join(_format_validation_issues(validation.errors)) or 'unknown validation error'
        raise ValueError(f'Grouped EMS config validation failed: {detail_text}')
    if static_topology is None:
        raise ValueError('Direct runtime packet configuration required for runtime entity registry.')
    packet = _read_runtime_packet_attrs(
        read_attrs,
        static_topology.policy_config_entity_id,
        'policy_config',
    )
    return build_runtime_entities_from_policy_config_packet(packet, static_topology)
