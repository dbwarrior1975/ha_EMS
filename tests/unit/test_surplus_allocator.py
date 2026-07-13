import pytest

from ems_core.domain.models import SurplusDeviceTarget, SurplusDispatchInput
from ems_core.net_zero.surplus_allocator import (
    SURPLUS_RELEASE_DEADBAND_W,
    compute_surplus_device_dispatch,
)


def _target(device_id, *, priority, active):
    return SurplusDeviceTarget(
        device_id=device_id,
        priority=priority,
        rank=1,
        threshold_w=1000,
        active=active,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ('rpnz_w', 'expected_release'),
    (
        (4.0, 'RELAY1'),
        (10.0, 'RELAY1'),
        (0.0, 'RELAY1'),
        (-1.0, 'RELAY1'),
        (11.0, None),
    ),
)
def test_surplus_release_deadband_releases_only_at_or_below_threshold(rpnz_w, expected_release):
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=rpnz_w,
        targets=(
            _target('EV_CHARGER', priority=3, active=True),
            _target('RELAY1', priority=2, active=True),
        ),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == expected_release
    if expected_release is None:
        assert decision.explanation != 'RPNZ <= 10 W release deadband -> release lowest-priority active target'
    else:
        assert decision.explanation == 'RPNZ <= 10 W release deadband -> release lowest-priority active target'


@pytest.mark.unit
def test_surplus_release_deadband_applies_to_single_active_ev_target():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=SURPLUS_RELEASE_DEADBAND_W,
        targets=(
            _target('EV_CHARGER', priority=3, active=True),
            _target('RELAY1', priority=2, active=False),
        ),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == 'EV_CHARGER'
    assert decision.explanation == 'RPNZ <= 10 W release deadband -> release lowest-priority active target'


@pytest.mark.unit
@pytest.mark.parametrize('device_id', ('EV_CHARGER', 'RELAY1'))
def test_active_priority_zero_target_is_released_as_ineligible(device_id):
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=5.0,
        rpnz_w=5000.0,
        targets=(
            _target(device_id, priority=0, active=True),
        ),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == device_id
    assert decision.explanation == f'{device_id} no longer eligible -> release dispatch state'


@pytest.mark.unit
def test_unavailable_inactive_surplus_candidate_is_skipped_for_next_eligible_device():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=3.0,
        rpnz_w=3000.0,
        targets=(
            SurplusDeviceTarget(
                device_id='EV_CHARGER',
                priority=4,
                rank=1,
                threshold_w=2000,
                active=False,
                activation_allowed=False,
            ),
            SurplusDeviceTarget(
                device_id='RELAY1',
                priority=3,
                rank=2,
                threshold_w=2500,
                active=False,
                activation_allowed=True,
            ),
        ),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.activate == 'RELAY1'
    assert decision.release is None


@pytest.mark.unit
def test_active_surplus_candidate_that_becomes_unavailable_is_released():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=5.0,
        rpnz_w=5000.0,
        targets=(
            SurplusDeviceTarget(
                device_id='EV_CHARGER',
                priority=4,
                rank=1,
                threshold_w=2000,
                active=True,
                activation_allowed=False,
            ),
        ),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == 'EV_CHARGER'
    assert decision.activate is None
    assert decision.explanation == 'EV_CHARGER no longer eligible -> release dispatch state'
