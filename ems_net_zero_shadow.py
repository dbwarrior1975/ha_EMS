from ems_core.domain.models import ControlProfile, GoalProfile, ForecastProfile, GuardProfile, Profiles, EmsConfig, RuntimeMeasurements, HaeoTargets, NetZeroState
from ems_core.guard.evaluator import evaluate_guard
from ems_core.net_zero.balance import compute_rpnz_w
from ems_core.net_zero.engine import compute_net_zero_engine_outputs, configured_forecast, effective_forecast
from ems_core.integrations.haeo_horizon import latest_forecast_value_at_or_before
from ems_core.diagnostics.decision_trace import net_zero_attrs
from ems_adapter.entity_map import ENT
from ems_adapter.ha_adapter import get_float, get_int, get_bool, get_str, age_seconds, get_attr, parse_input_datetime_ts, publish_sensor


def _enum(allowed_cls, value, default):
    allowed = {v for k, v in allowed_cls.__dict__.items() if k.isupper()}
    return value if value in allowed else default


def read_config():
    return EmsConfig(
        deadband_w=get_float(ENT['deadband_w'], 50),
        ramp_max_w=get_float(ENT['ramp_max_w'], 1000),
        strict_limits_max_w=get_float(ENT['strict_limits_max_w'], 4600),
        max_solar_charge_w=get_float(ENT['max_solar_charge_w'], 3700),
        battery_protect_soc=get_float(ENT['battery_protect_soc'], 2),
        battery_protect_soc_recovery_margin=get_float(ENT['battery_protect_soc_recovery_margin'], 1),
        battery_protect_min_cell_voltage_v=get_float(ENT['battery_protect_min_cell_voltage_v'], 3.030),
        ev_min_current_a=get_int(ENT['ev_min_current_a'], 4),
        ev_max_current_a=get_int(ENT['ev_max_current_a'], 28),
        ev_charger_phases=get_int(ENT['ev_charger_phases'], 1),
        ev_force_current_a=get_int(ENT['ev_force_current_a'], 0),
        haeo_stale_timeout_s=get_float(ENT['haeo_stale_timeout_s'], 300),
        relay1_power_kw=get_float(ENT['relay1_power_kw'], 2.5),
        relay2_power_kw=get_float(ENT['relay2_power_kw'], 5.0),
        ev_priority=get_int(ENT['ev_priority'], 3),
        relay1_priority=get_int(ENT['relay1_priority'], 2),
        relay2_priority=get_int(ENT['relay2_priority'], 1),
    )
    
def read_profiles():
    return Profiles(
        control=_enum(ControlProfile, get_str(ENT['control_profile'], 'AUTOMATIC'), ControlProfile.AUTOMATIC),
        goal=_enum(GoalProfile, get_str(ENT['goal_profile'], 'NET_ZERO'), GoalProfile.NET_ZERO),
        forecast=_enum(ForecastProfile, get_str(ENT['forecast_profile'], 'NONE'), ForecastProfile.NONE),
        guard=_enum(GuardProfile, get_str(ENT['guard_profile'], 'NORMAL_LIMITS'), GuardProfile.NORMAL_LIMITS),
    )


def read_measurements(now_ts):
    return RuntimeMeasurements(
        now_ts=now_ts,
        soc=get_float(ENT['soc'], None),
        min_cell_voltage_v=get_float(ENT['min_cell_voltage_v'], None),
        victron_heartbeat_age_s=age_seconds(ENT['victron_heartbeat'], now_ts),
        grid_power_w=get_float(ENT['grid_power_w'], 0),
        current_battery_setpoint_w=get_float(ENT['current_battery_sp'], 100),
        hourly_energy_balance_kwh=get_float(ENT['hourly_energy_balance'], 0),
        charger_on=get_bool(ENT['charger_control']),
        charger_current_a=get_int(ENT['charger_current'], 4),
        relay1_on=get_bool(ENT['relay1']),
        relay2_on=get_bool(ENT['relay2']),
    )


