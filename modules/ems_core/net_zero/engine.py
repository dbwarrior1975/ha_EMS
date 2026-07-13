import time
from types import SimpleNamespace

from ems_core.domain.models import (
    ControlProfile, GoalProfile, ForecastProfile, GuardProfile, DominantLimitation,
    HaeoTargets, HaeoNetZeroPlan, SurplusDispatchInput, NetZeroOutputs,
    DevicePolicy, EmsDeviceConfig, DeviceControlContext, HardOffLifecycleTransition,
)
from ems_core.domain.capabilities import clamp_target_w_for_capabilities, capability_block_reason
from ems_core.domain.ev_power import (
    ev_current_a_to_power_w,
    ev_max_power_w,
    ev_min_power_w,
)
from ems_core.net_zero.battery_controller import candidate_sp_net_zero, net_zero_feedback_state
from ems_core.net_zero.load_projection import ev_strategy_target_w, relay_strategy_command
from ems_core.net_zero.surplus_allocator import (
    RPNZ_PRACTICAL_ZERO_W,
    compute_surplus_device_dispatch,
    next_device_target,
    release_device_target,
)
from ems_core.net_zero.surplus_candidates import build_surplus_candidates, candidate_payload

# Production default: expose only outer policy/tick timings collected by the caller.
# Flip to True temporarily when detailed NET_ZERO profiling is needed.
NET_ZERO_DETAILED_METRICS_ENABLED = False


def set_net_zero_detailed_metrics_enabled(enabled):
    global NET_ZERO_DETAILED_METRICS_ENABLED
    NET_ZERO_DETAILED_METRICS_ENABLED = bool(enabled)


def net_zero_detailed_metrics_enabled():
    return bool(NET_ZERO_DETAILED_METRICS_ENABLED)


def _net_zero_profile_started_ts():
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return 0.0
    return time.time()


_LAST_NET_ZERO_COMPUTE_METRICS = {
    'policy_engine_net_zero_cfg_scalar_reads': 0,
    'policy_engine_net_zero_cfg_scalar_read_ms': 0,
    'policy_engine_net_zero_cfg_device_by_id_calls': 0,
    'policy_engine_net_zero_cfg_device_kind_calls': 0,
    'policy_engine_net_zero_cfg_device_ids_by_kind_calls': 0,
    'policy_engine_net_zero_cfg_devices_by_kind_calls': 0,
    'policy_engine_net_zero_cfg_device_capability_calls': 0,
    'policy_engine_net_zero_cfg_device_adapter_value_calls': 0,
    'policy_engine_net_zero_cfg_device_policy_value_calls': 0,
    'policy_engine_net_zero_cfg_device_accessor_ms': 0,
    'policy_engine_net_zero_state_parse_ms': 0,
    'policy_engine_net_zero_facts_provider_ms': 0,
    'policy_engine_net_zero_facts_context_build_ms': 0,
    'policy_engine_net_zero_facts_copy_ms': 0,
    'policy_engine_net_zero_role_normalization_ms': 0,
    'policy_engine_net_zero_previous_device_state_normalization_ms': 0,
    'policy_engine_net_zero_forecast_haeo_normalization_ms': 0,
    'policy_engine_net_zero_facts_device_count': 0,
    'policy_engine_net_zero_facts_capability_fields': 0,
    'policy_engine_net_zero_facts_policy_fields': 0,
    'policy_engine_net_zero_facts_adapter_fields': 0,
    'policy_engine_net_zero_fact_dict_copies': 0,
    'policy_engine_net_zero_facts_fallback_used': 0,
    'policy_engine_net_zero_facts_dynamic_bindings': 0,
    'policy_engine_net_zero_facts_dynamic_binding_groups': 0,
    'policy_engine_net_zero_surplus_targets_ms': 0,
    'policy_engine_net_zero_ev_policy_ms': 0,
    'policy_engine_net_zero_battery_policy_ms': 0,
    'policy_engine_net_zero_relay_policy_ms': 0,
}
_ACTIVE_NET_ZERO_COMPUTE_METRICS = None


def net_zero_compute_metrics_attrs():
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return {}
    return dict(_LAST_NET_ZERO_COMPUTE_METRICS)


def _reset_net_zero_compute_metrics():
    _LAST_NET_ZERO_COMPUTE_METRICS.clear()
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return
    _LAST_NET_ZERO_COMPUTE_METRICS.update(
        {
            'policy_engine_net_zero_cfg_scalar_reads': 0,
            'policy_engine_net_zero_cfg_scalar_read_ms': 0,
            'policy_engine_net_zero_cfg_device_by_id_calls': 0,
            'policy_engine_net_zero_cfg_device_kind_calls': 0,
            'policy_engine_net_zero_cfg_device_ids_by_kind_calls': 0,
            'policy_engine_net_zero_cfg_devices_by_kind_calls': 0,
            'policy_engine_net_zero_cfg_device_capability_calls': 0,
            'policy_engine_net_zero_cfg_device_adapter_value_calls': 0,
            'policy_engine_net_zero_cfg_device_policy_value_calls': 0,
            'policy_engine_net_zero_cfg_device_accessor_ms': 0,
                            'policy_engine_net_zero_state_parse_ms': 0,
            'policy_engine_net_zero_facts_provider_ms': 0,
            'policy_engine_net_zero_facts_context_build_ms': 0,
            'policy_engine_net_zero_facts_copy_ms': 0,
            'policy_engine_net_zero_role_normalization_ms': 0,
            'policy_engine_net_zero_previous_device_state_normalization_ms': 0,
            'policy_engine_net_zero_forecast_haeo_normalization_ms': 0,
            'policy_engine_net_zero_facts_device_count': 0,
            'policy_engine_net_zero_facts_capability_fields': 0,
            'policy_engine_net_zero_facts_policy_fields': 0,
            'policy_engine_net_zero_facts_adapter_fields': 0,
            'policy_engine_net_zero_fact_dict_copies': 0,
            'policy_engine_net_zero_facts_fallback_used': 0,
            'policy_engine_net_zero_facts_dynamic_bindings': 0,
            'policy_engine_net_zero_facts_dynamic_binding_groups': 0,
            'policy_engine_net_zero_surplus_targets_ms': 0,
            'policy_engine_net_zero_ev_policy_ms': 0,
            'policy_engine_net_zero_battery_policy_ms': 0,
            'policy_engine_net_zero_relay_policy_ms': 0,
        }
    )


def _note_net_zero_metric(key, increment=1):
    global _ACTIVE_NET_ZERO_COMPUTE_METRICS
    if not NET_ZERO_DETAILED_METRICS_ENABLED or _ACTIVE_NET_ZERO_COMPUTE_METRICS is None:
        return
    _ACTIVE_NET_ZERO_COMPUTE_METRICS[key] = int(_ACTIVE_NET_ZERO_COMPUTE_METRICS.get(key, 0) or 0) + int(increment)


def _note_net_zero_duration_ms(key, started_ts):
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return
    _note_net_zero_metric(key, int(round(max(0.0, time.time() - started_ts) * 1000.0)))


def _note_policy_runtime_facts_metrics(facts):
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return
    if not isinstance(facts, dict):
        return
    metrics = facts.get('_metrics')
    if isinstance(metrics, dict):
        _note_net_zero_metric('policy_engine_net_zero_facts_context_build_ms', metrics.get('policy_runtime_facts_context_build_ms', 0) or 0)
        _note_net_zero_metric('policy_engine_net_zero_facts_device_count', metrics.get('policy_runtime_facts_device_count', 0) or 0)
        _note_net_zero_metric('policy_engine_net_zero_facts_capability_fields', metrics.get('policy_runtime_facts_capability_fields', 0) or 0)
        _note_net_zero_metric('policy_engine_net_zero_facts_policy_fields', metrics.get('policy_runtime_facts_policy_fields', 0) or 0)
        _note_net_zero_metric('policy_engine_net_zero_facts_adapter_fields', metrics.get('policy_runtime_facts_adapter_fields', 0) or 0)
        _note_net_zero_metric('policy_engine_net_zero_fact_dict_copies', metrics.get('policy_runtime_fact_dict_copies', 0) or 0)
        _note_net_zero_metric('policy_engine_net_zero_facts_dynamic_bindings', metrics.get('policy_runtime_facts_dynamic_bindings', 0) or 0)
        _note_net_zero_metric('policy_engine_net_zero_facts_dynamic_binding_groups', metrics.get('policy_runtime_facts_dynamic_binding_groups', 0) or 0)
        return

    device_kind_by_id = facts.get('device_kind_by_id', {}) or {}
    if hasattr(device_kind_by_id, '__len__'):
        _note_net_zero_metric('policy_engine_net_zero_facts_device_count', len(device_kind_by_id))

    capability_count = 0
    for values in (facts.get('device_capabilities_by_id', {}) or {}).values():
        capability_count += len(values or {})
    _note_net_zero_metric('policy_engine_net_zero_facts_capability_fields', capability_count)

    policy_count = 0
    for values in (facts.get('device_policy_by_id', {}) or {}).values():
        policy_count += len(values or {})
    _note_net_zero_metric('policy_engine_net_zero_facts_policy_fields', policy_count)

    adapter_count = 0
    for values in (facts.get('device_adapter_by_id', {}) or {}).values():
        adapter_count += len(values or {})
    _note_net_zero_metric('policy_engine_net_zero_facts_adapter_fields', adapter_count)

def _global_config_value(cfg, field_name, default=None):
    global_config = getattr(cfg, 'global_config', None)
    if global_config is None:
        return default
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return getattr(global_config, field_name, default)
    started_ts = time.time()
    _note_net_zero_metric('policy_engine_net_zero_cfg_global_reads')
    value = getattr(global_config, field_name, default)
    _note_net_zero_duration_ms('policy_engine_net_zero_cfg_global_read_ms', started_ts)
    return value


def _battery_guard_value(cfg, device_id, field_name, default=None):
    if hasattr(cfg, 'battery_guard_value'):
        return cfg.battery_guard_value(str(device_id), field_name, default)
    device = _device_by_id(cfg, device_id) if device_id else None
    guard = getattr(device, 'guard', None) if device is not None else None
    return getattr(guard, field_name, default) if guard is not None else default


def _cfg_accessor_call(count_key, fn, *args):
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return fn(*args)
    started_ts = time.time()
    _note_net_zero_metric(count_key)
    try:
        return fn(*args)
    finally:
        _note_net_zero_duration_ms('policy_engine_net_zero_cfg_device_accessor_ms', started_ts)



def _ev_context_from_fact_maps(facts, device_id):
    def _positive_float(value, default):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        return parsed if parsed > 0 else float(default)

    def _non_negative_float(value, default=0.0):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        return parsed if parsed >= 0 else float(default)

    def _int_or_default(value, default=0):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return int(default)

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
            uses_hard_off_lifecycle=False,
            hard_off_pv_threshold_kw=0.0,
            hard_off_low_pv_cycles=0,
            hard_off_release_cycles=0,
            priority=0,
        )
    capabilities = (facts.get('device_capabilities_by_id', {}) or {}).get(device_id, {}) or {}
    policy = (facts.get('device_policy_by_id', {}) or {}).get(device_id, {}) or {}
    adapter = (facts.get('device_adapter_by_id', {}) or {}).get(device_id, {}) or {}
    current_step_a = _positive_float(adapter.get('current_step_a'), 1.0)
    phases = _positive_float(adapter.get('phases'), 1.0)
    voltage_v = _positive_float(adapter.get('voltage_v'), 230.0)

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

    low_pv_threshold = _non_negative_float(policy.get('low_pv_threshold_w', 0), 0.0)
    hard_off_pv_threshold_kw = (
        low_pv_threshold / 1000.0
        if low_pv_threshold > 50.0
        else low_pv_threshold
    )
    min_absorb_w = _non_negative_float(capabilities.get('min_absorb_w', None), 0.0)
    max_absorb_w = _non_negative_float(capabilities.get('max_absorb_w', None), 0.0)
    configured_step_w = _non_negative_float(capabilities.get('step_w', 0), 0.0)
    power_step_w = configured_step_w if configured_step_w > 0 else float(
        ev_current_a_to_power_w(
            current_step_a,
            phases,
            voltage_v,
        )
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
        uses_hard_off_lifecycle=bool(capabilities.get('uses_hard_off_lifecycle', False)),
        hard_off_pv_threshold_kw=hard_off_pv_threshold_kw,
        hard_off_low_pv_cycles=_int_or_default(policy.get('hard_off_low_pv_cycles', 0), 0),
        hard_off_release_cycles=_int_or_default(policy.get('hard_off_release_cycles', 0), 0),
        priority=_int_or_default(policy.get('priority', 0), 0),
    )



def _build_policy_runtime_facts(cfg):
    direct_maps = getattr(cfg, 'direct_policy_maps', None)
    if isinstance(direct_maps, dict):
        return direct_maps

    facts_provider = getattr(cfg, 'policy_runtime_facts', None)
    if callable(facts_provider):
        provider_started_ts = _net_zero_profile_started_ts()
        raw_facts = facts_provider() or {}
        _note_net_zero_duration_ms('policy_engine_net_zero_facts_provider_ms', provider_started_ts)

        copy_started_ts = _net_zero_profile_started_ts()
        if isinstance(raw_facts, dict):
            facts = raw_facts
        else:
            facts = dict(raw_facts)
            _note_net_zero_metric('policy_engine_net_zero_fact_dict_copies')
        _note_net_zero_duration_ms('policy_engine_net_zero_facts_copy_ms', copy_started_ts)
        _note_policy_runtime_facts_metrics(facts)

        return facts

    _note_net_zero_metric('policy_engine_net_zero_facts_fallback_used')
    fallback_started_ts = _net_zero_profile_started_ts()
    ids_by_kind = {}
    for kind in ('BATTERY', 'EV_CHARGER', 'RELAY'):
        ids_by_kind[kind] = tuple(_device_ids_by_kind(cfg, kind))

    ordered_device_ids = []
    for kind in ('BATTERY', 'EV_CHARGER', 'RELAY'):
        for device_id in ids_by_kind.get(kind, ()):
            text = str(device_id)
            if text not in ordered_device_ids:
                ordered_device_ids.append(text)

    device_kind_by_id = {}
    for kind, device_ids in ids_by_kind.items():
        for device_id in device_ids:
            device_kind_by_id[str(device_id)] = str(kind)

    device_capabilities_by_id = {}
    device_policy_by_id = {}
    device_adapter_by_id = {}
    capability_fields = (
        'min_absorb_w',
        'max_absorb_w',
        'min_produce_w',
        'max_produce_w',
        'step_w',
        'can_absorb_w',
        'can_produce_w',
        'supports_primary_consuming_regulation',
        'supports_producing_regulation',
        'uses_hard_off_lifecycle',
    )
    for device_id in ordered_device_ids:
        kind = str(device_kind_by_id.get(device_id, '') or '')
        capabilities = {}
        for field in capability_fields:
            default = False if field in (
                'can_absorb_w',
                'can_produce_w',
                'supports_primary_consuming_regulation',
                'supports_producing_regulation',
                'uses_hard_off_lifecycle',
            ) else 0
            capabilities[field] = _device_capability(cfg, device_id, field, default)
        device_capabilities_by_id[device_id] = capabilities

        policy = {
            'priority': _device_policy_value(cfg, device_id, 'priority', 0),
            'producing_priority': _device_policy_value(cfg, device_id, 'producing_priority', 0),
        }
        if kind == 'EV_CHARGER':
            policy['surplus_allowed'] = _device_policy_value(cfg, device_id, 'surplus_allowed', False)
            policy['force_on'] = _device_policy_value(cfg, device_id, 'force_on', False)
            policy['low_pv_threshold_w'] = _device_policy_value(cfg, device_id, 'low_pv_threshold_w', 0)
            policy['hard_off_low_pv_cycles'] = _device_policy_value(cfg, device_id, 'hard_off_low_pv_cycles', 0)
            policy['hard_off_release_cycles'] = _device_policy_value(cfg, device_id, 'hard_off_release_cycles', 0)
            device_adapter_by_id[device_id] = {
                'current_step_a': _device_adapter_value(cfg, device_id, 'current_step_a', None),
                'phases': _device_adapter_value(cfg, device_id, 'phases', None),
                'voltage_v': _device_adapter_value(cfg, device_id, 'voltage_v', None),
            }
        elif kind == 'RELAY':
            policy['surplus_allowed'] = _device_policy_value(cfg, device_id, 'surplus_allowed', False)
            policy['force_on'] = _device_policy_value(cfg, device_id, 'force_on', False)
        device_policy_by_id[device_id] = policy

    facts = {
        'device_ids_by_kind': ids_by_kind,
        'device_kind_by_id': device_kind_by_id,
        'device_capabilities_by_id': device_capabilities_by_id,
        'device_policy_by_id': device_policy_by_id,
        'device_adapter_by_id': device_adapter_by_id,
    }
    _note_net_zero_duration_ms('policy_engine_net_zero_facts_context_build_ms', fallback_started_ts)
    _note_policy_runtime_facts_metrics(facts)
    return facts


