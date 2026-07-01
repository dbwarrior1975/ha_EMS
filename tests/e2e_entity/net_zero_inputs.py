from __future__ import annotations

from ems_core.net_zero.derived_inputs import remaining_template_minutes
from ems_core.net_zero.derived_inputs import seconds_until_next_quarter


EXPORT_BALANCE_STOP_KWH = 0.130


def balance_for_rpnz_w(rpnz_w, remaining_s):
    return -(float(rpnz_w) / 1000.0) * float(remaining_s) / 3600.0


def grid_power_for_required_power_kw(
    required_power_consumption_kw,
    quarter_energy_balance_kwh,
    remaining_min,
):
    required_power_w = float(required_power_consumption_kw) * 1000.0
    return -required_power_w - float(quarter_energy_balance_kwh) * 60000.0 / float(remaining_min)


def runtime_inputs_for_net_zero_intent(
    entity_ids,
    *,
    rpnz_w,
    required_power_consumption_kw,
    at_s,
    pv_power_w=None,
    pv_power_kw=None,
):
    remaining_s = seconds_until_next_quarter(at_s)
    remaining_min = float(remaining_template_minutes(at_s))
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
            remaining_min,
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
    return {
        'rpnz_w': int(round(float(rpnz_w))),
        'required_power_w': int(round(float(required_power_consumption_kw) * 1000.0)),
        'required_power_consumption_kw': float(required_power_consumption_kw),
        'remaining_quarter_s': seconds_until_next_quarter(at_s),
        'remaining_quarter_min': float(remaining_template_minutes(at_s)),
    }
