import pytest

from ems_core.integrations.haeo_horizon import _to_ts, ev_kw_to_selector_current_a, latest_forecast_value_at_or_before


@pytest.mark.unit
def test_forecast_parsing_ok():
    forecast = [
        {'time': '1970-01-01T00:00:00+00:00', 'value': 1.5},
        {'time': '1970-01-01T00:05:00+00:00', 'value': 2.5},
    ]
    assert latest_forecast_value_at_or_before(forecast, 301, 0.0) == 2.5


@pytest.mark.unit
def test_forecast_missing_payload():
    assert latest_forecast_value_at_or_before(None, 100, 7.0) == 7.0
    assert latest_forecast_value_at_or_before([], 100, 7.0) == 7.0


@pytest.mark.unit
def test_forecast_timezone_handling():
    zulu = _to_ts('1970-01-01T00:05:00Z')
    explicit = _to_ts('1970-01-01T00:05:00+00:00')
    assert zulu == explicit == 300.0


@pytest.mark.unit
def test_forecast_stale_detection():
    # When there is no forecast point at or before now, integration falls back.
    forecast = [{'time': '1970-01-01T00:05:00+00:00', 'value': 2.0}]
    assert latest_forecast_value_at_or_before(forecast, 299, 0.0) == 0.0


@pytest.mark.unit
def test_forecast_partial_payload():
    forecast = [
        {'time': '1970-01-01T00:00:00+00:00', 'value': 'bad'},
        {'time': 'invalid', 'value': 3.0},
        {'time': '1970-01-01T00:10:00+00:00', 'value': 4.0},
    ]
    assert latest_forecast_value_at_or_before(forecast, 601, 1.0) == 4.0


@pytest.mark.unit
def test_ev_kw_to_selector_current_a_rounds_to_nearest_allowed_current():
    assert ev_kw_to_selector_current_a(2.7, phases=1, max_a=28) == 12


@pytest.mark.unit
def test_ev_kw_to_selector_current_a_uses_param_based_step_set():
    # min=4, step=2 produces [4, 6, 8, ..., 28], so 2.3 kW (~10 A) maps to 10 A.
    assert ev_kw_to_selector_current_a(2.3, phases=1, max_a=28, min_a=4, step_a=2) == 10


@pytest.mark.unit
def test_ev_kw_to_selector_current_a_caps_candidates_to_max_bound():
    # min=6, step=4, max=27 produces [6, 10, 14, 18, 22, 26].
    assert ev_kw_to_selector_current_a(6.0, phases=1, max_a=27, min_a=6, step_a=4) == 26


@pytest.mark.unit
def test_ev_kw_to_selector_current_a_returns_zero_below_one_amp():
    assert ev_kw_to_selector_current_a(0.2, phases=1, max_a=28, min_a=4, step_a=2) == 0


@pytest.mark.unit
def test_ev_kw_to_selector_current_a_step_fallback_and_clamps():
    # step<=0 falls back to 1 and min<=0 clamps to 1.
    assert ev_kw_to_selector_current_a(0.6, phases=1, max_a=6, min_a=0, step_a=0) == 3
