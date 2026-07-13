from datetime import datetime

import pytest

from ems_core.net_zero.derived_inputs import (
    compute_required_power_w,
    compute_rpnz_w,
    control_horizon_s,
    derive_net_zero_inputs,
    seconds_until_next_quarter,
)


@pytest.mark.unit
def test_zero_balance_at_quarter_start_produces_zero_rpnz():
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=0.0,
        grid_power_w=0.0,
        now_ts=datetime(2026, 1, 1, 12, 0, 0),
    )
    assert derived.rpnz_w == 0


@pytest.mark.unit
def test_negative_balance_with_900_seconds_remaining_produces_positive_rpnz():
    assert compute_rpnz_w(quarter_energy_balance_kwh=-0.25, remaining_s=900.0) == 1000


@pytest.mark.unit
def test_positive_balance_with_900_seconds_remaining_produces_negative_rpnz():
    assert compute_rpnz_w(quarter_energy_balance_kwh=0.25, remaining_s=900.0) == -1000


@pytest.mark.unit
def test_rpnz_remaining_seconds_clamps_to_30_seconds():
    assert compute_rpnz_w(quarter_energy_balance_kwh=-0.01, remaining_s=1.0) == 1200


@pytest.mark.unit
def test_control_horizon_uses_exact_seconds_until_final_30_second_floor():
    assert control_horizon_s(146.0) == 146.0
    assert control_horizon_s(30.0) == 30.0
    assert control_horizon_s(1.0) == 30.0


@pytest.mark.unit
def test_required_power_formula_uses_exact_remaining_seconds():
    now_ts = datetime(2026, 1, 1, 12, 10, 45)
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=-0.2,
        grid_power_w=3000.0,
        now_ts=now_ts,
    )
    assert derived.remaining_quarter_s == 255.0
    assert derived.remaining_quarter_min == 4.25
    assert derived.control_horizon_s == 255.0
    assert derived.rpnz_w == 2824
    assert derived.required_power_w == -176
    assert derived.required_power_consumption_kw == -0.176


@pytest.mark.unit
def test_required_power_user_example_uses_146_second_horizon():
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=-0.068,
        grid_power_w=-450.0,
        now_ts=datetime(2026, 1, 1, 19, 57, 34),
    )
    assert derived.remaining_quarter_s == 146.0
    assert derived.remaining_quarter_min == pytest.approx(146.0 / 60.0)
    assert derived.rpnz_w == 1677
    assert derived.required_power_w == 2127
    assert derived.required_power_consumption_kw == 2.127


@pytest.mark.unit
def test_required_power_has_no_whole_minute_boundary_jump():
    before = derive_net_zero_inputs(
        quarter_energy_balance_kwh=-0.068,
        grid_power_w=-450.0,
        now_ts=datetime(2026, 1, 1, 19, 57, 59),
    )
    after = derive_net_zero_inputs(
        quarter_energy_balance_kwh=-0.068,
        grid_power_w=-450.0,
        now_ts=datetime(2026, 1, 1, 19, 58, 0),
    )
    assert before.remaining_quarter_s == 121.0
    assert after.remaining_quarter_s == 120.0
    assert before.required_power_w == 2473
    assert after.required_power_w == 2490
    assert after.required_power_w - before.required_power_w == 17


@pytest.mark.unit
def test_required_power_uses_same_30_second_floor_as_rpnz():
    assert compute_required_power_w(
        quarter_energy_balance_kwh=-0.01,
        grid_power_w=-450.0,
        remaining_s=1.0,
    ) == 1650


@pytest.mark.unit
def test_quarter_balance_at_or_above_stop_threshold_forces_required_power_zero():
    assert compute_required_power_w(
        quarter_energy_balance_kwh=0.130,
        grid_power_w=5000.0,
        remaining_s=600.0,
    ) == 0


@pytest.mark.unit
def test_datetime_and_float_timestamp_inputs_both_work():
    dt = datetime(2026, 1, 1, 12, 5, 0)
    timestamp = dt.timestamp()
    assert seconds_until_next_quarter(dt) == seconds_until_next_quarter(timestamp)


@pytest.mark.unit
def test_missing_quarter_balance_degrades_safely():
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh='unknown',
        grid_power_w=500.0,
        now_ts=datetime(2026, 1, 1, 12, 1, 0),
    )
    assert derived.input_quality == 'degraded_missing_quarter_balance'
    assert 'missing_or_invalid_quarter_energy_balance_kwh' in derived.input_warnings
    assert derived.rpnz_w == 0


@pytest.mark.unit
def test_missing_grid_power_degrades_required_power_safely():
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=-0.2,
        grid_power_w='unavailable',
        now_ts=datetime(2026, 1, 1, 12, 10, 0),
    )
    assert derived.input_quality == 'degraded_missing_grid_power'
    assert 'missing_or_invalid_grid_power_w' in derived.input_warnings
    assert derived.required_power_w == 2400
    assert derived.required_power_consumption_kw == 2.4


@pytest.mark.unit
def test_rounding_golden_case_avoids_half_watt_ambiguity():
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=-0.37,
        grid_power_w=-250.0,
        now_ts=datetime(2026, 1, 1, 12, 9, 0),
    )
    assert derived.required_power_w == 3950
    assert derived.rpnz_w == 3700
