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
from ems_core.net_zero.battery_controller import candidate_sp_net_zero
from ems_core.net_zero.load_projection import ev_strategy_target_w, relay_strategy_command
from ems_core.net_zero.surplus_allocator import (
    RPNZ_PRACTICAL_ZERO_W,
    active_device_stack,
    compute_surplus_device_dispatch,
    next_device_target,
    release_device_target,
)
from ems_core.net_zero.surplus_device_targets import build_surplus_device_targets, decision_name_for_device_id, device_targets_payload

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
    'policy_engine_net_zero_cfg_legacy_bridge_count_calls': 0,
    'policy_engine_net_zero_cfg_legacy_bridge_counts_by_kind_calls': 0,
    'policy_engine_net_zero_state_parse_ms': 0,
    'policy_engine_net_zero_facts_provider_ms': 0,
    'policy_engine_net_zero_facts_context_build_ms': 0,
    'policy_engine_net_zero_facts_copy_ms': 0,
    'policy_engine_net_zero_selected_ev_context_ms': 0,
    'policy_engine_net_zero_role_normalization_ms': 0,
    'policy_engine_net_zero_previous_ev_state_normalization_ms': 0,
    'policy_engine_net_zero_forecast_haeo_normalization_ms': 0,
    'policy_engine_net_zero_facts_device_count': 0,
    'policy_engine_net_zero_facts_capability_fields': 0,
    'policy_engine_net_zero_facts_policy_fields': 0,
    'policy_engine_net_zero_facts_adapter_fields': 0,
    'policy_engine_net_zero_fact_dict_copies': 0,
    'policy_engine_net_zero_facts_fallback_used': 0,
    'policy_engine_net_zero_facts_dynamic_bindings': 0,
    'policy_engine_net_zero_facts_dynamic_binding_groups': 0,
    'policy_engine_net_zero_selected_ev_contexts': 0,
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
            'policy_engine_net_zero_cfg_legacy_bridge_count_calls': 0,
            'policy_engine_net_zero_cfg_legacy_bridge_counts_by_kind_calls': 0,
            'policy_engine_net_zero_state_parse_ms': 0,
            'policy_engine_net_zero_facts_provider_ms': 0,
            'policy_engine_net_zero_facts_context_build_ms': 0,
            'policy_engine_net_zero_facts_copy_ms': 0,
            'policy_engine_net_zero_selected_ev_context_ms': 0,
            'policy_engine_net_zero_role_normalization_ms': 0,
            'policy_engine_net_zero_previous_ev_state_normalization_ms': 0,
            'policy_engine_net_zero_forecast_haeo_normalization_ms': 0,
            'policy_engine_net_zero_facts_device_count': 0,
            'policy_engine_net_zero_facts_capability_fields': 0,
            'policy_engine_net_zero_facts_policy_fields': 0,
            'policy_engine_net_zero_facts_adapter_fields': 0,
            'policy_engine_net_zero_fact_dict_copies': 0,
            'policy_engine_net_zero_facts_fallback_used': 0,
            'policy_engine_net_zero_facts_dynamic_bindings': 0,
            'policy_engine_net_zero_facts_dynamic_binding_groups': 0,
            'policy_engine_net_zero_selected_ev_contexts': 0,
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
        _note_net_zero_metric('policy_engine_net_zero_selected_ev_contexts', metrics.get('policy_runtime_selected_ev_contexts', 0) or 0)
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

def _cfg_scalar_value(cfg, field_name, default=None):
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return getattr(cfg, field_name, default)
    started_ts = time.time()
    _note_net_zero_metric('policy_engine_net_zero_cfg_scalar_reads')
    value = getattr(cfg, field_name, default)
    _note_net_zero_duration_ms('policy_engine_net_zero_cfg_scalar_read_ms', started_ts)
    return value


def _cfg_accessor_call(count_key, fn, *args):
    if not NET_ZERO_DETAILED_METRICS_ENABLED:
        return fn(*args)
    started_ts = time.time()
    _note_net_zero_metric(count_key)
    try:
        return fn(*args)
    finally:
        _note_net_zero_duration_ms('policy_engine_net_zero_cfg_device_accessor_ms', started_ts)



def _selected_ev_context_from_fact_maps(facts, device_id):
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
        selected_ev_context_by_id = direct_maps.get('selected_ev_context_by_id')
        if not isinstance(selected_ev_context_by_id, dict):
            selected_ev_context_by_id = {}
            direct_maps['selected_ev_context_by_id'] = selected_ev_context_by_id
        if not selected_ev_context_by_id:
            for device_id in tuple((direct_maps.get('device_ids_by_kind', {}) or {}).get('EV_CHARGER', ()) or ()):
                selected_ev_context_by_id[str(device_id)] = _selected_ev_context_from_fact_maps(direct_maps, device_id)
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

        selected_ev_context_started_ts = _net_zero_profile_started_ts()
        selected_ev_context_by_id = facts.get('selected_ev_context_by_id')
        if not isinstance(selected_ev_context_by_id, dict):
            selected_ev_context_by_id = {}
            for device_id in tuple((facts.get('device_ids_by_kind', {}) or {}).get('EV_CHARGER', ()) or ()):
                selected_ev_context_by_id[str(device_id)] = _selected_ev_context_from_fact_maps(facts, device_id)
            facts['selected_ev_context_by_id'] = selected_ev_context_by_id
        _note_net_zero_duration_ms('policy_engine_net_zero_selected_ev_context_ms', selected_ev_context_started_ts)
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
        'max_produce_w',
        'step_w',
        'can_absorb_w',
        'can_produce_w',
        'supports_primary_regulation',
        'supports_residual_regulation',
        'uses_hard_off_lifecycle',
    )
    for device_id in ordered_device_ids:
        kind = str(device_kind_by_id.get(device_id, '') or '')
        capabilities = {}
        for field in capability_fields:
            default = False if field in (
                'can_absorb_w',
                'can_produce_w',
                'supports_primary_regulation',
                'supports_residual_regulation',
                'uses_hard_off_lifecycle',
            ) else 0
            capabilities[field] = _device_capability(cfg, device_id, field, default)
        device_capabilities_by_id[device_id] = capabilities

        policy = {'priority': _device_policy_value(cfg, device_id, 'priority', 0)}
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
        'selected_ev_context_by_id': {},
    }
    selected_ev_context_by_id = {}
    for device_id in ids_by_kind.get('EV_CHARGER', ()):
        selected_ev_context_by_id[str(device_id)] = _selected_ev_context_from_fact_maps(facts, device_id)
    facts['selected_ev_context_by_id'] = selected_ev_context_by_id
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


def _normalized_adjustable_surplus_load(cfg, facts=None):
    raw_value = _cfg_scalar_value(cfg, 'adjustable_surplus_load', '')
    raw = str(raw_value or '').strip().lower()
    if raw in ('ev_charger', 'ev', 'charger_current'):
        selected_ev_device_id = _default_ev_device_id(cfg, facts=facts)
        return selected_ev_device_id or 'HOME_BATTERY'
    if raw in ('home_battery', 'battery', 'actuator_battery_setpoint_w'):
        return 'HOME_BATTERY'
    resolved = _resolved_device_id(cfg, raw_value, '', facts=facts)
    if resolved:
        return resolved
    return 'HOME_BATTERY'


