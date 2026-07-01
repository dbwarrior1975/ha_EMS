from datetime import datetime

import pytest

from ems_core.net_zero.derived_inputs import (
    compute_required_power_w,
    compute_rpnz_w,
    derive_net_zero_inputs,
    remaining_template_minutes,
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
def test_remaining_template_minutes_boundary_behavior():
    assert remaining_template_minutes(datetime(2026, 1, 1, 12, 0, 0)) == 15
    assert remaining_template_minutes(datetime(2026, 1, 1, 12, 0, 1)) == 15
    assert remaining_template_minutes(datetime(2026, 1, 1, 12, 14, 59)) == 1
    assert remaining_template_minutes(datetime(2026, 1, 1, 12, 15, 0)) == 15


@pytest.mark.unit
def test_required_power_formula_uses_template_minutes_not_seconds():
    now_ts = datetime(2026, 1, 1, 12, 10, 45)
    derived = derive_net_zero_inputs(
        quarter_energy_balance_kwh=-0.2,
        grid_power_w=3000.0,
        now_ts=now_ts,
    )
    assert derived.remaining_quarter_min == 5.0
    assert derived.required_power_w == -600
    assert derived.required_power_consumption_kw == -0.6


@pytest.mark.unit
def test_quarter_balance_at_or_above_stop_threshold_forces_required_power_zero():
    assert compute_required_power_w(
        quarter_energy_balance_kwh=0.130,
        grid_power_w=5000.0,
        remaining_min=10.0,
    ) == 0


@pytest.mark.unit
def test_datetime_and_float_timestamp_inputs_both_work():
    dt = datetime(2026, 1, 1, 12, 5, 0)
    timestamp = dt.timestamp()
    assert seconds_until_next_quarter(dt) == seconds_until_next_quarter(timestamp)
    assert remaining_template_minutes(dt) == remaining_template_minutes(timestamp)


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
