import pytest

from ems_core.domain.capabilities import clamp_target_w_for_capabilities, capability_block_reason
from ems_core.domain.models import EmsDeviceConfig


def _device(**overrides):
    data = dict(
        device_id='TEST',
        kind='GENERIC',
        response_kind='continuous',
        can_absorb_w=True,
        can_produce_w=True,
        min_absorb_w=0,
        max_absorb_w=3000,
        max_produce_w=4000,
        step_w=50,
        priority=1,
    )
    data.update(overrides)
    return EmsDeviceConfig(**data)


@pytest.mark.unit
def test_capabilities_block_positive_target_when_absorb_disabled():
    device = _device(can_absorb_w=False)
    assert clamp_target_w_for_capabilities(device, 1200) == 0
    assert capability_block_reason(device, 1200) == 'capability_blocked_absorb'


@pytest.mark.unit
def test_capabilities_block_negative_target_when_produce_disabled():
    device = _device(can_produce_w=False)
    assert clamp_target_w_for_capabilities(device, -1800) == 0
    assert capability_block_reason(device, -1800) == 'capability_blocked_produce'


@pytest.mark.unit
def test_capabilities_clamp_to_device_limits():
    device = _device(max_absorb_w=1400, max_produce_w=1600)
    assert clamp_target_w_for_capabilities(device, 2200) == 1400
    assert clamp_target_w_for_capabilities(device, -2600) == -1600
    assert capability_block_reason(device, 2200) == ''
