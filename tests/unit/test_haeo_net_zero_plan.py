import pytest

from ems_adapter.config_loader import (
    build_core_config_from_grouped_reader,
    load_grouped_ems_config,
)
from ems_core.domain.models import ControlProfile, ForecastProfile, GoalProfile, GuardProfile
from ems_core.integrations.haeo_net_zero_plan import compute_haeo_net_zero_plan
from tests.helpers import ev_w, make_cfg, make_haeo, make_profiles


def _fresh_haeo(**overrides):
    data = dict(
        configured_forecast=ForecastProfile.HAEO,
        effective_forecast=ForecastProfile.HAEO,
        fresh=True,
    )
    data.update(overrides)
    return make_haeo(**data)


def _haeo_profiles(**overrides):
    data = dict(
        control=ControlProfile.HORIZON_BY_HAEO,
        goal=GoalProfile.NET_ZERO,
        forecast=ForecastProfile.NONE,
        guard=GuardProfile.NORMAL_LIMITS,
    )
    data.update(overrides)
    return make_profiles(**data)


def _core_cfg_with_selected_custom_ev(
    project_root,
    *,
    selected_ev_device_id='EV_GARAGE',
):
    grouped = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped['ems']['devices']['EV_GARAGE'] = {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_consuming_regulation': True,
            'supports_producing_regulation': False,
            'uses_hard_off_lifecycle': True,
            'min_absorb_w': 'input_number.ems_ev_garage_min_power_w',
            'max_absorb_w': 'input_number.ems_ev_garage_max_power_w',
            'min_produce_w': 0,
            'max_produce_w': 0,
            'step_w': 'input_number.ems_ev_garage_power_step_w',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_ev_garage_priority',
            'producing_priority': 0,
            'surplus_allowed': 'input_boolean.ems_ev_garage_surplus_allowed',
            'surplus_dispatch_mode': 'max_absorb',
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

    values = {
        'input_number.ems_deadband_w': 50,
        'input_number.ems_ramp_max_w': 5000,
        'input_number.ems_strict_limits_max_w': 4600,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_nz_battery_floor_default_w': 100,
        'input_number.ems_nz_battery_floor_ev_active_w': 0,
        'input_select.ems_primary_consuming_device': 'HOME_BATTERY',
        'input_number.ems_home_battery_min_absorb_w': 100,
        'input_number.ems_max_battery_charge_w': 3700,
        'input_number.ems_max_battery_discharge_w': 4000,
        'input_number.ems_home_battery_surplus_priority': 3,
        'input_number.ems_battery_protect_soc': 2,
        'input_number.ems_battery_protect_soc_recovery_margin': 1,
        'input_number.ems_battery_protect_min_cell_voltage_v': 3.03,
        'input_number.ems_battery_protect_charge_floor_w': 0,
        'input_number.ems_surplus_ev_priority': 3,
        'input_number.ems_ev_hard_off_pv_threshold_kw': 1.6,
        'input_number.ems_ev_hard_off_low_pv_cycles': 2,
        'input_number.ems_ev_hard_off_release_cycles': 2,
        'input_number.ems_ev_current_step_a': 2,
        'input_number.ems_ev_charger_phases': 1,
        'input_number.ems_ev_voltage_v': 230,
        'input_number.ems_surplus_relay1_priority': 2,
        'input_number.ems_relay1_nominal_absorb_w': 2500,
        'input_number.ems_relay1_power_kw': 2500,
        'input_number.ems_surplus_relay2_priority': 1,
        'input_number.ems_relay2_nominal_absorb_w': 5000,
        'input_number.ems_relay2_power_kw': 5000,
        'input_number.ems_ev_garage_min_power_w': 2300,
        'input_number.ems_ev_garage_max_power_w': 6900,
        'input_number.ems_ev_garage_power_step_w': 2300,
        'input_number.ems_surplus_ev_garage_priority': 4,
        'input_boolean.ems_ev_garage_surplus_allowed': True,
        'input_number.ems_ev_garage_low_pv_threshold_w': 1600,
        'input_number.ems_ev_garage_low_pv_cycles': 2,
        'input_number.ems_ev_garage_release_cycles': 2,
        'input_number.ems_ev_garage_current_step_a': 10,
        'input_number.ems_ev_garage_phases': 1,
        'input_number.ems_ev_garage_voltage_v': 230,
        'input_boolean.ems_ev_garage_force_on': False,
    }
    return build_core_config_from_grouped_reader(grouped, lambda entity_id, default: values.get(entity_id, default))


@pytest.mark.unit
def test_ev_larger_forecast_selects_ev_primary():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(ev_min_absorb_w=ev_w(4), ev_current_step_a=4),
        _fresh_haeo(device_target_kw_by_id={'HOME_BATTERY': 2.0, 'EV_CHARGER': 5.0}, device_age_s_by_id={'HOME_BATTERY': 0.0, 'EV_CHARGER': 0.0}),
        now_ts=0.0,
    )

    assert plan.active is True
    assert plan.primary_consuming_device_id == 'EV_CHARGER'
    assert plan.preferred_surplus_device_id == 'HOME_BATTERY'
    assert plan.device_limits_w == {'HOME_BATTERY': 2000, 'EV_CHARGER': 5000}
    assert plan.reason == 'largest_explicit_device_target'


