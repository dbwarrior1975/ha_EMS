import pytest
from ems_core.domain.models import ControlProfile, GoalProfile, GuardProfile
from ems_core.guard.evaluator import evaluate_guard
from ems_core.net_zero.engine import compute_net_zero_engine_outputs
from ems_core.diagnostics.decision_trace import net_zero_attrs
from tests.helpers import make_profiles, make_cfg, make_m, make_haeo, make_nz


@pytest.mark.scenario
@pytest.mark.parametrize(
    'name, profiles, cfg, m, expected_guard, expected_limitation',
    [
        (
            'manual_trace_and_authority',
            make_profiles(control=ControlProfile.MANUAL, goal=GoalProfile.NET_ZERO),
            make_cfg(),
            make_m(current_battery_setpoint_w=250),
            GuardProfile.NORMAL_LIMITS,
            'USER_MANUAL_OVERRIDE',
        ),
        (
            'battery_protect_min_cell_only',
            make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO),
            make_cfg(battery_protect_soc=1.0, battery_protect_soc_recovery_margin=1.0, battery_protect_min_cell_voltage_v=3.03),
            make_m(soc=50.0, min_cell_voltage_v=3.02),
            GuardProfile.BATTERY_PROTECT,
            'BATTERY_SOC_LIMIT',
        ),
        (
            'degraded_fallback',
            make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO),
            make_cfg(battery_heartbeat_timeout_s=10),
            make_m(battery_heartbeat_age_s=999),
            GuardProfile.DEGRADED,
            'SYSTEM_DEGRADED',
        ),
    ],
)
def test_regression_scenarios(name, profiles, cfg, m, expected_guard, expected_limitation):
    gd = evaluate_guard(profiles.guard, m, cfg)
    profiles = make_profiles(control=profiles.control, goal=profiles.goal, forecast=profiles.forecast, guard=gd.guard)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    attrs = net_zero_attrs(out, profiles, gd)
    assert gd.guard == expected_guard, name
    assert attrs['dominant_limitation'] == expected_limitation, name
