from __future__ import annotations

from ems_core.net_zero.derived_inputs import control_horizon_s
from ems_core.net_zero.derived_inputs import seconds_until_next_quarter


EXPORT_BALANCE_STOP_KWH = 0.130


def balance_for_rpnz_w(rpnz_w, remaining_s):
    horizon_s = control_horizon_s(remaining_s)
    return -(float(rpnz_w) / 1000.0) * horizon_s / 3600.0


def grid_power_for_required_power_kw(
    required_power_consumption_kw,
    quarter_energy_balance_kwh,
    remaining_s,
):
    required_power_w = float(required_power_consumption_kw) * 1000.0
    target_grid_w = -(
        float(quarter_energy_balance_kwh)
        * 3_600_000.0
        / control_horizon_s(remaining_s)
    )
    return target_grid_w - required_power_w


def runtime_inputs_for_net_zero_intent(
    entity_ids,
    *,
    rpnz_w,
    required_power_consumption_kw,
    at_s,
    pv_power_w=None,
    pv_power_kw=None,
):
    """Build production-equivalent raw EMS runtime inputs for a NET_ZERO fixture intent.

    The caller describes the intended derived business situation with `rpnz_w`
    and `required_power_consumption_kw`, but those values are not written to
    EMS runtime entities directly. This helper instead calculates the raw
    production inputs that EMS actually reads at runtime:

    - `quarter_energy_balance_kwh`
    - `grid_power_w`
    - optional `pv_power_w`

    The paired `expect_derived_for_net_zero_intent()` assertion documents the
    expected outcome of production `derive_net_zero_inputs()`. Together the
    helper and the assertion prove that the raw fixture values encode the same
    NET_ZERO intent as the shorthand RPNZ/RPC arguments.
    """
    remaining_s = seconds_until_next_quarter(at_s)
    quarter_energy_balance_kwh = balance_for_rpnz_w(rpnz_w, remaining_s)
    if (
        float(required_power_consumption_kw) != 0.0
        and float(quarter_energy_balance_kwh) >= EXPORT_BALANCE_STOP_KWH
    ):
        raise AssertionError(
            "Invalid E2E fixture: raw runtime inputs cannot encode nonzero NET_ZERO required_power "
            f"above export stop threshold (required_power_consumption_kw={required_power_consumption_kw} "
            f"quarter_energy_balance_kwh={quarter_energy_balance_kwh})"
        )
    values = {
        entity_ids['quarter_energy_balance_kwh']: quarter_energy_balance_kwh,
        entity_ids['grid_power_w']: grid_power_for_required_power_kw(
            required_power_consumption_kw,
            quarter_energy_balance_kwh,
            remaining_s,
        ),
    }
    if pv_power_w is not None and pv_power_kw is not None:
        raise AssertionError('provide pv_power_w or pv_power_kw, not both')
    if pv_power_kw is not None:
        pv_power_w = float(pv_power_kw) * 1000.0
    if pv_power_w is not None:
        values[entity_ids['pv_power_w']] = float(pv_power_w)
    return values


def expect_derived_for_net_zero_intent(
    *,
    rpnz_w,
    required_power_consumption_kw,
    at_s,
):
    """Return the expected derived NET_ZERO values for the fixture intent.

    The E2E runner compares this mapping against production
    `derive_net_zero_inputs()` output after the raw runtime entities from
    `runtime_inputs_for_net_zero_intent()` have been applied. A mismatch points
    first to fixture-construction drift or unit/conversion errors, not
    immediately to a surplus-policy regression.
    """
    return {
        'rpnz_w': int(round(float(rpnz_w))),
        'required_power_w': int(round(float(required_power_consumption_kw) * 1000.0)),
        'required_power_consumption_kw': float(required_power_consumption_kw),
        'remaining_quarter_s': seconds_until_next_quarter(at_s),
        'remaining_quarter_min': seconds_until_next_quarter(at_s) / 60.0,
        'control_horizon_s': control_horizon_s(seconds_until_next_quarter(at_s)),
    }