@pytest.mark.unit
def test_battery_larger_forecast_selects_home_battery_primary():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(ev_min_absorb_w=ev_w(4), ev_current_step_a=4),
        _fresh_haeo(battery_target_kw=3.0, ev_target_kw=1.5),
        now_ts=0.0,
    )

    assert plan.active is True
    assert plan.primary_consuming_device_id == 'HOME_BATTERY'
    assert plan.preferred_surplus_device_id == 'EV_CHARGER'
    assert plan.device_limits_w == {'HOME_BATTERY': 3000, 'EV_CHARGER': 1500}
    assert not hasattr(plan, 'battery_limit_w')
    assert not hasattr(plan, 'ev_limit_w')
    assert plan.device_limits_w['HOME_BATTERY'] == 3000
    assert plan.device_limits_w['EV_CHARGER'] == 1500


@pytest.mark.unit
def test_tie_keeps_previous_primary_when_available():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(),
        _fresh_haeo(device_target_kw_by_id={'HOME_BATTERY': 2.0, 'EV_CHARGER': 2.0}, device_age_s_by_id={'HOME_BATTERY': 0.0, 'EV_CHARGER': 0.0}),
        now_ts=30.0,
        previous_quarter_key='0',
        previous_primary_consuming_device_id='EV_CHARGER',
    )
    assert plan.primary_consuming_device_id == 'EV_CHARGER'
    assert plan.preferred_surplus_device_id == 'HOME_BATTERY'
    assert plan.reason == 'tie_keep_previous'
    assert plan.changed is False


@pytest.mark.unit
def test_tie_keeps_previous_primary_consuming_device_id_when_available():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(),
        _fresh_haeo(device_target_kw_by_id={'HOME_BATTERY': 2.0, 'EV_CHARGER': 2.0}, device_age_s_by_id={'HOME_BATTERY': 0.0, 'EV_CHARGER': 0.0}),
        now_ts=30.0,
        previous_quarter_key='0',
        previous_primary_consuming_device_id='EV_CHARGER',
    )

    assert plan.primary_consuming_device_id == 'EV_CHARGER'
    assert plan.reason == 'tie_keep_previous'
    assert plan.changed is False


@pytest.mark.unit
def test_stale_forecast_disables_plan():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(),
        make_haeo(
            configured_forecast=ForecastProfile.HAEO,
            effective_forecast=ForecastProfile.NONE,
            fresh=False,
            battery_target_kw=3.0,
            ev_target_kw=1.5,
        ),
        now_ts=0.0,
    )

    assert plan.active is False
    assert plan.reason == 'forecast_not_effective'


@pytest.mark.unit
def test_wrong_guard_disables_plan():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(guard=GuardProfile.BATTERY_PROTECT),
        make_cfg(),
        _fresh_haeo(battery_target_kw=3.0, ev_target_kw=1.5),
        now_ts=0.0,
    )

    assert plan.active is False
    assert plan.reason == 'guard_not_normal_limits'


@pytest.mark.unit
def test_zero_forecast_disables_plan():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(),
        _fresh_haeo(battery_target_kw=0.0, ev_target_kw=0.0),
        now_ts=0.0,
    )

    assert plan.active is False
    assert plan.reason == 'zero_forecast'


@pytest.mark.unit
def test_limits_are_clamped_to_device_bounds():
    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        make_cfg(max_solar_charge_w=2500, ev_max_absorb_w=ev_w(10), ev_min_absorb_w=ev_w(4), ev_current_step_a=4),
        _fresh_haeo(battery_target_kw=6.0, ev_target_kw=9.0),
        now_ts=0.0,
    )

    assert plan.device_limits_w == {'HOME_BATTERY': 2500, 'EV_CHARGER': 2300}


@pytest.mark.unit
def test_custom_selected_ev_device_id_is_used_in_haeo_plan(project_root):
    cfg = _core_cfg_with_selected_custom_ev(project_root)

    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        cfg,
        _fresh_haeo(device_target_kw_by_id={'HOME_BATTERY': 2.0, 'EV_GARAGE': 5.0}, device_age_s_by_id={'HOME_BATTERY': 0.0, 'EV_GARAGE': 0.0}),
        now_ts=0.0,
    )

    assert plan.active is True
    assert plan.primary_consuming_device_id == 'EV_GARAGE'
    assert plan.preferred_surplus_device_id == 'HOME_BATTERY'
    assert plan.device_limits_w == {'HOME_BATTERY': 2000, 'EV_GARAGE': 5000}


@pytest.mark.unit
def test_custom_selected_ev_device_limit_cap_is_used(project_root):
    cfg = _core_cfg_with_selected_custom_ev(project_root)

    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        cfg,
        _fresh_haeo(device_target_kw_by_id={'HOME_BATTERY': 1.0, 'EV_GARAGE': 9.0}, device_age_s_by_id={'HOME_BATTERY': 0.0, 'EV_GARAGE': 0.0}),
        now_ts=0.0,
    )

    assert plan.primary_consuming_device_id == 'EV_GARAGE'
    assert plan.device_limits_w == {'HOME_BATTERY': 1000, 'EV_GARAGE': 6900}
    assert plan.device_limits_w['EV_GARAGE'] == 6900


@pytest.mark.unit
def test_tie_keeps_previous_custom_ev_primary_consuming_device_id(project_root):
    cfg = _core_cfg_with_selected_custom_ev(project_root)

    plan = compute_haeo_net_zero_plan(
        _haeo_profiles(),
        cfg,
        _fresh_haeo(device_target_kw_by_id={'HOME_BATTERY': 2.0, 'EV_GARAGE': 2.0}, device_age_s_by_id={'HOME_BATTERY': 0.0, 'EV_GARAGE': 0.0}),
        now_ts=30.0,
        previous_quarter_key='0',
        previous_primary_consuming_device_id='EV_GARAGE',
    )

    assert plan.primary_consuming_device_id == 'EV_GARAGE'
    assert plan.preferred_surplus_device_id == 'HOME_BATTERY'
    assert plan.reason == 'tie_keep_previous'
