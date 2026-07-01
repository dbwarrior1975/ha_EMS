import pytest
from ems_core.diagnostics.policy_diagnostics import net_zero_attrs
from ems_core.domain.models import DevicePolicy, NetZeroOutputs
from tests.helpers import make_profiles


@pytest.mark.unit
def test_policy_diagnostics_exposes_core_fields_and_battery_authority():
    out = NetZeroOutputs(
        battery_target_w=100,
        battery_write_enabled=False,
        surplus_policy_active=True,
        surplus_next_target='EV',
        surplus_next_threshold_kw=2.5,
        surplus_release_candidate='NONE',
        surplus_dispatch_decision='NOOP',
        surplus_explanation='testing',
        effective_forecast='NONE',
        dominant_limitation='USER_MANUAL_OVERRIDE',
        explanation='User manual control active',
        device_policies=(
            DevicePolicy(
                device_id='HOME_BATTERY',
                target_w=100,
                enabled=False,
                mode='power',
                reason='battery_policy',
            ),
        ),
        attrs={
            'configured_forecast': 'NONE',
            'device_policy_parity_ok': True,
        },
    )
    attrs = net_zero_attrs(out, make_profiles())
    assert attrs['battery_write_enabled'] is False
    assert attrs['battery_target_w'] == 100
    assert attrs['configured_forecast'] == 'NONE'
    assert attrs['device_policy_parity_ok'] is True
    assert attrs['device_policies'][0]['device_id'] == 'HOME_BATTERY'
    assert 'ev_current_a' not in attrs
    assert 'relay1_command' not in attrs
    assert 'relay2_command' not in attrs
