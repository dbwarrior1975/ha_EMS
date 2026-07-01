import os

from ems_adapter.config_loader import (
    build_core_config_from_grouped_reader,
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
    ):
        return (
            _RUNTIME_CONTEXT_CONFIG_CACHE['config'],
            _RUNTIME_CONTEXT_CONFIG_CACHE['validation'],
            True,
        )

    grouped_config, validation = load_and_validate_grouped_ems_config(path)
    _RUNTIME_CONTEXT_CONFIG_CACHE.update(
        {
            'path': path,
            'mtime_ns': mtime_ns,
            'size': size,
            'config': grouped_config,
            'validation': validation,
        }
    )
    return grouped_config, validation, False

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
        grouped_config, validation, cache_hit = _load_grouped_config_cached(path)
    except Exception as exc:
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

    def grouped_reader(entity_id, default):
        return _read_grouped_entity(
            entity_id,
            default,
            read_bool,
            read_float,
            read_int,
            read_str,
        )

    grouped_cfg = build_core_config_from_grouped_reader(grouped_config, grouped_reader)
    grouped_entities = build_runtime_entities_from_grouped_config(grouped_config)
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
        'required_power_consumption_kw',
        'rpnz_w',
        'pv_power_kw',
    ):
        alias = alias_index.get(key)
        if alias is not None and alias.value:
            ent[key] = alias.value

    ems = config.get('ems', {})
    runtime = ems.get('runtime', {})
    state = ems.get('state', {})
    outputs = ems.get('policy_outputs', {})
    diagnostics = ems.get('diagnostics_outputs', {})
    haeo = ems.get('haeo', {})
    devices = ems.get('devices', {})
    if isinstance(runtime, dict):
        ent['grid_power_w'] = runtime.get('grid_power_w')
        ent['quarter_energy_balance'] = runtime.get('quarter_energy_balance_kwh')
    if isinstance(state, dict):
        ent['surplus_freeze_until'] = state.get('surplus_freeze_until')
        ent['active_surplus_devices'] = state.get('active_surplus_devices')
        ent['previous_device_state'] = state.get('previous_device_state')
    if isinstance(outputs, dict):
        ent['device_policies'] = outputs.get('device_policies')
        ent['dispatch_command'] = outputs.get('dispatch_command')
        ent['policy_state'] = outputs.get('policy_state')
    if isinstance(diagnostics, dict):
        ent['policy_diagnostics'] = diagnostics.get('policy_diagnostics')
        ent['actuator_writer_trace'] = diagnostics.get('actuator_writer_trace')
        ent['dispatch_state_applier_trace'] = diagnostics.get('dispatch_state_applier_trace')
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
