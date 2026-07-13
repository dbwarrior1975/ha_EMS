def net_zero_feedback_state(*, rpnz_w: float, grid_actual_w: float, current_control_target_w: float, deadband_w: float):
    """Return the canonical NET_ZERO feedback state before transient ramping.

    `rpnz_w` is the quarter-derived target grid power and `grid_actual_w` is the
    measured grid power. The signed current control target is controller state;
    it is not a power measurement. The unbounded desired target is intentionally
    computed before ramp limiting so producer hard-allocation can be separated
    from transient actuator movement.
    """
    target_grid_w = float(rpnz_w)
    actual_grid_w = float(grid_actual_w)
    current_target_w = float(current_control_target_w)
    error_w = target_grid_w - actual_grid_w
    delta_w = error_w / 2.0
    in_deadband = abs(delta_w) < float(deadband_w)
    control_step_w = 0.0
    desired_target_w = current_target_w
    if not in_deadband:
        control_step_w = float(int(round(delta_w / 100.0)) * 100)
        desired_target_w += control_step_w
    return {
        'target_grid_w': target_grid_w,
        'grid_actual_w': actual_grid_w,
        'error_w': error_w,
        'delta_w': delta_w,
        'in_deadband': bool(in_deadband),
        'control_step_w': control_step_w,
        'current_control_target_w': current_target_w,
        'desired_control_target_w': desired_target_w,
    }


def candidate_sp_net_zero(*, rpnz_w: float, grid_actual_w: float, current_sp_w: float, deadband_w: float, ramp_w: float, max_sp_w: float, min_charge_floor_w: float = 100.0) -> int:
    feedback = net_zero_feedback_state(
        rpnz_w=rpnz_w,
        grid_actual_w=grid_actual_w,
        current_control_target_w=current_sp_w,
        deadband_w=deadband_w,
    )
    if feedback['in_deadband']:
        return int(round(current_sp_w))
    step = float(feedback['control_step_w'])
    step_clamped = max(min(step, int(ramp_w)), -int(ramp_w))
    raw = float(current_sp_w) + step_clamped
    if rpnz_w < 0 and feedback['error_w'] < -deadband_w:
        return int(round(min(raw, max_sp_w)))
    return int(round(min(max(raw, min_charge_floor_w), max_sp_w)))
