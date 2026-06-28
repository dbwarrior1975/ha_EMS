from __future__ import annotations

import math


DEFAULT_EV_VOLTAGE_V = 230.0


def _as_positive_float(value, field_name):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _ceil_to_step(value, step):
    safe_step = _as_positive_float(step, 'current_step_a')
    return math.ceil(float(value) / safe_step) * safe_step


def _floor_to_step(value, step):
    safe_step = _as_positive_float(step, 'current_step_a')
    return math.floor(float(value) / safe_step) * safe_step


def _quantize_to_supported_step(value, step):
    safe_step = _as_positive_float(step, 'current_step_a')
    return round(float(value) / safe_step) * safe_step


def _normalize_current_value(current_a):
    rounded = round(float(current_a), 9)
    if math.isclose(rounded, round(rounded), abs_tol=1e-9):
        return int(round(rounded))
    return rounded


def _cfg_ev_voltage_v(cfg):
    return getattr(cfg, 'ev_voltage_v', DEFAULT_EV_VOLTAGE_V)


def _cfg_capability_power_w(cfg, *names):
    for name in names:
        if hasattr(cfg, name):
            value = getattr(cfg, name)
            if value not in (None, ''):
                return float(value)
    return None


def ev_per_amp_w(phases, voltage_v):
    safe_phases = _as_positive_float(phases, 'phases')
    safe_voltage_v = _as_positive_float(voltage_v, 'voltage_v')
    return safe_phases * safe_voltage_v


def ev_phase_power_w(phases, voltage_v=DEFAULT_EV_VOLTAGE_V):
    return ev_per_amp_w(phases, voltage_v)


def ev_current_a_to_power_w(current_a, phases, voltage_v=DEFAULT_EV_VOLTAGE_V):
    return max(float(current_a), 0.0) * ev_per_amp_w(phases, voltage_v)


def ev_min_current_a_from_min_absorb_w(
    min_absorb_w,
    *,
    phases,
    voltage_v,
    current_step_a,
):
    safe_min_absorb_w = _as_positive_float(min_absorb_w, 'min_absorb_w')
    raw_min_a = safe_min_absorb_w / ev_per_amp_w(phases, voltage_v)
    return _normalize_current_value(_ceil_to_step(raw_min_a, current_step_a))


def ev_max_current_a_from_max_absorb_w(
    max_absorb_w,
    *,
    phases,
    voltage_v,
    current_step_a,
):
    safe_max_absorb_w = _as_positive_float(max_absorb_w, 'max_absorb_w')
    raw_max_a = safe_max_absorb_w / ev_per_amp_w(phases, voltage_v)
    return _normalize_current_value(_floor_to_step(raw_max_a, current_step_a))


def ev_power_w_to_current_a(
    power_w,
    *,
    phases,
    voltage_v,
    min_absorb_w,
    max_absorb_w,
    current_step_a,
):
    safe_power_w = float(power_w)
    min_current_a = ev_min_current_a_from_min_absorb_w(
        min_absorb_w,
        phases=phases,
        voltage_v=voltage_v,
        current_step_a=current_step_a,
    )
    max_current_a = ev_max_current_a_from_max_absorb_w(
        max_absorb_w,
        phases=phases,
        voltage_v=voltage_v,
        current_step_a=current_step_a,
    )
    if float(min_current_a) > float(max_current_a):
        raise ValueError(
            'EV watt limits cannot be represented by configured current_step_a, phases, and voltage_v'
        )

    target_a = safe_power_w / ev_per_amp_w(phases, voltage_v)
    quantized_a = _quantize_to_supported_step(target_a, current_step_a)
    clamped_a = min(max(quantized_a, float(min_current_a)), float(max_current_a))
    return _normalize_current_value(clamped_a)


def ev_min_power_w(cfg):
    capability_w = _cfg_capability_power_w(cfg, 'min_absorb_w', 'ev_min_absorb_w')
    if capability_w is not None:
        return capability_w
    return ev_current_a_to_power_w(
        cfg.ev_min_current_a,
        cfg.ev_charger_phases,
        _cfg_ev_voltage_v(cfg),
    )


def ev_max_power_w(cfg):
    capability_w = _cfg_capability_power_w(cfg, 'max_absorb_w', 'ev_max_absorb_w')
    if capability_w is not None:
        return capability_w
    return ev_current_a_to_power_w(
        cfg.ev_max_current_a,
        cfg.ev_charger_phases,
        _cfg_ev_voltage_v(cfg),
    )


def ev_power_step_w(cfg):
    configured_step_w = _cfg_capability_power_w(cfg, 'ev_power_step_w', 'step_w')
    if configured_step_w is not None:
        return configured_step_w
    step_a = getattr(cfg, 'ev_current_step_a', 1) or 1
    return ev_current_a_to_power_w(step_a, cfg.ev_charger_phases, _cfg_ev_voltage_v(cfg))


def ev_power_w_to_selector_current_a(
    power_w,
    phases,
    max_a,
    min_a=4,
    step_a=4,
    voltage_v=DEFAULT_EV_VOLTAGE_V,
):
    raw_a = float(power_w) / ev_per_amp_w(phases, voltage_v)
    if raw_a < 1:
        return 0

    safe_min_a = max(1, int(float(min_a)))
    safe_max_a = max(safe_min_a, int(float(max_a)))
    safe_step_a = max(1, int(float(step_a)))

    candidates = list(range(safe_min_a, safe_max_a + 1, safe_step_a))
    if candidates and candidates[-1] != safe_max_a:
        candidates.append(safe_max_a)
    if not candidates:
        return 0

    best = candidates[0]
    bestdiff = abs(raw_a - best)
    for current_a in candidates[1:]:
        diff = abs(raw_a - current_a)
        if diff < bestdiff:
            best, bestdiff = current_a, diff
    return int(best)
