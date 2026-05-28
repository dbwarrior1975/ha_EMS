import pytest
from ems_core.diagnostics.decision_trace import net_zero_attrs
from ems_core.domain.models import NetZeroOutputs
from tests.helpers import make_profiles


@pytest.mark.unit
def test_decision_trace_exposes_core_fields_and_battery_authority():
    out = NetZeroOutputs(
        battery_target_w=100,
        battery_write_enabled=False,
        ev_current_a=12,
        relay1_command=1,
        relay2_command=0,
        surplus_policy_active=True,
        surplus_next_target='EV',
        surplus_next_threshold_kw=2.5,
        surplus_release_candidate='NONE',
        surplus_dispatch_decision='NOOP',
        surplus_explanation='testing',
        effective_forecast='NONE',
        dominant_limitation='USER_MANUAL_OVERRIDE',
        explanation='User manual control active',
        attrs={'configured_forecast': 'NONE'},
    )
    attrs = net_zero_attrs(out, make_profiles())
    assert attrs['battery_write_enabled'] is False
    assert attrs['battery_target_w'] == 100
    assert attrs['ev_current_a'] == 12
    assert attrs['configured_forecast'] == 'NONE'
