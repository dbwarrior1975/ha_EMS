from ems_core.domain.models import ControlProfile, GoalProfile, ForecastProfile, GuardProfile, Profiles, EmsConfig, RuntimeMeasurements, HaeoTargets, NetZeroState, CoreConfig
from ems_core.guard.evaluator import evaluate_guard
from ems_core.net_zero.balance import compute_rpnz_w
from ems_core.net_zero.engine import compute_net_zero_engine_outputs, configured_forecast, effective_forecast
from ems_core.integrations.haeo_horizon import latest_forecast_value_at_or_before
from ems_core.integrations.haeo_net_zero_plan import compute_haeo_net_zero_plan
from ems_core.diagnostics.decision_trace import net_zero_attrs
from ems_adapter.config_loader import (
    build_ems_config_from_core_config,
)
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
    }


def read_core_config():
    cfg, _entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    return cfg


def read_config():
    return build_ems_config_from_core_config(read_core_config())


def _read_compat_config():
    # Parity helper exposes the current grouped-config-backed scalar view.
    return read_config()
    
def read_profiles(entities):
    return Profiles(
        control=_enum(ControlProfile, get_str(entities['control_profile'], 'AUTOMATIC'), ControlProfile.AUTOMATIC),
        goal=_enum(GoalProfile, get_str(entities['goal_profile'], 'NET_ZERO'), GoalProfile.NET_ZERO),
        forecast=_enum(ForecastProfile, get_str(entities['forecast_profile'], 'NONE'), ForecastProfile.NONE),
        guard=_enum(GuardProfile, get_str(entities['guard_profile'], 'NORMAL_LIMITS'), GuardProfile.NORMAL_LIMITS),
    )


