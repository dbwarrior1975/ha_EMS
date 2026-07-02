import hashlib
import json

from ems_core.domain.models import ControlProfile, GoalProfile, ForecastProfile, GuardProfile, Profiles, RuntimeMeasurements, HaeoTargets, NetZeroState, CoreConfig
from ems_core.guard.evaluator import evaluate_guard
from ems_core.net_zero.derived_inputs import derive_net_zero_inputs
from ems_core.net_zero.engine import compute_net_zero_engine_outputs, configured_forecast, effective_forecast
from ems_core.integrations.haeo_horizon import latest_forecast_value_at_or_before
from ems_core.integrations.haeo_net_zero_plan import compute_haeo_net_zero_plan
from ems_core.diagnostics.policy_diagnostics import net_zero_attrs
from ems_adapter.ha_adapter import get_float, get_int, get_bool, get_str, age_seconds, get_attr, parse_input_datetime_ts, publish_sensor
from ems_adapter.runtime_context import _GROUPED_CONFIG_DUAL_READ_STATUS, config_trace_attrs, read_runtime_context
_POLICY_ENGINE_BUILD = 'pyscript_ast_loop_safe_2026_06_15'
_POLICY_ENGINE_TIMER_STATE = {
    'last_run_ts': None,
    'last_diagnostics_publish_ts': None,
    'effective_interval_seconds': 5.0,
    'effective_diagnostics_interval_seconds': 30.0,
    'scheduler_tick_seconds': 2.0,
    'ticks_seen': 0,
    'runs_seen': 0,
    'skipped_ticks': 0,
    'previous_device_policies_hash': None,
    'previous_dispatch_command_hash': None,
    'previous_policy_state_hash': None,
    'previous_warning_signature': None,
}


def _enum(allowed_cls, value, default):
    allowed = set()
    for key, enum_value in allowed_cls.__dict__.items():
        if key.isupper():
            allowed.add(enum_value)
    return value if value in allowed else default


def _policy_output_contract_attrs():
    return {
        'policy_engine_build': _POLICY_ENGINE_BUILD,
        'policy_output_contract': 'device_policy_primary',
        'canonical_policy_output_contract': 'device_policies',
        'diagnostics_contract': 'policy_explanation_only',
        'runtime_contract': False,
    }


def _json_stable(value):
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            normalized[str(key)] = _json_stable(item)
        return normalized
    if isinstance(value, (list, tuple)):
        normalized = []
        for item in value:
            normalized.append(_json_stable(item))
        return normalized
    if isinstance(value, set):
        sortable_items = []
        for item in value:
            normalized_item = _json_stable(item)
            sortable_items.append((_stable_json_text(normalized_item), normalized_item))
        sortable_items.sort()
        normalized = []
        for _serialized_item, normalized_item in sortable_items:
            normalized.append(normalized_item)
        return normalized
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return str(value)


def _stable_json_text(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _payload_hash(payload):
    serialized = _stable_json_text(_json_stable(payload))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]


def read_core_config():
    cfg, _entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    return cfg


def read_config():
    return read_core_config()
    
def read_profiles(entities):
    return Profiles(
        control=_enum(ControlProfile, get_str(entities['control_profile'], 'AUTOMATIC'), ControlProfile.AUTOMATIC),
        goal=_enum(GoalProfile, get_str(entities['goal_profile'], 'NET_ZERO'), GoalProfile.NET_ZERO),
        forecast=_enum(ForecastProfile, get_str(entities['forecast_profile'], 'NONE'), ForecastProfile.NONE),
        guard=_enum(GuardProfile, get_str(entities['guard_profile'], 'NORMAL_LIMITS'), GuardProfile.NORMAL_LIMITS),
    )


def _ev_state_payload(device):
    enabled_entity = device.get('enabled', '')
    current_entity = device.get('current_a', '')
    current_a = get_int(current_entity, 0)
    return {
        'enabled': get_bool(enabled_entity),
        'current_a': current_a,
        'surplus_allowed': get_bool(device.get('surplus_allowed', '')),
        'active': bool(get_bool(enabled_entity) and current_a > 0),
    }


