import pytest

from ems_core.net_zero.battery_controller import candidate_sp_net_zero


@pytest.mark.unit
def test_deadband_exact_threshold():
    result = candidate_sp_net_zero(
        rpnz_w=200,
        grid_actual_w=100,
        current_sp_w=300,
        deadband_w=50,
        ramp_w=1000,
        max_sp_w=3700,
    )
    assert result == 300


@pytest.mark.unit
def test_deadband_inside_threshold():
    result = candidate_sp_net_zero(
        rpnz_w=180,
        grid_actual_w=100,
        current_sp_w=300,
        deadband_w=50,
        ramp_w=1000,
        max_sp_w=3700,
    )
    assert result == 300


@pytest.mark.unit
def test_ramp_clipping_positive():
    result = candidate_sp_net_zero(
        rpnz_w=3000,
        grid_actual_w=0,
        current_sp_w=100,
        deadband_w=50,
        ramp_w=500,
        max_sp_w=3700,
    )
    assert result == 600


@pytest.mark.unit
def test_ramp_clipping_negative():
    result = candidate_sp_net_zero(
        rpnz_w=-3000,
        grid_actual_w=0,
        current_sp_w=1000,
        deadband_w=50,
        ramp_w=500,
        max_sp_w=3700,
    )
    assert result == 500


@pytest.mark.unit
def test_quantization_100w():
    result = candidate_sp_net_zero(
        rpnz_w=430,
        grid_actual_w=0,
        current_sp_w=100,
        deadband_w=50,
        ramp_w=1000,
        max_sp_w=3700,
    )
    assert result == 300


@pytest.mark.unit
def test_minimum_floor_behavior():
    result = candidate_sp_net_zero(
        rpnz_w=0,
        grid_actual_w=500,
        current_sp_w=200,
        deadband_w=50,
        ramp_w=1000,
        max_sp_w=3700,
        min_charge_floor_w=100,
    )
    assert result == 100


@pytest.mark.unit
def test_negative_import_export_transition():
    result = candidate_sp_net_zero(
        rpnz_w=-800,
        grid_actual_w=400,
        current_sp_w=200,
        deadband_w=50,
        ramp_w=1000,
        max_sp_w=3700,
    )
    assert result == -400
