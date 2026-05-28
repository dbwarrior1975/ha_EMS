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


def make_m(**overrides):
    data = dict(
        now_ts=0.0,
        soc=50.0,
        min_cell_voltage_v=3.2,
        victron_heartbeat_age_s=0.0,
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