def read_measurements(now_ts, cfg, entities):
    device_entities = entities.get('devices', {}) or {}
    active_surplus_device_ids = set(_read_active_surplus_device_ids(entities))
    relay_states = {}
    ev_states = {}
    for device_id, device in device_entities.items():
        if not isinstance(device, dict):
            continue
        kind = str(device.get('kind') or '')
        if kind == 'RELAY':
            relay_states[str(device_id)] = {
                'enabled': get_bool(device.get('enabled', '')),
                'surplus_allowed': get_bool(device.get('surplus_allowed', '')),
                'force_on': get_bool(device.get('force_on', '')),
                'active': str(device_id) in active_surplus_device_ids,
            }
        elif kind == 'EV_CHARGER':
            ev_states[str(device_id)] = _ev_state_payload(device)

    return RuntimeMeasurements(
        now_ts=now_ts,
        soc=get_float(entities['soc'], None),
        min_cell_voltage_v=get_float(entities['min_cell_voltage_v'], None),
        battery_heartbeat_age_s=age_seconds(entities['battery_heartbeat'], now_ts),
        grid_power_w=get_float(entities['grid_power_w'], 0),
        current_battery_setpoint_w=get_float(entities['current_battery_sp'], 100),
        quarter_energy_balance_kwh=get_float(entities['quarter_energy_balance_kwh'], 0),
        pv_power_w=get_float(entities['pv_power_w'], None),
        relay_states=relay_states,
        ev_states=ev_states,
    )


def read_haeo(now_ts, profiles, cfg, entities):
    configured = configured_forecast(profiles.control, profiles.forecast)
    batt_age = age_seconds(entities['haeo_battery_active_power_fresh_source'], now_ts)
    ev_age = age_seconds(entities['haeo_ev_active_power_fresh_source'], now_ts)
    fresh = batt_age < cfg.haeo_stale_timeout_s and ev_age < cfg.haeo_stale_timeout_s
    eff = effective_forecast(configured, fresh)
    batt_forecast = get_attr(entities['haeo_battery_power_active'], 'forecast', []) or []
    ev_forecast = get_attr(entities['haeo_ev_battery_power_active'], 'forecast', []) or []
    return HaeoTargets(
        effective_forecast=eff,
        configured_forecast=configured,
        fresh=fresh,
        battery_target_kw=latest_forecast_value_at_or_before(batt_forecast, now_ts, 0),
        ev_target_kw=max(latest_forecast_value_at_or_before(ev_forecast, now_ts, 0), 0),
    )


def _trace_state(profiles, outputs):
    return f"{profiles.control}/{profiles.goal}/{profiles.guard}/{outputs.effective_forecast}"


def _parse_active_device_ids(raw_value):
    if raw_value in (None, '', 'unknown', 'unavailable', 'none'):
        return ()
    if isinstance(raw_value, (list, tuple, set)):
        parsed = []
        for item in raw_value:
            text = str(item)
            if text:
                parsed.append(text)
        return tuple(parsed)
    text = str(raw_value).strip()
    if not text:
        return ()
    parsed = []
    for part in text.split(','):
        item = part.strip()
        if item:
            parsed.append(item)
    return tuple(parsed)


def _read_active_surplus_device_ids(entities):
    device_ids = get_attr(entities['active_surplus_devices'], 'device_ids', None)
    parsed = _parse_active_device_ids(device_ids)
    if parsed:
        return parsed
    parsed = _parse_active_device_ids(get_str(entities['active_surplus_devices'], ''))
    if parsed:
        return parsed
    return ()


def _read_previous_device_state(entities):
    return _read_selected_previous_device_state(entities)


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


def _read_previous_ev_device_states(entities):
    states = {}
    raw_states = get_attr(entities['previous_device_state'], 'device_states', None)
    if isinstance(raw_states, dict):
        for device_id, state in raw_states.items():
            states[str(device_id)] = _normalize_previous_device_state_entry(device_id, state)

    mode = get_attr(entities['previous_device_state'], 'mode', '')
    if mode:
        device_id = get_attr(entities['previous_device_state'], 'device_id', '')
        if device_id:
            states[str(device_id)] = _normalize_previous_device_state_entry(
                device_id,
                {
                    'device_id': device_id,
                    'mode': mode,
                    'low_pv_cycles': get_attr(entities['previous_device_state'], 'low_pv_cycles', 0),
                    'hard_off_release_ready_cycles': get_attr(entities['previous_device_state'], 'hard_off_release_ready_cycles', 0),
                    'hard_off_active': get_attr(entities['previous_device_state'], 'hard_off_active', False),
                },
            )
    return states


def _read_selected_previous_device_state(entities):
    states = _read_previous_ev_device_states(entities)
    adjustable_device_id = get_str(entities['adjustable_surplus_load'], 'EV_CHARGER')
    if adjustable_device_id in states:
        return states[adjustable_device_id]
    return _default_previous_device_state(adjustable_device_id)


