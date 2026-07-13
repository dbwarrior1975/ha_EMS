from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union


MIN_CONTROL_HORIZON_S = 30.0
EXPORT_BALANCE_STOP_KWH = 0.130


@dataclass
class NetZeroDerivedInputs:
    remaining_quarter_s: float
    remaining_quarter_min: float
    control_horizon_s: float
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


def control_horizon_s(remaining_s: float) -> float:
    """Return the stabilized quarter-control horizon used by RPNZ and RPC.

    The actual remaining quarter time is retained in diagnostics. Both control
    calculations use the same 30-second minimum horizon to avoid an unbounded
    final-seconds gain increase.
    """
    return max(float(remaining_s), MIN_CONTROL_HORIZON_S)


def _target_grid_power_w_float(
    *,
    quarter_energy_balance_kwh: float,
    remaining_s: float,
) -> float:
    horizon_s = control_horizon_s(remaining_s)
    return -(float(quarter_energy_balance_kwh) * 3600.0 / horizon_s) * 1000.0


def compute_rpnz_w(
    *,
    quarter_energy_balance_kwh: float,
    remaining_s: float,
) -> int:
    return int(
        round(
            _target_grid_power_w_float(
                quarter_energy_balance_kwh=quarter_energy_balance_kwh,
                remaining_s=remaining_s,
            )
        )
    )


def compute_required_power_w(
    *,
    quarter_energy_balance_kwh: float,
    grid_power_w: float,
    remaining_s: float,
    export_balance_stop_kwh: float = EXPORT_BALANCE_STOP_KWH,
) -> int:
    """Return RPC in watts using the exact second-based quarter horizon.

    RPC is the additional consuming power required to move measured grid power
    to the quarter-derived target grid power:

        rpc_w = target_grid_w - measured_grid_w

    The target and RPC use the same stabilized second horizon as RPNZ. Positive
    RPC means additional consumption; negative RPC means consumption should be
    reduced. The historical export-balance stop remains unchanged.
    """
    if float(quarter_energy_balance_kwh) >= float(export_balance_stop_kwh):
        return 0
    target_grid_w = _target_grid_power_w_float(
        quarter_energy_balance_kwh=quarter_energy_balance_kwh,
        remaining_s=remaining_s,
    )
    return int(round(target_grid_w - float(grid_power_w)))


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
    horizon_s = control_horizon_s(remaining_s)
    required_power_w = compute_required_power_w(
        quarter_energy_balance_kwh=quarter_balance_value,
        grid_power_w=grid_power_value,
        remaining_s=remaining_s,
    )
    return NetZeroDerivedInputs(
        remaining_quarter_s=remaining_s,
        remaining_quarter_min=float(remaining_s) / 60.0,
        control_horizon_s=horizon_s,
        rpnz_w=compute_rpnz_w(
            quarter_energy_balance_kwh=quarter_balance_value,
            remaining_s=remaining_s,
        ),
        required_power_w=required_power_w,
        required_power_consumption_kw=float(required_power_w) / 1000.0,
        input_quality=input_quality,
        input_warnings=warnings,
    )