def read_measurements(now_ts, entities):
    return RuntimeMeasurements(
        now_ts=now_ts,
        soc=get_float(entities['soc'], None),
        min_cell_voltage_v=get_float(entities['min_cell_voltage_v'], None),
        battery_heartbeat_age_s=age_seconds(entities['battery_heartbeat'], now_ts),
        grid_power_w=get_float(entities['grid_power_w'], 0),
        current_battery_setpoint_w=get_float(entities['current_battery_sp'], 100),
        hourly_energy_balance_kwh=get_float(entities['hourly_energy_balance'], 0),
        charger_on=get_bool(entities['charger_control']),
        charger_current_a=get_int(entities['charger_current'], 4),
        relay1_on=get_bool(entities['relay1']),
        relay2_on=get_bool(entities['relay2']),
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
    mode = get_attr(entities['previous_device_state'], 'mode', '')
    if mode:
        return {
            'device_id': get_attr(entities['previous_device_state'], 'device_id', ''),
            'mode': mode,
            'low_pv_cycles': get_attr(entities['previous_device_state'], 'low_pv_cycles', 0),
            'hard_off_release_ready_cycles': get_attr(entities['previous_device_state'], 'hard_off_release_ready_cycles', 0),
            'hard_off_active': get_attr(entities['previous_device_state'], 'hard_off_active', False),
        }

    return {
        'device_id': '',
        'mode': '',
        'low_pv_cycles': 0,
        'hard_off_release_ready_cycles': 0,
        'hard_off_active': False,
    }


def _read_adjustable_surplus_active(entities):
    active_device_ids = _read_active_surplus_device_ids(entities)
    for device_id in ('EV_CHARGER', 'HOME_BATTERY'):
        if device_id in active_device_ids:
            return True
    return False


@time_trigger('period(now, 30s)')
@state_trigger('input_select.ems_control_profile or input_select.ems_goal_profile or input_select.ems_guard_profile or input_select.ems_forecast_profile or sensor.required_power_consumption or sensor.ems_calculated_required_power_for_net_zero')
def ems_policy_engine_loop():
    import time
    now_ts = time.time()
    cfg, entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    profiles = read_profiles(entities)
    m = read_measurements(now_ts, entities)
    guard_decision = evaluate_guard(profiles.guard, m, cfg)
    profiles = Profiles(profiles.control, profiles.goal, profiles.forecast, guard_decision.guard)
    haeo = read_haeo(now_ts, profiles, cfg, entities)
    haeo_nz_plan = compute_haeo_net_zero_plan(
        profiles,
        cfg,
        haeo,
        now_ts,
        previous_quarter_key=get_attr(entities['policy_decision_trace'], 'haeo_nz_quarter_key', ''),
        previous_primary_load='',
        previous_primary_device_id=get_attr(
            entities['policy_decision_trace'],
            'haeo_nz_primary_device_id',
            '',
        ),
    )
    remaining_s = max((15 - (int(now_ts / 60) % 15)) * 60, 30)
    active_surplus_device_ids = _read_active_surplus_device_ids(entities)
    previous_device_state = _read_previous_device_state(entities)
    nz = NetZeroState(
        rpnz_w=get_float(entities['rpnz_w'], compute_rpnz_w(m.hourly_energy_balance_kwh, remaining_s)),
        required_power_consumption_kw=get_float(entities['required_power_consumption_kw'], 0),
    )
    outputs = compute_net_zero_engine_outputs(
        profiles, cfg, m, haeo, nz, now_ts,
        freeze_until_ts=parse_input_datetime_ts(entities['surplus_freeze_until']),
        ev_burn_active=_read_adjustable_surplus_active(entities),
        relay1_surplus_allowed=get_bool(entities['relay1_surplus_allowed']),
        relay2_surplus_allowed=get_bool(entities['relay2_surplus_allowed']),
        relay1_force_on=get_bool(entities['relay1_force_on']),
        relay2_force_on=get_bool(entities['relay2_force_on']),
        relay1_net_zero_active='RELAY1' in active_surplus_device_ids,
        relay2_net_zero_active='RELAY2' in active_surplus_device_ids,
        adjustable_surplus_active=_read_adjustable_surplus_active(entities),
        pv_power_kw=get_float(entities['pv_power_kw'], None),
        ev_hard_off_active=bool(previous_device_state['hard_off_active']),
        ev_low_pv_cycles=previous_device_state['low_pv_cycles'],
        ev_hard_off_release_ready_cycles=previous_device_state['hard_off_release_ready_cycles'],
        prev_relay1_force_on=get_attr(entities['policy_decision_trace'], 'prev_relay1_force_on', False),
        prev_relay2_force_on=get_attr(entities['policy_decision_trace'], 'prev_relay2_force_on', False),
        haeo_nz_plan=haeo_nz_plan,
    )
    attrs = net_zero_attrs(outputs, profiles, guard_decision)
    attrs.update(config_trace_attrs())
    attrs.update(_policy_output_contract_attrs())
    publish_sensor(
        entities['previous_device_state'],
        outputs.attrs.get('ev_policy_mode', ''),
        {
            'device_id': get_str(entities['adjustable_surplus_load'], 'EV_CHARGER'),
            'mode': outputs.attrs.get('ev_policy_mode', ''),
            'low_pv_cycles': outputs.attrs.get('ev_low_pv_cycles', 0),
            'hard_off_active': outputs.attrs.get('ev_hard_off_active', False),
            'hard_off_release_ready_cycles': outputs.attrs.get('ev_hard_off_release_ready_cycles', 0),
        },
    )
    publish_sensor(entities['device_policies'], len(attrs.get('device_policies', ())), attrs)
    publish_sensor(entities['policy_decision_trace'], _trace_state(profiles, outputs), attrs)
    publish_sensor(entities['surplus_policy_active_pys'], 'on' if outputs.surplus_policy_active else 'off', attrs)
    publish_sensor(entities['surplus_next_target_pys'], outputs.surplus_next_target, attrs)
    publish_sensor(entities['surplus_next_threshold_pys'], outputs.surplus_next_threshold_kw, attrs)
    publish_sensor(entities['surplus_release_candidate_pys'], outputs.surplus_release_candidate, attrs)
    publish_sensor(entities['surplus_explanation_pys'], outputs.surplus_explanation, attrs)