def _selected_ev_device_id_from_outputs(outputs):
    return str(outputs.attrs.get('selected_ev_device_id', 'EV_CHARGER') or 'EV_CHARGER')


def _previous_device_state_attrs_from_outputs(outputs):
    device_id = _selected_ev_device_id_from_outputs(outputs)
    selected_state = outputs.attrs.get('previous_device_state', {}) or {}
    normalized_selected = _normalize_previous_device_state_entry(device_id, selected_state)
    normalized_states = {}
    raw_states = outputs.attrs.get('previous_ev_device_states', {}) or {}
    for raw_device_id, raw_state in raw_states.items():
        normalized_states[str(raw_device_id)] = _normalize_previous_device_state_entry(raw_device_id, raw_state)
    if device_id not in normalized_states:
        normalized_states[device_id] = normalized_selected
    return {
        'device_id': normalized_selected['device_id'],
        'mode': normalized_selected['mode'],
        'low_pv_cycles': normalized_selected['low_pv_cycles'],
        'hard_off_active': normalized_selected['hard_off_active'],
        'hard_off_release_ready_cycles': normalized_selected['hard_off_release_ready_cycles'],
        'device_states': normalized_states,
    }


def _selected_previous_device_state_for_outputs(outputs):
    device_id = _selected_ev_device_id_from_outputs(outputs)
    return _normalize_previous_device_state_entry(device_id, outputs.attrs.get('previous_device_state', {}))


def _read_adjustable_surplus_active(entities):
    active_device_ids = _read_active_surplus_device_ids(entities)
    adjustable_device_id = get_str(entities['adjustable_surplus_load'], 'EV_CHARGER')
    return adjustable_device_id in active_device_ids


_MISSING = object()


def _policy_state_attr(entities, key, default):
    policy_state_entity = entities.get('policy_state')
    if policy_state_entity:
        value = get_attr(policy_state_entity, key, _MISSING)
        if value is not _MISSING:
            return value
    return default


def _read_previous_force_on_device_ids(entities):
    return _parse_active_device_ids(_policy_state_attr(entities, 'prev_force_on_device_ids', ()))


def _device_policies_hash(attrs):
    return _payload_hash({
        'device_policies': attrs.get('device_policies', ()),
    })


def _canonical_surplus_freeze_until_ts_for_dispatch(attrs):
    action = str(attrs.get('surplus_device_dispatch_action') or '')
    decision = str(attrs.get('surplus_device_dispatch_decision') or '')
    clear_reason = str(attrs.get('surplus_state_clear_reason') or '')
    freeze_until_ts = attrs.get('surplus_freeze_until_ts')
    if action == 'CLEAR_ALL' and decision == 'CLEAR_ALL' and clear_reason != 'HAEO_COMBO_CHANGED':
        return None
    return freeze_until_ts


def _dispatch_command_attrs(attrs):
    freeze_until_ts = _canonical_surplus_freeze_until_ts_for_dispatch(attrs)
    command_hash = _payload_hash({
        'surplus_device_dispatch_action': attrs.get('surplus_device_dispatch_action', ''),
        'surplus_device_dispatch_decision': attrs.get('surplus_device_dispatch_decision', ''),
        'surplus_device_dispatch_device_id': attrs.get('surplus_device_dispatch_device_id', ''),
        'surplus_device_dispatch_target': attrs.get('surplus_device_dispatch_target', ''),
        'surplus_device_targets': attrs.get('surplus_device_targets', ()),
        'surplus_freeze_until_ts': freeze_until_ts,
        'surplus_state_clear_reason': attrs.get('surplus_state_clear_reason', ''),
    })
    return {
        'dispatch_command_hash': command_hash,
        'dispatch_command_state_kind': 'content_hash',
        'dispatch_command_version': command_hash,
        'surplus_device_dispatch_action': attrs.get('surplus_device_dispatch_action', ''),
        'surplus_device_dispatch_decision': attrs.get('surplus_device_dispatch_decision', ''),
        'surplus_device_dispatch_device_id': attrs.get('surplus_device_dispatch_device_id', ''),
        'surplus_device_dispatch_target': attrs.get('surplus_device_dispatch_target', ''),
        'surplus_device_targets': attrs.get('surplus_device_targets', ()),
        'surplus_freeze_until_ts': freeze_until_ts,
        'surplus_state_clear_reason': attrs.get('surplus_state_clear_reason', ''),
        'surplus_explanation': attrs.get('surplus_explanation', ''),
    }


