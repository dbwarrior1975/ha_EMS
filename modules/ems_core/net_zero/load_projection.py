from ems_core.domain.models import ControlProfile, GoalProfile, ForecastProfile, GuardProfile
from ems_core.integrations.haeo_horizon import ev_kw_to_selector_current_a


def ev_strategy_current_a(profiles, cfg, haeo, burn_active):
    # Safety first: degraded -> no EV control
    if profiles.guard == GuardProfile.DEGRADED:
        return -1

    # P2: MANUAL -> user force current acts as direct override
    if profiles.control == ControlProfile.MANUAL:
        if cfg.ev_force_current_a > 0:
            return int(min(max(cfg.ev_force_current_a, 0), cfg.ev_max_current_a))
        return -1

    # MANUAL_SAFE -> same user-facing EV semantics as MANUAL for now
    # (battery-side safety/clamping is handled elsewhere)
    if profiles.control == ControlProfile.MANUAL_SAFE:
        if cfg.ev_force_current_a > 0:
            return int(min(max(cfg.ev_force_current_a, 0), cfg.ev_max_current_a))
        return -1

    # P3: NET_ZERO -> force current acts as floor
    if profiles.goal == GoalProfile.NET_ZERO:
        base = int(cfg.ev_max_current_a) if burn_active else 0
        if cfg.ev_force_current_a > 0:
            return int(min(cfg.ev_max_current_a, max(cfg.ev_force_current_a, base)))
        return base

    # Existing force-current behavior remains for CHEAP_GRID_CHARGE / MAX_EXPORT
    if cfg.ev_force_current_a > 0 and profiles.goal in (GoalProfile.CHEAP_GRID_CHARGE, GoalProfile.MAX_EXPORT):
        return int(min(cfg.ev_force_current_a, cfg.ev_max_current_a))

    if haeo.effective_forecast == ForecastProfile.HAEO and profiles.goal in (GoalProfile.CHEAP_GRID_CHARGE, GoalProfile.MAX_EXPORT):
        return ev_kw_to_selector_current_a(haeo.ev_target_kw, cfg.ev_charger_phases, cfg.ev_max_current_a)

    if profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        return int(cfg.ev_max_current_a)

    if profiles.goal == GoalProfile.MAX_EXPORT:
        return int(cfg.ev_min_current_a)

    return -1


def relay_strategy_command(profiles, enabled_import_zero, force_on, net_zero_active):
    # MANUAL / MANUAL_SAFE -> direct user override
    if profiles.control == ControlProfile.MANUAL:
        return 1 if force_on else 0

    if profiles.control == ControlProfile.MANUAL_SAFE:
        return 1 if force_on else 0

    if profiles.guard == GuardProfile.DEGRADED:
        return -1

    if profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        return 0

    if profiles.goal == GoalProfile.NET_ZERO:
        if force_on:
            return 1
        if not enabled_import_zero:
            return 0
        if net_zero_active:
            return 1
        return 0

    if profiles.goal == GoalProfile.MAX_EXPORT:
        return 0

    return -1