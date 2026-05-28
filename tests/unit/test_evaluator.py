import pytest
from ems_core.guard.evaluator import evaluate_guard
from ems_core.domain.models import GuardProfile
from tests.helpers import make_cfg, make_m


@pytest.mark.unit
def test_strict_limits_is_never_overridden():
    cfg = make_cfg()
    m = make_m()
    dec = evaluate_guard(GuardProfile.STRICT_LIMITS, m, cfg)
    assert dec.guard == GuardProfile.STRICT_LIMITS
    assert 'STRICT_LIMITS' in dec.reason


@pytest.mark.unit
def test_stale_or_invalid_soc_enters_degraded():
    cfg = make_cfg(victron_heartbeat_timeout_s=10)
    m = make_m(victron_heartbeat_age_s=999)
    dec = evaluate_guard(GuardProfile.NORMAL_LIMITS, m, cfg)
    assert dec.guard == GuardProfile.DEGRADED
    assert dec.soc_stale is True


@pytest.mark.unit
def test_low_soc_enters_battery_protect():
    cfg = make_cfg(battery_protect_soc=2.0)
    m = make_m(soc=1.5, min_cell_voltage_v=3.2)
    dec = evaluate_guard(GuardProfile.NORMAL_LIMITS, m, cfg)
    assert dec.guard == GuardProfile.BATTERY_PROTECT
    assert 'SOC below threshold' in dec.reason


@pytest.mark.unit
def test_low_min_cell_enters_battery_protect():
    cfg = make_cfg(battery_protect_min_cell_voltage_v=3.03)
    m = make_m(soc=50.0, min_cell_voltage_v=3.02)
    dec = evaluate_guard(GuardProfile.NORMAL_LIMITS, m, cfg)
    assert dec.guard == GuardProfile.BATTERY_PROTECT
    assert 'minimum cell voltage below threshold' in dec.reason


@pytest.mark.unit
def test_both_low_mentions_both_thresholds():
    cfg = make_cfg(battery_protect_soc=2.0, battery_protect_min_cell_voltage_v=3.03)
    m = make_m(soc=1.0, min_cell_voltage_v=3.02)
    dec = evaluate_guard(GuardProfile.NORMAL_LIMITS, m, cfg)
    assert dec.guard == GuardProfile.BATTERY_PROTECT
    assert 'SOC and minimum cell voltage below thresholds' in dec.reason


@pytest.mark.unit
def test_recovery_requires_both_soc_margin_and_min_cell_recovery():
    cfg = make_cfg(battery_protect_soc=1.0, battery_protect_soc_recovery_margin=1.0, battery_protect_min_cell_voltage_v=3.03)

    still_low_soc = make_m(soc=1.5, min_cell_voltage_v=3.05)
    dec1 = evaluate_guard(GuardProfile.BATTERY_PROTECT, still_low_soc, cfg)
    assert dec1.guard == GuardProfile.BATTERY_PROTECT

    still_low_cell = make_m(soc=2.0, min_cell_voltage_v=3.02)
    dec2 = evaluate_guard(GuardProfile.BATTERY_PROTECT, still_low_cell, cfg)
    assert dec2.guard == GuardProfile.BATTERY_PROTECT

    recovered = make_m(soc=2.0, min_cell_voltage_v=3.03)
    dec3 = evaluate_guard(GuardProfile.BATTERY_PROTECT, recovered, cfg)
    assert dec3.guard == GuardProfile.NORMAL_LIMITS
    assert 'Guard recovered' in dec3.reason