def _policy_state_payload(entities, attrs):
    prev_force_on_device_ids = _parse_active_device_ids(
        attrs.get(
            'prev_force_on_device_ids',
            _policy_state_attr(entities, 'prev_force_on_device_ids', ()),
        )
    )
    policy_state_hash = _payload_hash({
        'haeo_nz_quarter_key': attrs.get('haeo_nz_quarter_key', ''),
        'haeo_nz_primary_device_id': attrs.get('haeo_nz_primary_device_id', ''),
        'prev_force_on_device_ids': prev_force_on_device_ids,
    })
    return policy_state_hash, {
        'policy_state_hash': policy_state_hash,
        'policy_state_state_kind': 'content_hash',
        'policy_state_version': policy_state_hash,
        'haeo_nz_quarter_key': attrs.get('haeo_nz_quarter_key', ''),
        'haeo_nz_primary_device_id': attrs.get('haeo_nz_primary_device_id', ''),
        'prev_force_on_device_ids': prev_force_on_device_ids,
    }


def _policy_engine_interval_seconds(cfg):
    policy_engine_cfg = getattr(cfg, 'policy_engine', None)
    if policy_engine_cfg is None:
        return 5.0
    interval_seconds = getattr(policy_engine_cfg, 'interval_seconds', 5.0)
    if interval_seconds in (None, '', False):
        return 5.0
    return float(interval_seconds)


def _policy_engine_diagnostics_interval_seconds(cfg):
    policy_engine_cfg = getattr(cfg, 'policy_engine', None)
    if policy_engine_cfg is None:
        return 30.0
    interval_seconds = getattr(policy_engine_cfg, 'diagnostics_interval_seconds', 30.0)
    if interval_seconds in (None, ''):
        return 30.0
    if isinstance(interval_seconds, bool):
        return 30.0
    return float(interval_seconds)


def _policy_engine_interval_elapsed(now_ts, interval_seconds):
    last_run_ts = _POLICY_ENGINE_TIMER_STATE.get('last_run_ts')
    if last_run_ts is None:
        return True
    return (now_ts - float(last_run_ts)) >= float(interval_seconds)


def _policy_engine_interval_elapsed_fast(now_ts):
    interval_seconds = float(_POLICY_ENGINE_TIMER_STATE.get('effective_interval_seconds', 5.0) or 5.0)
    return _policy_engine_interval_elapsed(now_ts, interval_seconds)


def _update_policy_engine_effective_intervals(cfg):
    _POLICY_ENGINE_TIMER_STATE['effective_interval_seconds'] = _policy_engine_interval_seconds(cfg)
    _POLICY_ENGINE_TIMER_STATE['effective_diagnostics_interval_seconds'] = _policy_engine_diagnostics_interval_seconds(cfg)


def _policy_warning_signature(attrs):
    return _payload_hash({
        'net_zero_input_quality': attrs.get('net_zero_input_quality', ''),
        'net_zero_input_warnings': attrs.get('net_zero_input_warnings', ()),
    })


def _should_publish_policy_diagnostics(
    now_ts,
    trigger_reason,
    diagnostics_interval_seconds,
    canonical_changed,
    warning_state_changed,
):
    reason = str(trigger_reason or '')
    if reason == 'e2e':
        return True, 'e2e'
    if reason == 'manual':
        return True, 'manual'
    if _POLICY_ENGINE_TIMER_STATE.get('last_diagnostics_publish_ts') is None:
        return True, 'startup'
    if canonical_changed:
        return True, 'canonical_changed'
    if warning_state_changed:
        return True, 'warning_changed'
    last_ts = float(_POLICY_ENGINE_TIMER_STATE.get('last_diagnostics_publish_ts') or 0.0)
    if now_ts - last_ts >= float(diagnostics_interval_seconds):
        return True, 'interval'
    return False, 'throttled'


def _note_policy_tick(now_ts):
    _POLICY_ENGINE_TIMER_STATE['ticks_seen'] = int(_POLICY_ENGINE_TIMER_STATE.get('ticks_seen', 0) or 0) + 1
    _POLICY_ENGINE_TIMER_STATE['last_tick_ts'] = now_ts


def _note_policy_skip():
    _POLICY_ENGINE_TIMER_STATE['skipped_ticks'] = int(_POLICY_ENGINE_TIMER_STATE.get('skipped_ticks', 0) or 0) + 1


