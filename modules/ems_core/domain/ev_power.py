EV_PHASE_VOLTAGE_V = 230


def ev_phase_power_w(phases):
    return max(int(phases), 1) * EV_PHASE_VOLTAGE_V


def ev_current_a_to_power_w(current_a, phases):
    return int(max(int(current_a), 0) * ev_phase_power_w(phases))


def ev_min_power_w(cfg):
    return ev_current_a_to_power_w(cfg.ev_min_current_a, cfg.ev_charger_phases)


def ev_max_power_w(cfg):
    return ev_current_a_to_power_w(cfg.ev_max_current_a, cfg.ev_charger_phases)


def ev_power_step_w(cfg):
    step_a = max(1, int(getattr(cfg, 'ev_current_step_a', 1) or 1))
    return ev_current_a_to_power_w(step_a, cfg.ev_charger_phases)


def ev_power_w_to_selector_current_a(power_w, phases, max_a, min_a=4, step_a=4):
    raw_a = float(power_w) / float(ev_phase_power_w(phases))
    if raw_a < 1:
        return 0

    safe_min_a = max(1, int(min_a))
    safe_max_a = max(safe_min_a, int(max_a))
    safe_step_a = max(1, int(step_a))

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
