import pytest
from types import SimpleNamespace
from ems_core.domain.models import ControlProfile, GoalProfile, ForecastProfile, GuardProfile
from ems_core.net_zero.load_projection import ev_strategy_target_w, relay_strategy_command
from tests.helpers import ev_w, make_profiles, make_cfg, make_haeo


def _ev_context(*, force_on=False, min_absorb_w=0.0, max_absorb_w=0.0):
    return SimpleNamespace(
        device_id='EV_CHARGER',
        force_on=bool(force_on),
        min_absorb_w=float(min_absorb_w),
        max_absorb_w=float(max_absorb_w),
    )


@pytest.mark.unit
def test_ev_manual_force_on_returns_max_power():
    profiles = make_profiles(control=ControlProfile.MANUAL, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(ev_force_on=True, ev_max_absorb_w=ev_w(28))
    haeo = make_haeo()
    assert ev_strategy_target_w(profiles, _ev_context(force_on=True, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=False) == 6440


@pytest.mark.unit
def test_ev_manual_without_force_is_off():
    profiles = make_profiles(control=ControlProfile.MANUAL)
    cfg = make_cfg(ev_force_on=False)
    haeo = make_haeo()
    assert ev_strategy_target_w(profiles, _ev_context(force_on=False, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=False) == 0


@pytest.mark.unit
def test_ev_manual_safe_behaves_like_manual_for_force_on():
    profiles = make_profiles(control=ControlProfile.MANUAL_SAFE)
    cfg = make_cfg(ev_force_on=True, ev_max_absorb_w=ev_w(16))
    haeo = make_haeo()
    assert ev_strategy_target_w(profiles, _ev_context(force_on=True, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=False) == 3680


@pytest.mark.unit
def test_ev_degraded_always_skips():
    profiles = make_profiles(guard=GuardProfile.DEGRADED)
    cfg = make_cfg(ev_force_on=True, ev_max_absorb_w=ev_w(20))
    haeo = make_haeo()
    assert ev_strategy_target_w(profiles, _ev_context(force_on=True, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=True) == 0


@pytest.mark.unit
def test_net_zero_force_on_overrides_to_max_power():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(ev_force_on=True, ev_max_absorb_w=ev_w(28))
    haeo = make_haeo()
    context = _ev_context(force_on=True, max_absorb_w=cfg.ev_max_absorb_w)
    assert ev_strategy_target_w(profiles, context, haeo, burn_active=False) == 6440
    assert ev_strategy_target_w(profiles, context, haeo, burn_active=True) == 6440


@pytest.mark.unit
def test_net_zero_burn_active_returns_capability_max_power():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = SimpleNamespace(
        force_on=False,
        max_absorb_w=5000,
        min_absorb_w=0,
    )
    haeo = make_haeo()
    assert ev_strategy_target_w(profiles, cfg, haeo, burn_active=True) == 5000


@pytest.mark.unit
def test_cheap_charge_force_on_uses_max_power():
    profiles = make_profiles(goal=GoalProfile.CHEAP_GRID_CHARGE)
    cfg = make_cfg(ev_force_on=True, ev_max_absorb_w=ev_w(16))
    haeo = make_haeo(effective_forecast=ForecastProfile.NONE)
    assert ev_strategy_target_w(profiles, _ev_context(force_on=True, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=False) == 3680


@pytest.mark.unit
def test_cheap_charge_default_ev_is_max_power():
    profiles = make_profiles(goal=GoalProfile.CHEAP_GRID_CHARGE)
    cfg = make_cfg(ev_force_on=False, ev_max_absorb_w=ev_w(20))
    haeo = make_haeo(effective_forecast=ForecastProfile.NONE)
    assert ev_strategy_target_w(profiles, _ev_context(force_on=False, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=False) == 4600


@pytest.mark.unit
def test_cheap_charge_haeo_ev_target_returns_watt_target():
    profiles = make_profiles(goal=GoalProfile.CHEAP_GRID_CHARGE)
    cfg = make_cfg(
        ev_force_on=False,
        ev_min_absorb_w=ev_w(4),
        ev_max_absorb_w=ev_w(28),
        ev_current_step_a=2,
        ev_charger_phases=1,
    )
    haeo = make_haeo(effective_forecast=ForecastProfile.HAEO, ev_target_kw=2.3)
    assert ev_strategy_target_w(profiles, _ev_context(force_on=False, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=False) == 2300


@pytest.mark.unit
def test_max_export_default_ev_is_off():
    profiles = make_profiles(goal=GoalProfile.MAX_EXPORT)
    cfg = make_cfg(ev_force_on=False, ev_min_absorb_w=ev_w(4), ev_max_absorb_w=ev_w(28))
    haeo = make_haeo(effective_forecast=ForecastProfile.NONE)
    assert ev_strategy_target_w(profiles, _ev_context(force_on=False, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=False) == 0


@pytest.mark.unit
def test_max_export_force_on_overrides_to_max_power():
    profiles = make_profiles(goal=GoalProfile.MAX_EXPORT)
    cfg = make_cfg(ev_force_on=True, ev_max_absorb_w=ev_w(16), ev_min_absorb_w=ev_w(4))
    haeo = make_haeo(effective_forecast=ForecastProfile.NONE)
    assert ev_strategy_target_w(profiles, _ev_context(force_on=True, max_absorb_w=cfg.ev_max_absorb_w), haeo, burn_active=False) == 3680


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
