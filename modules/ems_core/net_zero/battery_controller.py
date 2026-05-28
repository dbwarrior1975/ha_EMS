def candidate_sp_net_zero(*, rpnz_w: float, grid_actual_w: float, current_sp_w: float, deadband_w: float, ramp_w: float, max_sp_w: float, min_charge_floor_w: float = 100.0) -> int:
    error = rpnz_w - grid_actual_w
    delta = error / 2.0
    if abs(delta) < deadband_w:
        return int(round(current_sp_w))
    step = int(round(delta / 100.0)) * 100
    step_clamped = max(min(step, int(ramp_w)), -int(ramp_w))
    raw = current_sp_w + step_clamped
    if rpnz_w < 0 and error < -deadband_w:
        return int(round(min(raw, max_sp_w)))
    return int(round(min(max(raw, min_charge_floor_w), max_sp_w)))
