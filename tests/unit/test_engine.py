import pytest
from ems_core.domain.models import ControlProfile, GoalProfile, GuardProfile, DominantLimitation, ForecastProfile
from ems_core.net_zero.engine import compute_net_zero_engine_outputs
from tests.helpers import make_profiles, make_cfg, make_m, make_haeo, make_nz


@pytest.mark.unit
def test_engine_manual_disables_battery_write_and_keeps_current_battery_setpoint():
    profiles = make_profiles(control=ControlProfile.MANUAL, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=650)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == 650
    assert out.battery_write_enabled is False
    assert out.dominant_limitation == DominantLimitation.USER_MANUAL_OVERRIDE


@pytest.mark.unit
def test_engine_manual_safe_without_guard_clamp_keeps_current_and_write_disabled():
    profiles = make_profiles(control=ControlProfile.MANUAL_SAFE, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=444)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == 444
    assert out.battery_write_enabled is False


@pytest.mark.unit
def test_engine_manual_safe_clamps_in_battery_protect():
    profiles = make_profiles(control=ControlProfile.MANUAL_SAFE, guard=GuardProfile.BATTERY_PROTECT)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=-500)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == 0
    assert out.battery_write_enabled is True


@pytest.mark.unit
def test_engine_respects_max_solar_charge_limit_in_net_zero():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(max_solar_charge_w=500, deadband_w=0, ramp_max_w=5000)
    m = make_m(grid_power_w=-3000, current_battery_setpoint_w=0)
    nz = make_nz(rpnz_w=2500)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w <= 500
    assert out.battery_write_enabled is True


@pytest.mark.unit
def test_engine_trace_attrs_contain_authority_flag():
    profiles = make_profiles(control=ControlProfile.MANUAL)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=100)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.attrs['battery_write_enabled'] is False


@pytest.mark.unit
def test_engine_cheap_grid_charge_local_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.CHEAP_GRID_CHARGE, forecast=ForecastProfile.NONE)
    cfg = make_cfg()
    m = make_m()
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == 100
    assert out.explanation == 'Local cheap-charge policy'


@pytest.mark.unit
def test_engine_cheap_grid_charge_haeo_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.CHEAP_GRID_CHARGE, forecast=ForecastProfile.HAEO)
    cfg = make_cfg()
    m = make_m()
    haeo = make_haeo(
        effective_forecast=ForecastProfile.HAEO,
        configured_forecast=ForecastProfile.HAEO,
        fresh=True,
        battery_target_kw=1.234,
    )
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, haeo, make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == 1234
    assert out.explanation == 'Cheap charge policy with HAEO forecast assistance'


@pytest.mark.unit
def test_engine_max_export_local_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.MAX_EXPORT, forecast=ForecastProfile.NONE)
    cfg = make_cfg()
    m = make_m()
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == -4000
    assert out.explanation == 'Local export-oriented policy'


@pytest.mark.unit
def test_engine_max_export_haeo_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.MAX_EXPORT, forecast=ForecastProfile.HAEO)
    cfg = make_cfg()
    m = make_m()
    haeo = make_haeo(
        effective_forecast=ForecastProfile.HAEO,
        configured_forecast=ForecastProfile.HAEO,
        fresh=True,
        battery_target_kw=-2.5,
    )
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, haeo, make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == -2500
    assert out.explanation == 'Export-oriented policy with HAEO forecast assistance'


@pytest.mark.unit
def test_engine_force_rising_edge_sets_freeze_and_blocks_immediate_activation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30)
    m = make_m()
    nz = make_nz(rpnz_w=1000, required_power_consumption_kw=10.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 100.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=True,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        prev_relay1_force_on=False,
        prev_relay2_force_on=False,
    )

    assert out.attrs['surplus_freeze_until_ts'] == 130.0
    assert out.surplus_dispatch_decision == 'NOOP'


@pytest.mark.unit
def test_engine_force_without_rising_edge_allows_activation_without_new_freeze():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30)
    m = make_m()
    nz = make_nz(rpnz_w=1000, required_power_consumption_kw=10.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 100.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=True,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        prev_relay1_force_on=True,
        prev_relay2_force_on=False,
    )

    assert out.attrs['surplus_freeze_until_ts'] == 130.0
    assert out.surplus_dispatch_decision == 'ACTIVATE_EV'
