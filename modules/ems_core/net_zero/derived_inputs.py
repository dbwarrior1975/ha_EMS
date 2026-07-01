from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union


@dataclass
class NetZeroDerivedInputs:
    remaining_quarter_s: float
    remaining_quarter_min: float
    rpnz_w: int
    required_power_w: int
    required_power_consumption_kw: float
    input_quality: str = 'ok'
    input_warnings: tuple[str, ...] = ()


def _to_datetime(now_ts: Union[float, datetime]) -> datetime:
    if isinstance(now_ts, datetime):
        return now_ts
    return datetime.fromtimestamp(float(now_ts))


def seconds_until_next_quarter(now_ts: Union[float, datetime]) -> float:
    now_dt = _to_datetime(now_ts)
    seconds_into_quarter = (
        (now_dt.minute % 15) * 60.0
        + float(now_dt.second)
        + (float(now_dt.microsecond) / 1_000_000.0)
    )
    return 900.0 - seconds_into_quarter


def remaining_template_minutes(now_ts: Union[float, datetime]) -> int:
    return 15 - (_to_datetime(now_ts).minute % 15)


def compute_rpnz_w(
    *,
    quarter_energy_balance_kwh: float,
    remaining_s: float,
) -> int:
    remaining_s = max(float(remaining_s), 30.0)
    return int(round(-(float(quarter_energy_balance_kwh) * 3600.0 / remaining_s) * 1000.0))


def compute_required_power_w(
    *,
    quarter_energy_balance_kwh: float,
    grid_power_w: float,
    remaining_min: float,
    export_balance_stop_kwh: float = 0.130,
) -> int:
    if float(quarter_energy_balance_kwh) >= float(export_balance_stop_kwh):
        return 0
    power_kw = float(grid_power_w) / 1000.0
    remaining_min = float(remaining_min)
    estimated_balance_delta_kwh = power_kw * remaining_min / 60.0
    required_consumption_kwh = float(quarter_energy_balance_kwh) + estimated_balance_delta_kwh
    required_consumption_kw = required_consumption_kwh * 60.0 / remaining_min
    return int(round(required_consumption_kw * -1000.0))


def _coerce_float(value: object, warning_name: str) -> tuple[float, Optional[str]]:
    if value in (None, '', 'unknown', 'unavailable'):
        return 0.0, warning_name
    try:
        return float(value), None
    except (TypeError, ValueError):
        return 0.0, warning_name


def derive_net_zero_inputs(
    *,
    quarter_energy_balance_kwh: object,
    grid_power_w: object,
    now_ts: Union[float, datetime],
) -> NetZeroDerivedInputs:
    quarter_balance_value, quarter_warning = _coerce_float(
        quarter_energy_balance_kwh,
        'missing_or_invalid_quarter_energy_balance_kwh',
    )
    grid_power_value, grid_warning = _coerce_float(
        grid_power_w,
        'missing_or_invalid_grid_power_w',
    )

    warnings_list = []
    for warning in (quarter_warning, grid_warning):
        if warning is not None:
            warnings_list.append(warning)
    warnings = tuple(warnings_list)
    if len(warnings) > 1:
        input_quality = 'degraded_missing_multiple_inputs'
    elif quarter_warning is not None:
        input_quality = 'degraded_missing_quarter_balance'
    elif grid_warning is not None:
        input_quality = 'degraded_missing_grid_power'
    else:
        input_quality = 'ok'

    remaining_s = seconds_until_next_quarter(now_ts)
    remaining_min = float(remaining_template_minutes(now_ts))
    required_power_w = compute_required_power_w(
        quarter_energy_balance_kwh=quarter_balance_value,
        grid_power_w=grid_power_value,
        remaining_min=remaining_min,
    )
    return NetZeroDerivedInputs(
        remaining_quarter_s=remaining_s,
        remaining_quarter_min=remaining_min,
        rpnz_w=compute_rpnz_w(
            quarter_energy_balance_kwh=quarter_balance_value,
            remaining_s=remaining_s,
        ),
        required_power_w=required_power_w,
        required_power_consumption_kw=float(required_power_w) / 1000.0,
        input_quality=input_quality,
        input_warnings=warnings,
    )
