import os
import time

from ems_adapter.config_loader import (
    build_policy_context_view,
    compile_dynamic_runtime_read_plan,
    compile_core_config_plan_from_grouped_config,
    runtime_alias_index,
    load_and_validate_grouped_ems_config,
)
from ems_adapter.ha_adapter import get_bool as _get_bool
from ems_adapter.ha_adapter import get_float as _get_float
from ems_adapter.ha_adapter import get_int as _get_int
from ems_adapter.ha_adapter import get_str as _get_str
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


_GROUPED_CONFIG_DUAL_READ_STATUS = {
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
    'grouped_entities': None,
    'core_config_plan': None,
    'dynamic_runtime_read_plan': None,
    'hits': 0,
    'misses': 0,
}
_RUNTIME_CONTEXT_LAST_METRICS = {
    'policy_engine_config_signature_ms': 0,
    'policy_engine_static_context_cache_hit': False,
    'policy_engine_static_context_cache_hits': 0,
    'policy_engine_static_context_cache_misses': 0,
    'policy_engine_static_context_build_ms': 0,
    'policy_engine_dynamic_config_reads_ms': 0,
    'policy_engine_dynamic_config_logical_reads': 0,
    'policy_engine_dynamic_config_reader_total_ms': 0,
    'policy_engine_dynamic_config_reader_overhead_ms': 0,
    'policy_engine_dynamic_config_audit_overhead_ms': 0,
    'policy_engine_dynamic_config_full_audit_collected': False,
    'policy_engine_dynamic_read_plan_apply_total_ms': 0,
    'policy_engine_dynamic_read_underlying_ha_ms': 0,
    'policy_engine_dynamic_read_wrapper_overhead_ms': 0,
    'policy_engine_dynamic_read_audit_update_ms': 0,
    'policy_engine_dynamic_read_audit_build_ms': 0,
    'policy_engine_dynamic_read_audit_sort_ms': 0,
    'policy_engine_runtime_entity_registry_ms': 0,
    'policy_engine_core_config_build_ms': 0,
    'policy_engine_core_config_materialize_total_ms': 0,
    'policy_engine_core_config_profiles_global_runtime_state_ms': 0,
    'policy_engine_core_config_devices_ms': 0,
    'policy_engine_core_config_home_battery_ms': 0,
    'policy_engine_core_config_haeo_ms': 0,
    'policy_engine_core_config_role_constraints_ms': 0,
    'policy_engine_core_config_derived_fields_ms': 0,
    'policy_engine_dynamic_runtime_snapshot_ms': 0,
    'policy_engine_policy_context_view_ms': 0,
    'policy_engine_dynamic_config_unique_reads': 0,
    'policy_engine_dynamic_config_audit_entries': 0,
    'policy_engine_dynamic_runtime_snapshot_dict_nodes': 0,
    'policy_engine_dynamic_runtime_snapshot_tuple_nodes': 0,
    'policy_engine_dynamic_runtime_snapshot_dynamic_refs_seen': 0,
    'policy_engine_dynamic_runtime_snapshot_dynamic_refs_unique': 0,
    'policy_engine_dynamic_runtime_snapshot_dynamic_ref_cache_hits': 0,
    'policy_engine_core_config_unexplained_overhead_ms': 0,
}
_RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT = {
    'entries': (),
    'total_reads': 0,
    'underlying_reads': 0,
    'cache_hits': 0,
    'full_audit_collected': False,
}
_RUNTIME_CONTEXT_AUDIT_STATE = {
    'runs_seen': 0,
}


