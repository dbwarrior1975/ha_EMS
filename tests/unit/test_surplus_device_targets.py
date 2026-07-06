import pytest

from ems_adapter.config_loader import build_policy_context_view, compile_core_config_plan_from_grouped_config, load_grouped_ems_config
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
@pytest.mark.parametrize(
    ('device_id', 'max_solar_charge_w'),
    (
        ('EV_CHARGER', 3700),
        ('HOME_BATTERY', 3700),
    ),
)
def test_invalid_activation_value_is_not_replaced_by_device_derived_threshold(device_id, max_solar_charge_w):
    cfg = make_cfg(
        adjustable_surplus_activation=0,
        max_solar_charge_w=max_solar_charge_w,
        ev_min_absorb_w=1380,
        ev_max_absorb_w=6440,
    )

    targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id=device_id,
        adjustable_priority=4,
        adjustable_active=False,
        relay_candidates=_relay_candidates(),
    )

    adjustable = targets[0]
    assert adjustable.threshold_w == 0
    assert adjustable.threshold_source == 'configured_adjustable_surplus_activation_w'
    assert adjustable.incremental_surplus_threshold_w is None


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


@pytest.mark.unit
def test_core_config_view_second_ev_adjustable_target_does_not_materialize_selected_ev(project_root, monkeypatch):
    grouped = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped['ems']['devices']['EV_GARAGE'] = {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_regulation': True,
            'supports_residual_regulation': False,
            'uses_hard_off_lifecycle': True,
            'min_absorb_w': 'input_number.ems_ev_garage_min_power_w',
            'max_absorb_w': 'input_number.ems_ev_garage_max_power_w',
            'step_w': 'input_number.ems_ev_garage_power_step_w',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_ev_garage_priority',
            'surplus_allowed': 'input_boolean.ems_ev_garage_surplus_allowed',
            'force_on': 'input_boolean.ems_ev_garage_force_on',
            'low_pv_threshold_w': 'input_number.ems_ev_garage_low_pv_threshold_w',
            'hard_off_low_pv_cycles': 'input_number.ems_ev_garage_low_pv_cycles',
            'hard_off_release_cycles': 'input_number.ems_ev_garage_release_cycles',
        },
        'adapter': {
            'enabled': 'switch.ev_garage_enabled',
            'current_a': 'number.ev_garage_current_a',
            'current_step_a': 'input_number.ems_ev_garage_current_step_a',
            'phases': 'input_number.ems_ev_garage_phases',
            'voltage_v': 'input_number.ems_ev_garage_voltage_v',
        },
    }
    plan = compile_core_config_plan_from_grouped_config(grouped)
    values = {
        'input_number.ems_ev_garage_min_power_w': 1380,
        'input_number.ems_ev_garage_max_power_w': 3680,
        'input_number.ems_ev_garage_power_step_w': 460,
        'input_number.ems_surplus_ev_garage_priority': 4,
        'input_boolean.ems_ev_garage_surplus_allowed': True,
        'input_boolean.ems_ev_garage_force_on': False,
        'input_number.ems_ev_garage_low_pv_threshold_w': 1600,
        'input_number.ems_ev_garage_low_pv_cycles': 2,
        'input_number.ems_ev_garage_release_cycles': 2,
        'input_number.ems_ev_garage_current_step_a': 2,
        'input_number.ems_ev_garage_phases': 1,
        'input_number.ems_ev_garage_voltage_v': 230,
        'input_number.ems_adjustable_surplus_activation_w': 2300,
    }
    call_counts = {}

    def counting_build_ev(plan_arg, values_arg):
        device_id = str(plan_arg.device_id)
        call_counts[device_id] = int(call_counts.get(device_id, 0) or 0) + 1
        return real_build_ev(plan_arg, values_arg)

    real_build_ev = __import__('ems_adapter.config_loader', fromlist=['_build_view_ev_device'])._build_view_ev_device
    monkeypatch.setattr('ems_adapter.config_loader._build_view_ev_device', counting_build_ev)

    cfg = build_policy_context_view(plan, lambda entity_id, default: values.get(entity_id, default))
    targets = build_surplus_device_targets(
        cfg,
        adjustable_device_id='EV_GARAGE',
        adjustable_priority=4,
        adjustable_active=False,
        relay_candidates=(),
    )

    assert targets[0].device_id == 'EV_GARAGE'
    assert targets[0].threshold_w == 2300
    assert call_counts == {}
