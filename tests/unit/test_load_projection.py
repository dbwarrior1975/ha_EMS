import pytest
from ems_core.domain.models import ControlProfile, GoalProfile, ForecastProfile, GuardProfile
from ems_core.net_zero.load_projection import ev_strategy_current_a, relay_strategy_command
from tests.helpers import make_profiles, make_cfg, make_haeo


@pytest.mark.unit
def test_ev_manual_force_current_overrides():
    profiles = make_profiles(control=ControlProfile.MANUAL, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(ev_force_current_a=12, ev_max_current_a=28)
    haeo = make_haeo()
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == 12


@pytest.mark.unit
def test_ev_manual_without_force_is_skip():
    profiles = make_profiles(control=ControlProfile.MANUAL)
    cfg = make_cfg(ev_force_current_a=0)
    haeo = make_haeo()
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == -1


@pytest.mark.unit
def test_ev_manual_safe_behaves_like_manual_for_force_current():
    profiles = make_profiles(control=ControlProfile.MANUAL_SAFE)
    cfg = make_cfg(ev_force_current_a=10, ev_max_current_a=16)
    haeo = make_haeo()
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == 10


@pytest.mark.unit
def test_ev_degraded_always_skips():
    profiles = make_profiles(guard=GuardProfile.DEGRADED)
    cfg = make_cfg(ev_force_current_a=20)
    haeo = make_haeo()
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=True) == -1


@pytest.mark.unit
def test_net_zero_force_current_is_floor():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(ev_force_current_a=12, ev_max_current_a=28)
    haeo = make_haeo()
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == 12
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=True) == 28


@pytest.mark.unit
def test_cheap_charge_force_current_respected():
    profiles = make_profiles(goal=GoalProfile.CHEAP_GRID_CHARGE)
    cfg = make_cfg(ev_force_current_a=11, ev_max_current_a=16)
    haeo = make_haeo(effective_forecast=ForecastProfile.NONE)
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == 11


@pytest.mark.unit
def test_cheap_charge_default_ev_is_max_current():
    profiles = make_profiles(goal=GoalProfile.CHEAP_GRID_CHARGE)
    cfg = make_cfg(ev_force_current_a=0, ev_max_current_a=20)
    haeo = make_haeo(effective_forecast=ForecastProfile.NONE)
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == 20


@pytest.mark.unit
def test_cheap_charge_haeo_ev_target_uses_parametric_current_step():
    profiles = make_profiles(goal=GoalProfile.CHEAP_GRID_CHARGE)
    cfg = make_cfg(
        ev_force_current_a=0,
        ev_min_current_a=4,
        ev_max_current_a=28,
        ev_current_step_a=2,
        ev_charger_phases=1,
    )
    haeo = make_haeo(effective_forecast=ForecastProfile.HAEO, ev_target_kw=2.3)
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == 10


@pytest.mark.unit
def test_max_export_default_ev_is_off():
    profiles = make_profiles(goal=GoalProfile.MAX_EXPORT)
    cfg = make_cfg(ev_force_current_a=0, ev_min_current_a=4, ev_max_current_a=28)
    haeo = make_haeo(effective_forecast=ForecastProfile.NONE)
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == 0


@pytest.mark.unit
def test_max_export_force_current_ignored_and_ev_is_off():
    profiles = make_profiles(goal=GoalProfile.MAX_EXPORT)
    cfg = make_cfg(ev_force_current_a=9, ev_max_current_a=16, ev_min_current_a=4)
    haeo = make_haeo(effective_forecast=ForecastProfile.NONE)
    assert ev_strategy_current_a(profiles, cfg, haeo, burn_active=False) == 0


@pytest.mark.unit
def test_relay_manual_force_on_and_release_to_off():
    profiles = make_profiles(control=ControlProfile.MANUAL)
    assert relay_strategy_command(profiles, surplus_allowed=True, force_on=True, net_zero_active=False) == 1
    assert relay_strategy_command(profiles, surplus_allowed=True, force_on=False, net_zero_active=False) == 0


@pytest.mark.unit
def test_relay_manual_safe_force_on_and_release_to_off():
    profiles = make_profiles(control=ControlProfile.MANUAL_SAFE)
    assert relay_strategy_command(profiles, surplus_allowed=True, force_on=True, net_zero_active=False) == 1
    assert relay_strategy_command(profiles, surplus_allowed=True, force_on=False, net_zero_active=False) == 0


@pytest.mark.unit
def test_relay_degraded_skips():
    profiles = make_profiles(guard=GuardProfile.DEGRADED)
    assert relay_strategy_command(profiles, surplus_allowed=True, force_on=True, net_zero_active=False) == -1


@pytest.mark.unit
def test_relay_net_zero_force_on_overrides_allocator_state():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    assert relay_strategy_command(profiles, surplus_allowed=False, force_on=True, net_zero_active=False) == 1
    assert relay_strategy_command(profiles, surplus_allowed=False, force_on=False, net_zero_active=False) == 0


@pytest.mark.unit
def test_relay_cheap_charge_is_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.CHEAP_GRID_CHARGE)
    assert relay_strategy_command(profiles, surplus_allowed=True, force_on=False, net_zero_active=False) == 0


@pytest.mark.unit
def test_relay_max_export_is_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.MAX_EXPORT)
    assert relay_strategy_command(profiles, surplus_allowed=True, force_on=False, net_zero_active=False) == 0
