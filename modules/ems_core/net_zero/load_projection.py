from ems_core.domain.ev_power import ev_max_power_w
from ems_core.domain.models import ControlProfile, GoalProfile, ForecastProfile, GuardProfile


def ev_strategy_target_w(profiles, ev_context, haeo, burn_active):
    # Safety first: degraded -> no EV control.
    if profiles.guard == GuardProfile.DEGRADED:
        return 0.0

    force_on = bool(getattr(ev_context, 'force_on', False))
    max_absorb_w = float(ev_max_power_w(ev_context))

    # P2: MANUAL -> user force_on acts as direct max-charge override.
    if profiles.control == ControlProfile.MANUAL:
        return max_absorb_w if force_on else 0.0

    # MANUAL_SAFE -> same user-facing EV semantics as MANUAL for now.
    if profiles.control == ControlProfile.MANUAL_SAFE:
        return max_absorb_w if force_on else 0.0

    # NET_ZERO -> force_on overrides optimizer mode but not downstream safety gates.
    if profiles.goal == GoalProfile.NET_ZERO:
        return max_absorb_w if (force_on or burn_active) else 0.0

    # MAX_EXPORT stays export-first unless the user explicitly forces EV on.
    if profiles.goal == GoalProfile.MAX_EXPORT:
        return max_absorb_w if force_on else 0.0

    if force_on and profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        return max_absorb_w

    if haeo.effective_forecast == ForecastProfile.HAEO and profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        target_w = float(getattr(haeo, 'ev_target_kw', 0.0) or 0.0) * 1000.0
        return target_w if target_w > 0.0 else 0.0

    if profiles.goal == GoalProfile.CHEAP_GRID_CHARGE:
        return max_absorb_w

    return 0.0


def relay_strategy_command(profiles, surplus_allowed, force_on, net_zero_active):
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
        if not surplus_allowed:
            return 0
        if net_zero_active:
            return 1
        return 0

    if profiles.goal == GoalProfile.MAX_EXPORT:
        return 0

    return -1