def _reset_runtime_context_config_cache():
    _RUNTIME_CONTEXT_CONFIG_CACHE.clear()
    _RUNTIME_CONTEXT_CONFIG_CACHE.update(
        {
            'path': None,
            'mtime_ns': None,
            'size': None,
            'config': None,
            'validation': None,
            'grouped_entities': None,
            'core_config_plan': None,
            'dynamic_runtime_read_plan': None,
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
            'policy_engine_dynamic_config_reads_ms': 0,
            'policy_engine_dynamic_config_logical_reads': 0,
            'policy_engine_dynamic_config_reader_total_ms': 0,
            'policy_engine_dynamic_config_reader_overhead_ms': 0,
            'policy_engine_dynamic_config_audit_overhead_ms': 0,
            'policy_engine_dynamic_config_full_audit_collected': False,
            'policy_engine_dynamic_read_plan_apply_total_ms': 0,
            'policy_engine_dynamic_read_underlying_ha_ms': 0,
            'policy_engine_dynamic_read_wrapper_overhead_ms': 0,
            'policy_engine_dynamic_read_audit_update_ms': 0,
            'policy_engine_dynamic_read_audit_build_ms': 0,
            'policy_engine_dynamic_read_audit_sort_ms': 0,
            'policy_engine_runtime_entity_registry_ms': 0,
            'policy_engine_core_config_build_ms': 0,
            'policy_engine_core_config_materialize_total_ms': 0,
            'policy_engine_core_config_profiles_global_runtime_state_ms': 0,
            'policy_engine_core_config_devices_ms': 0,
            'policy_engine_core_config_home_battery_ms': 0,
            'policy_engine_core_config_haeo_ms': 0,
            'policy_engine_core_config_role_constraints_ms': 0,
            'policy_engine_core_config_derived_fields_ms': 0,
            'policy_engine_dynamic_runtime_snapshot_ms': 0,
            'policy_engine_policy_context_view_ms': 0,
            'policy_engine_dynamic_config_unique_reads': 0,
            'policy_engine_dynamic_config_audit_entries': 0,
            'policy_engine_dynamic_runtime_snapshot_dict_nodes': 0,
            'policy_engine_dynamic_runtime_snapshot_tuple_nodes': 0,
            'policy_engine_dynamic_runtime_snapshot_dynamic_refs_seen': 0,
            'policy_engine_dynamic_runtime_snapshot_dynamic_refs_unique': 0,
            'policy_engine_dynamic_runtime_snapshot_dynamic_ref_cache_hits': 0,
            'policy_engine_core_config_unexplained_overhead_ms': 0,
        }
    )
    _RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT.clear()
    _RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT.update(
        {
            'entries': (),
            'total_reads': 0,
            'underlying_reads': 0,
            'cache_hits': 0,
            'full_audit_collected': False,
        }
    )


def _grouped_config_file_signature(path):
    stat_result = os.stat(path)
    return stat_result.st_mtime_ns, stat_result.st_size


def _load_grouped_config_cached(path):
    mtime_ns, size = _grouped_config_file_signature(path)
    if (
        _RUNTIME_CONTEXT_CONFIG_CACHE.get('path') == path
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('mtime_ns') == mtime_ns
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('size') == size
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('config') is not None
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('validation') is not None
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('grouped_entities') is not None
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('core_config_plan') is not None
        and _RUNTIME_CONTEXT_CONFIG_CACHE.get('dynamic_runtime_read_plan') is not None
    ):
        _RUNTIME_CONTEXT_CONFIG_CACHE['hits'] = int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('hits', 0) or 0) + 1
        return (
            _RUNTIME_CONTEXT_CONFIG_CACHE['config'],
            _RUNTIME_CONTEXT_CONFIG_CACHE['validation'],
            _RUNTIME_CONTEXT_CONFIG_CACHE['grouped_entities'],
            _RUNTIME_CONTEXT_CONFIG_CACHE['core_config_plan'],
            _RUNTIME_CONTEXT_CONFIG_CACHE['dynamic_runtime_read_plan'],
            True,
            0,
            0,
        )

    build_started_ts = time.time()
    grouped_config, validation = load_and_validate_grouped_ems_config(path)
    grouped_entities = None
    core_config_plan = None
    dynamic_runtime_read_plan = None
    runtime_entity_registry_ms = 0
    if validation.ok:
        registry_started_ts = time.time()
        grouped_entities = build_runtime_entities_from_grouped_config(grouped_config)
        runtime_entity_registry_ms = _elapsed_ms(registry_started_ts, time.time())
        core_config_plan = compile_core_config_plan_from_grouped_config(grouped_config)
        dynamic_runtime_read_plan = compile_dynamic_runtime_read_plan(core_config_plan)
    static_context_build_ms = _elapsed_ms(build_started_ts, time.time())
    _RUNTIME_CONTEXT_CONFIG_CACHE['misses'] = int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('misses', 0) or 0) + 1
    _RUNTIME_CONTEXT_CONFIG_CACHE.update(
        {
            'path': path,
            'mtime_ns': mtime_ns,
            'size': size,
            'config': grouped_config,
            'validation': validation,
            'grouped_entities': grouped_entities,
            'core_config_plan': core_config_plan,
            'dynamic_runtime_read_plan': dynamic_runtime_read_plan,
        }
    )
    return (
        grouped_config,
        validation,
        grouped_entities,
        core_config_plan,
        dynamic_runtime_read_plan,
        False,
        static_context_build_ms,
        runtime_entity_registry_ms,
    )