def configured_forecast(control, forecast_profile):
    if control in (ControlProfile.MANUAL, ControlProfile.MANUAL_SAFE):
        return ForecastProfile.NONE
    if forecast_profile == ForecastProfile.HAEO:
        return ForecastProfile.HAEO
    if forecast_profile == ForecastProfile.NONE and control == ControlProfile.HORIZON_BY_HAEO:
        return ForecastProfile.HAEO
    return ForecastProfile.NONE


def effective_forecast(configured, haeo_fresh):
    return ForecastProfile.HAEO if configured == ForecastProfile.HAEO and haeo_fresh else ForecastProfile.NONE


def dominant_limitation(profiles, configured_fc, effective_fc):
    if profiles.guard == GuardProfile.DEGRADED:
        return DominantLimitation.SYSTEM_DEGRADED
    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return DominantLimitation.BATTERY_SOC_LIMIT
    if profiles.control == ControlProfile.MANUAL:
        return DominantLimitation.USER_MANUAL_OVERRIDE
    if profiles.control == ControlProfile.MANUAL_SAFE:
        return DominantLimitation.MANUAL_SAFE_ACTIVE
    if profiles.guard == GuardProfile.STRICT_LIMITS:
        return DominantLimitation.STRICT_POWER_LIMITS
    if configured_fc == ForecastProfile.HAEO and effective_fc != ForecastProfile.HAEO:
        return DominantLimitation.FORECAST_FALLBACK_LOCAL
    return DominantLimitation.OPTIMIZATION_ACTIVE


def explain(profiles, configured_fc, effective_fc, haeo_nz_plan_active=False):
    if profiles.guard == GuardProfile.DEGRADED:
        return 'Guard forces degraded fallback'
    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return 'Guard prevents harmful battery discharge'
    if profiles.control == ControlProfile.MANUAL:
        return 'User manual control active'
    if profiles.control == ControlProfile.MANUAL_SAFE:
        return 'User manual control with guard enforcement'
    if profiles.goal == GoalProfile.NET_ZERO and configured_fc == ForecastProfile.HAEO and effective_fc == ForecastProfile.NONE:
        return 'Net zero goal with configured HAEO forecast, but stale forecast causes local fallback'
    if profiles.goal == GoalProfile.NET_ZERO and haeo_nz_plan_active:
        return 'HAEO net zero plan active'
    if profiles.goal == GoalProfile.NET_ZERO and effective_fc == ForecastProfile.HAEO:
        return 'Net zero goal with HAEO forecast visible, but local policy remains dominant'
    if profiles.goal == GoalProfile.NET_ZERO:
        return 'Local quarter balancing without forecast'
    if profiles.goal == GoalProfile.MAX_EXPORT and effective_fc == ForecastProfile.HAEO:
        return 'Export-oriented policy with HAEO forecast assistance'
    if profiles.goal == GoalProfile.CHEAP_GRID_CHARGE and effective_fc == ForecastProfile.HAEO:
        return 'Cheap charge policy with HAEO forecast assistance'
    if profiles.goal == GoalProfile.MAX_EXPORT:
        return 'Local export-oriented policy'
    if profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        return 'Local cheap-charge policy'
    return 'Policy active'


def _resolved_device_id(cfg, raw_value, default='', facts=None):
    text = str(raw_value or '').strip()
    if not text:
        return str(default or '')
    if facts is not None:
        if str((facts.get('device_kind_by_id', {}) or {}).get(text, '') or ''):
            return text
    elif hasattr(cfg, 'device_kind'):
        if cfg.device_kind(text):
            return text
    if hasattr(cfg, 'device_by_id'):
        device = cfg.device_by_id(text)
        if device is not None:
            return str(device.device_id)
    return text


def _normalized_primary_consuming_device_ids(cfg, facts=None):
    raw_values = _global_config_value(cfg, 'primary_consuming_device_ids', ()) or ()
    if isinstance(raw_values, str):
        raw_values = (raw_values,)
    resolved_ids = []
    for raw_value in tuple(raw_values):
        resolved = _resolved_device_id(cfg, raw_value, '', facts=facts)
        if resolved and resolved not in resolved_ids:
            resolved_ids.append(resolved)
    return tuple(resolved_ids)


def _device_by_id(cfg, device_id):
    if not device_id:
        return None
    if hasattr(cfg, 'device_by_id'):
        return _cfg_accessor_call('policy_engine_net_zero_cfg_device_by_id_calls', cfg.device_by_id, device_id)
    return None


def _device_kind(cfg, device_id, facts=None):
    if not device_id:
        return ''
    if facts is not None:
        return str((facts.get('device_kind_by_id', {}) or {}).get(str(device_id), '') or '')
    if hasattr(cfg, 'device_kind'):
        return str(_cfg_accessor_call('policy_engine_net_zero_cfg_device_kind_calls', cfg.device_kind, device_id) or '')
    device = _device_by_id(cfg, device_id)
    if device is None:
        return ''
    return str(getattr(device, 'kind', '') or '')


def _device_ids_by_kind(cfg, kind, facts=None):
    if facts is not None:
        return tuple((facts.get('device_ids_by_kind', {}) or {}).get(str(kind), ()) or ())
    if hasattr(cfg, 'device_ids_by_kind'):
        started_ts = time.time()
        _note_net_zero_metric('policy_engine_net_zero_cfg_device_ids_by_kind_calls')
        ids = []
        try:
            for device_id in cfg.device_ids_by_kind(kind):
                ids.append(str(device_id))
        finally:
            _note_net_zero_duration_ms('policy_engine_net_zero_cfg_device_accessor_ms', started_ts)
        return tuple(ids)
    if hasattr(cfg, 'devices_by_kind'):
        started_ts = time.time()
        _note_net_zero_metric('policy_engine_net_zero_cfg_devices_by_kind_calls')
        ids = []
        try:
            for device in cfg.devices_by_kind(kind):
                ids.append(str(device.device_id))
        finally:
            _note_net_zero_duration_ms('policy_engine_net_zero_cfg_device_accessor_ms', started_ts)
        return tuple(ids)
    return ()



def _device_capability(cfg, device_id, field, default=None, facts=None):
    if facts is not None:
        values = (facts.get('device_capabilities_by_id', {}) or {}).get(str(device_id), {}) or {}
        return values.get(field, default)
    if hasattr(cfg, 'device_capability'):
        return _cfg_accessor_call(
            'policy_engine_net_zero_cfg_device_capability_calls',
            cfg.device_capability,
            device_id,
            field,
            default,
        )
    device = _device_by_id(cfg, device_id)
    if device is None:
        return default
    capabilities = getattr(device, 'capabilities', None)
    if capabilities is None:
        return default
    return getattr(capabilities, field, default)



def _device_adapter_value(cfg, device_id, field, default=None, facts=None):
    if facts is not None:
        values = (facts.get('device_adapter_by_id', {}) or {}).get(str(device_id), {}) or {}
        return values.get(field, default)
    if hasattr(cfg, 'device_adapter_value'):
        return _cfg_accessor_call(
            'policy_engine_net_zero_cfg_device_adapter_value_calls',
            cfg.device_adapter_value,
            device_id,
            field,
            default,
        )
    device = _device_by_id(cfg, device_id)
    if device is None:
        return default
    adapter = getattr(device, 'adapter', None)
    if adapter is None:
        return default
    return getattr(adapter, field, default)



def _device_policy_value(cfg, device_id, field, default=None, facts=None):
    if facts is not None:
        values = (facts.get('device_policy_by_id', {}) or {}).get(str(device_id), {}) or {}
        return values.get(field, default)
    if hasattr(cfg, 'device_policy_value'):
        return _cfg_accessor_call(
            'policy_engine_net_zero_cfg_device_policy_value_calls',
            cfg.device_policy_value,
            device_id,
            field,
            default,
        )
    device = _device_by_id(cfg, device_id)
    if device is None:
        return default
    policy = getattr(device, 'policy', None)
    if policy is None:
        return default
    return getattr(policy, field, default)


def _runtime_policy_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ('true', 'on', '1', 'yes'):
            return True
        if text in ('false', 'off', '0', 'no', '', 'unknown', 'unavailable', 'none'):
            return False
        return bool(default)
    if value is None:
        return bool(default)
    return bool(value)


def _device_can_absorb(cfg, device_id, facts=None):
    return bool(_device_capability(cfg, device_id, 'can_absorb_w', False, facts=facts))


def _device_uses_hard_off_lifecycle(cfg, device_id, facts=None):
    return bool(_device_capability(cfg, device_id, 'uses_hard_off_lifecycle', False, facts=facts))


def _device_supports_primary_consuming_regulation(cfg, device_id, facts=None):
    return bool(_device_capability(cfg, device_id, 'supports_primary_consuming_regulation', False, facts=facts))


def _device_supports_producing_regulation(cfg, device_id, facts=None):
    return bool(_device_capability(cfg, device_id, 'supports_producing_regulation', False, facts=facts))


def _device_control_context(cfg, device_id, *, current_control_target_w=0.0, facts=None):
    device_id = str(device_id or '')
    if not device_id:
        return None
    return DeviceControlContext(
        device_id=device_id,
        kind=_device_kind(cfg, device_id, facts=facts),
        can_absorb_w=_device_can_absorb(cfg, device_id, facts=facts),
        can_produce_w=bool(_device_capability(cfg, device_id, 'can_produce_w', False, facts=facts)),
        min_absorb_w=float(_device_capability(cfg, device_id, 'min_absorb_w', 0, facts=facts) or 0),
        max_absorb_w=float(_device_capability(cfg, device_id, 'max_absorb_w', 0, facts=facts) or 0),
        min_produce_w=float(_device_capability(cfg, device_id, 'min_produce_w', 0, facts=facts) or 0),
        max_produce_w=float(_device_capability(cfg, device_id, 'max_produce_w', 0, facts=facts) or 0),
        step_w=float(_device_capability(cfg, device_id, 'step_w', 0, facts=facts) or 0),
        supports_primary_consuming_regulation=_device_supports_primary_consuming_regulation(cfg, device_id, facts=facts),
        supports_producing_regulation=_device_supports_producing_regulation(cfg, device_id, facts=facts),
        uses_hard_off_lifecycle=_device_uses_hard_off_lifecycle(cfg, device_id, facts=facts),
        priority=int(_device_policy_value(cfg, device_id, 'priority', 0, facts=facts) or 0),
        producing_priority=int(_device_policy_value(cfg, device_id, 'producing_priority', 0, facts=facts) or 0),
        current_control_target_w=float(current_control_target_w or 0.0),
    )


def _producer_device_contexts(cfg, context_by_id, facts=None):
    rank_by_id = {}
    rank = 0
    for device_id in _ordered_device_ids(cfg, facts=facts):
        rank_by_id[str(device_id)] = rank
        rank += 1
    ordered = []
    for device_id, context in (context_by_id or {}).items():
        if context is None or not context.supports_producing_regulation:
            continue
        ordered.append((
            -int(context.producing_priority),
            rank_by_id.get(str(context.device_id), 10 ** 9),
            context,
        ))
    ordered.sort()
    producers = []
    for item in ordered:
        producers.append(item[2])
    return tuple(producers)