def read_haeo(now_ts, profiles, cfg):
    configured = configured_forecast(profiles.control, profiles.forecast)
    batt_age = age_seconds(ENT['haeo_battery_active_power_fresh_source'], now_ts)
    ev_age = age_seconds(ENT['haeo_ev_active_power_fresh_source'], now_ts)
    fresh = batt_age < cfg.haeo_stale_timeout_s and ev_age < cfg.haeo_stale_timeout_s
    eff = effective_forecast(configured, fresh)
    batt_forecast = get_attr(ENT['haeo_battery_power_active'], 'forecast', []) or []
    ev_forecast = get_attr(ENT['haeo_ev_battery_power_active'], 'forecast', []) or []
    return HaeoTargets(
        effective_forecast=eff,
        configured_forecast=configured,
        fresh=fresh,
        battery_target_kw=latest_forecast_value_at_or_before(batt_forecast, now_ts, 0),
        ev_target_kw=max(latest_forecast_value_at_or_before(ev_forecast, now_ts, 0), 0),
    )


def _trace_state(profiles, outputs):
    return f"{profiles.control}/{profiles.goal}/{profiles.guard}/{outputs.effective_forecast}"


@time_trigger('period(now, 30s)')
@state_trigger('input_select.ems_control_profile or input_select.ems_goal_profile or input_select.ems_guard_profile or input_select.ems_forecast_profile or sensor.required_power_consumption or sensor.ems_calculated_required_power_for_net_zero')
def ems_net_zero_shadow_loop():
    import time
    now_ts = time.time()
    cfg = read_config()
    profiles = read_profiles()
    m = read_measurements(now_ts)
    guard_decision = evaluate_guard(profiles.guard, m, cfg)
    profiles = Profiles(profiles.control, profiles.goal, profiles.forecast, guard_decision.guard)
    haeo = read_haeo(now_ts, profiles, cfg)
    remaining_s = max((15 - (int(now_ts / 60) % 15)) * 60, 30)
    nz = NetZeroState(
        rpnz_w=get_float(ENT['rpnz_w'], compute_rpnz_w(m.hourly_energy_balance_kwh, remaining_s)),
        required_power_consumption_kw=get_float(ENT['required_power_consumption_kw'], 0),
    )
    outputs = compute_net_zero_engine_outputs(
        profiles, cfg, m, haeo, nz, now_ts,
        freeze_until_ts=parse_input_datetime_ts(ENT['surplus_freeze_until']),
        ev_burn_active=get_bool(ENT['surplus_ev_active']),
        relay1_enabled_import_zero=get_bool(ENT['relay1_enabled_import_zero']),
        relay2_enabled_import_zero=get_bool(ENT['relay2_enabled_import_zero']),
        relay1_force_on=get_bool(ENT['relay1_force_on']),
        relay2_force_on=get_bool(ENT['relay2_force_on']),
        relay1_net_zero_active=get_bool(ENT['surplus_r1_active']),
        relay2_net_zero_active=get_bool(ENT['surplus_r2_active']),
    )
    attrs = net_zero_attrs(outputs, profiles, guard_decision)
    publish_sensor(ENT['policy_battery_target_w'], outputs.battery_target_w, attrs)
    publish_sensor(ENT['policy_ev_current_a'], outputs.ev_current_a, attrs)
    publish_sensor(ENT['policy_relay1_command'], outputs.relay1_command, attrs)
    publish_sensor(ENT['policy_relay2_command'], outputs.relay2_command, attrs)
    publish_sensor(ENT['policy_decision_trace'], _trace_state(profiles, outputs), attrs)
    publish_sensor(ENT['surplus_policy_active_pys'], 'on' if outputs.surplus_policy_active else 'off', attrs)
    publish_sensor(ENT['surplus_next_target_pys'], outputs.surplus_next_target, attrs)
    publish_sensor(ENT['surplus_next_threshold_pys'], outputs.surplus_next_threshold_kw, attrs)
    publish_sensor(ENT['surplus_release_candidate_pys'], outputs.surplus_release_candidate, attrs)
    publish_sensor(ENT['surplus_explanation_pys'], outputs.surplus_explanation, attrs)
    publish_sensor(ENT['surplus_dispatch_decision_pys'], outputs.surplus_dispatch_decision, attrs)