def _note_policy_run(now_ts):
    _POLICY_ENGINE_TIMER_STATE['last_run_ts'] = now_ts
    _POLICY_ENGINE_TIMER_STATE['runs_seen'] = int(_POLICY_ENGINE_TIMER_STATE.get('runs_seen', 0) or 0) + 1


def run_policy_loop(now_ts, cfg, entities, trigger_reason):
    import time
    run_started_ts = time.time()
    profiles = read_profiles(entities)
    m = read_measurements(now_ts, cfg, entities)
    guard_decision = evaluate_guard(profiles.guard, m, cfg)
    profiles = Profiles(profiles.control, profiles.goal, profiles.forecast, guard_decision.guard)
    haeo = read_haeo(now_ts, profiles, cfg, entities)
    haeo_nz_plan = compute_haeo_net_zero_plan(
        profiles,
        cfg,
        haeo,
        now_ts,
        previous_quarter_key=_policy_state_attr(entities, 'haeo_nz_quarter_key', ''),
        previous_primary_load='',
        previous_primary_device_id=_policy_state_attr(entities, 'haeo_nz_primary_device_id', ''),
    )
    active_surplus_device_ids = _read_active_surplus_device_ids(entities)
    previous_device_state = _read_previous_device_state(entities)
    previous_force_on_device_ids = _read_previous_force_on_device_ids(entities)
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=m.quarter_energy_balance_kwh,
        grid_power_w=m.grid_power_w,
        now_ts=now_ts,
    )
    nz = NetZeroState(
        rpnz_w=derived.rpnz_w,
        required_power_consumption_kw=derived.required_power_consumption_kw,
    )
    pv_power_kw = None if m.pv_power_w is None else m.pv_power_w / 1000.0
    outputs = compute_net_zero_engine_outputs(
        profiles, cfg, m, haeo, nz, now_ts,
        freeze_until_ts=parse_input_datetime_ts(entities['surplus_freeze_until']),
        ev_burn_active=_read_adjustable_surplus_active(entities),
        adjustable_surplus_active=_read_adjustable_surplus_active(entities),
        pv_power_kw=pv_power_kw,
        ev_hard_off_active=bool(previous_device_state['hard_off_active']),
        ev_low_pv_cycles=previous_device_state['low_pv_cycles'],
        ev_hard_off_release_ready_cycles=previous_device_state['hard_off_release_ready_cycles'],
        relay_device_states=getattr(m, 'relay_states', {}),
        previous_ev_device_states=_read_previous_ev_device_states(entities),
        previous_force_on_device_ids=previous_force_on_device_ids,
        haeo_nz_plan=haeo_nz_plan,
    )
    attrs = net_zero_attrs(outputs, profiles, guard_decision)
    attrs.update(config_trace_attrs())
    attrs.update(_policy_output_contract_attrs())
    attrs.update(
        {
            'runtime_input_contract': 'raw_measurements_only',
            'net_zero_derived_source': 'internal',
            'net_zero_input_quality': derived.input_quality,
            'net_zero_input_warnings': derived.input_warnings,
            'grid_power_w': m.grid_power_w,
            'quarter_energy_balance_kwh': m.quarter_energy_balance_kwh,
            'pv_power_w': m.pv_power_w,
            'pv_power_kw': pv_power_kw,
            'remaining_quarter_s': derived.remaining_quarter_s,
            'remaining_quarter_min': derived.remaining_quarter_min,
            'rpnz_w': derived.rpnz_w,
            'required_power_w': derived.required_power_w,
            'required_power_consumption_kw': derived.required_power_consumption_kw,
            'policy_engine_trigger_mode': 'timer',
            'policy_engine_scheduler_tick_seconds': _POLICY_ENGINE_TIMER_STATE.get('scheduler_tick_seconds', 2.0),
            'policy_engine_interval_seconds': _policy_engine_interval_seconds(cfg),
            'policy_engine_last_tick_ts': _POLICY_ENGINE_TIMER_STATE.get('last_tick_ts', now_ts),
            'policy_engine_last_run_reason': trigger_reason,
            'policy_engine_ticks_seen': int(_POLICY_ENGINE_TIMER_STATE.get('ticks_seen', 0) or 0),
            'policy_engine_runs_seen': int(_POLICY_ENGINE_TIMER_STATE.get('runs_seen', 0) or 0),
            'policy_engine_skipped_ticks': int(_POLICY_ENGINE_TIMER_STATE.get('skipped_ticks', 0) or 0),
        }
    )
    device_policies_hash = _device_policies_hash(attrs)
    attrs['device_policies_hash'] = device_policies_hash
    attrs['device_policies_state_kind'] = 'content_hash'
    attrs['device_policies_version'] = device_policies_hash
    dispatch_command_attrs = _dispatch_command_attrs(attrs)
    policy_state_hash, policy_state_attrs = _policy_state_payload(entities, attrs)
    dispatch_command_hash = dispatch_command_attrs['dispatch_command_hash']
    warning_signature = _policy_warning_signature(attrs)
    canonical_changed = (
        device_policies_hash != _POLICY_ENGINE_TIMER_STATE.get('previous_device_policies_hash')
        or dispatch_command_hash != _POLICY_ENGINE_TIMER_STATE.get('previous_dispatch_command_hash')
        or policy_state_hash != _POLICY_ENGINE_TIMER_STATE.get('previous_policy_state_hash')
    )
    warning_state_changed = warning_signature != _POLICY_ENGINE_TIMER_STATE.get('previous_warning_signature')
    diagnostics_interval_seconds = _policy_engine_diagnostics_interval_seconds(cfg)
    publish_diagnostics, diagnostics_publish_reason = _should_publish_policy_diagnostics(
        now_ts,
        trigger_reason,
        diagnostics_interval_seconds,
        canonical_changed,
        warning_state_changed,
    )
    publish_started_ts = time.time()
    published_device_policies = False
    published_dispatch_command = False
    published_policy_state = False
    publish_sensor(
        entities['previous_device_state'],
        _selected_previous_device_state_for_outputs(outputs)['mode'],
        _previous_device_state_attrs_from_outputs(outputs),
    )
    publish_sensor(entities['device_policies'], device_policies_hash, attrs)
    published_device_policies = True
    publish_sensor(entities['dispatch_command'], dispatch_command_hash, dispatch_command_attrs)
    published_dispatch_command = True
    publish_sensor(entities['policy_state'], policy_state_hash, policy_state_attrs)
    published_policy_state = True
    publish_ms = int(round((time.time() - publish_started_ts) * 1000.0))
    if publish_diagnostics:
        diagnostics_attrs = dict(attrs)
        diagnostics_attrs.update(
            {
                'policy_engine_run_duration_ms': int(round((time.time() - run_started_ts) * 1000.0)),
                'policy_engine_publish_ms': publish_ms,
                'policy_engine_published_device_policies': published_device_policies,
                'policy_engine_published_dispatch_command': published_dispatch_command,
                'policy_engine_published_policy_state': published_policy_state,
                'policy_engine_published_policy_diagnostics': True,
                'policy_engine_diagnostics_publish_reason': diagnostics_publish_reason,
                'policy_engine_last_diagnostics_publish_ts': now_ts,
                'policy_engine_diagnostics_interval_seconds': diagnostics_interval_seconds,
            }
        )
        publish_sensor(entities['policy_diagnostics'], _trace_state(profiles, outputs), diagnostics_attrs)
        _POLICY_ENGINE_TIMER_STATE['last_diagnostics_publish_ts'] = now_ts
    _POLICY_ENGINE_TIMER_STATE['previous_device_policies_hash'] = device_policies_hash
    _POLICY_ENGINE_TIMER_STATE['previous_dispatch_command_hash'] = dispatch_command_hash
    _POLICY_ENGINE_TIMER_STATE['previous_policy_state_hash'] = policy_state_hash
    _POLICY_ENGINE_TIMER_STATE['previous_warning_signature'] = warning_signature


@time_trigger('period(now, 2s)')
def ems_policy_engine_tick():
    import time
    now_ts = time.time()
    _note_policy_tick(now_ts)
    if not _policy_engine_interval_elapsed_fast(now_ts):
        _note_policy_skip()
        return
    cfg, entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    _update_policy_engine_effective_intervals(cfg)
    if not _policy_engine_interval_elapsed(now_ts, _POLICY_ENGINE_TIMER_STATE['effective_interval_seconds']):
        _note_policy_skip()
        return
    _note_policy_run(now_ts)
    run_policy_loop(now_ts, cfg, entities, 'timer')


def ems_policy_engine_loop(trigger_reason='manual'):
    import time
    now_ts = time.time()
    cfg, entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    _update_policy_engine_effective_intervals(cfg)
    if str(trigger_reason) == 'timer':
        _note_policy_tick(now_ts)
    _note_policy_run(now_ts)
    run_policy_loop(now_ts, cfg, entities, trigger_reason)