def _uses_ev_adjustable_mode(cfg, facts=None):
    return _is_ev_device_id(cfg, _normalized_adjustable_surplus_load(cfg, facts=facts), facts=facts)


def _normalized_adjustable_primary_load(cfg, facts=None):
    raw_value = _cfg_scalar_value(cfg, 'adjustable_primary_load', '')
    raw = str(raw_value or '').strip().lower()
    if raw in ('ev_charger', 'ev', 'charger_current'):
        return _default_ev_device_id(cfg, facts=facts)
    if raw in ('home_battery', 'battery', 'actuator_battery_setpoint_w'):
        return 'HOME_BATTERY'
    resolved = _resolved_device_id(cfg, raw_value, '', facts=facts)
    if resolved:
        return resolved
    return ''


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


def _device_can_absorb(cfg, device_id, facts=None):
    return bool(_device_capability(cfg, device_id, 'can_absorb_w', False, facts=facts))


def _device_uses_hard_off_lifecycle(cfg, device_id, facts=None):
    return bool(_device_capability(cfg, device_id, 'uses_hard_off_lifecycle', False, facts=facts))


def _device_supports_primary_regulation(cfg, device_id, facts=None):
    return bool(_device_capability(cfg, device_id, 'supports_primary_regulation', False, facts=facts))


def _device_supports_residual_regulation(cfg, device_id, facts=None):
    return bool(_device_capability(cfg, device_id, 'supports_residual_regulation', False, facts=facts))


def _device_control_context(cfg, device_id, *, current_measured_power_w=0.0, facts=None):
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
        max_produce_w=float(_device_capability(cfg, device_id, 'max_produce_w', 0, facts=facts) or 0),
        step_w=float(_device_capability(cfg, device_id, 'step_w', 0, facts=facts) or 0),
        supports_primary_regulation=_device_supports_primary_regulation(cfg, device_id, facts=facts),
        supports_residual_regulation=_device_supports_residual_regulation(cfg, device_id, facts=facts),
        uses_hard_off_lifecycle=_device_uses_hard_off_lifecycle(cfg, device_id, facts=facts),
        priority=int(_device_policy_value(cfg, device_id, 'priority', 0, facts=facts) or 0),
        current_measured_power_w=float(current_measured_power_w or 0.0),
    )


def _derive_residual_regulator_device_id(primary_device, surplus_adjustable_device):
    if primary_device is not None and primary_device.supports_residual_regulation:
        return primary_device.device_id
    if surplus_adjustable_device is not None and surplus_adjustable_device.supports_residual_regulation:
        return surplus_adjustable_device.device_id
    return ''


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


def compute_primary_device_target_w(device_context, requested_w):
    if device_context is None or not device_context.supports_primary_regulation:
        return 0.0
    if not device_context.can_absorb_w:
        return 0.0
    return quantize_absorb_target_w(
        requested_w,
        device_context.min_absorb_w,
        device_context.max_absorb_w,
        device_context.step_w,
    )


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
    loop_risk,
    hard_off_low_pv_cycles,
    hard_off_release_cycles,
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
    low_cycles = 0 if requested_active else (previous_low_cycles + 1 if low_pv else 0)
    required_low_cycles = max(1, int(hard_off_low_pv_cycles or 1))
    required_release_cycles = max(1, int(hard_off_release_cycles or 1))
    recovery_condition = (
        pv_known
        and float(pv_power_w) >= float(low_pv_threshold_w)
        and float(rpc_w) >= float(release_rpc_threshold_w)
        and (not bool(loop_risk))
    )

    if previous_hard_off:
        release_cycles = previous_release_cycles + 1 if recovery_condition else 0
        release_allowed = release_cycles >= required_release_cycles
        return HardOffLifecycleTransition(
            low_pv_cycles=0 if release_allowed else low_cycles,
            hard_off_release_ready_cycles=release_cycles,
            hard_off_active=not release_allowed,
            activation_allowed=release_allowed,
            release_allowed=release_allowed,
            recovery_condition=recovery_condition,
            mode='released' if release_allowed else 'hard_off',
        )

    enter_hard_off = (not requested_active) and low_cycles >= required_low_cycles
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


def _default_ev_device_id(cfg, facts=None):
    ev_device_ids = _device_ids_by_kind(cfg, 'EV_CHARGER', facts=facts)
    if ev_device_ids:
        return str(ev_device_ids[0])
    if hasattr(cfg, 'device_ids_by_kind') or hasattr(cfg, 'devices_by_kind'):
        return ''
    return 'EV_CHARGER'


def _selected_ev_device_id_for_roles(cfg, adjustable_surplus_load, adjustable_primary_load='', facts=None):
    if _is_ev_device_id(cfg, adjustable_surplus_load, facts=facts):
        return str(adjustable_surplus_load)
    if _is_ev_device_id(cfg, adjustable_primary_load, facts=facts):
        return str(adjustable_primary_load)
    return _default_ev_device_id(cfg, facts=facts)


def _selected_ev_context(cfg, device_id, facts=None):
    if facts is not None:
        selected_ev_context_by_id = facts.get('selected_ev_context_by_id', {}) or {}
        selected_ev_context = selected_ev_context_by_id.get(str(device_id or ''))
        if selected_ev_context is not None:
            return selected_ev_context
        return _selected_ev_context_from_fact_maps(facts, '')

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


def _normalized_discharge_limit_w(cfg):
    strict_limits_max_w = _cfg_scalar_value(cfg, 'strict_limits_max_w', 0)
    configured = float(_cfg_scalar_value(cfg, 'max_battery_discharge_w', strict_limits_max_w))
    # Canonical config is negative (export/discharge domain), but keep
    # legacy positive magnitude values backward-compatible.
    if configured < 0.0:
        return int(round(abs(configured))), 'canonical_negative', configured
    if configured > 0.0:
        return int(round(configured)), 'legacy_positive', configured
    return 0, 'zero_discharge', configured


def _normal_limits_discharge_cap(raw, cfg):
    limit, _, _ = _normalized_discharge_limit_w(cfg)
    return max(int(raw), -limit)


def _battery_protect_charge_floor_w(cfg):
    return int(round(max(float(_cfg_scalar_value(cfg, 'battery_protect_charge_floor_w', 0.0)), 0.0)))


def _haeo_plan_primary_device_id(plan):
    return getattr(plan, 'primary_device_id', '') or getattr(plan, 'primary_load', '')


def _haeo_plan_adjustable_device_id(plan):
    return getattr(plan, 'adjustable_device_id', '') or getattr(plan, 'adjustable_surplus_load', '')


def _haeo_plan_device_limit_w(plan, device_id, legacy_limit_w=0):
    limits = getattr(plan, 'device_limits_w', {}) or {}
    if isinstance(limits, dict) and device_id in limits:
        return int(limits.get(device_id, 0) or 0)
    return int(legacy_limit_w or 0)