def _elapsed_ms(started_ts, ended_ts):
    return int(round((ended_ts - started_ts) * 1000.0))


def runtime_context_metrics_attrs():
    return dict(_RUNTIME_CONTEXT_LAST_METRICS)


def runtime_context_dynamic_read_audit():
    return {
        'entries': tuple(_RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT.get('entries', ()) or ()),
        'total_reads': int(_RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT.get('total_reads', 0) or 0),
        'underlying_reads': int(_RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT.get('underlying_reads', 0) or 0),
        'cache_hits': int(_RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT.get('cache_hits', 0) or 0),
        'full_audit_collected': bool(_RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT.get('full_audit_collected', False)),
    }


def _runtime_context_full_audit_sample_every():
    raw = os.environ.get('EMS_RUNTIME_CONTEXT_AUDIT_SAMPLE_EVERY', '').strip()
    if not raw:
        return 20
    try:
        parsed = int(raw)
    except ValueError:
        return 20
    return max(1, parsed)


def _runtime_context_should_collect_full_audit():
    if os.environ.get('PYTEST_CURRENT_TEST'):
        return True
    raw = os.environ.get('EMS_RUNTIME_CONTEXT_FULL_AUDIT', '').strip().lower()
    if raw in ('1', 'true', 'yes', 'on'):
        return True
    _RUNTIME_CONTEXT_AUDIT_STATE['runs_seen'] = int(_RUNTIME_CONTEXT_AUDIT_STATE.get('runs_seen', 0) or 0) + 1
    return int(_RUNTIME_CONTEXT_AUDIT_STATE['runs_seen']) % int(_runtime_context_full_audit_sample_every()) == 0


def _read_grouped_entity(entity_id, default, read_bool, read_float, read_int, read_str):
    if isinstance(default, bool):
        return read_bool(entity_id)
    if isinstance(default, int) and not isinstance(default, bool):
        return read_int(entity_id, default)
    if isinstance(default, float):
        return read_float(entity_id, default)
    return read_str(entity_id, default)


def _set_grouped_config_status(status):
    _GROUPED_CONFIG_DUAL_READ_STATUS.clear()
    _GROUPED_CONFIG_DUAL_READ_STATUS.update(status)


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
    status = dict(_GROUPED_CONFIG_DUAL_READ_STATUS)
    production_ready, production_ready_reason = _grouped_config_production_ready(status)
    attrs = {
        'config_source': status.get('source', 'grouped_config'),
        'config_dual_read_enabled': bool(status.get('enabled', False)),
        'config_dual_read_ok': status.get('ok'),
        'config_dual_read_reason': status.get('reason', ''),
        'config_grouped_production_ready': production_ready,
        'config_grouped_production_ready_reason': production_ready_reason,
    }
    if 'path' in status:
        attrs['config_grouped_path'] = status['path']
    if 'default_path' in status:
        attrs['config_grouped_default_path'] = status['default_path']
    if 'issues' in status:
        attrs['config_dual_read_issues'] = status['issues']
    if 'mismatches' in status:
        attrs['config_dual_read_mismatches'] = status['mismatches']
    return attrs


