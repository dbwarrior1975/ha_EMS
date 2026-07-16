import pytest

from ems_core.domain.models import SurplusDeviceTarget, SurplusDispatchInput
from ems_core.net_zero.surplus_allocator import (
    SURPLUS_RELEASE_DEADBAND_W,
    compute_surplus_device_dispatch,
)


def _target(
    device_id,
    *,
    priority,
    active,
    rank=1,
    threshold_w=1000,
    releasable_power_w=None,
    **overrides,
):
    return SurplusDeviceTarget(
        device_id=device_id,
        priority=priority,
        rank=rank,
        threshold_w=threshold_w,
        active=active,
        releasable_power_w=releasable_power_w,
        **overrides,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ('rpnz_w', 'expected_release'),
    (
        (4.0, 'EV_CHARGER'),
        (10.0, 'EV_CHARGER'),
        (0.0, 'EV_CHARGER'),
        (-1.0, 'EV_CHARGER'),
        (11.0, None),
    ),
)
def test_anchor_release_deadband_applies_only_to_single_active_target(
    rpnz_w,
    expected_release,
):
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=rpnz_w,
        targets=(
            _target('EV_CHARGER', priority=3, active=True),
            _target('RELAY1', priority=2, active=False),
        ),
        active_device_ids=('EV_CHARGER',),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == expected_release
    if expected_release is None:
        assert decision.release_mode == ''
    else:
        assert decision.release_mode == 'anchor_rpnz_deadband'
        assert decision.explanation == (
            'RPNZ <= 10 W release deadband -> release lowest-priority active target'
        )


@pytest.mark.unit
def test_rpnz_deadband_does_not_release_n_minus_one_target_without_excess_rpc():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=SURPLUS_RELEASE_DEADBAND_W,
        targets=(
            _target('EV_CHARGER', priority=4, active=True, rank=1),
            _target(
                'RELAY1',
                priority=3,
                active=True,
                rank=2,
                threshold_w=2700,
                releasable_power_w=2700,
            ),
        ),
        active_device_ids=('EV_CHARGER', 'RELAY1'),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release is None
    assert decision.release_mode == ''
    assert decision.explanation == 'No eligible next surplus target'


@pytest.mark.unit
def test_n_minus_one_release_uses_nominal_power_with_five_percent_margin():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=-2.565,
        rpnz_w=500.0,
        targets=(
            _target('EV_CHARGER', priority=4, active=True, rank=1),
            _target(
                'RELAY1',
                priority=3,
                active=True,
                rank=2,
                threshold_w=2700,
                releasable_power_w=2700,
            ),
        ),
        active_device_ids=('EV_CHARGER', 'RELAY1'),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=100.0, freeze_s=30)

    assert decision.release == 'RELAY1'
    assert decision.release_mode == 'n_minus_one_incremental'
    assert decision.release_power_w == 2700
    assert decision.release_margin_w == 135
    assert decision.release_threshold_w == 2565
    assert decision.excess_consumption_w == 2565
    assert decision.freeze_until_ts == 130.0
    assert decision.explanation == (
        'N-1 excess 2565 W >= RELAY1 release threshold 2565 W '
        '(2700 W - 135 W margin)'
    )


@pytest.mark.unit
def test_n_minus_one_release_holds_just_below_margin_adjusted_threshold():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=-2.564,
        rpnz_w=500.0,
        targets=(
            _target('EV_CHARGER', priority=4, active=True, rank=1),
            _target(
                'RELAY1',
                priority=3,
                active=True,
                rank=2,
                threshold_w=2700,
                releasable_power_w=2700,
            ),
        ),
        active_device_ids=('EV_CHARGER', 'RELAY1'),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=100.0, freeze_s=30)

    assert decision.release is None
    assert decision.release_mode == 'n_minus_one_hold'
    assert decision.release_power_w == 2700
    assert decision.release_margin_w == 135
    assert decision.release_threshold_w == 2565
    assert decision.excess_consumption_w == 2564
    assert decision.explanation == (
        'Holding RELAY1; excess 2564 W below N-1 release threshold 2565 W'
    )


@pytest.mark.unit
def test_n_minus_one_release_uses_100_w_minimum_margin_for_small_load():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=-0.9,
        rpnz_w=500.0,
        targets=(
            _target('EV_CHARGER', priority=4, active=True, rank=1),
            _target(
                'SMALL_RELAY',
                priority=3,
                active=True,
                rank=2,
                threshold_w=1000,
                releasable_power_w=1000,
            ),
        ),
        active_device_ids=('EV_CHARGER', 'SMALL_RELAY'),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == 'SMALL_RELAY'
    assert decision.release_margin_w == 100
    assert decision.release_threshold_w == 900


@pytest.mark.unit
def test_n_minus_one_release_uses_activation_order_not_priority_order():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=-1.9,
        rpnz_w=500.0,
        targets=(
            _target(
                'HIGH_PRIORITY_EV',
                priority=5,
                active=True,
                rank=1,
                threshold_w=2000,
                releasable_power_w=2000,
            ),
            _target(
                'LOW_PRIORITY_RELAY',
                priority=2,
                active=True,
                rank=2,
                threshold_w=1000,
                releasable_power_w=1000,
            ),
        ),
        # LOW_PRIORITY_RELAY was activated first; HIGH_PRIORITY_EV was later
        # reactivated and is therefore the newest n-1 step.
        active_device_ids=('LOW_PRIORITY_RELAY', 'HIGH_PRIORITY_EV'),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == 'HIGH_PRIORITY_EV'
    assert decision.release_power_w == 2000
    assert decision.release_threshold_w == 1900


@pytest.mark.unit
def test_n_minus_one_release_waits_for_existing_measurement_freeze():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=120.0,
        rpc_kw=-2.7,
        rpnz_w=500.0,
        targets=(
            _target('EV_CHARGER', priority=4, active=True, rank=1),
            _target(
                'RELAY1',
                priority=3,
                active=True,
                rank=2,
                threshold_w=2700,
                releasable_power_w=2700,
            ),
        ),
        active_device_ids=('EV_CHARGER', 'RELAY1'),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=100.0, freeze_s=30)

    assert decision.release is None
    assert decision.explanation == 'Freeze active -> wait for measurements to settle'


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
        active_device_ids=(device_id,),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == device_id
    assert decision.release_mode == 'ineligible'
    assert decision.explanation == (
        f'{device_id} no longer eligible -> release dispatch state'
    )


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
        active_device_ids=('EV_CHARGER',),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=0.0)

    assert decision.release == 'EV_CHARGER'
    assert decision.activate is None
    assert decision.release_mode == 'ineligible'
    assert decision.explanation == (
        'EV_CHARGER no longer eligible -> release dispatch state'
    )


@pytest.mark.unit
def test_anchor_release_also_waits_for_measurement_freeze_after_n_minus_one_release():
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=120.0,
        rpc_kw=0.0,
        rpnz_w=0.0,
        targets=(
            _target('EV_CHARGER', priority=4, active=True, rank=1),
        ),
        active_device_ids=('EV_CHARGER',),
    )

    decision = compute_surplus_device_dispatch(inp, now_ts=100.0)

    assert decision.release is None
    assert decision.explanation == 'Freeze active -> wait for measurements to settle'
