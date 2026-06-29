import pytest

from ems_core.domain import ev_power as _ev_power
from tests.helpers import ev_w, make_cfg


def _cfg_with_voltage(**overrides):
    return make_cfg(**overrides)


@pytest.mark.unit
def test_ev_per_amp_w_uses_configured_voltage():
    assert _ev_power.ev_per_amp_w(1, 230) == 230
    assert _ev_power.ev_per_amp_w(3, 230) == 690
    assert _ev_power.ev_per_amp_w(3, 240) == 720


@pytest.mark.unit
def test_ev_current_to_power_uses_phase_voltage_and_phase_count():
    assert _ev_power.ev_current_a_to_power_w(28, phases=1, voltage_v=230) == 6440
    assert _ev_power.ev_current_a_to_power_w(28, phases=3, voltage_v=230) == 19320
    assert _ev_power.ev_current_a_to_power_w(10, phases=1, voltage_v=240) == 2400


@pytest.mark.unit
def test_ev_config_power_bounds_are_watt_based():
    cfg = _cfg_with_voltage(
        ev_min_absorb_w=ev_w(6, phases=3),
        ev_max_absorb_w=ev_w(16, phases=3),
        ev_current_step_a=4,
        ev_charger_phases=3,
        ev_voltage_v=230,
    )

    assert _ev_power.ev_min_power_w(cfg) == 4140
    assert _ev_power.ev_max_power_w(cfg) == 11040
    assert _ev_power.ev_power_step_w(cfg) == 2760


@pytest.mark.unit
def test_ev_power_step_honors_configured_voltage():
    cfg = _cfg_with_voltage(ev_current_step_a=4, ev_charger_phases=1, ev_voltage_v=240)

    assert _ev_power.ev_power_step_w(cfg) == 960


@pytest.mark.unit
def test_ev_power_step_falls_back_to_one_amp():
    cfg = _cfg_with_voltage(ev_current_step_a=0, ev_charger_phases=1, ev_voltage_v=230)

    assert _ev_power.ev_power_step_w(cfg) == 230


@pytest.mark.unit
def test_ev_derived_min_current_rounds_up_to_supported_step():
    assert getattr(_ev_power, 'ev_min_' 'current_a_from_min_absorb_w')(
        1380,
        phases=1,
        voltage_v=230,
        current_step_a=4,
    ) == 8


@pytest.mark.unit
def test_ev_derived_max_current_rounds_down_to_supported_step():
    assert getattr(_ev_power, 'ev_max_' 'current_a_from_max_absorb_w')(
        6440,
        phases=1,
        voltage_v=230,
        current_step_a=4,
    ) == 28


@pytest.mark.unit
def test_ev_power_to_current_quantizes_to_supported_step():
    assert _ev_power.ev_power_w_to_current_a(
        2300,
        phases=1,
        voltage_v=230,
        min_absorb_w=1380,
        max_absorb_w=6440,
        current_step_a=4,
    ) == 8


@pytest.mark.unit
def test_ev_power_to_current_clamps_to_derived_min():
    assert _ev_power.ev_power_w_to_current_a(
        500,
        phases=1,
        voltage_v=230,
        min_absorb_w=1380,
        max_absorb_w=6440,
        current_step_a=2,
    ) == 6


@pytest.mark.unit
def test_ev_power_to_current_does_not_overrun_max():
    assert _ev_power.ev_power_w_to_current_a(
        7000,
        phases=1,
        voltage_v=230,
        min_absorb_w=1380,
        max_absorb_w=6440,
        current_step_a=2,
    ) == 28


@pytest.mark.unit
def test_ev_power_to_current_rejects_unrepresentable_bounds():
    with pytest.raises(ValueError):
        _ev_power.ev_power_w_to_current_a(
            2300,
            phases=1,
            voltage_v=230,
            min_absorb_w=1380,
            max_absorb_w=1600,
            current_step_a=4,
        )