def _decision_text_from_dispatch(targets, surplus_decision, combo_change_requires_clear):
    if combo_change_requires_clear or surplus_decision.clear_all:
        return 'CLEAR_ALL'
    if surplus_decision.activate:
        decision_name = decision_name_for_device_id(targets, surplus_decision.activate) or surplus_decision.activate
        return 'ACTIVATE_' + decision_name
    if surplus_decision.release:
        decision_name = decision_name_for_device_id(targets, surplus_decision.release) or surplus_decision.release
        return 'RELEASE_' + decision_name
    return 'NOOP'


def _dispatch_action_and_target(decision_text):
    text = str(decision_text or 'NOOP')
    if text == 'CLEAR_ALL':
        return 'CLEAR_ALL', ''
    if text.startswith('ACTIVATE_'):
        return 'ACTIVATE', text[len('ACTIVATE_'):]
    if text.startswith('RELEASE_'):
        return 'RELEASE', text[len('RELEASE_'):]
    return 'NOOP', ''


def _device_id_for_decision_name(targets, decision_name):
    if not decision_name:
        return ''
    for target in targets:
        if target.decision_name == decision_name:
            return target.device_id
    return ''


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
            max_produce_w=int(round(abs(float(max_produce_w or 0)))),
            step_w=max(1, int(round(float(step_w or 0)))),
            priority=int(round(float(_device_policy_value(cfg, device_id, 'priority', 0, facts=facts) or 0))),
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


def _selected_ev_device_id(cfg, adjustable_surplus_load, facts=None):
    return _selected_ev_device_id_for_roles(cfg, adjustable_surplus_load, '', facts=facts)


def _has_ev_devices(cfg, facts=None):
    return bool(_ev_devices(cfg, facts=facts))


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


# Compatibility aliases for callers/tests that still use the EV-centric names.
_default_previous_ev_device_state = _default_previous_device_state
_normalize_previous_ev_device_state_entry = _normalize_previous_device_state_entry
_normalize_previous_ev_device_states = _normalize_previous_device_states


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
            if policy.device_id == 'HOME_BATTERY':
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


def _legacy_bridge_metrics(cfg):
    if not hasattr(cfg, 'legacy_device_bridge_count'):
        return 0, {}
    try:
        count = int(_cfg_accessor_call('policy_engine_net_zero_cfg_legacy_bridge_count_calls', cfg.legacy_device_bridge_count))
    except Exception:
        count = 0
    try:
        counts_by_kind = dict(
            _cfg_accessor_call(
                'policy_engine_net_zero_cfg_legacy_bridge_counts_by_kind_calls',
                cfg.legacy_device_bridge_counts_by_kind,
            )
        )
    except Exception:
        counts_by_kind = {}
    normalized = {}
    for kind, item_count in counts_by_kind.items():
        normalized[str(kind)] = int(item_count)
    return count, normalized


def _build_device_policies(
    cfg,
    *,
    battery_target_w,
    battery_write_enabled,
    ev_target_w,
    ev_policy_mode,
    adjustable_ev_device_id,
    relay_policies,
    facts=None,
):
    selected_ev_device_id = str(adjustable_ev_device_id or _selected_ev_device_id(cfg, '', facts=facts))
    relay_policy_by_id = {}
    for relay_policy in relay_policies:
        relay_policy_by_id[str(relay_policy['device_id'])] = relay_policy

    ordered_device_ids = []
    if facts is not None:
        for device_id in (facts.get('device_kind_by_id', {}) or {}):
            ordered_device_ids.append(str(device_id))
    if not ordered_device_ids:
        for kind in ('BATTERY', 'EV_CHARGER', 'RELAY'):
            for device_id in _device_ids_by_kind(cfg, kind, facts=facts):
                text = str(device_id)
                if text not in ordered_device_ids:
                    ordered_device_ids.append(text)

    policies = []
    for device_id in ordered_device_ids:
        kind = _device_kind(cfg, device_id, facts=facts)
        if kind == 'BATTERY':
            policies.append(
                DevicePolicy(
                    device_id=device_id,
                    target_w=int(round(float(battery_target_w))),
                    enabled=bool(battery_write_enabled),
                    mode='power',
                    reason='battery_policy',
                )
            )
            continue
        if kind == 'EV_CHARGER':
            if device_id == selected_ev_device_id:
                policies.append(
                    DevicePolicy(
                        device_id=device_id,
                        target_w=int(round(float(ev_target_w))),
                        enabled=float(ev_target_w) > 0.0,
                        mode=str(ev_policy_mode),
                        reason='ev_policy',
                    )
                )
            else:
                policies.append(
                    DevicePolicy(
                        device_id=device_id,
                        target_w=0,
                        enabled=False,
                        mode='restore_min',
                        reason='inactive_ev_policy',
                    )
                )
            continue
        if kind == 'RELAY':
            relay_policy = relay_policy_by_id.get(device_id, {'device_id': device_id, 'command': 0})
            relay_cfg = _capability_device_config_for_id(cfg, device_id, facts=facts)
            relay_target_w = int(round(float(relay_cfg.max_absorb_w))) if int(relay_policy['command']) > 0 else 0
            policies.append(
                DevicePolicy(
                    device_id=device_id,
                    target_w=relay_target_w,
                    enabled=int(relay_policy['command']) > 0,
                    mode='skip' if int(relay_policy['command']) < 0 else 'relay',
                    reason='relay_policy',
                )
            )
    return tuple(policies)


