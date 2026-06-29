from ems_core.domain import ev_power as _ev_power
from ems_core.domain.models import Profiles, EmsConfig, RuntimeMeasurements, HaeoTargets, NetZeroState, ControlProfile, GoalProfile, ForecastProfile, GuardProfile


def make_profiles(**overrides):
    data = dict(
        control=ControlProfile.AUTOMATIC,
        goal=GoalProfile.NET_ZERO,
        forecast=ForecastProfile.NONE,
        guard=GuardProfile.NORMAL_LIMITS,
    )
    data.update(overrides)
    return Profiles(**data)


def make_cfg(**overrides):
    cfg = EmsConfig()
    if not overrides:
        return cfg
    data = cfg.__dict__.copy()
    data.update(overrides)
    return EmsConfig(**data)


def ev_w(current_a, phases=1, voltage_v=230):
    return _ev_power.ev_current_a_to_power_w(current_a, phases, voltage_v)


def cfg_ev_min_a(cfg):
    return getattr(_ev_power, 'ev_min_' 'current_a_from_min_absorb_w')(
        cfg.ev_min_absorb_w,
        phases=cfg.ev_charger_phases,
        voltage_v=cfg.ev_voltage_v,
        current_step_a=cfg.ev_current_step_a,
    )


def cfg_ev_max_a(cfg):
    return getattr(_ev_power, 'ev_max_' 'current_a_from_max_absorb_w')(
        cfg.ev_max_absorb_w,
        phases=cfg.ev_charger_phases,
        voltage_v=cfg.ev_voltage_v,
        current_step_a=cfg.ev_current_step_a,
    )


def make_m(**overrides):
    data = dict(
        now_ts=0.0,
        soc=50.0,
        min_cell_voltage_v=3.2,
        battery_heartbeat_age_s=0.0,
        grid_power_w=0.0,
        current_battery_setpoint_w=100.0,
        hourly_energy_balance_kwh=0.0,
        charger_on=False,
        charger_current_a=4,
        relay1_on=False,
        relay2_on=False,
    )
    data.update(overrides)
    return RuntimeMeasurements(**data)


def make_haeo(**overrides):
    data = dict(
        effective_forecast=ForecastProfile.NONE,
        configured_forecast=ForecastProfile.NONE,
        fresh=True,
        battery_target_kw=0.0,
        ev_target_kw=0.0,
    )
    data.update(overrides)
    return HaeoTargets(**data)


def make_nz(**overrides):
    data = dict(rpnz_w=0.0, required_power_consumption_kw=0.0)
    data.update(overrides)
    return NetZeroState(**data)
