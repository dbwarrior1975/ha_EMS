import pytest

from ems_core.domain.models import SurplusTargetConfig, SurplusDispatchInput
from ems_core.net_zero.surplus_allocator import (
    active_stack,
    next_target,
    release_target,
    compute_surplus_dispatch,
)


def _targets(*, r1_active=False, ev_active=False, r2_active=False,
             r1_enabled=True, ev_enabled=True, r2_enabled=True,
             r1_force=False, ev_force=False, r2_force=False):
    # Käyttötapaus: RELAY1 priority=3, EV priority=2, RELAY2 priority=1
    return (
        SurplusTargetConfig(
            name='RELAY1',
            priority=3,
            rank=1,
            threshold_kw=1.0,
            enabled=r1_enabled,
            force_on=r1_force,
            active=r1_active,
        ),
        SurplusTargetConfig(
            name='EV',
            priority=2,
            rank=2,
            threshold_kw=2.0,
            enabled=ev_enabled,
            force_on=ev_force,
            active=ev_active,
        ),
        SurplusTargetConfig(
            name='RELAY2',
            priority=1,
            rank=3,
            threshold_kw=3.0,
            enabled=r2_enabled,
            force_on=r2_force,
            active=r2_active,
        ),
    )


@pytest.mark.unit
def test_next_target_activation_order_respects_priority_3_2_1():
    t0 = _targets()
    assert next_target(t0).name == 'RELAY1'

    t1 = _targets(r1_active=True)
    assert next_target(t1).name == 'EV'

    t2 = _targets(r1_active=True, ev_active=True)
    assert next_target(t2).name == 'RELAY2'

    t3 = _targets(r1_active=True, ev_active=True, r2_active=True)
    assert next_target(t3) is None


@pytest.mark.unit
def test_release_target_release_order_is_reverse_priority():
    t_all = _targets(r1_active=True, ev_active=True, r2_active=True)
    assert release_target(t_all).name == 'RELAY2'

    t_after_r2 = _targets(r1_active=True, ev_active=True, r2_active=False)
    assert release_target(t_after_r2).name == 'EV'

    t_after_ev = _targets(r1_active=True, ev_active=False, r2_active=False)
    assert release_target(t_after_ev).name == 'RELAY1'

    t_none = _targets()
    assert release_target(t_none) is None


@pytest.mark.unit
def test_active_stack_orders_by_priority_desc():
    assert active_stack(_targets()) == 'NONE'
    assert active_stack(_targets(r1_active=True)) == 'RELAY1'
    assert active_stack(_targets(r1_active=True, ev_active=True)) == 'RELAY1 > EV'
    assert active_stack(_targets(r1_active=True, ev_active=True, r2_active=True)) == 'RELAY1 > EV > RELAY2'


@pytest.mark.unit
def test_compute_surplus_dispatch_activation_sequence():
    now = 1000.0

    # 1) none active -> activate RELAY1 first
    inp0 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_targets(),
    )
    dec0 = compute_surplus_dispatch(inp0, now_ts=now, freeze_s=30)
    assert dec0.activate == 'RELAY1'
    assert dec0.freeze_until_ts == now + 30

    # 2) after RELAY1 active & freeze expired -> activate EV next
    inp1 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=now,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_targets(r1_active=True),
    )
    dec1 = compute_surplus_dispatch(inp1, now_ts=now + 31, freeze_s=30)
    assert dec1.activate == 'EV'

    # 3) after RELAY1 + EV active & freeze expired -> activate RELAY2 next
    inp2 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=now,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_targets(r1_active=True, ev_active=True),
    )
    dec2 = compute_surplus_dispatch(inp2, now_ts=now + 62, freeze_s=30)
    assert dec2.activate == 'RELAY2'


@pytest.mark.unit
def test_compute_surplus_dispatch_release_sequence_when_rpnz_nonpositive():
    now = 1000.0
    all_active = _targets(r1_active=True, ev_active=True, r2_active=True)

    inp0 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=0.0,
        targets=all_active,
    )
    dec0 = compute_surplus_dispatch(inp0, now_ts=now, freeze_s=30)
    assert dec0.release == 'RELAY2'

    two_active = _targets(r1_active=True, ev_active=True, r2_active=False)
    inp1 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=-100.0,
        targets=two_active,
    )
    dec1 = compute_surplus_dispatch(inp1, now_ts=now, freeze_s=30)
    assert dec1.release == 'EV'

    one_active = _targets(r1_active=True, ev_active=False, r2_active=False)
    inp2 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=-100.0,
        targets=one_active,
    )
    dec2 = compute_surplus_dispatch(inp2, now_ts=now, freeze_s=30)
    assert dec2.release == 'RELAY1'


@pytest.mark.unit
def test_policy_inactive_clears_all():
    now = 1000.0
    inp = SurplusDispatchInput(
        policy_active=False,
        freeze_until_ts=None,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_targets(r1_active=True, ev_active=True),
    )
    dec = compute_surplus_dispatch(inp, now_ts=now, freeze_s=30)
    assert dec.clear_all is True
    assert dec.freeze_until_ts == now


@pytest.mark.unit
def test_freeze_blocks_new_activation():
    now = 1000.0
    inp = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=now + 20,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_targets(r1_active=True),
    )
    dec = compute_surplus_dispatch(inp, now_ts=now, freeze_s=30)
    assert dec.activate is None
    assert dec.release is None
    assert 'Freeze active' in dec.explanation


@pytest.mark.unit
def test_active_target_no_longer_eligible_releases_it():
    now = 1000.0

    # Active but force_on toggled on -> allocator releases latch
    inp_force = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_targets(r1_active=True, r1_force=True),
    )
    dec_force = compute_surplus_dispatch(inp_force, now_ts=now, freeze_s=30)
    assert dec_force.release == 'RELAY1'

    # Active but disabled -> allocator releases latch
    inp_disabled = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_targets(ev_active=True, ev_enabled=False),
    )
    dec_disabled = compute_surplus_dispatch(inp_disabled, now_ts=now, freeze_s=30)
    assert dec_disabled.release == 'EV'