def quantize_produce_magnitude_toward_zero(requested_w, step_w):
    requested_w = max(float(requested_w or 0.0), 0.0)
    step_w = max(float(step_w or 0.0), 0.0)
    if requested_w <= 0.0 or step_w <= 0.0:
        return requested_w
    return float(int(requested_w // step_w) * step_w)


def _producer_effective_hard_ceiling_w(profiles, cfg, device_context):
    if device_context is None:
        return 0.0
    if not device_context.supports_producing_regulation or not device_context.can_produce_w:
        return 0.0
    ceiling_w = max(float(device_context.max_produce_w or 0.0), 0.0)
    if ceiling_w <= 0.0:
        return 0.0
    # Hard ceilings determine strict producer opening. Transient ramp, deadband,
    # and current output are deliberately excluded from this value.
    if profiles.guard in (GuardProfile.DEGRADED, GuardProfile.BATTERY_PROTECT):
        return 0.0
    if profiles.guard == GuardProfile.STRICT_LIMITS:
        ceiling_w = min(ceiling_w, max(float(_global_config_value(cfg, 'strict_limit_w', 0) or 0), 0.0))
    return quantize_produce_magnitude_toward_zero(ceiling_w, device_context.step_w)


def _producer_feedback_request(cfg, producer_contexts, rpnz_w, grid_actual_w):
    current_control_target_w = 0.0
    for context in tuple(producer_contexts or ()):
        current_control_target_w += float(context.current_control_target_w or 0.0)

    feedback = net_zero_feedback_state(
        rpnz_w=float(rpnz_w or 0.0),
        grid_actual_w=float(grid_actual_w or 0.0),
        current_control_target_w=current_control_target_w,
        deadband_w=float(_global_config_value(cfg, 'deadband_w', 50.0)),
    )
    feedback['requested_w'] = max(
        -float(feedback['desired_control_target_w']), 0.0
    )
    return feedback


def _allocate_producer_dispatch(profiles, cfg, producer_contexts, requested_w):
    requested_w = max(float(requested_w or 0.0), 0.0)
    remaining_need_w = requested_w
    contexts = tuple(producer_contexts or ())
    allocated_w_by_id = {}
    ceiling_w_by_id = {}
    skipped_below_min = []

    # Compute every hard ceiling first so diagnostics remain complete even when
    # strict priority closes the chain before lower-priority producers open.
    for context in contexts:
        device_id = str(context.device_id)
        allocated_w_by_id[device_id] = 0.0
        ceiling_w_by_id[device_id] = float(
            _producer_effective_hard_ceiling_w(profiles, cfg, context)
        )

    for context in contexts:
        device_id = str(context.device_id)
        ceiling_w = ceiling_w_by_id[device_id]
        if remaining_need_w <= 0.0:
            break
        if ceiling_w <= 0.0:
            # Unavailable or zero-ceiling producers never block the chain.
            continue

        need_before_w = remaining_need_w
        requested_for_device_w = min(need_before_w, ceiling_w)
        allocated_w = quantize_produce_magnitude_toward_zero(
            requested_for_device_w,
            context.step_w,
        )
        min_produce_w = max(float(context.min_produce_w or 0.0), 0.0)
        if allocated_w > 0.0 and allocated_w < min_produce_w:
            # Canonical no-overshoot policy for a non-zero minimum: skip this
            # producer and allow the next explicit producer to serve.
            skipped_below_min.append(device_id)
            continue

        allocated_w_by_id[device_id] = float(allocated_w)
        remaining_need_w = max(need_before_w - allocated_w, 0.0)

        # Strict producing priority: when this producer's hard ceiling could
        # cover the need, lower-priority producers stay closed. Any remainder
        # caused solely by step quantization remains explicitly unserved.
        if need_before_w <= ceiling_w:
            break
        # Otherwise need_before_w exceeded the reachable hard ceiling. Since
        # ceiling_w is already step-quantized, this producer is at its effective
        # hard ceiling and the next producer may open.

    return {
        'requested_w': float(requested_w),
        'allocated_w_by_id': allocated_w_by_id,
        'ceiling_w_by_id': ceiling_w_by_id,
        'unserved_w': float(remaining_need_w),
        'skipped_below_min_device_ids': tuple(skipped_below_min),
    }


def _ramp_toward_target_w(current_w, desired_w, ramp_w):
    current_w = float(current_w or 0.0)
    desired_w = float(desired_w or 0.0)
    ramp_w = max(float(ramp_w or 0.0), 0.0)
    if ramp_w <= 0.0:
        return desired_w
    delta = desired_w - current_w
    if delta > ramp_w:
        return current_w + ramp_w
    if delta < -ramp_w:
        return current_w - ramp_w
    return desired_w


def _producer_transient_target_w(cfg, device_context, allocated_magnitude_w):
    desired_w = -max(float(allocated_magnitude_w or 0.0), 0.0)
    target_w = _ramp_toward_target_w(
        device_context.current_control_target_w,
        desired_w,
        _global_config_value(cfg, 'ramp_w', 1000.0),
    )
    if target_w < 0.0:
        return -quantize_produce_magnitude_toward_zero(abs(target_w), device_context.step_w)
    return target_w


def _active_producer_for_feedback(primary_device, producer_contexts):
    if primary_device is None:
        return None
    for producer in tuple(producer_contexts or ()):
        if str(producer.device_id) == str(primary_device.device_id):
            continue
        if producer.can_produce_w and float(producer.current_control_target_w) < 0.0:
            return producer
    return None

def quantize_absorb_target_w(requested_w, min_absorb_w, max_absorb_w, step_w):
    requested_w = max(float(requested_w or 0.0), 0.0)
    min_absorb_w = max(float(min_absorb_w or 0.0), 0.0)
    max_absorb_w = max(float(max_absorb_w or 0.0), 0.0)
    step_w = max(float(step_w or 0.0), 0.0)
    if max_absorb_w <= 0.0 or requested_w <= 0.0:
        return 0.0
    clamped_w = min(max(requested_w, min_absorb_w), max_absorb_w)
    if step_w <= 0.0:
        return clamped_w
    steps = int((clamped_w - min_absorb_w) // step_w)
    return min(max_absorb_w, min_absorb_w + (steps * step_w))


def compute_primary_consuming_device_target_w(device_context, requested_w):
    if device_context is None or not device_context.supports_primary_consuming_regulation:
        return 0.0
    if not device_context.can_absorb_w:
        return 0.0
    return quantize_absorb_target_w(
        requested_w,
        device_context.min_absorb_w,
        device_context.max_absorb_w,
        device_context.step_w,
    )


def _ordered_primary_consuming_device_ids(cfg, haeo_nz_plan=None, facts=None):
    configured_ids = list(_normalized_primary_consuming_device_ids(cfg, facts=facts))
    ordered = []
    if haeo_nz_plan is not None and bool(getattr(haeo_nz_plan, 'active', False)):
        planned_id = str(_haeo_plan_primary_consuming_device_id(haeo_nz_plan) or '')
        if planned_id:
            ordered.append(planned_id)
    for device_id in configured_ids:
        device_id = str(device_id or '')
        if device_id and device_id not in ordered:
            ordered.append(device_id)
    return tuple(ordered)


def _resolve_primary_consuming_authority(
    profiles,
    cfg,
    ordered_device_ids,
    context_by_id,
    lifecycle_transitions_by_id,
    producer_contexts,
    m,
    nz,
    *,
    pv_power_kw=None,
    haeo_nz_plan=None,
    facts=None,
):
    """Select one effective consuming regulator from an explicit fallback order.

    The common grid-feedback request is evaluated against each candidate's own
    current control target. Device-specific realizability is applied only after
    that shared request is known. Unavailable or unrealizable candidates are
    skipped rather than blocking the rest of the ordered pool.
    """
    requested_w_by_id = {}
    skipped_by_id = {}
    if profiles.goal != GoalProfile.NET_ZERO or profiles.control not in (
        ControlProfile.AUTOMATIC,
        ControlProfile.HORIZON_BY_HAEO,
    ):
        return {
            'configured_ids': tuple(ordered_device_ids or ()),
            'effective_device_id': '',
            'effective_target_w': 0.0,
            'effective_reason': 'primary_regulation_inactive',
            'requested_w_by_id': requested_w_by_id,
            'skipped_by_id': skipped_by_id,
            'unserved_consuming_w': 0.0,
            'feedback_protection_active': False,
            'feedback_protection_low_energy_active': False,
            'feedback_protection_low_energy_threshold_kw': 0.0,
            'feedback_producer_device': None,
        }

    saw_positive_request = False
    first_positive_request_w = 0.0
    for raw_device_id in tuple(ordered_device_ids or ()):
        device_id = str(raw_device_id or '')
        context = context_by_id.get(device_id)
        if context is None:
            skipped_by_id[device_id] = 'device_not_found'
            continue
        if not bool(context.supports_primary_consuming_regulation):
            skipped_by_id[device_id] = 'primary_regulation_not_supported'
            continue
        if not bool(context.can_absorb_w) or float(context.max_absorb_w) <= 0.0:
            skipped_by_id[device_id] = 'absorb_capability_unavailable'
            continue

        force_on = _runtime_policy_bool(
            _device_policy_value(cfg, device_id, 'force_on', False, facts=None)
        )
        transition = (lifecycle_transitions_by_id or {}).get(device_id)
        if (
            transition is not None
            and bool(getattr(transition, 'hard_off_active', False))
            and not force_on
        ):
            skipped_by_id[device_id] = 'lifecycle_hard_off'
            continue

        feedback_producer_device = _active_producer_for_feedback(context, producer_contexts)
        low_energy_active, low_energy_threshold_kw = _device_low_energy_condition(
            cfg, device_id, pv_power_kw
        )
        feedback_protection_active = compute_primary_producer_feedback_protection(
            context,
            feedback_producer_device,
            low_energy_active=low_energy_active,
            explicit_activation_request=force_on,
        )
        if feedback_protection_active:
            skipped_by_id[device_id] = 'producer_feedback_protection'
            continue

        if force_on and str(context.kind) == 'EV_CHARGER':
            target_w = float(context.max_absorb_w)
            requested_w_by_id[device_id] = target_w
            return {
                'configured_ids': tuple(ordered_device_ids or ()),
                'effective_device_id': device_id,
                'effective_target_w': target_w,
                'effective_reason': 'force_on',
                'requested_w_by_id': requested_w_by_id,
                'skipped_by_id': skipped_by_id,
                'unserved_consuming_w': 0.0,
                'feedback_protection_active': False,
                'feedback_protection_low_energy_active': bool(low_energy_active),
                'feedback_protection_low_energy_threshold_kw': float(low_energy_threshold_kw),
                'feedback_producer_device': feedback_producer_device,
            }

        requested_w = float(_primary_device_power_envelope_w(cfg, context, m, nz))
        requested_w_by_id[device_id] = requested_w
        if requested_w <= 0.0:
            skipped_by_id[device_id] = 'no_positive_consuming_request'
            continue
        saw_positive_request = True
        if first_positive_request_w <= 0.0:
            first_positive_request_w = float(requested_w)

        min_absorb_w = max(float(context.min_absorb_w or 0.0), 0.0)
        if min_absorb_w > 0.0 and requested_w < min_absorb_w:
            skipped_by_id[device_id] = 'below_min_absorb_w'
            continue

        target_w = compute_primary_consuming_device_target_w(context, requested_w)
        if haeo_nz_plan is not None and bool(getattr(haeo_nz_plan, 'active', False)):
            limit_w = float(_haeo_plan_device_limit_w(haeo_nz_plan, device_id))
            if limit_w > 0.0:
                target_w = min(float(target_w), limit_w)
            elif str(device_id) == str(_haeo_plan_primary_consuming_device_id(haeo_nz_plan) or ''):
                target_w = 0.0
        if min_absorb_w > 0.0 and 0.0 < float(target_w) < min_absorb_w:
            skipped_by_id[device_id] = 'haeo_limit_below_min_absorb_w'
            continue
        if float(target_w) <= 0.0:
            skipped_by_id[device_id] = 'target_not_realisable'
            continue

        return {
            'configured_ids': tuple(ordered_device_ids or ()),
            'effective_device_id': device_id,
            'effective_target_w': float(target_w),
            'effective_reason': 'selected',
            'requested_w_by_id': requested_w_by_id,
            'skipped_by_id': skipped_by_id,
            'unserved_consuming_w': 0.0,
            'feedback_protection_active': False,
            'feedback_protection_low_energy_active': bool(low_energy_active),
            'feedback_protection_low_energy_threshold_kw': float(low_energy_threshold_kw),
            'feedback_producer_device': feedback_producer_device,
        }

    if not tuple(ordered_device_ids or ()):
        reason = 'no_primary_consuming_devices_configured'
    elif saw_positive_request:
        reason = 'no_realisable_primary_consuming_device'
    else:
        reason = 'no_positive_consuming_request'
    return {
        'configured_ids': tuple(ordered_device_ids or ()),
        'effective_device_id': '',
        'effective_target_w': 0.0,
        'effective_reason': reason,
        'requested_w_by_id': requested_w_by_id,
        'skipped_by_id': skipped_by_id,
        'unserved_consuming_w': float(first_positive_request_w),
        'feedback_protection_active': False,
        'feedback_protection_low_energy_active': False,
        'feedback_protection_low_energy_threshold_kw': 0.0,
        'feedback_producer_device': None,
    }


def compute_primary_producer_feedback_protection(
    primary_device,
    producer_device,
    *,
    low_energy_active,
    explicit_activation_request=False,
):
    """Return whether the selected control topology risks a primary->residual loop.

    The decision is intentionally kind-agnostic: an absorbing primary may be blocked
    only when a different residual regulator can produce power and is actually doing
    so under the applicable low-energy condition. Explicit activation requests are
    authoritative unless an independent lifecycle/safety mechanism blocks them.
    """
    if primary_device is None or producer_device is None:
        return False
    if str(primary_device.device_id) == str(producer_device.device_id):
        return False
    return bool(
        low_energy_active
        and (not bool(explicit_activation_request))
        and bool(primary_device.supports_primary_consuming_regulation)
        and bool(primary_device.can_absorb_w)
        and bool(producer_device.supports_producing_regulation)
        and bool(producer_device.can_produce_w)
        and float(producer_device.current_control_target_w) < 0.0
    )


def _device_low_energy_condition(cfg, device_id, pv_power_kw):
    raw_threshold = float(
        _device_policy_value(cfg, device_id, 'low_pv_threshold_w', 0, facts=None) or 0
    )
    threshold_kw = raw_threshold / 1000.0 if raw_threshold > 50.0 else raw_threshold
    active = (
        threshold_kw > 0.0
        and pv_power_kw is not None
        and float(pv_power_kw) < float(threshold_kw)
    )
    return bool(active), float(threshold_kw)


def compute_hard_off_lifecycle_transition(
    device_context,
    previous_state,
    *,
    lifecycle_enabled,
    requested_active,
    pv_power_w,
    low_pv_threshold_w,
    rpc_w,
    release_rpc_threshold_w,
    activation_blocked=False,
    hard_off_low_pv_cycles=1,
    hard_off_release_cycles=1,
):
    previous_state = previous_state or {}
    previous_low_cycles = int(previous_state.get('low_pv_cycles', 0) or 0)
    previous_release_cycles = int(previous_state.get('hard_off_release_ready_cycles', 0) or 0)
    previous_hard_off = bool(previous_state.get('hard_off_active', False))
    if device_context is None or not device_context.uses_hard_off_lifecycle or not lifecycle_enabled:
        return HardOffLifecycleTransition(
            low_pv_cycles=0,
            hard_off_release_ready_cycles=0,
            hard_off_active=False,
            activation_allowed=True,
            release_allowed=False,
            recovery_condition=False,
            mode='inactive',
        )

    pv_known = pv_power_w is not None
    low_pv = pv_known and float(pv_power_w) < float(low_pv_threshold_w)
    effective_requested_active = bool(requested_active) and not bool(activation_blocked)
    required_low_cycles = max(1, int(hard_off_low_pv_cycles or 1))
    required_release_cycles = max(1, int(hard_off_release_cycles or 1))
    low_cycles = (
        0
        if effective_requested_active or not low_pv
        else min(previous_low_cycles + 1, required_low_cycles)
    )
    recovery_condition = (
        pv_known
        and float(pv_power_w) >= float(low_pv_threshold_w)
        and float(rpc_w) >= float(release_rpc_threshold_w)
        and (not bool(activation_blocked))
    )

    if previous_hard_off:
        release_cycles = previous_release_cycles + 1 if recovery_condition else 0
        release_allowed = release_cycles >= required_release_cycles
        return HardOffLifecycleTransition(
            # Once HARD_OFF has latched, the low-PV debounce counter has already
            # served its purpose. Keep it saturated at the configured threshold
            # until release so persisted Policy State stays stable across long
            # low-PV periods and oversized legacy values normalize on one tick.
            low_pv_cycles=0 if release_allowed else required_low_cycles,
            hard_off_release_ready_cycles=release_cycles,
            hard_off_active=not release_allowed,
            activation_allowed=release_allowed,
            release_allowed=release_allowed,
            recovery_condition=recovery_condition,
            mode='released' if release_allowed else 'hard_off',
        )

    enter_hard_off = (not effective_requested_active) and low_cycles >= required_low_cycles
    return HardOffLifecycleTransition(
        low_pv_cycles=low_cycles,
        hard_off_release_ready_cycles=0,
        hard_off_active=enter_hard_off,
        activation_allowed=not enter_hard_off,
        release_allowed=False,
        recovery_condition=False,
        mode='hard_off' if enter_hard_off else 'active',
    )


def _hard_off_lifecycle_device_ids(cfg, facts=None):
    lifecycle_device_ids = []
    if facts is not None:
        capabilities_by_id = facts.get('device_capabilities_by_id', {}) or {}
        for device_id, capabilities in capabilities_by_id.items():
            if bool((capabilities or {}).get('uses_hard_off_lifecycle', False)):
                lifecycle_device_ids.append(str(device_id))
        return tuple(lifecycle_device_ids)
    device_ids = []
    devices = getattr(cfg, 'devices', {}) or {}
    if isinstance(devices, dict):
        for device_id in devices:
            device_ids.append(str(device_id))
    if not device_ids:
        for kind in ('BATTERY', 'EV_CHARGER', 'RELAY'):
            for device_id in _device_ids_by_kind(cfg, kind, facts=facts):
                text = str(device_id)
                if text not in device_ids:
                    device_ids.append(text)
    for device_id in device_ids:
        if _device_uses_hard_off_lifecycle(cfg, device_id, facts=facts):
            lifecycle_device_ids.append(device_id)
    return tuple(lifecycle_device_ids)


def _device_response_kind(kind):
    kind = str(kind or '')
    if kind == 'BATTERY':
        return 'continuous'
    if kind == 'EV_CHARGER':
        return 'selector'
    return 'relay'


def _is_ev_device_id(cfg, device_id, facts=None):
    device_id = str(device_id or '')
    kind = _device_kind(cfg, device_id, facts=facts)
    if kind:
        return kind == 'EV_CHARGER'
    return device_id == 'EV_CHARGER'


def _ev_context(cfg, device_id, facts=None):
    if facts is not None:
        return _ev_context_from_fact_maps(facts, device_id)

    def _positive_float(value, default):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        return parsed if parsed > 0 else float(default)

    def _non_negative_float(value, default=0.0):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        return parsed if parsed >= 0 else float(default)

    def _int_or_default(value, default=0):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return int(default)

    kind = _device_kind(cfg, device_id, facts=facts)
    device = None
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
            uses_hard_off_lifecycle=False,
            hard_off_pv_threshold_kw=0.0,
            hard_off_low_pv_cycles=0,
            hard_off_release_cycles=0,
            priority=0,
        )
    if not hasattr(cfg, 'device_adapter_value'):
        device = _device_by_id(cfg, device_id)

    current_step_a = _positive_float(_device_adapter_value(cfg, device_id, 'current_step_a', None, facts=facts), 1.0)
    phases = _positive_float(_device_adapter_value(cfg, device_id, 'phases', None, facts=facts), 1.0)
    voltage_v = _positive_float(_device_adapter_value(cfg, device_id, 'voltage_v', None, facts=facts), 230.0)

    raw_force_on = _device_policy_value(cfg, device_id, 'force_on', False, facts=facts)
    if isinstance(raw_force_on, str):
        text = raw_force_on.strip().lower()
        if text in ('true', 'on', '1', 'yes'):
            force_on = True
        elif text in ('false', 'off', '0', 'no', '', 'unknown', 'unavailable', 'none'):
            force_on = False
        else:
            # Grouped-config entity refs must not coerce truthy just because they
            # are non-empty strings.
            force_on = False
    else:
        force_on = bool(raw_force_on)

    low_pv_threshold = _non_negative_float(_device_policy_value(cfg, device_id, 'low_pv_threshold_w', 0, facts=facts), 0.0)
    hard_off_pv_threshold_kw = (
        low_pv_threshold / 1000.0
        if low_pv_threshold > 50.0
        else low_pv_threshold
    )
    min_absorb_w = _non_negative_float(_device_capability(cfg, device_id, 'min_absorb_w', None, facts=facts), 0.0)
    max_absorb_w = _non_negative_float(_device_capability(cfg, device_id, 'max_absorb_w', None, facts=facts), 0.0)
    configured_step_w = _non_negative_float(_device_capability(cfg, device_id, 'step_w', 0, facts=facts), 0.0)
    power_step_w = configured_step_w if configured_step_w > 0 else float(
        ev_current_a_to_power_w(
            current_step_a,
            phases,
            voltage_v,
        )
    )

    return SimpleNamespace(
        device_id=str(device_id or ''),
        device=device,
        adapter=getattr(device, 'adapter', None),
        capabilities=getattr(device, 'capabilities', None),
        policy=getattr(device, 'policy', None),
        current_step_a=int(round(current_step_a)),
        phases=int(round(phases)),
        voltage_v=float(voltage_v),
        min_absorb_w=min_absorb_w,
        max_absorb_w=max_absorb_w,
        power_step_w=float(power_step_w),
        force_on=force_on,
        uses_hard_off_lifecycle=bool(_device_capability(cfg, device_id, 'uses_hard_off_lifecycle', False, facts=facts)),
        hard_off_pv_threshold_kw=hard_off_pv_threshold_kw,
        hard_off_low_pv_cycles=_int_or_default(
            _device_policy_value(cfg, device_id, 'hard_off_low_pv_cycles', 0, facts=facts),
            0,
        ),
        hard_off_release_cycles=_int_or_default(
            _device_policy_value(cfg, device_id, 'hard_off_release_cycles', 0, facts=facts),
            0,
        ),
        priority=_int_or_default(
            _device_policy_value(cfg, device_id, 'priority', 0, facts=facts),
            0,
        ),
    )

def _ev_runtime_state(m, device_id):
    return dict((getattr(m, 'ev_states', {}) or {}).get(str(device_id), {}) or {})


def _ev_runtime_enabled(m, device_id):
    return bool(_ev_runtime_state(m, device_id).get('enabled', False))


def _ev_runtime_current_a(m, device_id):
    return int(_ev_runtime_state(m, device_id).get('current_a', 0) or 0)


def _normalized_discharge_limit_w(cfg, device_id):
    strict_limits_max_w = _global_config_value(cfg, 'strict_limit_w', 0)
    configured = float(_device_capability(cfg, device_id, 'max_produce_w', strict_limits_max_w) or 0.0)
    return max(int(round(configured)), 0), 'positive_magnitude', configured


def _normal_limits_discharge_cap(raw, cfg, device_id):
    limit, _, _ = _normalized_discharge_limit_w(cfg, device_id)
    return max(int(raw), -limit)


def _battery_protect_charge_floor_w(cfg, device_id):
    return int(round(max(float(_battery_guard_value(cfg, device_id, 'protect_min_absorb_w', 0.0) or 0.0), 0.0)))

def _haeo_plan_primary_consuming_device_id(plan):
    return getattr(plan, 'primary_consuming_device_id', '') or getattr(plan, 'primary_load', '')


def _haeo_plan_preferred_surplus_device_id(plan):
    return getattr(plan, 'preferred_surplus_device_id', '')


def _haeo_plan_device_limit_w(plan, device_id):
    limits = getattr(plan, 'device_limits_w', {}) or {}
    if isinstance(limits, dict) and device_id in limits:
        return int(limits.get(device_id, 0) or 0)
    return 0


def _dispatch_action_and_device_id(surplus_decision, combo_change_requires_clear):
    if combo_change_requires_clear or surplus_decision.clear_all:
        return 'CLEAR_ALL', ''
    if surplus_decision.activate:
        return 'ACTIVATE', str(surplus_decision.activate)
    if surplus_decision.release:
        return 'RELEASE', str(surplus_decision.release)
    return 'NOOP', ''


def _kw_to_w(power_kw):
    return int(round(float(power_kw) * 1000.0))


def _device_policy_payload(policy):
    payload = {
        'device_id': policy.device_id,
        'target_w': int(policy.target_w),
        'enabled': bool(policy.enabled),
        'mode': policy.mode,
        'reason': policy.reason,
    }
    return payload


def _capability_device_config_for_id(cfg, device_id, facts=None):
    kind = _device_kind(cfg, device_id, facts=facts)
    if kind:
        min_absorb_w = _device_capability(cfg, device_id, 'min_absorb_w', 0, facts=facts)
        max_absorb_w = _device_capability(cfg, device_id, 'max_absorb_w', 0, facts=facts)
        min_produce_w = _device_capability(cfg, device_id, 'min_produce_w', 0, facts=facts)
        max_produce_w = _device_capability(cfg, device_id, 'max_produce_w', 0, facts=facts)
        step_w = _device_capability(cfg, device_id, 'step_w', 0, facts=facts)
        return EmsDeviceConfig(
            device_id=str(device_id),
            kind=str(kind),
            response_kind=_device_response_kind(kind),
            can_absorb_w=bool(_device_capability(cfg, device_id, 'can_absorb_w', False, facts=facts)),
            can_produce_w=bool(_device_capability(cfg, device_id, 'can_produce_w', False, facts=facts)),
            min_absorb_w=int(round(float(min_absorb_w or 0))),
            max_absorb_w=int(round(float(max_absorb_w or 0))),
            min_produce_w=int(round(float(min_produce_w or 0))),
            max_produce_w=int(round(float(max_produce_w or 0))),
            step_w=max(1, int(round(float(step_w or 0)))),
            priority=int(round(float(_device_policy_value(cfg, device_id, 'priority', 0, facts=facts) or 0))),
            producing_priority=int(round(float(_device_policy_value(cfg, device_id, 'producing_priority', 0, facts=facts) or 0))),
        )
    raise KeyError(f'unknown device_id: {device_id}')


def _relay_devices(cfg, facts=None):
    return tuple(_device_ids_by_kind(cfg, 'RELAY', facts=facts))


def _ev_devices(cfg, facts=None):
    return tuple(_device_ids_by_kind(cfg, 'EV_CHARGER', facts=facts))


def _relay_device_ids_payload(cfg, facts=None):
    payload = []
    for relay in _relay_devices(cfg, facts=facts):
        payload.append(str(relay))
    return tuple(payload)


def _ev_device_ids_payload(cfg, facts=None):
    payload = []
    for ev in _ev_devices(cfg, facts=facts):
        payload.append(str(ev))
    return tuple(payload)


def _ordered_device_ids(cfg, facts=None):
    ordered = []
    if facts is not None:
        for device_id in (facts.get('device_kind_by_id', {}) or {}):
            text = str(device_id)
            if text not in ordered:
                ordered.append(text)
    if not ordered:
        devices = getattr(cfg, 'devices', {}) or {}
        if isinstance(devices, dict):
            for device_id in devices:
                text = str(device_id)
                if text not in ordered:
                    ordered.append(text)
    if not ordered:
        for kind in ('BATTERY', 'EV_CHARGER', 'RELAY'):
            for device_id in _device_ids_by_kind(cfg, kind, facts=facts):
                text = str(device_id)
                if text not in ordered:
                    ordered.append(text)
    return tuple(ordered)


def _surplus_threshold_w(cfg, device_id, facts=None):
    # Single authoritative surplus activation semantic:
    # threshold_w == physical max_absorb_w capability.
    max_w = float(_device_capability(cfg, device_id, 'max_absorb_w', 0, facts=facts) or 0)
    return max(max_w, 0.0), 'device_capabilities.max_absorb_w'

def _surplus_dispatch_mode(cfg, device_id, facts=None):
    mode = str(_device_policy_value(cfg, device_id, 'surplus_dispatch_mode', '', facts=None) or '')
    if mode in ('max_absorb', 'fixed'):
        return mode
    min_w = float(_device_capability(cfg, device_id, 'min_absorb_w', 0, facts=facts) or 0)
    max_w = float(_device_capability(cfg, device_id, 'max_absorb_w', 0, facts=facts) or 0)
    return 'fixed' if min_w > 0.0 and abs(max_w - min_w) < 0.5 else 'max_absorb'


def _surplus_target_w_for_device(cfg, device_id, dispatch_mode, facts=None):
    if str(dispatch_mode) == 'fixed':
        min_w = float(_device_capability(cfg, device_id, 'min_absorb_w', 0, facts=facts) or 0)
        max_w = float(_device_capability(cfg, device_id, 'max_absorb_w', 0, facts=facts) or 0)
        if min_w > 0.0:
            return int(round(min_w))
        return int(round(max(max_w, 0.0)))
    return int(round(max(float(_device_capability(cfg, device_id, 'max_absorb_w', 0, facts=facts) or 0), 0.0)))


def _generic_surplus_candidate_contexts(
    cfg,
    *,
    active_device_ids,
    lifecycle_transitions_by_id,
    primary_consuming_device_id='',
    runtime_device_states=None,
    facts=None,
):
    active_set = set()
    for item in (active_device_ids or ()):
        active_set.add(str(item))
    runtime_state_by_id = {}
    for state_device_id, state in (runtime_device_states or {}).items():
        runtime_state_by_id[str(state_device_id)] = dict(state or {})
    contexts = []
    for device_id in _ordered_device_ids(cfg, facts=facts):
        if str(device_id) == str(primary_consuming_device_id or ''):
            # The effective primary consuming regulator owns its target for this tick.
            # Producer membership is independent and remains available in the opposite
            # signed direction, but the same device must not also enter surplus dispatch.
            continue
        state = runtime_state_by_id.get(str(device_id), {})
        can_absorb = _device_can_absorb(cfg, device_id, facts=facts)
        surplus_allowed = _runtime_policy_bool(
            state.get(
                'surplus_allowed',
                _device_policy_value(cfg, device_id, 'surplus_allowed', False, facts=None),
            )
        )
        is_active = str(device_id) in active_set
        force_on = _runtime_policy_bool(
            state.get(
                'force_on',
                _device_policy_value(cfg, device_id, 'force_on', False, facts=None),
            )
        )
        # Retain an already-active device as a disabled target long enough for the
        # allocator to emit a release when eligibility/capability is withdrawn.
        # An explicit FORCE_ON request bypasses optimizer-owned surplus eligibility,
        # but never a missing absorb capability.
        if not is_active and (not can_absorb or ((not surplus_allowed) and (not force_on))):
            continue
        threshold_w, threshold_source = _surplus_threshold_w(
            cfg, device_id, facts=facts
        )
        transition = (lifecycle_transitions_by_id or {}).get(str(device_id))
        lifecycle_activation_allowed = (
            True if transition is None else bool(transition.activation_allowed)
        )
        # FORCE_ON is an explicit user override of optimizer-owned activation gates.
        # Keep lifecycle state latched in the background, but do not expose an
        # optimizer HARD_OFF as an effective activation denial for this request.
        activation_allowed = bool(lifecycle_activation_allowed or force_on)
        contexts.append(
            {
                'device_id': str(device_id),
                'priority': int(_device_policy_value(cfg, device_id, 'priority', 0, facts=None) or 0),
                'threshold_w': threshold_w,
                'surplus_dispatch_mode': _surplus_dispatch_mode(cfg, device_id, facts=facts),
                'enabled': bool(
                    can_absorb and (surplus_allowed or force_on) and threshold_w > 0.0
                ),
                'force_on': force_on,
                'active': is_active,
                'activation_allowed': activation_allowed,
                'threshold_source': threshold_source,
            }
        )
    ordered = []
    for context in contexts:
        insert_at = len(ordered)
        index = 0
        while index < len(ordered):
            if int(context['priority']) > int(ordered[index]['priority']):
                insert_at = index
                break
            index += 1
        ordered.insert(insert_at, context)
    return tuple(ordered)


def _surplus_target_by_device_id(targets):
    result = {}
    for target in (targets or ()):
        result[str(target.device_id)] = target
    return result


def _lifecycle_transition_maps(
    cfg,
    profiles,
    nz,
    *,
    previous_device_states,
    active_device_ids,
    primary_consuming_device_ids,
    pv_power_kw,
    current_power_by_id,
    primary_requested_active_by_id=None,
    feedback_protection_by_id=None,
    facts=None,
):
    transitions = {}
    next_states = _normalize_previous_device_states(previous_device_states)
    active_set = set()
    for item in (active_device_ids or ()):
        active_set.add(str(item))
    primary_set = set()
    for item in (primary_consuming_device_ids or ()):
        primary_set.add(str(item))
    requested_active_map = dict(primary_requested_active_by_id or {})
    feedback_protection_map = dict(feedback_protection_by_id or {})
    lifecycle_enabled = (
        profiles.control == ControlProfile.AUTOMATIC
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
    )
    for device_id in _hard_off_lifecycle_device_ids(cfg, facts=facts):
        device_id = str(device_id)
        previous = next_states.get(device_id, _default_previous_device_state(device_id))
        participates = (
            device_id in primary_set
            or (
                _device_can_absorb(cfg, device_id, facts=facts)
                and _runtime_policy_bool(_device_policy_value(cfg, device_id, 'surplus_allowed', False, facts=None))
            )
            or bool(previous.get('hard_off_active', False))
        )
        if not participates:
            next_states.setdefault(device_id, previous)
            continue
        context = _device_control_context(
            cfg,
            device_id,
            current_control_target_w=(current_power_by_id or {}).get(device_id, 0.0),
            facts=facts,
        )
        raw_low_pv = float(_device_policy_value(cfg, device_id, 'low_pv_threshold_w', 0, facts=None) or 0)
        low_pv_threshold_kw = raw_low_pv / 1000.0 if raw_low_pv > 50.0 else raw_low_pv
        threshold_w, _source = _surplus_threshold_w(
            cfg, device_id, facts=facts
        )
        if device_id in primary_set:
            # Primary lifecycle recovery preserves the established EV-minimum threshold;
            # a surplus activation threshold is a different policy concern.
            threshold_w = float(_device_capability(cfg, device_id, 'min_absorb_w', 0, facts=facts) or 0)
        requested_active = (
            bool(requested_active_map.get(device_id, False))
            if device_id in primary_set
            else device_id in active_set
        )
        activation_blocked = bool(feedback_protection_map.get(device_id, False))
        transition = compute_hard_off_lifecycle_transition(
            context,
            previous,
            lifecycle_enabled=lifecycle_enabled,
            requested_active=requested_active,
            pv_power_w=pv_power_kw,
            low_pv_threshold_w=low_pv_threshold_kw,
            rpc_w=float(nz.required_power_consumption_kw),
            release_rpc_threshold_w=float(max(threshold_w, 0.0)) / 1000.0,
            activation_blocked=activation_blocked,
            hard_off_low_pv_cycles=int(_device_policy_value(cfg, device_id, 'hard_off_low_pv_cycles', 1, facts=None) or 1),
            hard_off_release_cycles=int(_device_policy_value(cfg, device_id, 'hard_off_release_cycles', 1, facts=None) or 1),
        )
        transitions[device_id] = transition
        next_states[device_id] = _normalize_previous_device_state_entry(
            device_id,
            {
                'device_id': device_id,
                'mode': transition.mode,
                'low_pv_cycles': transition.low_pv_cycles,
                'hard_off_release_ready_cycles': transition.hard_off_release_ready_cycles,
                'hard_off_active': transition.hard_off_active,
            },
        )
    return transitions, next_states


def _relay_runtime_candidates(cfg, relay_device_states, facts=None):
    candidates = []
    state_map = relay_device_states or {}
    for relay in _relay_devices(cfg, facts=facts):
        device_id = str(relay)
        state = dict(state_map.get(device_id, {}) or {})
        threshold_w = max(int(round(float(_device_capability(cfg, device_id, 'max_absorb_w', 0, facts=facts) or 0))), 0)
        candidates.append(
            {
                'device_id': device_id,
                'priority': int(round(float(_device_policy_value(cfg, device_id, 'priority', 0, facts=facts) or 0))),
                'threshold_w': threshold_w,
                'enabled': bool(state.get('surplus_allowed', False)) and _device_can_absorb(cfg, device_id, facts=facts),
                'force_on': bool(state.get('force_on', False)),
                'active': bool(state.get('active', False)),
            }
        )
    return tuple(candidates)


def _default_previous_device_state(device_id=''):
    return {
        'device_id': str(device_id or ''),
        'mode': '',
        'low_pv_cycles': 0,
        'hard_off_release_ready_cycles': 0,
        'hard_off_active': False,
    }


def _normalize_previous_device_state_entry(device_id, state):
    normalized = _default_previous_device_state(device_id)
    state = dict(state or {})
    normalized['device_id'] = str(state.get('device_id') or device_id or '')
    normalized['mode'] = str(state.get('mode') or '')
    normalized['low_pv_cycles'] = int(state.get('low_pv_cycles', 0) or 0)
    normalized['hard_off_release_ready_cycles'] = int(state.get('hard_off_release_ready_cycles', 0) or 0)
    normalized['hard_off_active'] = bool(state.get('hard_off_active', False))
    return normalized


def _normalize_previous_device_states(previous_device_states):
    normalized = {}
    for device_id, state in (previous_device_states or {}).items():
        normalized[str(device_id)] = _normalize_previous_device_state_entry(device_id, state)
    return normalized


def _enforce_device_policy_capabilities(cfg, device_policies, facts=None):
    sanitized = []
    blocked = []
    for policy in device_policies:
        device_cfg = _capability_device_config_for_id(cfg, policy.device_id, facts=facts)
        clamped_target_w = clamp_target_w_for_capabilities(device_cfg, policy.target_w)
        block_reason = capability_block_reason(device_cfg, policy.target_w)
        enabled = bool(policy.enabled)
        mode = policy.mode
        reason = policy.reason
        if block_reason:
            blocked.append(policy.device_id + ':' + block_reason)
            if str(device_cfg.kind) == 'BATTERY':
                enabled = True
                mode = 'power'
            elif str(device_cfg.kind) == 'EV_CHARGER':
                enabled = False
                mode = 'restore_min'
            else:
                enabled = False
                mode = 'relay'
            reason = block_reason
        sanitized.append(
            DevicePolicy(
                device_id=policy.device_id,
                target_w=int(clamped_target_w),
                enabled=enabled,
                mode=mode,
                reason=reason,
            )
        )
    return tuple(sanitized), tuple(blocked)


def _device_policy_payloads(device_policies):
    payloads = []
    for policy in device_policies:
        payloads.append(_device_policy_payload(policy))
    return tuple(payloads)



def _build_device_policies(
    cfg,
    *,
    battery_policies_by_id,
    ev_policies_by_id,
    relay_policies,
    producer_authority_by_id=None,
    facts=None,
):
    ev_policy_by_id = {}
    for key, value in (ev_policies_by_id or {}).items():
        ev_policy_by_id[str(key)] = dict(value or {})
    battery_policy_by_id = {}
    for key, value in (battery_policies_by_id or {}).items():
        battery_policy_by_id[str(key)] = dict(value or {})
    relay_policy_by_id = {}
    for item in (relay_policies or ()):
        relay_policy_by_id[str(item['device_id'])] = item
    normalized_producer_authority_by_id = {}
    for key, value in (producer_authority_by_id or {}).items():
        normalized_producer_authority_by_id[str(key)] = dict(value or {})
    producer_authority_by_id = normalized_producer_authority_by_id

    policies = []
    for device_id in _ordered_device_ids(cfg, facts=facts):
        device_id = str(device_id)
        kind = _device_kind(cfg, device_id, facts=facts)
        if device_id in producer_authority_by_id:
            authority = producer_authority_by_id[device_id]
            policies.append(DevicePolicy(
                device_id=device_id,
                target_w=int(round(float(authority.get('target_w', 0) or 0))),
                enabled=True,
                mode='power',
                reason='producer_authority',
            ))
            continue
        if kind == 'BATTERY':
            item = battery_policy_by_id.get(device_id, {})
            policies.append(DevicePolicy(
                device_id=device_id,
                target_w=int(round(float(item.get('target_w', 0) or 0))),
                enabled=bool(item.get('enabled', False)),
                mode=str(item.get('mode', 'power') or 'power'),
                reason=str(item.get('reason', 'battery_policy_inactive') or 'battery_policy_inactive'),
            ))
            continue
        if kind == 'EV_CHARGER':
            item = ev_policy_by_id.get(device_id, {
                'target_w': 0, 'enabled': False, 'mode': 'restore_min', 'reason': 'ev_policy_inactive'
            })
            policies.append(DevicePolicy(
                device_id=device_id,
                target_w=int(round(float(item.get('target_w', 0) or 0))),
                enabled=bool(item.get('enabled', False)),
                mode=str(item.get('mode', 'restore_min') or 'restore_min'),
                reason=str(item.get('reason', 'ev_policy') or 'ev_policy'),
            ))
            continue
        if kind == 'RELAY':
            relay_policy = relay_policy_by_id.get(device_id, {'device_id': device_id, 'command': 0})
            relay_cfg = _capability_device_config_for_id(cfg, device_id, facts=facts)
            relay_target_w = int(round(float(relay_cfg.max_absorb_w))) if int(relay_policy['command']) > 0 else 0
            policies.append(DevicePolicy(
                device_id=device_id,
                target_w=relay_target_w,
                enabled=int(relay_policy['command']) > 0,
                mode='skip' if int(relay_policy['command']) < 0 else 'relay',
                reason='relay_policy',
            ))
    return tuple(policies)

def _battery_target_and_authority(
    profiles,
    cfg,
    battery_device_id,
    primary_device_context,
    m,
    haeo,
    nz,
    *,
    primary_active=False,
    battery_surplus_release_pending=False,
    primary_target_w=0.0,
    separate_primary_regulation=False,
    is_effective_primary=False,
    no_effective_primary_regulation=False,
    haeo_nz_plan=None,
    battery_surplus_target=None,
    facts=None,
):
    """Return the canonical consuming/baseline battery target before producer override."""
    battery_device_id = str(battery_device_id or '')
    battery_state = m.battery_state(battery_device_id) if hasattr(m, 'battery_state') else {}
    current_sp_w = float(battery_state.get('current_setpoint_w', 0.0) or 0.0)
    max_absorb_w = float(_device_capability(cfg, battery_device_id, 'max_absorb_w', 0.0, facts=facts) or 0.0)
    battery_min_floor_w = None
    battery_min_floor_reason = 'not_applicable'

    if profiles.control == ControlProfile.MANUAL:
        return int(round(current_sp_w)), False, battery_min_floor_w, battery_min_floor_reason

    if profiles.control == ControlProfile.MANUAL_SAFE:
        current = int(round(current_sp_w))
        protect_floor = _battery_protect_charge_floor_w(cfg, battery_device_id)
        if profiles.guard == GuardProfile.DEGRADED:
            return 0, True, battery_min_floor_w, battery_min_floor_reason
        if profiles.guard == GuardProfile.BATTERY_PROTECT:
            return max(current, protect_floor), True, battery_min_floor_w, battery_min_floor_reason
        if profiles.guard == GuardProfile.STRICT_LIMITS:
            limit = int(_global_config_value(cfg, 'strict_limit_w', 0) or 0)
            return min(max(current, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason
        return current, False, battery_min_floor_w, battery_min_floor_reason

    if profiles.goal == GoalProfile.NET_ZERO:
        effective_rpnz_w = float(nz.rpnz_w)
        min_charge_floor_w = float(_global_config_value(cfg, 'nz_battery_floor_default_w', 100.0) or 0.0)
        battery_surplus_active = bool(
            battery_surplus_target is not None and getattr(battery_surplus_target, 'active', False)
        )
        battery_surplus_authority_active = bool(battery_surplus_active)
        battery_surplus_configured = battery_surplus_target is not None
        configured_activation_w = (
            float(getattr(battery_surplus_target, 'threshold_w', 0) or 0)
            if battery_surplus_configured else 0.0
        )

        if separate_primary_regulation:
            min_charge_floor_w = float(_global_config_value(cfg, 'nz_battery_floor_ev_active_w', 0.0) or 0.0)
            battery_min_floor_reason = (
                'ev_active_floor_override'
                if str(getattr(primary_device_context, 'kind', '') or '') == 'EV_CHARGER'
                else 'primary_consuming_active_floor_override'
            )
            battery_min_floor_w = float(min_charge_floor_w)
            # Do not subtract the commanded primary target: once realized, its
            # effect is already present in measured grid power. The grid meter
            # remains the feedback truth for this controller.
            effective_rpnz_w = float(nz.rpnz_w)
        if battery_min_floor_w is None:
            battery_min_floor_w = float(min_charge_floor_w)

        raw = candidate_sp_net_zero(
            rpnz_w=effective_rpnz_w,
            grid_actual_w=m.grid_power_w,
            current_sp_w=current_sp_w,
            deadband_w=_global_config_value(cfg, 'deadband_w', 50.0),
            ramp_w=_global_config_value(cfg, 'ramp_w', 1000.0),
            max_sp_w=max_absorb_w,
            min_charge_floor_w=min_charge_floor_w,
        )

        if is_effective_primary:
            # The common primary resolver owns consuming-direction target formation.
            # Surplus activation thresholds must never gate effective primary control.
            raw = int(round(max(float(primary_target_w or 0.0), 0.0)))

        if separate_primary_regulation and primary_active:
            # The explicit primary consuming regulator owns *increases* in the
            # consuming direction. A battery may still unwind an existing
            # positive target toward its floor under measured grid feedback;
            # this preserves controller continuity without letting the battery
            # compete with the active primary for new absorb authority.
            max_baseline_consuming_w = max(float(current_sp_w), float(min_charge_floor_w))
            uncapped_raw = float(raw)
            raw = min(uncapped_raw, max_baseline_consuming_w)
            if float(raw) < uncapped_raw:
                battery_min_floor_reason = 'primary_consuming_authority_hold'

        if no_effective_primary_regulation and not battery_surplus_authority_active:
            # A configured fallback pool with no realizable effective primary must
            # not create an implicit battery fallback outside the resolver. Existing
            # positive controller state may unwind, but new consuming authority is not
            # invented here.
            max_baseline_consuming_w = max(float(current_sp_w), float(min_charge_floor_w))
            uncapped_raw = float(raw)
            raw = min(uncapped_raw, max_baseline_consuming_w)
            if float(raw) < uncapped_raw:
                battery_min_floor_reason = 'no_effective_primary_hold'

        # Canonical directional ownership: negative control is allocated only
        # by the explicit producer pool below.
        if raw < 0:
            raw = 0

        if (
            separate_primary_regulation
            and battery_surplus_configured
            and battery_surplus_authority_active
            and float(nz.rpnz_w) >= 0.0
        ):
            raw = int(round(min(max(configured_activation_w, 0.0), max_absorb_w)))

        activation_gate_active = (
            (not is_effective_primary)
            and battery_surplus_configured
            and configured_activation_w > 0.0
            and (not battery_surplus_authority_active)
            and float(nz.required_power_consumption_kw) < (configured_activation_w / 1000.0)
        )
        if activation_gate_active and raw > current_sp_w and raw >= 0 and current_sp_w >= 0:
            raw = int(round(current_sp_w))
            battery_min_floor_reason = 'activation_gate_hold'

        if haeo_nz_plan is not None and bool(getattr(haeo_nz_plan, 'active', False)):
            plan_limit_w = _haeo_plan_device_limit_w(haeo_nz_plan, battery_device_id)
            if plan_limit_w > 0 and raw > plan_limit_w:
                raw = plan_limit_w
    elif haeo.effective_forecast == ForecastProfile.HAEO and profiles.goal in (
        GoalProfile.MAX_EXPORT, GoalProfile.CHEAP_GRID_CHARGE
    ):
        raw = int(round(float(haeo.target_kw(battery_device_id, 0.0) or 0.0) * 1000.0))
    elif profiles.goal == GoalProfile.MAX_EXPORT:
        # Preserve the independent local MAX_EXPORT behavior; directional producer
        # ceilings govern NET_ZERO dispatch, not this separate goal.
        raw = -4000
    elif profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        raw = min(100, int(round(max_absorb_w)))
    else:
        raw = int(round(_global_config_value(cfg, 'default_sp_w', 100.0) or 0.0))

    if profiles.guard == GuardProfile.DEGRADED:
        return 0, True, battery_min_floor_w, battery_min_floor_reason
    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return max(raw, _battery_protect_charge_floor_w(cfg, battery_device_id)), True, battery_min_floor_w, battery_min_floor_reason
    if profiles.guard == GuardProfile.STRICT_LIMITS:
        limit = int(_global_config_value(cfg, 'strict_limit_w', 0) or 0)
        return min(max(raw, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason
    if profiles.guard == GuardProfile.NORMAL_LIMITS:
        raw = _normal_limits_discharge_cap(raw, cfg, battery_device_id)
    return int(round(raw)), True, battery_min_floor_w, battery_min_floor_reason

def net_zero_surplus_policy_active(profiles, effective_fc, haeo_nz_plan_active=False):
    return (
        profiles.control == ControlProfile.AUTOMATIC
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and effective_fc == ForecastProfile.NONE
    ) or (
        profiles.control == ControlProfile.HORIZON_BY_HAEO
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and bool(haeo_nz_plan_active)
    )


def _ev_policy_mode_and_target_w(
    profiles, ev_context, haeo, *,
    role,
    burn_active,
    activation_blocked,
    surplus_active,
    ev_release_pending,
    rpnz_w,
    lifecycle_transition,
    uses_hard_off_lifecycle=False,
    haeo_nz_plan=None,
):
    target_w = ev_strategy_target_w(
        profiles,
        ev_context,
        haeo,
        burn_active,
    )

    if (
        burn_active
        and surplus_active
        and (not ev_release_pending)
        and role == 'surplus_candidate'
        and float(rpnz_w) > 0.0
    ):
        target_w = float(ev_max_power_w(ev_context))

    force_on = bool(getattr(ev_context, 'force_on', False))

    if (
        profiles.goal == GoalProfile.NET_ZERO
        and haeo_nz_plan is not None
        and bool(getattr(haeo_nz_plan, 'active', False))
        and target_w > 0
        and (not force_on)
    ):
        limit_w = float(_haeo_plan_device_limit_w(haeo_nz_plan, ev_context.device_id))
        target_w = min(float(target_w), limit_w) if limit_w > 0 else 0.0

    if profiles.goal == GoalProfile.MAX_EXPORT and target_w == 0:
        mode = 'hard_off' if uses_hard_off_lifecycle else 'restore_min'
        return mode, 0.0

    if activation_blocked and (not force_on):
        target_w = 0.0

    if (
        uses_hard_off_lifecycle
        and lifecycle_transition is not None
        and lifecycle_transition.hard_off_active
        and (not force_on)
    ):
        return 'hard_off', 0.0

    if target_w > 0:
        return 'burn', float(target_w)

    restore_min_w = float(ev_min_power_w(ev_context)) if role == 'primary' else 0.0
    return 'restore_min', restore_min_w


def _ev_surplus_policy_for_device(
    profiles,
    cfg,
    device_id,
    ev_context,
    haeo,
    *,
    surplus_target=None,
    lifecycle_transition=None,
    dispatch_decision=None,
    combo_change_requires_clear=False,
    rpnz_w=0.0,
    haeo_nz_plan=None,
    facts=None,
):
    device_id = str(device_id)
    active = bool(getattr(surplus_target, 'active', False))
    release_pending = bool(
        dispatch_decision is not None and str(getattr(dispatch_decision, 'release', '') or '') == device_id
    )
    clear_pending = bool(
        profiles.goal == GoalProfile.NET_ZERO
        and (
            combo_change_requires_clear
            or (
                surplus_target is not None
                and dispatch_decision is not None
                and bool(getattr(dispatch_decision, 'clear_all', False))
            )
        )
    )
    release_allowed = bool(
        lifecycle_transition is not None and getattr(lifecycle_transition, 'release_allowed', False)
    )
    force_on = bool(getattr(ev_context, 'force_on', False))
    burn_active = (active or release_allowed) and not clear_pending

    target_w = float(ev_strategy_target_w(profiles, ev_context, haeo, burn_active))
    if (
        burn_active
        and active
        and (not release_pending)
        and float(rpnz_w) > 0.0
        and surplus_target is not None
    ):
        # Preserve the established one-cycle active surplus EV target while a
        # goal transition clears the dispatch stack. The rule is per device,
        # resolved per device-ID.
        target_w = float(
            _surplus_target_w_for_device(
                cfg,
                device_id,
                getattr(surplus_target, 'surplus_dispatch_mode', ''),
                facts=facts,
            )
        )
    if (
        profiles.goal == GoalProfile.NET_ZERO
        and burn_active
        and surplus_target is not None
    ):
        target_w = float(
            _surplus_target_w_for_device(
                cfg,
                device_id,
                getattr(surplus_target, 'surplus_dispatch_mode', ''),
                facts=facts,
            )
        )

    if (
        profiles.goal == GoalProfile.NET_ZERO
        and haeo_nz_plan is not None
        and bool(getattr(haeo_nz_plan, 'active', False))
        and target_w > 0.0
        and (not force_on)
    ):
        limit_w = float(_haeo_plan_device_limit_w(haeo_nz_plan, device_id))
        target_w = min(target_w, limit_w) if limit_w > 0.0 else 0.0

    if (
        lifecycle_transition is not None
        and bool(getattr(lifecycle_transition, 'hard_off_active', False))
        and (not force_on)
    ):
        return {
            'target_w': 0.0,
            'enabled': False,
            'mode': 'hard_off',
            'reason': 'ev_lifecycle_hard_off',
        }
    if (clear_pending or (release_pending and not active)) and (not force_on):
        return {
            'target_w': 0.0,
            'enabled': False,
            'mode': 'restore_min',
            'reason': 'ev_surplus_release',
        }
    if profiles.goal == GoalProfile.MAX_EXPORT and target_w <= 0.0:
        return {
            'target_w': 0.0,
            'enabled': False,
            'mode': 'hard_off' if _device_uses_hard_off_lifecycle(cfg, device_id, facts=facts) else 'restore_min',
            'reason': 'ev_policy',
        }
    if target_w > 0.0:
        return {
            'target_w': target_w,
            'enabled': True,
            'mode': 'burn',
            'reason': 'ev_force_on' if force_on else 'ev_surplus_policy',
        }
    return {
        'target_w': 0.0,
        'enabled': False,
        'mode': 'restore_min',
        'reason': 'ev_policy_inactive',
    }


def _primary_device_power_envelope_w(cfg, device_context, m, nz):
    return candidate_sp_net_zero(
        rpnz_w=float(nz.rpnz_w),
        grid_actual_w=float(m.grid_power_w),
        current_sp_w=float(device_context.current_control_target_w),
        deadband_w=float(_global_config_value(cfg, 'deadband_w', 50.0)),
        ramp_w=float(_global_config_value(cfg, 'ramp_w', 1000.0)),
        max_sp_w=float(device_context.max_absorb_w),
        min_charge_floor_w=0.0,
    )


def _apply_force_rising_edge_freeze_for_devices(
    now_ts,
    freeze_until_ts,
    freeze_s,
    relay_candidates,
    previous_force_on_device_ids=None,
):
    freeze_until = freeze_until_ts
    previous_force_on_device_ids = set(previous_force_on_device_ids or ())
    current_force_on_device_ids = set()
    for relay in relay_candidates:
        if bool(relay.get('force_on', False)):
            current_force_on_device_ids.add(str(relay.get('device_id')))
    rising_edge = False
    for device_id in current_force_on_device_ids:
        if device_id not in previous_force_on_device_ids:
            rising_edge = True
            break
    if rising_edge:
        target_freeze = now_ts + freeze_s
        if freeze_until is None:
            freeze_until = target_freeze
        else:
            freeze_until = max(float(freeze_until), float(target_freeze))
    return freeze_until, tuple(sorted(current_force_on_device_ids))


def _canonical_surplus_freeze_until_ts_for_output(
    dispatch_action,
    combo_change_freeze_until_ts,
    decision_freeze_until_ts,
    effective_freeze_until_ts,
):
    if combo_change_freeze_until_ts is not None:
        return combo_change_freeze_until_ts
    action = str(dispatch_action or '')
    if action == 'CLEAR_ALL':
        return None
    if action == 'NOOP':
        return effective_freeze_until_ts
    if decision_freeze_until_ts is not None:
        return decision_freeze_until_ts
    return effective_freeze_until_ts


def compute_net_zero_engine_outputs(
    profiles, cfg, m, haeo, nz, now_ts, *,
    freeze_until_ts,
    pv_power_kw=None,
    relay_device_states=None,
    previous_device_states=None,
    previous_force_on_device_ids=None,
    haeo_nz_plan=None,
    current_device_control_target_w_by_id=None,
    active_surplus_device_ids=None,
):
    global _ACTIVE_NET_ZERO_COMPUTE_METRICS
    _reset_net_zero_compute_metrics()
    if NET_ZERO_DETAILED_METRICS_ENABLED:
        _ACTIVE_NET_ZERO_COMPUTE_METRICS = dict(_LAST_NET_ZERO_COMPUTE_METRICS)
    else:
        _ACTIVE_NET_ZERO_COMPUTE_METRICS = None
    try:
        state_parse_started_ts = _net_zero_profile_started_ts()
        policy_runtime_facts = _build_policy_runtime_facts(cfg)

        forecast_haeo_started_ts = _net_zero_profile_started_ts()
        conf_fc = configured_forecast(profiles.control, profiles.forecast)
        eff_fc = effective_forecast(conf_fc, haeo.fresh)

        normalized_haeo = HaeoTargets(
            effective_forecast=eff_fc,
            configured_forecast=conf_fc,
            fresh=haeo.fresh,
            device_target_kw_by_id=dict(getattr(haeo, 'device_target_kw_by_id', {}) or {}),
            device_age_s_by_id=dict(getattr(haeo, 'device_age_s_by_id', {}) or {}),
        )

        if haeo_nz_plan is None:
            haeo_nz_plan = HaeoNetZeroPlan(False, device_limits_w={})
        haeo_nz_plan_active = bool(getattr(haeo_nz_plan, 'active', False))
        _note_net_zero_duration_ms('policy_engine_net_zero_forecast_haeo_normalization_ms', forecast_haeo_started_ts)

        role_normalization_started_ts = _net_zero_profile_started_ts()
        configured_primary_consuming_device_ids = _normalized_primary_consuming_device_ids(
            cfg, facts=policy_runtime_facts
        )
        ordered_primary_consuming_device_ids = _ordered_primary_consuming_device_ids(
            cfg, haeo_nz_plan=haeo_nz_plan, facts=policy_runtime_facts
        )
        preferred_primary_consuming_device_id = (
            str(ordered_primary_consuming_device_ids[0])
            if ordered_primary_consuming_device_ids else ''
        )
        primary_surplus_combo_source = (
            'HAEO_NET_ZERO_PLAN' if haeo_nz_plan_active else 'CONFIG'
        )

        current_power_by_id = {}
        for device_id, power_w in (current_device_control_target_w_by_id or {}).items():
            current_power_by_id[str(device_id)] = float(power_w or 0.0)
        # Direct engine callers still get explicit controller-state fallbacks from
        # device-owned runtime state. These values are targets/state, not measurements.
        for configured_device_id in _ordered_device_ids(cfg, facts=policy_runtime_facts):
            configured_device_id = str(configured_device_id)
            if configured_device_id in current_power_by_id:
                continue
            kind = _device_kind(cfg, configured_device_id, facts=policy_runtime_facts)
            if kind == 'BATTERY' and hasattr(m, 'battery_state'):
                current_power_by_id[configured_device_id] = float(
                    m.battery_state(configured_device_id).get('current_setpoint_w', 0.0) or 0.0
                )
            elif kind == 'EV_CHARGER':
                ev_context_for_state = _ev_context(cfg, configured_device_id, facts=policy_runtime_facts)
                current_power_by_id[configured_device_id] = float(
                    ev_current_a_to_power_w(
                        _ev_runtime_current_a(m, configured_device_id),
                        ev_context_for_state.phases,
                        ev_context_for_state.voltage_v,
                    )
                )

        configured_device_contexts = []
        configured_device_context_by_id = {}
        for configured_device_id in _ordered_device_ids(cfg, facts=policy_runtime_facts):
            configured_context = _device_control_context(
                cfg,
                configured_device_id,
                current_control_target_w=current_power_by_id.get(str(configured_device_id), 0.0),
                facts=policy_runtime_facts,
            )
            configured_device_contexts.append(configured_context)
            configured_device_context_by_id[str(configured_device_id)] = configured_context
        preferred_primary_device = configured_device_context_by_id.get(
            str(preferred_primary_consuming_device_id or '')
        )
        producer_contexts = _producer_device_contexts(
            cfg, configured_device_context_by_id, facts=policy_runtime_facts
        )
        primary_requested_active_by_id = {}
        preliminary_feedback_protection_by_id = {}
        preliminary_feedback_producer_by_id = {}
        preliminary_low_energy_by_id = {}
        preliminary_low_energy_threshold_by_id = {}
        for primary_candidate_id in ordered_primary_consuming_device_ids:
            primary_candidate_id = str(primary_candidate_id or '')
            primary_candidate = configured_device_context_by_id.get(primary_candidate_id)
            if primary_candidate is None:
                continue
            explicit_activation = _runtime_policy_bool(
                _device_policy_value(
                    cfg, primary_candidate_id, 'force_on', False, facts=None
                )
            )
            # Preserve the established EV lifecycle trigger semantics.  The
            # common grid-feedback controller may request positive consumption
            # even while the quarter-derived RPNZ direction is non-consuming.
            # Treating that feedback request as a lifecycle activation request
            # would reset low-PV persistence and prevent HARD_OFF.
            primary_requested_active_by_id[primary_candidate_id] = bool(
                explicit_activation or float(nz.rpnz_w) > 0.0
            )
            candidate_feedback_producer = _active_producer_for_feedback(
                primary_candidate, producer_contexts
            )
            candidate_low_energy_active, candidate_low_energy_threshold_kw = (
                _device_low_energy_condition(cfg, primary_candidate_id, pv_power_kw)
            )
            candidate_feedback_protection = compute_primary_producer_feedback_protection(
                primary_candidate,
                candidate_feedback_producer,
                low_energy_active=candidate_low_energy_active,
                explicit_activation_request=explicit_activation,
            )
            preliminary_feedback_protection_by_id[primary_candidate_id] = bool(
                candidate_feedback_protection
            )
            preliminary_feedback_producer_by_id[primary_candidate_id] = candidate_feedback_producer
            preliminary_low_energy_by_id[primary_candidate_id] = bool(candidate_low_energy_active)
            preliminary_low_energy_threshold_by_id[primary_candidate_id] = float(
                candidate_low_energy_threshold_kw
            )
        preliminary_feedback_protection_active = False
        preliminary_feedback_producer = None
        preliminary_low_energy_active = False
        preliminary_low_energy_threshold_kw = 0.0
        preliminary_feedback_protection_device_id = ''
        for primary_candidate_id in ordered_primary_consuming_device_ids:
            primary_candidate_id = str(primary_candidate_id or '')
            if bool(preliminary_feedback_protection_by_id.get(primary_candidate_id, False)):
                preliminary_feedback_protection_active = True
                preliminary_feedback_protection_device_id = primary_candidate_id
                preliminary_feedback_producer = preliminary_feedback_producer_by_id.get(
                    primary_candidate_id
                )
                preliminary_low_energy_active = bool(
                    preliminary_low_energy_by_id.get(primary_candidate_id, False)
                )
                preliminary_low_energy_threshold_kw = float(
                    preliminary_low_energy_threshold_by_id.get(primary_candidate_id, 0.0) or 0.0
                )
                break
        combo_fallback_active = False
        combo_fallback_warning = ''
        _note_net_zero_duration_ms('policy_engine_net_zero_role_normalization_ms', role_normalization_started_ts)

        previous_device_state_started_ts = _net_zero_profile_started_ts()
        normalized_previous_device_states = _normalize_previous_device_states(previous_device_states)
        hard_off_lifecycle_device_ids = _hard_off_lifecycle_device_ids(cfg, facts=policy_runtime_facts)
        for lifecycle_device_id in hard_off_lifecycle_device_ids:
            normalized_previous_device_states.setdefault(
                lifecycle_device_id,
                _default_previous_device_state(lifecycle_device_id),
            )
        _note_net_zero_duration_ms('policy_engine_net_zero_previous_device_state_normalization_ms', previous_device_state_started_ts)
        _note_net_zero_duration_ms('policy_engine_net_zero_state_parse_ms', state_parse_started_ts)

        surplus_targets_started_ts = _net_zero_profile_started_ts()
        active_device_ids = set()
        for item in (active_surplus_device_ids or ()):
            active_device_ids.add(str(item))
        if active_surplus_device_ids is None:
            for device_id, state in (relay_device_states or {}).items():
                if bool((state or {}).get('active', False)):
                    active_device_ids.add(str(device_id))

        lifecycle_transitions_by_id, lifecycle_next_states = _lifecycle_transition_maps(
            cfg,
            profiles,
            nz,
            previous_device_states=normalized_previous_device_states,
            active_device_ids=tuple(active_device_ids),
            primary_consuming_device_ids=ordered_primary_consuming_device_ids,
            pv_power_kw=pv_power_kw,
            current_power_by_id=current_power_by_id,
            primary_requested_active_by_id=primary_requested_active_by_id,
            feedback_protection_by_id=preliminary_feedback_protection_by_id,
            facts=policy_runtime_facts,
        )
        primary_resolution = _resolve_primary_consuming_authority(
            profiles,
            cfg,
            ordered_primary_consuming_device_ids,
            configured_device_context_by_id,
            lifecycle_transitions_by_id,
            producer_contexts,
            m,
            nz,
            pv_power_kw=pv_power_kw,
            haeo_nz_plan=haeo_nz_plan,
            facts=policy_runtime_facts,
        )
        effective_primary_consuming_device_id = str(
            primary_resolution.get('effective_device_id', '') or ''
        )
        primary_consuming_device_target_w = float(
            primary_resolution.get('effective_target_w', 0.0) or 0.0
        )
        primary_device = configured_device_context_by_id.get(
            effective_primary_consuming_device_id
        )
        feedback_protection_active = bool(
            preliminary_feedback_protection_active
            or primary_resolution.get('feedback_protection_active', False)
        )
        feedback_protection_low_energy_active = bool(
            preliminary_low_energy_active
            if preliminary_feedback_protection_active
            else primary_resolution.get('feedback_protection_low_energy_active', False)
        )
        feedback_protection_low_energy_threshold_kw = float(
            preliminary_low_energy_threshold_kw
            if preliminary_feedback_protection_active
            else primary_resolution.get('feedback_protection_low_energy_threshold_kw', 0.0) or 0.0
        )
        feedback_producer_device = (
            preliminary_feedback_producer
            if preliminary_feedback_protection_active
            else primary_resolution.get('feedback_producer_device')
        )
        feedback_protection_primary_candidate_id = (
            preliminary_feedback_protection_device_id
            if preliminary_feedback_protection_active
            else effective_primary_consuming_device_id
        )
        feedback_protection_producer_active = bool(feedback_producer_device is not None)
        primary_surplus_combo_valid = bool(
            (not ordered_primary_consuming_device_ids)
            or effective_primary_consuming_device_id
            or primary_resolution.get('effective_reason') in (
                'no_positive_consuming_request',
                'no_primary_consuming_devices_configured',
            )
        )
        if not ordered_primary_consuming_device_ids:
            primary_surplus_combo_reason = 'surplus_only_topology'
        elif primary_surplus_combo_valid:
            primary_surplus_combo_reason = 'capability_driven_roles'
        else:
            primary_surplus_combo_reason = str(
                primary_resolution.get('effective_reason', '') or ''
            )
        candidate_contexts = _generic_surplus_candidate_contexts(
            cfg,
            active_device_ids=tuple(active_device_ids),
            lifecycle_transitions_by_id=lifecycle_transitions_by_id,
            primary_consuming_device_id=effective_primary_consuming_device_id,
            runtime_device_states=relay_device_states,
            facts=policy_runtime_facts,
        )
        surplus_candidates = build_surplus_candidates(candidate_contexts)
        surplus_target_by_id = _surplus_target_by_device_id(surplus_candidates)
        force_on_active_device_ids_list = []
        for force_device_id in _ordered_device_ids(cfg, facts=policy_runtime_facts):
            force_device_id = str(force_device_id)
            if _runtime_policy_bool(
                _device_policy_value(cfg, force_device_id, 'force_on', False, facts=None)
            ):
                force_on_active_device_ids_list.append(force_device_id)
        force_on_active_device_ids = tuple(force_on_active_device_ids_list)
        force_on_hard_off_bypass_device_ids_list = []
        for force_device_id in force_on_active_device_ids:
            if bool(
                getattr(
                    lifecycle_transitions_by_id.get(str(force_device_id)),
                    'hard_off_active',
                    False,
                )
            ):
                force_on_hard_off_bypass_device_ids_list.append(force_device_id)
        force_on_hard_off_bypass_device_ids = tuple(
            force_on_hard_off_bypass_device_ids_list
        )

        normalized_relay_device_states = {}
        for device_id, state in (relay_device_states or {}).items():
            normalized_relay_device_states[str(device_id)] = dict(state or {})
        for relay in _relay_devices(cfg, facts=policy_runtime_facts):
            device_id = str(relay)
            state = normalized_relay_device_states.setdefault(device_id, {})
            state['surplus_allowed'] = _runtime_policy_bool(
                _device_policy_value(cfg, device_id, 'surplus_allowed', False, facts=None)
            )
            state['force_on'] = _runtime_policy_bool(
                _device_policy_value(cfg, device_id, 'force_on', False, facts=None)
            )
            state['active'] = device_id in active_device_ids
        relay_runtime_candidates = _relay_runtime_candidates(
            cfg,
            normalized_relay_device_states,
            facts=policy_runtime_facts,
        )
        _note_net_zero_duration_ms('policy_engine_net_zero_surplus_targets_ms', surplus_targets_started_ts)

        surplus_active = net_zero_surplus_policy_active(profiles, eff_fc, haeo_nz_plan_active=haeo_nz_plan_active)

        surplus_freeze_s = _global_config_value(cfg, 'surplus_freeze_s', 0)
        effective_freeze_until_ts, current_force_on_device_ids = _apply_force_rising_edge_freeze_for_devices(
            now_ts=now_ts,
            freeze_until_ts=freeze_until_ts,
            freeze_s=surplus_freeze_s,
            relay_candidates=candidate_contexts,
            previous_force_on_device_ids=previous_force_on_device_ids or (),
        )

        surplus_device_inp = SurplusDispatchInput(
            policy_active=surplus_active,
            freeze_until_ts=effective_freeze_until_ts,
            rpc_kw=nz.required_power_consumption_kw,
            rpnz_w=nz.rpnz_w,
            targets=surplus_candidates,
        )
        surplus_device_decision = compute_surplus_device_dispatch(surplus_device_inp, now_ts, surplus_freeze_s)
        surplus_device_next = next_device_target(surplus_candidates)
        surplus_device_release = release_device_target(surplus_candidates)

        relay_active_now = False
        for relay in relay_runtime_candidates:
            if bool(relay.get('active', False)):
                relay_active_now = True
                break
        any_surplus_target_active = False
        for target in surplus_candidates:
            if bool(target.active):
                any_surplus_target_active = True
                break
        combo_change_requires_clear = (
            haeo_nz_plan_active
            and bool(getattr(haeo_nz_plan, 'changed', False))
            and any_surplus_target_active
        )
        combo_change_freeze_until_ts = (
            float(now_ts) + float(surplus_freeze_s)
            if combo_change_requires_clear
            else None
        )
        surplus_state_clear_reason = 'HAEO_COMBO_CHANGED' if combo_change_requires_clear else ''
        surplus_dispatch_action, surplus_dispatch_device_id = _dispatch_action_and_device_id(
            surplus_device_decision,
            combo_change_requires_clear,
        )
        surplus_next_device_id = surplus_device_next.device_id if surplus_device_next else ''
        surplus_release_device_id = surplus_device_release.device_id if surplus_device_release else ''

        primary_envelope_w = (
            primary_resolution.get('requested_w_by_id', {}).get(
                effective_primary_consuming_device_id
            )
            if effective_primary_consuming_device_id else None
        )
        primary_ev_device_id = (
            effective_primary_consuming_device_id
            if _is_ev_device_id(
                cfg, effective_primary_consuming_device_id, facts=policy_runtime_facts
            )
            else ''
        )
        primary_ev = _ev_context(
            cfg, primary_ev_device_id, facts=policy_runtime_facts
        )
        primary_ev_feedback_protection_active = bool(feedback_protection_active)
        primary_ev_policy_mode = (
            'burn' if primary_ev_device_id and primary_consuming_device_target_w > 0.0 else 'skip'
        )
        primary_ev_target_w = (
            float(primary_consuming_device_target_w) if primary_ev_device_id else 0.0
        )
        if (
            primary_ev_device_id
            and profiles.goal == GoalProfile.NET_ZERO
            and combo_change_requires_clear
            and not bool(getattr(primary_ev, 'force_on', False))
        ):
            primary_ev_policy_mode = 'restore_min'
            primary_ev_target_w = 0.0
            primary_consuming_device_target_w = 0.0
        primary_ev_burn_active_for_battery = bool(
            primary_ev_device_id and primary_ev_target_w > 0.0
        )
        residual_rpnz_w = float(nz.rpnz_w) - float(
            max(primary_consuming_device_target_w, 0.0)
        )
        _note_net_zero_duration_ms('policy_engine_net_zero_ev_policy_ms', _net_zero_profile_started_ts())

        battery_policy_started_ts = _net_zero_profile_started_ts()
        battery_policies_by_id = {}
        battery_floor_by_id = {}
        battery_floor_reason_by_id = {}
        for battery_device_id in _device_ids_by_kind(cfg, 'BATTERY', facts=policy_runtime_facts):
            battery_device_id = str(battery_device_id)
            target_w, write_enabled, floor_w, floor_reason = _battery_target_and_authority(
                profiles,
                cfg,
                battery_device_id,
                primary_device,
                m,
                normalized_haeo,
                nz,
                primary_active=primary_ev_burn_active_for_battery,
                battery_surplus_release_pending=(
                    str(surplus_device_decision.release or '') == battery_device_id
                ),
                primary_target_w=primary_consuming_device_target_w,
                separate_primary_regulation=bool(effective_primary_consuming_device_id) and (
                    str(effective_primary_consuming_device_id) != battery_device_id
                ),
                is_effective_primary=(
                    str(effective_primary_consuming_device_id) == battery_device_id
                ),
                no_effective_primary_regulation=(
                    not bool(effective_primary_consuming_device_id)
                ),
                haeo_nz_plan=haeo_nz_plan,
                battery_surplus_target=surplus_target_by_id.get(battery_device_id),
                facts=policy_runtime_facts,
            )
            battery_policies_by_id[battery_device_id] = {
                'target_w': int(round(float(target_w))),
                'enabled': bool(write_enabled),
                'mode': 'power',
                'reason': 'battery_policy',
            }
            battery_floor_by_id[battery_device_id] = floor_w
            battery_floor_reason_by_id[battery_device_id] = floor_reason

        if (
            effective_primary_consuming_device_id
            and _device_kind(
                cfg, effective_primary_consuming_device_id, facts=policy_runtime_facts
            ) == 'BATTERY'
        ):
            primary_battery_policy = battery_policies_by_id.get(
                str(effective_primary_consuming_device_id), {}
            )
            primary_consuming_device_target_w = max(
                float(primary_battery_policy.get('target_w', 0) or 0), 0.0
            )

        primary_is_same_producing_regulator = False
        for producer in producer_contexts:
            if str(producer.device_id) == str(effective_primary_consuming_device_id or ''):
                primary_is_same_producing_regulator = True
                break
        residual_rpnz_w = float(nz.rpnz_w) - (
            float(max(primary_consuming_device_target_w, 0.0))
            if not primary_is_same_producing_regulator
            else 0.0
        )
        producer_feedback = _producer_feedback_request(
            cfg,
            producer_contexts,
            nz.rpnz_w,
            m.grid_power_w,
        )
        producer_dispatch = {
            'requested_w': float(producer_feedback['requested_w']),
            'allocated_w_by_id': {},
            'ceiling_w_by_id': {},
            'unserved_w': float(producer_feedback['requested_w']),
            'skipped_below_min_device_ids': (),
        }
        producer_authority_by_id = {}
        if (
            profiles.goal == GoalProfile.NET_ZERO
            and profiles.control in (ControlProfile.AUTOMATIC, ControlProfile.HORIZON_BY_HAEO)
            and float(producer_feedback['requested_w']) > 0.0
        ):
            producer_dispatch = _allocate_producer_dispatch(
                profiles, cfg, producer_contexts, producer_feedback['requested_w']
            )
            for producer in producer_contexts:
                producer_id = str(producer.device_id)
                allocated_w = float(
                    producer_dispatch['allocated_w_by_id'].get(producer_id, 0.0) or 0.0
                )
                if allocated_w <= 0.0:
                    continue
                transient_target_w = _producer_transient_target_w(cfg, producer, allocated_w)
                producer_authority_by_id[producer_id] = {
                    'target_w': float(transient_target_w),
                    'allocated_magnitude_w': allocated_w,
                    'hard_ceiling_w': float(
                        producer_dispatch['ceiling_w_by_id'].get(producer_id, 0.0) or 0.0
                    ),
                }
                # Producer authority is singular and suppresses contradictory
                # positive surplus/baseline authority even through sign crossing.
                if producer_id in battery_policies_by_id:
                    battery_policies_by_id[producer_id] = {
                        'target_w': int(round(float(transient_target_w))),
                        'enabled': True,
                        'mode': 'power',
                        'reason': 'producer_authority',
                    }

        _note_net_zero_duration_ms('policy_engine_net_zero_battery_policy_ms', battery_policy_started_ts)
        summary_battery_device_id = ''
        if _device_kind(cfg, effective_primary_consuming_device_id, facts=policy_runtime_facts) == 'BATTERY':
            summary_battery_device_id = str(effective_primary_consuming_device_id)
        elif producer_contexts:
            summary_battery_device_id = str(producer_contexts[0].device_id)
        else:
            battery_ids = _device_ids_by_kind(cfg, 'BATTERY', facts=policy_runtime_facts)
            # A single battery is unambiguous. With multiple batteries there is
            # deliberately no implicit first-device fallback for scalar summary
            # diagnostics; canonical DevicePolicy output remains per-device.
            if len(battery_ids) == 1:
                for sole_battery_id in battery_ids:
                    summary_battery_device_id = str(sole_battery_id)
        summary_battery_policy = battery_policies_by_id.get(summary_battery_device_id, {})
        battery_target_w = int(round(float(summary_battery_policy.get('target_w', 0) or 0)))
        battery_write_enabled = bool(summary_battery_policy.get('enabled', False))
        battery_min_floor_w = battery_floor_by_id.get(summary_battery_device_id)
        battery_min_floor_reason = battery_floor_reason_by_id.get(summary_battery_device_id, 'not_applicable')
        discharge_limit_w, discharge_limit_sign_mode, configured_discharge_limit_w = (
            _normalized_discharge_limit_w(cfg, summary_battery_device_id)
            if summary_battery_device_id else (0, 'positive_magnitude', 0.0)
        )

        relay_policy_started_ts = _net_zero_profile_started_ts()
        relay_policy_states = []
        for relay in relay_runtime_candidates:
            relay_policy_states.append(
                {
                    'device_id': str(relay['device_id']),
                    'command': relay_strategy_command(
                        profiles,
                        bool(relay['enabled']),
                        bool(relay['force_on']),
                        bool(relay['active']),
                    ),
                }
            )
        _note_net_zero_duration_ms('policy_engine_net_zero_relay_policy_ms', relay_policy_started_ts)

        ev_policies_by_id = {}
        for ev_device_id in _ev_devices(cfg, facts=policy_runtime_facts):
            ev_device_id = str(ev_device_id)
            if ev_device_id == str(effective_primary_consuming_device_id or ''):
                primary_ev_reason = (
                    'ev_force_on'
                    if bool(getattr(primary_ev, 'force_on', False)) and float(primary_ev_target_w) > 0.0
                    else 'ev_lifecycle_hard_off'
                    if primary_ev_policy_mode == 'hard_off'
                    else 'primary_producer_feedback_protection'
                    if primary_ev_feedback_protection_active
                    else 'ev_primary_policy'
                )
                ev_policies_by_id[ev_device_id] = {
                    'target_w': primary_ev_target_w,
                    'enabled': float(primary_ev_target_w) > 0.0,
                    'mode': primary_ev_policy_mode,
                    'reason': primary_ev_reason,
                }
                continue
            ev_context = _ev_context(cfg, ev_device_id, facts=policy_runtime_facts)
            ev_policies_by_id[ev_device_id] = _ev_surplus_policy_for_device(
                profiles,
                cfg,
                ev_device_id,
                ev_context,
                normalized_haeo,
                surplus_target=surplus_target_by_id.get(ev_device_id),
                lifecycle_transition=lifecycle_transitions_by_id.get(ev_device_id),
                dispatch_decision=surplus_device_decision,
                combo_change_requires_clear=combo_change_requires_clear,
                rpnz_w=nz.rpnz_w,
                haeo_nz_plan=haeo_nz_plan,
                facts=policy_runtime_facts,
            )

        device_policies = _build_device_policies(
            cfg,
            battery_policies_by_id=battery_policies_by_id,
            ev_policies_by_id=ev_policies_by_id,
            relay_policies=tuple(relay_policy_states),
            producer_authority_by_id=producer_authority_by_id,
            facts=policy_runtime_facts,
        )
        device_policies, capability_blocked_devices = _enforce_device_policy_capabilities(
            cfg,
            device_policies,
            facts=policy_runtime_facts,
        )
        battery_policy = None
        for policy in device_policies:
            if str(policy.device_id) == str(summary_battery_device_id):
                battery_policy = policy
                break
        if battery_policy is not None:
            battery_target_w = int(battery_policy.target_w)
            battery_write_enabled = bool(battery_policy.enabled)
        updated_previous_device_states = _normalize_previous_device_states(lifecycle_next_states)
        policy_by_device_id = {}
        for policy in device_policies:
            policy_by_device_id[str(policy.device_id)] = policy
        for lifecycle_device_id in hard_off_lifecycle_device_ids:
            lifecycle_device_id = str(lifecycle_device_id)
            state = updated_previous_device_states.get(
                lifecycle_device_id, _default_previous_device_state(lifecycle_device_id)
            )
            policy = policy_by_device_id.get(lifecycle_device_id)
            if policy is not None:
                state['mode'] = str(policy.mode or '')
            updated_previous_device_states[lifecycle_device_id] = _normalize_previous_device_state_entry(
                lifecycle_device_id, state
            )
        device_lifecycle_states = {}
        for device_id in hard_off_lifecycle_device_ids:
            if device_id in updated_previous_device_states:
                device_lifecycle_states[device_id] = updated_previous_device_states[device_id]


        battery_policy_device_ids_payload = []
        for device_id in battery_policies_by_id.keys():
            battery_policy_device_ids_payload.append(str(device_id))
        producing_regulator_device_ids_payload = []
        for producer in producer_contexts:
            producing_regulator_device_ids_payload.append(str(producer.device_id))

        surplus_candidate_device_ids = []
        surplus_active_device_ids_payload = []
        for target in surplus_candidates:
            surplus_candidate_device_ids.append(str(target.device_id))
            if bool(target.active):
                surplus_active_device_ids_payload.append(str(target.device_id))
        surplus_candidate_stack = ' > '.join(surplus_candidate_device_ids) or 'NONE'

        result = NetZeroOutputs(
        battery_target_w=battery_target_w,
        battery_write_enabled=battery_write_enabled,
        surplus_policy_active=surplus_active,
        surplus_next_threshold_kw=round(float(surplus_device_next.threshold_w) / 1000.0, 3) if surplus_device_next else 0,
        surplus_explanation=surplus_device_decision.explanation,
        effective_forecast=eff_fc,
        dominant_limitation=dominant_limitation(profiles, conf_fc, eff_fc),
        explanation=explain(profiles, conf_fc, eff_fc, haeo_nz_plan_active=haeo_nz_plan_active),
        device_policies=device_policies,
        attrs={
            'configured_forecast': conf_fc,
            'surplus_candidates': candidate_payload(surplus_candidates),
            'surplus_candidate_device_ids': tuple(surplus_candidate_device_ids),
            'surplus_candidate_stack': surplus_candidate_stack,
            'surplus_active_device_ids': tuple(surplus_active_device_ids_payload),
            'surplus_next_device_id': surplus_next_device_id,
            'surplus_release_device_id': surplus_release_device_id,
            'surplus_dispatch_action': surplus_dispatch_action,
            'surplus_dispatch_device_id': surplus_dispatch_device_id,
            'surplus_dispatch_contract': 'device_id_primary',
            'relay_device_ids': _relay_device_ids_payload(cfg, facts=policy_runtime_facts),
            'ev_device_ids': _ev_device_ids_payload(cfg, facts=policy_runtime_facts),
            'battery_summary_device_id': summary_battery_device_id,
            'battery_policy_device_ids': tuple(battery_policy_device_ids_payload),
            'device_policies': _device_policy_payloads(device_policies),
            'capability_blocked_devices': capability_blocked_devices,
            'surplus_freeze_until_ts': _canonical_surplus_freeze_until_ts_for_output(
                surplus_dispatch_action,
                combo_change_freeze_until_ts,
                surplus_device_decision.freeze_until_ts,
                effective_freeze_until_ts,
            ),
            'surplus_state_clear_reason': surplus_state_clear_reason,
            'surplus_rpc_kw': nz.required_power_consumption_kw,
            'surplus_rpnz_w': nz.rpnz_w,
            'battery_write_enabled': battery_write_enabled,
            'configured_primary_consuming_device_ids': tuple(configured_primary_consuming_device_ids),
            'ordered_primary_consuming_device_ids': tuple(ordered_primary_consuming_device_ids),
            'effective_primary_consuming_device_id': effective_primary_consuming_device_id,
            'primary_consuming_device_id': effective_primary_consuming_device_id,
            'effective_primary_consuming_reason': str(primary_resolution.get('effective_reason', '') or ''),
            'primary_consuming_requested_w_by_id': dict(primary_resolution.get('requested_w_by_id', {}) or {}),
            'primary_consuming_skipped_by_id': dict(primary_resolution.get('skipped_by_id', {}) or {}),
            'unserved_primary_consuming_w': float(primary_resolution.get('unserved_consuming_w', 0.0) or 0.0),
            'producing_regulator_device_ids': tuple(producing_regulator_device_ids_payload),
            'producer_authority_device_ids': tuple(producer_authority_by_id.keys()),
            'producer_request_source': 'grid_feedback',
            'producer_feedback_target_grid_w': float(producer_feedback['target_grid_w']),
            'producer_feedback_grid_actual_w': float(producer_feedback['grid_actual_w']),
            'producer_feedback_error_w': float(producer_feedback['error_w']),
            'producer_feedback_current_control_target_w': float(producer_feedback['current_control_target_w']),
            'producer_feedback_desired_control_target_w': float(producer_feedback['desired_control_target_w']),
            'producer_requested_w': float(producer_dispatch['requested_w']),
            'producer_allocated_w_by_id': dict(producer_dispatch['allocated_w_by_id']),
            'producer_effective_hard_ceiling_w_by_id': dict(producer_dispatch['ceiling_w_by_id']),
            'unserved_production_w': float(producer_dispatch['unserved_w']),
            'producer_skipped_below_min_device_ids': tuple(producer_dispatch['skipped_below_min_device_ids']),
            'primary_consuming_device_target_w': int(round(float(primary_consuming_device_target_w))),
            'residual_rpnz_w': float(residual_rpnz_w),
            'previous_device_states': updated_previous_device_states,
            'device_lifecycle_states': device_lifecycle_states,
            'hard_off_lifecycle_devices': hard_off_lifecycle_device_ids,
            'force_on_active_device_ids': force_on_active_device_ids,
            'force_on_hard_off_bypass_device_ids': force_on_hard_off_bypass_device_ids,
            'pv_power_kw': pv_power_kw,
            'activation_block_reason': (
                'primary_producer_feedback_protection' if feedback_protection_active else ''
            ),
            'feedback_protection_active': bool(feedback_protection_active),
            'feedback_protection_primary_consuming_device_id': (
                str(feedback_protection_primary_candidate_id or '') if feedback_protection_active else ''
            ),
            'feedback_protection_producing_device_id': (
                str(getattr(feedback_producer_device, 'device_id', '') or '') if feedback_protection_active else ''
            ),
            'feedback_protection_low_energy_active': bool(feedback_protection_low_energy_active),
            'feedback_protection_low_energy_threshold_kw': float(
                feedback_protection_low_energy_threshold_kw
            ),
            'feedback_protection_producer_active': bool(
                feedback_protection_producer_active
            ),
            'feedback_protection_producer_control_target_w': float(
                feedback_producer_device.current_control_target_w
                if feedback_producer_device is not None
                else 0.0
            ),
            'primary_power_envelope_w': primary_envelope_w,
            'primary_surplus_combo_source': primary_surplus_combo_source,
            'primary_surplus_combo_valid': bool(primary_surplus_combo_valid),
            'primary_surplus_combo_reason': primary_surplus_combo_reason,
            'primary_surplus_combo_fallback_active': bool(combo_fallback_active),
            'primary_surplus_combo_warning': combo_fallback_warning,
            'battery_min_floor_w': battery_min_floor_w,
            'battery_min_floor_reason': battery_min_floor_reason,
            'discharge_limit_w': int(discharge_limit_w),
            'discharge_limit_sign_mode': discharge_limit_sign_mode,
            'configured_discharge_limit_w': float(configured_discharge_limit_w),
            'haeo_nz_plan_active': bool(haeo_nz_plan_active),
            'haeo_nz_quarter_key': getattr(haeo_nz_plan, 'quarter_key', ''),
            'haeo_nz_combo_changed': bool(getattr(haeo_nz_plan, 'changed', False)),
            'haeo_nz_primary_consuming_device_id': _haeo_plan_primary_consuming_device_id(haeo_nz_plan),
            'haeo_nz_preferred_surplus_device_id': _haeo_plan_preferred_surplus_device_id(haeo_nz_plan),
            'haeo_nz_device_limits_w': getattr(haeo_nz_plan, 'device_limits_w', {}) or {},
            'haeo_nz_combo_reason': getattr(haeo_nz_plan, 'reason', ''),
            'prev_force_on_device_ids': current_force_on_device_ids,
        },
    )
        return result
    finally:
        if NET_ZERO_DETAILED_METRICS_ENABLED:
            _LAST_NET_ZERO_COMPUTE_METRICS.update(_ACTIVE_NET_ZERO_COMPUTE_METRICS or {})
        else:
            _LAST_NET_ZERO_COMPUTE_METRICS.clear()
        _ACTIVE_NET_ZERO_COMPUTE_METRICS = None
