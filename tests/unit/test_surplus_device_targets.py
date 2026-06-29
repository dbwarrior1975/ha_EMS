import pytest

from ems_core.net_zero.surplus_device_targets import build_surplus_device_targets
from tests.helpers import ev_w, make_cfg


def _relay_candidates(
    *,
    states=None,
):
    states = dict(states or {})
    first = dict(states.get('RELAY1') or {})
    second = dict(states.get('RELAY2') or {})
    return (
        {
            'device_id': 'RELAY1',
            'priority': 2,
            'threshold_w': 2500,
            'enabled': bool(first.get('enabled', True) and first.get('capable', True)),
            'force_on': bool(first.get('force_on', False)),
            'active': bool(first.get('active', False)),
        },
        {
            'device_id': 'RELAY2',
            'priority': 1,
            'threshold_w': 5000,
            'enabled': bool(second.get('enabled', True) and second.get('capable', True)),
            'force_on': bool(second.get('force_on', False)),
            'active': bool(second.get('active', False)),
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
        ev_min_absorb_w=ev_w(6),
        ev_max_absorb_w=ev_w(28),
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
    cfg = make_cfg()

    targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='EV_CHARGER',
        adjustable_priority=3,
        adjustable_active=False,
        relay_candidates=_relay_candidates(
            states={
                'RELAY1': {
                    'enabled': True,
                    'force_on': True,
                    'active': False,
                    'capable': False,
                },
            },
        ),
    )

    assert targets[1].device_id == 'RELAY1'
    assert targets[1].enabled is False
