import pytest

from ems_core.net_zero.surplus_device_targets import (
    build_surplus_device_targets,
    device_dispatch_to_legacy_dispatch,
    device_target_to_legacy_target,
)
from ems_core.domain.models import SurplusDispatchDecision
from tests.helpers import make_cfg


def _relay_candidates(
    *,
    relay1_enabled=True,
    relay1_force_on=False,
    relay1_active=False,
    relay1_capable=True,
    relay2_enabled=True,
    relay2_force_on=False,
    relay2_active=False,
    relay2_capable=True,
):
    return (
        {
            'device_id': 'RELAY1',
            'priority': 2,
            'threshold_w': 2500,
            'enabled': bool(relay1_enabled and relay1_capable),
            'force_on': bool(relay1_force_on),
            'active': bool(relay1_active),
        },
        {
            'device_id': 'RELAY2',
            'priority': 1,
            'threshold_w': 5000,
            'enabled': bool(relay2_enabled and relay2_capable),
            'force_on': bool(relay2_force_on),
            'active': bool(relay2_active),
        },
    )


@pytest.mark.unit
def test_ev_adjustable_device_target_uses_ev_power_delta_when_no_explicit_activation():
    cfg = make_cfg(
        adjustable_surplus_activation=0,
        adjustable_surplus_load_priority=4,
    )

    targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='EV_CHARGER',
        adjustable_priority=4,
        adjustable_active=False,
        relay_candidates=_relay_candidates(),
    )

    adjustable = targets[0]
    assert adjustable.device_id == 'EV_CHARGER'
    assert adjustable.decision_name == 'ADJUSTABLE'
    assert adjustable.priority == 4
    assert adjustable.rank == 1
    assert adjustable.threshold_w == 5060
    assert adjustable.threshold_source == 'ev_incremental_max_minus_min_absorb_w'
    assert adjustable.incremental_surplus_threshold_w == 5060
    assert adjustable.active is False


@pytest.mark.unit
def test_home_battery_adjustable_device_target_uses_max_solar_charge_when_no_explicit_activation():
    cfg = make_cfg(
        adjustable_surplus_activation=0,
        max_solar_charge_w=3700,
        adjustable_surplus_load_priority=3,
    )

    targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='HOME_BATTERY',
        adjustable_priority=3,
        adjustable_active=True,
        relay_candidates=_relay_candidates(),
    )

    adjustable = targets[0]
    assert adjustable.device_id == 'HOME_BATTERY'
    assert adjustable.threshold_w == 3700
    assert adjustable.threshold_source == 'max_solar_charge_w'
    assert adjustable.incremental_surplus_threshold_w is None
    assert adjustable.active is True


@pytest.mark.unit
def test_explicit_adjustable_activation_overrides_device_default_threshold():
    cfg = make_cfg(
        adjustable_surplus_activation=2000,
        max_solar_charge_w=3700,
        ev_min_current_a=6,
        ev_max_current_a=28,
        ev_charger_phases=1,
    )

    ev_targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='EV_CHARGER',
        adjustable_priority=2,
        adjustable_active=False,
        relay_candidates=_relay_candidates(),
    )
    battery_targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='HOME_BATTERY',
        adjustable_priority=2,
        adjustable_active=False,
        relay_candidates=_relay_candidates(),
    )

    assert ev_targets[0].threshold_w == 2000
    assert ev_targets[0].threshold_source == 'configured_adjustable_surplus_activation_w'
    assert ev_targets[0].incremental_surplus_threshold_w is None
    assert battery_targets[0].threshold_w == 2000
    assert battery_targets[0].threshold_source == 'configured_adjustable_surplus_activation_w'


@pytest.mark.unit
def test_adjustable_target_is_disabled_when_device_cannot_absorb():
    cfg = make_cfg(adjustable_surplus_activation=2000)

    targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='HOME_BATTERY',
        adjustable_priority=3,
        adjustable_active=False,
        adjustable_enabled=False,
        relay_candidates=_relay_candidates(),
    )

    assert targets[0].device_id == 'HOME_BATTERY'
    assert targets[0].enabled is False


@pytest.mark.unit
def test_relay_target_is_disabled_when_device_cannot_absorb():
    cfg = make_cfg(relay1_power_kw=2.5)

    targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='EV_CHARGER',
        adjustable_priority=3,
        adjustable_active=False,
        relay_candidates=_relay_candidates(
            relay1_enabled=True,
            relay1_force_on=True,
            relay1_active=False,
            relay1_capable=False,
        ),
    )

    assert targets[1].device_id == 'RELAY1'
    assert targets[1].enabled is False


@pytest.mark.unit
def test_device_target_export_mapping_preserves_threshold_and_state():
    cfg = make_cfg(relay1_power_kw=2.5)
    relay1 = build_surplus_device_targets(
        cfg,
        adjustable_device_id='EV_CHARGER',
        adjustable_priority=2,
        adjustable_active=False,
        relay_candidates=_relay_candidates(
            relay1_enabled=False,
            relay1_force_on=True,
            relay1_active=True,
        ),
    )[1]

    legacy = device_target_to_legacy_target(relay1)

    assert legacy.name == 'RELAY1'
    assert legacy.priority == relay1.priority
    assert legacy.rank == relay1.rank
    assert legacy.threshold_kw == 2.5
    assert legacy.enabled is False
    assert legacy.force_on is True
    assert legacy.active is True


@pytest.mark.unit
def test_device_dispatch_export_mapping_maps_device_id_to_decision_name():
    cfg = make_cfg(adjustable_surplus_load='EV_CHARGER', adjustable_surplus_activation=2000)
    targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='EV_CHARGER',
        adjustable_priority=3,
        adjustable_active=False,
        relay_candidates=_relay_candidates(),
    )

    legacy = device_dispatch_to_legacy_dispatch(
        SurplusDispatchDecision(activate='EV_CHARGER', freeze_until_ts=35.0),
        targets,
    )

    assert legacy.activate == 'ADJUSTABLE'
    assert legacy.release is None
    assert legacy.freeze_until_ts == 35.0
