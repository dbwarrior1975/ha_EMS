import hashlib
import json

from ems_core.domain.models import ControlProfile, GoalProfile, ForecastProfile, GuardProfile, Profiles, RuntimeMeasurements, HaeoTargets, NetZeroState, CoreConfig
from ems_core.guard.evaluator import evaluate_guard
from ems_core.net_zero.balance import compute_rpnz_w
from ems_core.net_zero.engine import compute_net_zero_engine_outputs, configured_forecast, effective_forecast
from ems_core.integrations.haeo_horizon import latest_forecast_value_at_or_before
from ems_core.integrations.haeo_net_zero_plan import compute_haeo_net_zero_plan
from ems_core.diagnostics.policy_diagnostics import net_zero_attrs
from ems_adapter.ha_adapter import get_float, get_int, get_bool, get_str, age_seconds, get_attr, parse_input_datetime_ts, publish_sensor
from ems_adapter.runtime_context import _GROUPED_CONFIG_DUAL_READ_STATUS, config_trace_attrs, read_runtime_context
_POLICY_ENGINE_BUILD = 'pyscript_ast_loop_safe_2026_06_15'


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
        quarter_energy_balance_kwh=get_float(entities['quarter_energy_balance'], 0),
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


def _dispatch_command_attrs(attrs):
    command_hash = _payload_hash({
        'surplus_device_dispatch_action': attrs.get('surplus_device_dispatch_action', ''),
        'surplus_device_dispatch_decision': attrs.get('surplus_device_dispatch_decision', ''),
        'surplus_device_dispatch_device_id': attrs.get('surplus_device_dispatch_device_id', ''),
        'surplus_device_dispatch_target': attrs.get('surplus_device_dispatch_target', ''),
        'surplus_device_targets': attrs.get('surplus_device_targets', ()),
        'surplus_freeze_until_ts': attrs.get('surplus_freeze_until_ts'),
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
        'surplus_freeze_until_ts': attrs.get('surplus_freeze_until_ts'),
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


@time_trigger('period(now, 30s)')
@state_trigger('input_select.ems_control_profile or input_select.ems_goal_profile or input_select.ems_guard_profile or input_select.ems_forecast_profile or sensor.required_power_consumption or sensor.ems_calculated_required_power_for_net_zero')
def ems_policy_engine_loop():
    import time
    now_ts = time.time()
    cfg, entities = read_runtime_context(get_bool, get_float, get_int, get_str)
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
    remaining_s = max((15 - (int(now_ts / 60) % 15)) * 60, 30)
    active_surplus_device_ids = _read_active_surplus_device_ids(entities)
    previous_device_state = _read_previous_device_state(entities)
    previous_force_on_device_ids = _read_previous_force_on_device_ids(entities)
    nz = NetZeroState(
        rpnz_w=get_float(entities['rpnz_w'], compute_rpnz_w(m.quarter_energy_balance_kwh, remaining_s)),
        required_power_consumption_kw=get_float(entities['required_power_consumption_kw'], 0),
    )
    outputs = compute_net_zero_engine_outputs(
        profiles, cfg, m, haeo, nz, now_ts,
        freeze_until_ts=parse_input_datetime_ts(entities['surplus_freeze_until']),
        ev_burn_active=_read_adjustable_surplus_active(entities),
        adjustable_surplus_active=_read_adjustable_surplus_active(entities),
        pv_power_kw=get_float(entities['pv_power_kw'], None),
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
    device_policies_hash = _device_policies_hash(attrs)
    attrs['device_policies_hash'] = device_policies_hash
    attrs['device_policies_state_kind'] = 'content_hash'
    attrs['device_policies_version'] = device_policies_hash
    dispatch_command_attrs = _dispatch_command_attrs(attrs)
    policy_state_hash, policy_state_attrs = _policy_state_payload(entities, attrs)
    publish_sensor(
        entities['previous_device_state'],
        _selected_previous_device_state_for_outputs(outputs)['mode'],
        _previous_device_state_attrs_from_outputs(outputs),
    )
    publish_sensor(entities['device_policies'], device_policies_hash, attrs)
    publish_sensor(entities['dispatch_command'], dispatch_command_attrs['dispatch_command_hash'], dispatch_command_attrs)
    publish_sensor(entities['policy_state'], policy_state_hash, policy_state_attrs)
    publish_sensor(entities['policy_diagnostics'], _trace_state(profiles, outputs), attrs)