def _read_grouped_runtime_candidate(read_bool, read_float, read_int, read_str):
    path = os.environ.get('EMS_GROUPED_CONFIG_PATH', '').strip()
    if not path:
        path = _DEFAULT_GROUPED_CONFIG_PATH
    try:
        signature_started_ts = time.time()
        (
            grouped_config,
            validation,
            grouped_entities,
            core_config_plan,
            dynamic_runtime_read_plan,
            cache_hit,
            static_context_build_ms,
            runtime_entity_registry_ms,
        ) = _load_grouped_config_cached(path)
        config_signature_ms = _elapsed_ms(signature_started_ts, time.time()) - max(0, int(static_context_build_ms))
        config_signature_ms = max(0, config_signature_ms)
    except Exception as exc:
        _RUNTIME_CONTEXT_LAST_METRICS.update(
            {
                'policy_engine_static_context_cache_hit': False,
                'policy_engine_static_context_cache_hits': int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('hits', 0) or 0),
                'policy_engine_static_context_cache_misses': int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('misses', 0) or 0),
            }
        )
        status = {
            'enabled': True,
            'ok': False,
            'source': 'grouped_config',
            'path': path,
            'reason': type(exc).__name__,
        }
        _set_grouped_config_status(status)
        raise
    if not validation.ok:
        issue_paths = []
        for issue in validation.errors:
            issue_paths.append(issue.path)
        issue_details = _format_validation_issues(validation.errors)
        status = {
            'enabled': True,
            'ok': False,
            'source': 'grouped_config',
            'path': path,
            'reason': 'validation_failed',
            'issues': tuple(issue_paths),
            'issue_details': issue_details,
        }
        _set_grouped_config_status(status)
        detail_text = '; '.join(issue_details) if issue_details else 'unknown validation error'
        raise ValueError(f'Grouped EMS config validation failed: {detail_text}')

    dynamic_underlying_ha_s = {'value': 0.0}
    dynamic_audit_update_s = {'value': 0.0}
    collect_full_audit = _runtime_context_should_collect_full_audit()
    dynamic_read_audit = {} if collect_full_audit else None
    dynamic_read_totals = {
        'total_reads': 0,
        'underlying_reads': 0,
        'cache_hits': 0,
    }

    def _audit_cache_key(entity_id, default):
        default_type = type(default)
        return (
            str(entity_id),
            default_type,
            default,
        )

    def grouped_reader(entity_id, default):
        started_ts = time.time()
        value = _read_grouped_entity(
            entity_id,
            default,
            read_bool,
            read_float,
            read_int,
            read_str,
        )
        dynamic_underlying_ha_s['value'] += max(0.0, time.time() - started_ts)
        return value

    core_config_started_ts = time.time()
    dynamic_read_plan_apply_started_ts = time.time()
    dynamic_runtime_read_values = []
    unique_reads = tuple(dynamic_runtime_read_plan.get('unique_reads', ()) or ())
    logical_read_counts = tuple(dynamic_runtime_read_plan.get('logical_read_counts', ()) or ())
    for index, read_entry in enumerate(unique_reads):
        entity_id = str(read_entry.get('entity_id', ''))
        default = read_entry.get('default')
        ha_started_ts = time.time()
        value = _read_grouped_entity(
            entity_id,
            default,
            read_bool,
            read_float,
            read_int,
            read_str,
        )
        read_elapsed_s = max(0.0, time.time() - ha_started_ts)
        dynamic_underlying_ha_s['value'] += read_elapsed_s
        dynamic_runtime_read_values.append(value)
        if collect_full_audit and dynamic_read_audit is not None:
            audit_started_ts = time.time()
            logical_read_count = max(1, int(logical_read_counts[index]))
            duplicate_count = max(0, logical_read_count - 1)
            cache_key = _audit_cache_key(entity_id, default)
            dynamic_read_audit[cache_key] = {
                'entity_id': cache_key[0],
                'default_type_obj': cache_key[1],
                'default_value': default,
                'count': logical_read_count,
                'underlying_reads': 1,
                'cache_hits': duplicate_count,
                'total_read_ms': int(round(read_elapsed_s * 1000.0)),
            }
            dynamic_audit_update_s['value'] += max(0.0, time.time() - audit_started_ts)
    if collect_full_audit:
        total_reads = 0
        for logical_read_count in logical_read_counts:
            total_reads += max(1, int(logical_read_count))
        dynamic_read_totals['total_reads'] = total_reads
        dynamic_read_totals['underlying_reads'] = len(unique_reads)
        dynamic_read_totals['cache_hits'] = max(0, total_reads - len(unique_reads))
    else:
        total_reads = 0
        for logical_read_count in logical_read_counts:
            total_reads += max(1, int(logical_read_count))
        dynamic_read_totals['total_reads'] = total_reads
        dynamic_read_totals['underlying_reads'] = len(unique_reads)
        dynamic_read_totals['cache_hits'] = max(0, total_reads - len(unique_reads))
    dynamic_read_plan_apply_total_ms = _elapsed_ms(dynamic_read_plan_apply_started_ts, time.time())

    materialize_metrics = {}
    grouped_cfg = build_policy_context_view(
        core_config_plan,
        grouped_reader,
        metrics=materialize_metrics,
        dynamic_runtime_read_plan=dynamic_runtime_read_plan,
        dynamic_runtime_read_values=tuple(dynamic_runtime_read_values),
    )
    total_core_config_ms = _elapsed_ms(core_config_started_ts, time.time())
    dynamic_config_reads_ms = int(round(dynamic_underlying_ha_s['value'] * 1000.0))
    dynamic_audit_update_ms = int(round(dynamic_audit_update_s['value'] * 1000.0))
    dynamic_reader_total_ms = max(0, int(dynamic_read_plan_apply_total_ms))
    dynamic_reader_overhead_ms = max(0, dynamic_reader_total_ms - dynamic_config_reads_ms)
    core_config_build_ms = max(0, total_core_config_ms - dynamic_config_reads_ms)
    materialize_metrics['policy_engine_core_config_materialize_total_ms'] = max(0, int(total_core_config_ms))
    _RUNTIME_CONTEXT_LAST_METRICS.update(
        {
            'policy_engine_config_signature_ms': config_signature_ms,
            'policy_engine_static_context_cache_hit': bool(cache_hit),
            'policy_engine_static_context_cache_hits': int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('hits', 0) or 0),
            'policy_engine_static_context_cache_misses': int(_RUNTIME_CONTEXT_CONFIG_CACHE.get('misses', 0) or 0),
            'policy_engine_static_context_build_ms': max(0, int(static_context_build_ms)),
            'policy_engine_dynamic_config_reads_ms': max(0, int(dynamic_config_reads_ms)),
            'policy_engine_dynamic_config_logical_reads': int(dynamic_read_totals['total_reads']),
            'policy_engine_dynamic_config_reader_total_ms': max(0, int(dynamic_reader_total_ms)),
            'policy_engine_dynamic_config_reader_overhead_ms': max(0, int(dynamic_reader_overhead_ms)),
            'policy_engine_dynamic_config_audit_overhead_ms': max(0, int(dynamic_audit_update_ms)),
            'policy_engine_dynamic_config_full_audit_collected': bool(collect_full_audit),
            'policy_engine_dynamic_config_unique_reads': len(unique_reads),
            'policy_engine_dynamic_config_audit_entries': len(dynamic_read_audit or {}),
            'policy_engine_dynamic_read_plan_apply_total_ms': max(0, int(dynamic_read_plan_apply_total_ms)),
            'policy_engine_dynamic_read_underlying_ha_ms': max(0, int(dynamic_config_reads_ms)),
            'policy_engine_dynamic_read_wrapper_overhead_ms': max(0, int(dynamic_reader_overhead_ms)),
            'policy_engine_dynamic_read_audit_update_ms': max(0, int(dynamic_audit_update_ms)),
            'policy_engine_runtime_entity_registry_ms': max(0, int(runtime_entity_registry_ms)),
            'policy_engine_core_config_build_ms': max(0, int(core_config_build_ms)),
        }
    )
    _RUNTIME_CONTEXT_LAST_METRICS.update(materialize_metrics)
    audit_build_started_ts = time.time()
    audit_sort_entries = []
    if collect_full_audit and dynamic_read_audit is not None:
        for entry in dynamic_read_audit.values():
            audit_entry = {
                'entity_id': entry['entity_id'],
                'default_type': entry['default_type_obj'].__name__,
                'default_repr': repr(entry['default_value']),
                'count': int(entry['count']),
                'underlying_reads': int(entry['underlying_reads']),
                'cache_hits': int(entry['cache_hits']),
                'total_read_ms': int(entry['total_read_ms']),
            }
            audit_sort_entries.append(
                (
                    -int(audit_entry['count']),
                    -int(audit_entry['cache_hits']),
                    str(audit_entry['entity_id']),
                    str(audit_entry['default_repr']),
                    audit_entry,
                )
            )
    dynamic_read_audit_build_ms = _elapsed_ms(audit_build_started_ts, time.time())
    audit_sort_started_ts = time.time()
    audit_sort_entries.sort()
    dynamic_read_audit_sort_ms = _elapsed_ms(audit_sort_started_ts, time.time())
    audit_entries = []
    for item in audit_sort_entries:
        audit_entries.append(item[4])
    _RUNTIME_CONTEXT_LAST_METRICS['policy_engine_dynamic_read_audit_build_ms'] = max(
        0, int(dynamic_read_audit_build_ms)
    )
    _RUNTIME_CONTEXT_LAST_METRICS['policy_engine_dynamic_read_audit_sort_ms'] = max(
        0, int(dynamic_read_audit_sort_ms)
    )
    _RUNTIME_CONTEXT_LAST_METRICS['policy_engine_core_config_unexplained_overhead_ms'] = max(
        0,
        int(
            (_RUNTIME_CONTEXT_LAST_METRICS.get('policy_engine_core_config_materialize_total_ms', 0) or 0)
            - (_RUNTIME_CONTEXT_LAST_METRICS.get('policy_engine_dynamic_config_reads_ms', 0) or 0)
            - (_RUNTIME_CONTEXT_LAST_METRICS.get('policy_engine_dynamic_runtime_snapshot_ms', 0) or 0)
            - (_RUNTIME_CONTEXT_LAST_METRICS.get('policy_engine_policy_context_view_ms', 0) or 0)
        ),
    )
    _RUNTIME_CONTEXT_LAST_DYNAMIC_READ_AUDIT.update(
        {
            'entries': tuple(audit_entries),
            'total_reads': int(dynamic_read_totals['total_reads']),
            'underlying_reads': int(dynamic_read_totals['underlying_reads']),
            'cache_hits': int(dynamic_read_totals['cache_hits']),
            'full_audit_collected': bool(collect_full_audit),
        }
    )
    return grouped_cfg, grouped_entities, {
        'enabled': True,
        'ok': None,
        'source': 'grouped_config',
        'path': path,
        'reason': 'loaded',
        'config_cache_hit': cache_hit,
    }, grouped_config


