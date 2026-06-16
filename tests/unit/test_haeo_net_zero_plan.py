import pytest

from ems_core.domain.models import ControlProfile, ForecastProfile, GoalProfile, GuardProfile
from ems_core.integrations.haeo_net_zero_plan import compute_haeo_net_zero_plan
from tests.helpers import make_cfg, make_haeo, make_profiles


def _fresh_haeo(**overrides):
    data = dict(
        configured_forecast=ForecastProfile.HAEO,
        effective_forecast=ForecastProfile.HAEO,
        fresh=True,
    )
    data.update(overrides)
    return make_haeo(**data)


def _haeo_profiles(**overrides):
    data = dict(
        control=ControlProfile.HORIZON_BY_HAEO,
        goal=GoalProfile.NET_ZERO,
        forecast=ForecastProfile.NONE,
        guard=GuardProfile.NORMAL_LIMITS,
    )
    data.update(overrides)
    return make_profiles(**data)


@pytest.mark.unit
def test_ev_larger_forecast_selects_ev_primary():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(ev_min_current_a=4, ev_current_step_a=4),
        _fresh_haeo(battery_target_kw=2.0, ev_target_kw=5.0),
        now_ts=0.0,
    )

    assert plan.active is True
    assert plan.primary_load == 'EV_CHARGER'
    assert plan.adjustable_surplus_load == 'HOME_BATTERY'
    assert plan.primary_device_id == 'EV_CHARGER'
    assert plan.adjustable_device_id == 'HOME_BATTERY'
    assert plan.device_limits_w == {'HOME_BATTERY': 2000, 'EV_CHARGER': 5000}
    assert plan.reason == 'ev_forecast_larger'


@pytest.mark.unit
def test_battery_larger_forecast_selects_home_battery_primary():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(ev_min_current_a=4, ev_current_step_a=4),
        _fresh_haeo(battery_target_kw=3.0, ev_target_kw=1.5),
        now_ts=0.0,
    )

    assert plan.active is True
    assert plan.primary_load == 'HOME_BATTERY'
    assert plan.adjustable_surplus_load == 'EV_CHARGER'
    assert plan.primary_device_id == 'HOME_BATTERY'
    assert plan.adjustable_device_id == 'EV_CHARGER'
    assert plan.device_limits_w == {'HOME_BATTERY': 3000, 'EV_CHARGER': 1500}
    assert plan.battery_limit_w == 3000
    assert plan.ev_limit_w == 1500
    assert plan.ev_limit_a == 8


@pytest.mark.unit
def test_tie_keeps_previous_primary_when_available():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(),
        _fresh_haeo(battery_target_kw=2.0, ev_target_kw=2.0),
        now_ts=30.0,
        previous_quarter_key='0',
        previous_primary_load='EV_CHARGER',
    )

    assert plan.primary_load == 'EV_CHARGER'
    assert plan.adjustable_surplus_load == 'HOME_BATTERY'
    assert plan.primary_device_id == 'EV_CHARGER'
    assert plan.adjustable_device_id == 'HOME_BATTERY'
    assert plan.reason == 'tie_keep_previous'
    assert plan.changed is False


@pytest.mark.unit
def test_tie_keeps_previous_primary_device_id_when_available():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(),
        _fresh_haeo(battery_target_kw=2.0, ev_target_kw=2.0),
        now_ts=30.0,
        previous_quarter_key='0',
        previous_primary_load='HOME_BATTERY',
        previous_primary_device_id='EV_CHARGER',
    )

    assert plan.primary_device_id == 'EV_CHARGER'
    assert plan.primary_load == 'EV_CHARGER'
    assert plan.reason == 'tie_keep_previous'
    assert plan.changed is False


@pytest.mark.unit
def test_stale_forecast_disables_plan():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(),
        make_haeo(
            configured_forecast=ForecastProfile.HAEO,
            effective_forecast=ForecastProfile.NONE,
            fresh=False,
            battery_target_kw=3.0,
            ev_target_kw=1.5,
        ),
        now_ts=0.0,
    )

    assert plan.active is False
    assert plan.reason == 'forecast_not_effective'


@pytest.mark.unit
def test_wrong_guard_disables_plan():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(guard=GuardProfile.BATTERY_PROTECT),
        make_cfg(),
        _fresh_haeo(battery_target_kw=3.0, ev_target_kw=1.5),
        now_ts=0.0,
    )

    assert plan.active is False
    assert plan.reason == 'guard_not_normal_limits'


@pytest.mark.unit
def test_zero_forecast_disables_plan():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(),
        _fresh_haeo(battery_target_kw=0.0, ev_target_kw=0.0),
        now_ts=0.0,
    )

    assert plan.active is False
    assert plan.reason == 'zero_forecast'


@pytest.mark.unit
def test_limits_are_clamped_to_device_bounds():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(max_solar_charge_w=2500, ev_max_current_a=10, ev_min_current_a=4, ev_current_step_a=4),
        _fresh_haeo(battery_target_kw=6.0, ev_target_kw=9.0),
        now_ts=0.0,
    )

    assert plan.battery_limit_w == 2500
    assert plan.ev_limit_w == 2300
    assert plan.device_limits_w == {'HOME_BATTERY': 2500, 'EV_CHARGER': 2300}
    assert plan.ev_limit_a == 10
