import pytest

from ems_core.domain.ev_power import (
    ev_current_a_to_power_w,
    ev_max_power_w,
    ev_min_power_w,
    ev_power_step_w,
    ev_power_w_to_selector_current_a,
)
from tests.helpers import make_cfg


@pytest.mark.unit
def test_ev_current_to_power_uses_phase_voltage_and_phase_count():
    assert ev_current_a_to_power_w(10, phases=1) == 2300
    assert ev_current_a_to_power_w(10, phases=3) == 6900


@pytest.mark.unit
def test_ev_config_power_bounds_are_watt_based():
    cfg = make_cfg(
        ev_min_current_a=6,
        ev_max_current_a=16,
        ev_current_step_a=4,
        ev_charger_phases=3,
    )

    assert ev_min_power_w(cfg) == 4140
    assert ev_max_power_w(cfg) == 11040
    assert ev_power_step_w(cfg) == 2760


@pytest.mark.unit
def test_ev_power_step_falls_back_to_one_amp():
    cfg = make_cfg(ev_current_step_a=0, ev_charger_phases=1)

    assert ev_power_step_w(cfg) == 230


@pytest.mark.unit
def test_ev_power_to_selector_current_supports_one_amp_step():
    assert ev_power_w_to_selector_current_a(
        2300,
        phases=1,
        max_a=28,
        min_a=4,
        step_a=1,
    ) == 10


@pytest.mark.unit
def test_ev_power_to_selector_current_supports_four_amp_step():
    assert ev_power_w_to_selector_current_a(
        2300,
        phases=1,
        max_a=28,
        min_a=4,
        step_a=4,
    ) == 8


@pytest.mark.unit
def test_ev_power_to_selector_current_keeps_explicit_max_candidate():
    assert ev_power_w_to_selector_current_a(
        6440,
        phases=1,
        max_a=28,
        min_a=6,
        step_a=4,
    ) == 28