def build_runtime_entities_from_grouped_config(config):
    ent = {}
    alias_index = runtime_alias_index(config)
    for key in (
        'control_profile',
        'goal_profile',
        'forecast_profile',
        'guard_profile',
        'deadband_w',
        'ramp_max_w',
        'strict_limits_max_w',
        'surplus_freeze_s',
        'haeo_stale_timeout_s',
        'nz_battery_floor_default_w',
        'nz_battery_floor_ev_active_w',
        'adjustable_surplus_load',
        'adjustable_primary_load',
        'adjustable_surplus_activation',
        'max_solar_charge_w',
        'max_battery_discharge_w',
        'adjustable_surplus_load_priority',
        'battery_protect_soc',
        'battery_protect_soc_recovery_margin',
        'battery_protect_min_cell_voltage_v',
        'battery_protect_charge_floor_w',
        'soc',
        'min_cell_voltage_v',
        'battery_heartbeat',
        'current_battery_sp',
        'actuator_battery_setpoint_w',
        'ev_hard_off_pv_threshold_kw',
        'ev_hard_off_low_pv_cycles',
        'ev_hard_off_release_cycles',
        'charger_control',
        'actuator_ev_enabled',
        'charger_current',
        'actuator_ev_current_a',
        'ev_min_absorb_w',
        'ev_max_absorb_w',
        'ev_power_step_w',
        'ev_current_step_a',
        'ev_charger_phases',
        'ev_force_on',
        'actuator_relay1',
        'actuator_relay2',
    ):
        alias = alias_index.get(key)
        if alias is not None and alias.value:
            ent[key] = alias.value

    ems = config.get('ems', {})
    runtime = ems.get('runtime', {})
    state = ems.get('state', {})
    haeo = ems.get('haeo', {})
    devices = ems.get('devices', {})
    if isinstance(runtime, dict):
        ent['grid_power_w'] = runtime.get('grid_power_w')
        ent['quarter_energy_balance'] = runtime.get('quarter_energy_balance_kwh')
        ent['quarter_energy_balance_kwh'] = runtime.get('quarter_energy_balance_kwh')
        ent['pv_power_w'] = runtime.get('pv_power_w')
    if isinstance(state, dict):
        ent['surplus_freeze_until'] = state.get('surplus_freeze_until')
        ent['active_surplus_devices'] = state.get('active_surplus_devices')
        ent['previous_device_state'] = state.get('previous_device_state')
    ent['device_policies'] = CANONICAL_POLICY_OUTPUTS['device_policies']
    ent['dispatch_command'] = CANONICAL_POLICY_OUTPUTS['dispatch_command']
    ent['policy_state'] = CANONICAL_POLICY_OUTPUTS['policy_state']
    ent['policy_diagnostics'] = CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics']
    ent['actuator_writer_trace'] = CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace']
    ent['dispatch_state_applier_trace'] = CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace']
    if isinstance(haeo, dict):
        ent['haeo_battery_power_active'] = haeo.get('battery_power_active')
        ent['haeo_ev_battery_power_active'] = haeo.get('ev_power_active')
        ent['haeo_battery_active_power_fresh_source'] = haeo.get('battery_fresh_source')
        ent['haeo_ev_active_power_fresh_source'] = haeo.get('ev_fresh_source')
    device_entities = {}
    relay_device_ids = []
    ev_device_ids = []
    if isinstance(devices, dict):
        for device_id, device in devices.items():
            if not isinstance(device, dict):
                continue
            kind = str(device.get('kind') or '')
            policy = device.get('policy', {}) if isinstance(device.get('policy'), dict) else {}
            adapter = device.get('adapter', {}) if isinstance(device.get('adapter'), dict) else {}
            capabilities = device.get('capabilities', {}) if isinstance(device.get('capabilities'), dict) else {}
            entry = {
                'device_id': str(device_id),
                'kind': kind,
            }
            if kind == 'BATTERY':
                entry['target_w'] = adapter.get('target_w')
                entry['measured_power_w'] = adapter.get('measured_power_w')
            elif kind == 'EV_CHARGER':
                ev_device_ids.append(str(device_id))
                min_absorb_w = capabilities.get('min_absorb_w')
                max_absorb_w = capabilities.get('max_absorb_w')
                current_step_a = adapter.get('current_step_a')
                phases = adapter.get('phases')
                voltage_v = adapter.get('voltage_v')
                current_a = adapter.get('current_a')
                entry['enabled'] = adapter.get('enabled')
                entry['current_a'] = current_a
                entry['current_step_a'] = adapter.get('current_step_a')
                entry['phases'] = adapter.get('phases')
                entry['voltage_v'] = adapter.get('voltage_v')
                entry['min_absorb_w'] = min_absorb_w
                entry['max_absorb_w'] = max_absorb_w
                entry['surplus_allowed'] = policy.get('surplus_allowed')
                entry['force_on'] = policy.get('force_on')
                entry['priority'] = policy.get('priority')
                try:
                    has_step_context = (
                        phases not in (None, '')
                        and voltage_v not in (None, '')
                        and current_step_a not in (None, '')
                    )
                    has_min_context = (
                        min_absorb_w not in (None, '')
                        and phases not in (None, '')
                        and voltage_v not in (None, '')
                        and current_step_a not in (None, '')
                    )
                    has_max_context = (
                        max_absorb_w not in (None, '')
                        and phases not in (None, '')
                        and voltage_v not in (None, '')
                        and current_step_a not in (None, '')
                    )
                    has_current_power_context = (
                        current_a not in (None, '')
                        and phases not in (None, '')
                        and voltage_v not in (None, '')
                    )
                    if has_step_context:
                        entry['ev_per_amp_w'] = ev_per_amp_w(phases, voltage_v)
                        entry['ev_derived_step_w'] = ev_current_a_to_power_w(current_step_a, phases, voltage_v)
                    if has_min_context:
                        entry['ev_derived_min_current_a'] = ev_min_current_a_from_min_absorb_w(
                            min_absorb_w,
                            phases=phases,
                            voltage_v=voltage_v,
                            current_step_a=current_step_a,
                        )
                    if has_max_context:
                        entry['ev_derived_max_current_a'] = ev_max_current_a_from_max_absorb_w(
                            max_absorb_w,
                            phases=phases,
                            voltage_v=voltage_v,
                            current_step_a=current_step_a,
                        )
                    if has_current_power_context:
                        entry['ev_current_power_w'] = ev_current_a_to_power_w(current_a, phases, voltage_v)
                except (TypeError, ValueError):
                    pass
            elif kind == 'RELAY':
                relay_device_ids.append(str(device_id))
                entry['enabled'] = adapter.get('enabled')
                entry['surplus_allowed'] = policy.get('surplus_allowed')
                entry['force_on'] = policy.get('force_on')
                entry['priority'] = policy.get('priority')
                entry['max_absorb_w'] = capabilities.get('max_absorb_w')
            filtered_entry = {}
            for key, value in entry.items():
                if value not in (None, ''):
                    filtered_entry[key] = value
            device_entities[str(device_id)] = filtered_entry
    ent['devices'] = device_entities
    ent['relay_device_ids'] = tuple(relay_device_ids)
    ent['ev_device_ids'] = tuple(ev_device_ids)
    filtered = {}
    for key, value in ent.items():
        if value or key in {'devices', 'relay_device_ids', 'ev_device_ids'}:
            filtered[key] = value
    return filtered


def read_runtime_context(read_bool=None, read_float=None, read_int=None, read_str=None):
    read_bool = read_bool or _get_bool
    read_float = read_float or _get_float
    read_int = read_int or _get_int
    read_str = read_str or _get_str
    grouped_cfg, grouped_entities, status, _grouped_config = _read_grouped_runtime_candidate(read_bool, read_float, read_int, read_str)
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


def read_runtime_entities(read_bool=None, read_float=None, read_int=None, read_str=None):
    _cfg, entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    return entities