def _battery_target_and_authority(
    profiles,
    cfg,
    primary_device_context,
    m,
    haeo,
    nz,
    *,
    primary_active=False,
    primary_release_pending=False,
    primary_target_w=0.0,
    adjustable_surplus_active=False,
    separate_primary_regulation=False,
    haeo_nz_plan=None,
    surplus_adjustable_device_id='',
    facts=None,
):
    battery_min_floor_w = None
    battery_min_floor_reason = 'not_applicable'
    adjustable_surplus_active_next = bool(adjustable_surplus_active)

    if profiles.control == ControlProfile.MANUAL:
        return int(round(m.current_battery_setpoint_w)), False, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.control == ControlProfile.MANUAL_SAFE:
        current = int(round(m.current_battery_setpoint_w))
        battery_protect_floor = _battery_protect_charge_floor_w(cfg)

        if profiles.guard == GuardProfile.DEGRADED:
            return 0, True, battery_min_floor_w, battery_min_floor_reason, False

        if profiles.guard == GuardProfile.BATTERY_PROTECT:
            return max(current, battery_protect_floor), True, battery_min_floor_w, battery_min_floor_reason, False

        if profiles.guard == GuardProfile.STRICT_LIMITS:
            limit = int(cfg.strict_limits_max_w)
            return min(max(current, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason, False

        return current, False, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.goal == GoalProfile.NET_ZERO:
        effective_rpnz_w = nz.rpnz_w
        min_charge_floor_w = float(cfg.nz_battery_floor_default_w)
        primary_practical_zero_active = bool(separate_primary_regulation) and (
            bool(primary_active) or bool(adjustable_surplus_active)
        )
        primary_material_positive_rpnz = bool(separate_primary_regulation) and float(nz.rpnz_w) > (
            RPNZ_PRACTICAL_ZERO_W if primary_practical_zero_active else 0.0
        )
        adjustable_is_home_battery = str(surplus_adjustable_device_id or '') == 'HOME_BATTERY'
        configured_activation_w = float(cfg.adjustable_surplus_activation)

        if separate_primary_regulation:
            # EV primary path does not use legacy battery default floor.
            min_charge_floor_w = float(cfg.nz_battery_floor_ev_active_w)
            battery_min_floor_reason = 'ev_active_floor_override'

            battery_min_floor_w = float(min_charge_floor_w)
            effective_rpnz_w = float(nz.rpnz_w) - float(max(primary_target_w, 0.0))

            primary_max_w = float(getattr(primary_device_context, 'max_absorb_w', 0.0) or 0.0)
            if (
                primary_active
                and (not primary_material_positive_rpnz)
                and float(nz.rpnz_w) >= 0.0
                and float(nz.required_power_consumption_kw) * 1000.0 <= primary_max_w
            ):
                raw = int(round(min_charge_floor_w))
                if profiles.guard == GuardProfile.DEGRADED:
                    return 0, True, battery_min_floor_w, battery_min_floor_reason, False
                if profiles.guard == GuardProfile.BATTERY_PROTECT:
                    return max(raw, 0), True, battery_min_floor_w, battery_min_floor_reason, False
                if profiles.guard == GuardProfile.STRICT_LIMITS:
                    limit = int(cfg.strict_limits_max_w)
                    return min(max(raw, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason, False
                if profiles.guard == GuardProfile.NORMAL_LIMITS:
                    raw = _normal_limits_discharge_cap(raw, cfg)
                return raw, True, battery_min_floor_w, battery_min_floor_reason, False

        if battery_min_floor_w is None:
            battery_min_floor_w = float(min_charge_floor_w)

        if primary_material_positive_rpnz:
            raw = int(round(min_charge_floor_w))
        else:
            if (
                separate_primary_regulation
                and primary_active
                and float(nz.rpnz_w) <= RPNZ_PRACTICAL_ZERO_W
                and (not primary_release_pending)
            ):
                adjustable_surplus_active_next = False
                raw = int(round(min_charge_floor_w))
            else:
                adjustable_surplus_active_next = False
                raw = candidate_sp_net_zero(
                    rpnz_w=effective_rpnz_w,
                    grid_actual_w=m.grid_power_w,
                    current_sp_w=m.current_battery_setpoint_w,
                    deadband_w=cfg.deadband_w,
                    ramp_w=cfg.ramp_max_w,
                    max_sp_w=cfg.max_solar_charge_w,
                    min_charge_floor_w=min_charge_floor_w,
                )

        if (
            separate_primary_regulation
            and adjustable_is_home_battery
            and bool(adjustable_surplus_active)
            and float(nz.rpnz_w) >= 0.0
        ):
            activation_clamped_w = min(max(configured_activation_w, 0.0), float(cfg.max_solar_charge_w))
            raw = int(round(activation_clamped_w))

        activation_gate_active = (
            adjustable_is_home_battery
            and configured_activation_w > 0.0
            and (not bool(adjustable_surplus_active))
            and float(nz.required_power_consumption_kw) < (configured_activation_w / 1000.0)
        )
        if activation_gate_active:
            current_sp = int(round(m.current_battery_setpoint_w))
            # Activation gate protects only positive charging ramp-up before activation.
            # Negative-domain recovery toward zero must stay under normal controller dynamics.
            if raw > current_sp and raw >= 0 and current_sp >= 0:
                raw = current_sp
                battery_min_floor_reason = 'activation_gate_hold'

        if (
            haeo_nz_plan is not None
            and bool(getattr(haeo_nz_plan, 'active', False))
            and raw > _haeo_plan_device_limit_w(
                haeo_nz_plan,
                'HOME_BATTERY',
                getattr(haeo_nz_plan, 'battery_limit_w', 0),
            )
        ):
            raw = _haeo_plan_device_limit_w(
                haeo_nz_plan,
                'HOME_BATTERY',
                getattr(haeo_nz_plan, 'battery_limit_w', 0),
            )
    elif haeo.effective_forecast == ForecastProfile.HAEO and profiles.goal in (GoalProfile.MAX_EXPORT, GoalProfile.CHEAP_GRID_CHARGE):
        raw = int(round(haeo.battery_target_kw * 1000.0))
    elif profiles.goal == GoalProfile.MAX_EXPORT:
        raw = -4000
    elif profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        raw = 100
    else:
        raw = int(round(cfg.default_sp_w))

    if profiles.guard == GuardProfile.DEGRADED:
        return 0, True, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.guard == GuardProfile.BATTERY_PROTECT:
        return max(raw, _battery_protect_charge_floor_w(cfg)), True, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.guard == GuardProfile.STRICT_LIMITS:
        limit = int(cfg.strict_limits_max_w)
        return min(max(raw, -limit), limit), True, battery_min_floor_w, battery_min_floor_reason, False

    if profiles.guard == GuardProfile.NORMAL_LIMITS:
        raw = _normal_limits_discharge_cap(raw, cfg)

    return raw, True, battery_min_floor_w, battery_min_floor_reason, adjustable_surplus_active_next


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
    force_charge_blocked,
    adjustable_surplus_active,
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
        and adjustable_surplus_active
        and (not ev_release_pending)
        and role == 'surplus_adjustable'
        and float(rpnz_w) > 0.0
    ):
        target_w = float(ev_max_power_w(ev_context))

    if (
        profiles.goal == GoalProfile.NET_ZERO
        and haeo_nz_plan is not None
        and bool(getattr(haeo_nz_plan, 'active', False))
        and target_w > 0
    ):
        limit_w = float(getattr(haeo_nz_plan, 'ev_limit_w', 0))
        target_w = min(float(target_w), limit_w) if limit_w > 0 else 0.0

    if profiles.goal == GoalProfile.MAX_EXPORT and target_w == 0:
        mode = 'hard_off' if uses_hard_off_lifecycle else 'restore_min'
        return mode, 0.0

    if force_charge_blocked:
        target_w = 0.0

    if uses_hard_off_lifecycle and lifecycle_transition is not None and lifecycle_transition.hard_off_active:
        return 'hard_off', 0.0

    if target_w > 0:
        return 'burn', float(target_w)

    restore_min_w = float(ev_min_power_w(ev_context)) if role == 'primary' else 0.0
    return 'restore_min', restore_min_w


def _primary_device_power_envelope_w(cfg, device_context, m, nz):
    return candidate_sp_net_zero(
        rpnz_w=float(nz.rpnz_w),
        grid_actual_w=float(m.grid_power_w),
        current_sp_w=float(device_context.current_measured_power_w),
        deadband_w=float(cfg.deadband_w),
        ramp_w=float(cfg.ramp_max_w),
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
    dispatch_decision,
    combo_change_freeze_until_ts,
    decision_freeze_until_ts,
    effective_freeze_until_ts,
):
    if combo_change_freeze_until_ts is not None:
        return combo_change_freeze_until_ts
    action = str(dispatch_action or '')
    decision = str(dispatch_decision or '')
    if action == 'CLEAR_ALL' and decision == 'CLEAR_ALL':
        return None
    if action == 'NOOP':
        return effective_freeze_until_ts
    if decision_freeze_until_ts is not None:
        return decision_freeze_until_ts
    return effective_freeze_until_ts


def compute_net_zero_engine_outputs(
    profiles, cfg, m, haeo, nz, now_ts, *,
    freeze_until_ts,
    ev_burn_active,
    adjustable_surplus_active=False,
    pv_power_kw=None,
    ev_hard_off_active=False,
    ev_low_pv_cycles=0,
    ev_hard_off_release_ready_cycles=0,
    relay_device_states=None,
    previous_ev_device_states=None,
    previous_device_states=None,
    previous_force_on_device_ids=None,
    haeo_nz_plan=None,
    current_device_power_w_by_id=None,
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
            battery_target_kw=haeo.battery_target_kw,
            ev_target_kw=haeo.ev_target_kw,
        )

        if haeo_nz_plan is None:
            haeo_nz_plan = HaeoNetZeroPlan(False, device_limits_w={})
        haeo_nz_plan_active = bool(getattr(haeo_nz_plan, 'active', False))
        _note_net_zero_duration_ms('policy_engine_net_zero_forecast_haeo_normalization_ms', forecast_haeo_started_ts)

        role_normalization_started_ts = _net_zero_profile_started_ts()
        if haeo_nz_plan_active:
            primary_device_id = str(_haeo_plan_primary_device_id(haeo_nz_plan) or '')
            surplus_adjustable_device_id = str(_haeo_plan_adjustable_device_id(haeo_nz_plan) or '')
            primary_surplus_combo_source = 'HAEO_NET_ZERO_PLAN'
        else:
            surplus_adjustable_device_id = str(
                _normalized_adjustable_surplus_load(cfg, facts=policy_runtime_facts) or ''
            )
            requested_primary_device_id = str(
                _normalized_adjustable_primary_load(cfg, facts=policy_runtime_facts) or ''
            )
            primary_device_id = requested_primary_device_id or surplus_adjustable_device_id
            primary_surplus_combo_source = 'CONFIG'

        # Legacy external role names remain diagnostics-only aliases. Core execution keeps
        # physical device identity and derives controllability from capabilities.
        adjustable_primary_load = primary_device_id
        adjustable_surplus_load = surplus_adjustable_device_id
        explicit_same_target = (
            (not haeo_nz_plan_active)
            and bool(_normalized_adjustable_primary_load(cfg, facts=policy_runtime_facts))
            and primary_device_id == surplus_adjustable_device_id
        )
        current_power_by_id = {}
        for device_id, power_w in (current_device_power_w_by_id or {}).items():
            current_power_by_id[str(device_id)] = float(power_w or 0.0)
        if primary_device_id not in current_power_by_id and _is_ev_device_id(
            cfg, primary_device_id, facts=policy_runtime_facts
        ):
            ev_context_for_measurement = _selected_ev_context(
                cfg, primary_device_id, facts=policy_runtime_facts
            )
            current_power_by_id[primary_device_id] = float(
                ev_current_a_to_power_w(
                    _ev_runtime_current_a(m, primary_device_id),
                    ev_context_for_measurement.phases,
                    ev_context_for_measurement.voltage_v,
                )
            )

        primary_device = _device_control_context(
            cfg,
            primary_device_id,
            current_measured_power_w=current_power_by_id.get(primary_device_id, 0.0),
            facts=policy_runtime_facts,
        )
        surplus_adjustable_device = _device_control_context(
            cfg,
            surplus_adjustable_device_id,
            current_measured_power_w=current_power_by_id.get(surplus_adjustable_device_id, 0.0),
            facts=policy_runtime_facts,
        )
        residual_regulator_device_id = _derive_residual_regulator_device_id(
            primary_device, surplus_adjustable_device
        )
        primary_surplus_combo_valid = bool(
            primary_device
            and primary_device.supports_primary_regulation
            and residual_regulator_device_id
            and not explicit_same_target
        )
        if explicit_same_target:
            primary_surplus_combo_reason = 'unsupported_same_target_combo'
        elif primary_device is None or not primary_device.supports_primary_regulation:
            primary_surplus_combo_reason = 'primary_regulation_not_supported'
        elif not residual_regulator_device_id:
            primary_surplus_combo_reason = 'residual_regulator_not_available'
        else:
            primary_surplus_combo_reason = (
                'haeo_net_zero_plan' if haeo_nz_plan_active else 'capability_driven_roles'
            )
        combo_fallback_active = False
        combo_fallback_warning = ''

        has_ev_devices = _has_ev_devices(cfg, facts=policy_runtime_facts)
        selected_ev_device_id = _selected_ev_device_id_for_roles(
            cfg,
            surplus_adjustable_device_id,
            primary_device_id,
            facts=policy_runtime_facts,
        )
        selected_ev = _selected_ev_context(cfg, selected_ev_device_id, facts=policy_runtime_facts)
        selected_ev_role = (
            'surplus_adjustable'
            if selected_ev_device_id and selected_ev_device_id == surplus_adjustable_device_id
            else 'primary'
            if selected_ev_device_id and selected_ev_device_id == primary_device_id
            else 'inactive'
        )
        _note_net_zero_duration_ms('policy_engine_net_zero_role_normalization_ms', role_normalization_started_ts)

        previous_ev_state_started_ts = _net_zero_profile_started_ts()
        previous_state_source = previous_device_states if previous_device_states is not None else previous_ev_device_states
        normalized_previous_device_states = _normalize_previous_device_states(previous_state_source)
        hard_off_lifecycle_device_ids = _hard_off_lifecycle_device_ids(cfg, facts=policy_runtime_facts)
        selected_uses_hard_off_lifecycle = _device_uses_hard_off_lifecycle(
            cfg,
            selected_ev_device_id,
            facts=policy_runtime_facts,
        )
        selected_previous_ev_state = normalized_previous_device_states.get(selected_ev_device_id)
        if has_ev_devices and selected_previous_ev_state is None:
            # Preserve the legacy scalar state inputs while generic callers migrate
            # to previous_device_states[device_id].
            selected_previous_ev_state = _normalize_previous_device_state_entry(
                selected_ev_device_id,
                {
                    'device_id': selected_ev_device_id,
                    'mode': '',
                    'low_pv_cycles': ev_low_pv_cycles,
                    'hard_off_release_ready_cycles': ev_hard_off_release_ready_cycles,
                    'hard_off_active': ev_hard_off_active,
                },
            )
            normalized_previous_device_states[selected_ev_device_id] = selected_previous_ev_state
        for lifecycle_device_id in hard_off_lifecycle_device_ids:
            normalized_previous_device_states.setdefault(
                lifecycle_device_id,
                _default_previous_device_state(lifecycle_device_id),
            )
        if not has_ev_devices:
            selected_previous_ev_state = _default_previous_device_state('')
        _note_net_zero_duration_ms('policy_engine_net_zero_previous_ev_state_normalization_ms', previous_ev_state_started_ts)
        _note_net_zero_duration_ms('policy_engine_net_zero_state_parse_ms', state_parse_started_ts)

        surplus_targets_started_ts = _net_zero_profile_started_ts()
        configured_activation_w = float(cfg.adjustable_surplus_activation)
        adjustable_active_current = bool(adjustable_surplus_active or ev_burn_active)
        adjustable_priority = int(
            _device_policy_value(
                cfg,
                adjustable_surplus_load,
                'priority',
                0,
                facts=policy_runtime_facts,
            )
            or 0
        )
        adjustable_capable = _device_can_absorb(cfg, adjustable_surplus_load, facts=policy_runtime_facts)
        adjustable_enabled = adjustable_capable
        if surplus_adjustable_device_id == selected_ev_device_id and selected_ev_role == 'surplus_adjustable':
            adjustable_enabled = adjustable_capable and bool(
                _device_policy_value(
                    cfg,
                    adjustable_surplus_load,
                    'surplus_allowed',
                    False,
                    facts=policy_runtime_facts,
                )
            )
        normalized_relay_device_states = {}
        for device_id, state in (relay_device_states or {}).items():
            normalized_relay_device_states[str(device_id)] = dict(state or {})
        relay_devices = _relay_devices(cfg, facts=policy_runtime_facts)
        for index, relay in enumerate(relay_devices):
            device_id = str(relay)
            state = normalized_relay_device_states.setdefault(device_id, {})
            if 'surplus_allowed' not in state:
                state['surplus_allowed'] = bool(
                    _device_policy_value(cfg, device_id, 'surplus_allowed', False, facts=policy_runtime_facts)
                )
            if 'force_on' not in state:
                state['force_on'] = bool(
                    _device_policy_value(cfg, device_id, 'force_on', False, facts=policy_runtime_facts)
                )
            if 'active' not in state:
                state['active'] = False
        relay_runtime_candidates = _relay_runtime_candidates(
            cfg,
            normalized_relay_device_states,
            facts=policy_runtime_facts,
        )
        surplus_device_targets = build_surplus_device_targets(
            cfg,
            adjustable_device_id=adjustable_surplus_load,
            adjustable_priority=adjustable_priority,
            adjustable_active=adjustable_active_current,
            adjustable_enabled=adjustable_enabled,
            relay_candidates=relay_runtime_candidates,
        )
        _note_net_zero_duration_ms('policy_engine_net_zero_surplus_targets_ms', surplus_targets_started_ts)

        surplus_active = net_zero_surplus_policy_active(profiles, eff_fc, haeo_nz_plan_active=haeo_nz_plan_active)

        surplus_freeze_s = _cfg_scalar_value(cfg, 'surplus_freeze_s', 0)
        effective_freeze_until_ts, current_force_on_device_ids = _apply_force_rising_edge_freeze_for_devices(
            now_ts=now_ts,
            freeze_until_ts=freeze_until_ts,
            freeze_s=surplus_freeze_s,
            relay_candidates=relay_runtime_candidates,
            previous_force_on_device_ids=previous_force_on_device_ids or (),
        )

        surplus_device_inp = SurplusDispatchInput(
            policy_active=surplus_active,
            freeze_until_ts=effective_freeze_until_ts,
            rpc_kw=nz.required_power_consumption_kw,
            rpnz_w=nz.rpnz_w,
            targets=surplus_device_targets,
        )
        surplus_device_decision = compute_surplus_device_dispatch(surplus_device_inp, now_ts, surplus_freeze_s)
        surplus_device_next = next_device_target(surplus_device_targets)
        surplus_device_release = release_device_target(surplus_device_targets)

        relay_active_now = False
        for relay in relay_runtime_candidates:
            if bool(relay.get('active', False)):
                relay_active_now = True
                break
        combo_change_requires_clear = (
            haeo_nz_plan_active
            and bool(getattr(haeo_nz_plan, 'changed', False))
            and (
                bool(adjustable_active_current)
                or relay_active_now
            )
        )
        combo_change_freeze_until_ts = (
            float(now_ts) + float(surplus_freeze_s)
            if combo_change_requires_clear
            else None
        )
        surplus_state_clear_reason = 'HAEO_COMBO_CHANGED' if combo_change_requires_clear else ''
        surplus_device_decision_text = _decision_text_from_dispatch(
            surplus_device_targets,
            surplus_device_decision,
            combo_change_requires_clear,
        )
        surplus_device_action, surplus_device_target_name = _dispatch_action_and_target(surplus_device_decision_text)
        surplus_device_target_device_id = _device_id_for_decision_name(
            surplus_device_targets,
            surplus_device_target_name,
        ) if surplus_device_target_name else ''
        surplus_device_active_stack = active_device_stack(surplus_device_targets)
        surplus_device_active_device_stack = active_device_stack(surplus_device_targets)
        surplus_device_next_target = surplus_device_next.decision_name if surplus_device_next else 'NONE'
        surplus_device_release_candidate = surplus_device_release.decision_name if surplus_device_release else 'NONE'
        surplus_device_next_device_id = surplus_device_next.device_id if surplus_device_next else ''
        surplus_device_release_device_id = surplus_device_release.device_id if surplus_device_release else ''

        primary_release_target = 'ADJUSTABLE'
        low_pv = False
        battery_to_ev_loop_risk = False
        ev_min_power_kw = 0.0
        hard_off_release_rpc_kw = 0.0
        hard_off_release_cycles_required = 0
        hard_off_release_ready_cycles_next = 0
        ev_primary_burn_active = False
        ev_surplus_burn_active = False
        ev_policy_mode = 'skip'
        next_low_pv_cycles = 0
        ev_hard_off_active_next = False
        primary_envelope_w = None
        primary_device_target_w = 0.0
        residual_rpnz_w = float(nz.rpnz_w)
        ev_target_w = 0.0
        ev_burn_active_for_battery = False
        lifecycle_transition = None
        ev_policy_started_ts = _net_zero_profile_started_ts()
        if has_ev_devices:
            low_pv = (
                selected_uses_hard_off_lifecycle
                and pv_power_kw is not None
                and float(pv_power_kw) < float(selected_ev.hard_off_pv_threshold_kw)
            )
            battery_to_ev_loop_risk = low_pv and float(m.current_battery_setpoint_w) < 0.0
            ev_min_power_kw = float(ev_min_power_w(selected_ev)) / 1000.0
            hard_off_release_rpc_kw = (
                configured_activation_w / 1000.0
                if selected_ev_role == 'surplus_adjustable'
                else ev_min_power_kw
            )
            hard_off_release_cycles_required = max(
                1, int(getattr(selected_ev, 'hard_off_release_cycles', 2) or 2)
            )
            lifecycle_enabled = (
                profiles.control == ControlProfile.AUTOMATIC
                and profiles.goal == GoalProfile.NET_ZERO
                and profiles.guard == GuardProfile.NORMAL_LIMITS
            )
            requested_active = (
                float(nz.rpnz_w) > 0.0
                if selected_ev_role == 'primary'
                else bool(adjustable_active_current)
                if selected_ev_role == 'surplus_adjustable'
                else False
            )
            selected_ev_device_context = _device_control_context(
                cfg,
                selected_ev_device_id,
                current_measured_power_w=current_power_by_id.get(selected_ev_device_id, 0.0),
                facts=policy_runtime_facts,
            )
            lifecycle_transition = compute_hard_off_lifecycle_transition(
                selected_ev_device_context,
                selected_previous_ev_state,
                lifecycle_enabled=lifecycle_enabled,
                requested_active=(requested_active and not battery_to_ev_loop_risk),
                pv_power_w=pv_power_kw,
                low_pv_threshold_w=float(selected_ev.hard_off_pv_threshold_kw),
                rpc_w=float(nz.required_power_consumption_kw),
                release_rpc_threshold_w=float(hard_off_release_rpc_kw),
                loop_risk=battery_to_ev_loop_risk,
                hard_off_low_pv_cycles=int(getattr(selected_ev, 'hard_off_low_pv_cycles', 1) or 1),
                hard_off_release_cycles=hard_off_release_cycles_required,
            )
            next_low_pv_cycles = int(lifecycle_transition.low_pv_cycles)
            hard_off_release_ready_cycles_next = int(
                lifecycle_transition.hard_off_release_ready_cycles
            )
            ev_hard_off_active_next = bool(lifecycle_transition.hard_off_active)

            ev_primary_burn_active = (
                selected_ev_role == 'primary'
                and (
                    (
                        not bool(selected_previous_ev_state['hard_off_active'])
                        and float(nz.rpnz_w) > 0.0
                    )
                    or bool(lifecycle_transition.release_allowed)
                )
                and (not battery_to_ev_loop_risk)
            )
            ev_surplus_burn_active = (
                selected_ev_role == 'surplus_adjustable'
                and (bool(adjustable_active_current) or bool(lifecycle_transition.release_allowed))
                and (not battery_to_ev_loop_risk)
            )
            if combo_change_requires_clear:
                ev_primary_burn_active = False
                ev_surplus_burn_active = False
            ev_burn_for_cycle = ev_surplus_burn_active or ev_primary_burn_active
            ev_policy_mode, ev_target_w = _ev_policy_mode_and_target_w(
                profiles,
                selected_ev,
                normalized_haeo,
                role=selected_ev_role,
                burn_active=ev_burn_for_cycle,
                force_charge_blocked=battery_to_ev_loop_risk,
                adjustable_surplus_active=adjustable_active_current,
                ev_release_pending=(surplus_device_decision.release == primary_release_target),
                rpnz_w=nz.rpnz_w,
                lifecycle_transition=lifecycle_transition,
                uses_hard_off_lifecycle=selected_uses_hard_off_lifecycle,
                haeo_nz_plan=haeo_nz_plan,
            )

            if (
                profiles.goal == GoalProfile.NET_ZERO
                and (
                    combo_change_requires_clear
                    or (
                        selected_ev_role == 'surplus_adjustable'
                        and (
                            surplus_device_decision.clear_all
                            or surplus_device_decision.release == primary_release_target
                        )
                    )
                )
                and ev_policy_mode != 'skip'
            ):
                ev_policy_mode = 'restore_min'
                ev_target_w = 0.0

            if selected_ev_role == 'primary':
                primary_device_target_w = float(ev_target_w)

            if selected_ev_role == 'primary' and ev_policy_mode == 'burn':
                primary_envelope_w = _primary_device_power_envelope_w(cfg, primary_device, m, nz)
                primary_device_target_w = compute_primary_device_target_w(
                    primary_device, primary_envelope_w
                )
                if haeo_nz_plan_active:
                    limit_w = float(getattr(haeo_nz_plan, 'ev_limit_w', 0))
                    primary_device_target_w = (
                        min(float(primary_device_target_w), limit_w) if limit_w > 0 else 0.0
                    )
                ev_target_w = float(primary_device_target_w)
                ev_policy_mode = 'burn' if primary_device_target_w > 0 else 'restore_min'

            residual_rpnz_w = float(nz.rpnz_w) - (
                float(max(primary_device_target_w, 0.0))
                if primary_device_id != residual_regulator_device_id
                else 0.0
            )
            ev_burn_active_for_battery = (
                (ev_policy_mode == 'burn' and float(max(ev_target_w, 0.0)) > 0.0)
                or (
                    selected_ev_role == 'primary'
                    and ev_policy_mode == 'restore_min'
                    and _ev_runtime_enabled(m, selected_ev_device_id)
                    and float(max(ev_target_w, 0.0)) > 0.0
                    and not battery_to_ev_loop_risk
                )
            )
        _note_net_zero_duration_ms('policy_engine_net_zero_ev_policy_ms', ev_policy_started_ts)

        battery_policy_started_ts = _net_zero_profile_started_ts()
        battery_target_w, battery_write_enabled, battery_min_floor_w, battery_min_floor_reason, adjustable_surplus_active_next = _battery_target_and_authority(
            profiles,
            cfg,
            primary_device,
            m,
            normalized_haeo,
            nz,
            primary_active=ev_burn_active_for_battery,
            primary_release_pending=(surplus_device_decision.release == primary_release_target),
            primary_target_w=primary_device_target_w,
            adjustable_surplus_active=adjustable_surplus_active,
            separate_primary_regulation=(primary_device_id != residual_regulator_device_id),
            haeo_nz_plan=haeo_nz_plan,
            surplus_adjustable_device_id=surplus_adjustable_device_id,
            facts=policy_runtime_facts,
        )
        _note_net_zero_duration_ms('policy_engine_net_zero_battery_policy_ms', battery_policy_started_ts)
        discharge_limit_w, discharge_limit_sign_mode, configured_discharge_limit_w = _normalized_discharge_limit_w(cfg)

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
        device_policies = _build_device_policies(
            cfg,
            battery_target_w=battery_target_w,
            battery_write_enabled=battery_write_enabled,
            ev_target_w=ev_target_w,
            ev_policy_mode=ev_policy_mode,
            adjustable_ev_device_id=selected_ev_device_id,
            relay_policies=tuple(relay_policy_states),
            facts=policy_runtime_facts,
        )
        device_policies, capability_blocked_devices = _enforce_device_policy_capabilities(
            cfg,
            device_policies,
            facts=policy_runtime_facts,
        )
        battery_policy = None
        for policy in device_policies:
            if policy.device_id == 'HOME_BATTERY':
                battery_policy = policy
                break
        if battery_policy is not None:
            battery_target_w = int(battery_policy.target_w)
            battery_write_enabled = bool(battery_policy.enabled)
        updated_previous_device_states = _normalize_previous_device_states(normalized_previous_device_states)
        if has_ev_devices and selected_ev_device_id:
            updated_previous_device_states[selected_ev_device_id] = _normalize_previous_device_state_entry(
                selected_ev_device_id,
                {
                    'device_id': selected_ev_device_id,
                    'mode': ev_policy_mode,
                    'low_pv_cycles': next_low_pv_cycles,
                    'hard_off_active': ev_hard_off_active_next,
                    'hard_off_release_ready_cycles': hard_off_release_ready_cycles_next,
                },
            )
            selected_previous_ev_state_next = updated_previous_device_states[selected_ev_device_id]
        else:
            selected_previous_ev_state_next = _default_previous_device_state('')
        device_lifecycle_states = {}
        for device_id in hard_off_lifecycle_device_ids:
            if device_id in updated_previous_device_states:
                device_lifecycle_states[device_id] = updated_previous_device_states[device_id]

        legacy_device_bridge_count, legacy_device_bridge_counts_by_kind = _legacy_bridge_metrics(cfg)

        result = NetZeroOutputs(
        battery_target_w=battery_target_w,
        battery_write_enabled=battery_write_enabled,
        surplus_policy_active=surplus_active,
        surplus_next_target=surplus_device_next_target,
        surplus_next_threshold_kw=round(float(surplus_device_next.threshold_w) / 1000.0, 3) if surplus_device_next else 0,
        surplus_release_candidate=surplus_device_release_candidate,
        surplus_dispatch_decision=surplus_device_decision_text,
        surplus_explanation=surplus_device_decision.explanation,
        effective_forecast=eff_fc,
        dominant_limitation=dominant_limitation(profiles, conf_fc, eff_fc),
        explanation=explain(profiles, conf_fc, eff_fc, haeo_nz_plan_active=haeo_nz_plan_active),
        device_policies=device_policies,
        attrs={
            'configured_forecast': conf_fc,
            'active_stack': surplus_device_active_stack,
            'surplus_device_active_stack': surplus_device_active_stack,
            'surplus_device_active_device_stack': surplus_device_active_device_stack,
            'surplus_device_next_target': surplus_device_next_target,
            'surplus_device_next_device_id': surplus_device_next_device_id,
            'surplus_device_release_candidate': surplus_device_release_candidate,
            'surplus_device_release_device_id': surplus_device_release_device_id,
            'surplus_device_dispatch_decision': surplus_device_decision_text,
            'surplus_device_dispatch_action': surplus_device_action,
            'surplus_device_dispatch_target': surplus_device_target_name,
            'surplus_device_dispatch_device_id': surplus_device_target_device_id,
            'surplus_device_dispatch_contract': 'device_id_primary',
            'surplus_device_targets': device_targets_payload(surplus_device_targets),
            'relay_device_ids': _relay_device_ids_payload(cfg, facts=policy_runtime_facts),
            'ev_device_ids': _ev_device_ids_payload(cfg, facts=policy_runtime_facts),
            'device_policies': _device_policy_payloads(device_policies),
            'capability_blocked_devices': capability_blocked_devices,
            'surplus_primary_target': primary_release_target,
            'surplus_freeze_until_ts': _canonical_surplus_freeze_until_ts_for_output(
                surplus_device_action,
                surplus_device_decision_text,
                combo_change_freeze_until_ts,
                surplus_device_decision.freeze_until_ts,
                effective_freeze_until_ts,
            ),
            'surplus_state_clear_reason': surplus_state_clear_reason,
            'surplus_rpc_kw': nz.required_power_consumption_kw,
            'surplus_rpnz_w': nz.rpnz_w,
            'battery_write_enabled': battery_write_enabled,
            'primary_device_id': primary_device_id,
            'surplus_adjustable_device_id': surplus_adjustable_device_id,
            'residual_regulator_device_id': residual_regulator_device_id,
            'primary_device_target_w': int(round(float(primary_device_target_w))),
            'residual_rpnz_w': float(residual_rpnz_w),
            'selected_ev_device_id': selected_ev_device_id,
            'ev_policy_mode': ev_policy_mode,
            'ev_low_pv_cycles': next_low_pv_cycles,
            'ev_hard_off_active': ev_hard_off_active_next,
            'ev_hard_off_release_ready_cycles': hard_off_release_ready_cycles_next,
            'previous_device_state': selected_previous_ev_state_next,
            'previous_device_states': updated_previous_device_states,
            'device_lifecycle_states': device_lifecycle_states,
            'hard_off_lifecycle_devices': hard_off_lifecycle_device_ids,
            # Compatibility view derived from the generic device-owned state map.
            'previous_ev_device_states': updated_previous_device_states,
            'ev_hard_off_release_cycles_required': hard_off_release_cycles_required,
            'ev_hard_off_release_rpc_kw': hard_off_release_rpc_kw,
            'pv_power_kw': pv_power_kw,
            'ev_hard_off_pv_threshold_kw': selected_ev.hard_off_pv_threshold_kw,
            'battery_to_ev_loop_risk': bool(battery_to_ev_loop_risk),
            'ev_adjustable_mode': bool(selected_ev_role == 'surplus_adjustable'),
            'ev_primary_burn_active': bool(ev_primary_burn_active),
            'ev_surplus_burn_active': bool(ev_surplus_burn_active),
            'ev_current_step_a': int(getattr(selected_ev, 'current_step_a', 1) or 1),
            'ev_force_on': bool(getattr(selected_ev, 'force_on', False)),
            'ev_min_power_w': int(ev_min_power_w(selected_ev)),
            'ev_max_power_w': int(ev_max_power_w(selected_ev)),
            'ev_power_step_w': int(getattr(selected_ev, 'power_step_w', 0) or 0),
            'ev_target_w': int(round(ev_target_w)),
            'primary_power_envelope_w': primary_envelope_w,
            # Compatibility diagnostic: derived from the selected device policy.
            # DevicePolicy.priority is the only surplus-priority authority.
            'adjustable_surplus_load_priority': int(adjustable_priority),
            'adjustable_surplus_load': adjustable_surplus_load,
            'adjustable_surplus_activation': configured_activation_w,
            'adjustable_primary_load': adjustable_primary_load,
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
            'surplus_adjustable_active': bool(adjustable_surplus_active_next),
            'haeo_nz_plan_active': bool(haeo_nz_plan_active),
            'haeo_nz_quarter_key': getattr(haeo_nz_plan, 'quarter_key', ''),
            'haeo_nz_combo_changed': bool(getattr(haeo_nz_plan, 'changed', False)),
            'haeo_nz_primary_device_id': _haeo_plan_primary_device_id(haeo_nz_plan),
            'haeo_nz_adjustable_device_id': _haeo_plan_adjustable_device_id(haeo_nz_plan),
            'haeo_nz_device_limits_w': getattr(haeo_nz_plan, 'device_limits_w', {}) or {},
            'haeo_nz_battery_limit_w': int(getattr(haeo_nz_plan, 'battery_limit_w', 0)),
            'haeo_nz_ev_limit_w': int(getattr(haeo_nz_plan, 'ev_limit_w', 0)),
            'haeo_nz_combo_reason': getattr(haeo_nz_plan, 'reason', ''),
            'prev_force_on_device_ids': current_force_on_device_ids,
            'legacy_device_bridge_count': int(legacy_device_bridge_count),
            'legacy_device_bridge_counts_by_kind': legacy_device_bridge_counts_by_kind,
        },
    )
        return result
    finally:
        if NET_ZERO_DETAILED_METRICS_ENABLED:
            _LAST_NET_ZERO_COMPUTE_METRICS.update(_ACTIVE_NET_ZERO_COMPUTE_METRICS or {})
        else:
            _LAST_NET_ZERO_COMPUTE_METRICS.clear()
        _ACTIVE_NET_ZERO_COMPUTE_METRICS = None
