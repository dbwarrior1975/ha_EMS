import pytest
from ems_core.domain.models import ControlProfile, GoalProfile, GuardProfile, DominantLimitation, ForecastProfile
from ems_core.domain.ev_power import ev_min_power_w
from ems_core.net_zero.engine import compute_net_zero_engine_outputs
from ems_adapter.config_loader import (
    build_core_config_from_grouped_reader,
    build_policy_context_view,
    compile_core_config_plan_from_grouped_config,
    load_grouped_ems_config,
)
from tests.helpers import cfg_ev_min_a, ev_state, ev_w, make_profiles, make_cfg, make_m, make_haeo, make_nz


def _relay_runtime_args(
    *,
    surplus_allowed=True,
    active_device_ids=(),
    forced_device_ids=(),
    previous_force_on_device_ids=(),
    relay_device_states=None,
):
    states = {
        'RELAY1': {
            'surplus_allowed': bool(surplus_allowed),
            'force_on': 'RELAY1' in forced_device_ids,
            'active': 'RELAY1' in active_device_ids,
        },
        'RELAY2': {
            'surplus_allowed': bool(surplus_allowed),
            'force_on': 'RELAY2' in forced_device_ids,
            'active': 'RELAY2' in active_device_ids,
        },
    }
    for device_id, state_overrides in (relay_device_states or {}).items():
        states.setdefault(str(device_id), {}).update(state_overrides or {})
    return {
        'relay_device_states': states,
        'previous_force_on_device_ids': tuple(previous_force_on_device_ids),
    }


def _core_cfg_with_capability_overrides(project_root, value_overrides=None, **device_capability_overrides):
    grouped = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    for device_id, overrides in device_capability_overrides.items():
        grouped['ems']['devices'][device_id]['capabilities'].update(overrides)

    values = {
        'input_number.ems_deadband_w': 50,
        'input_number.ems_ramp_max_w': 5000,
        'input_number.ems_strict_limits_max_w': 4600,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_nz_battery_floor_default_w': 100,
        'input_number.ems_nz_battery_floor_ev_active_w': 0,
        'input_select.ems_adjustable_surplus_load': 'EV_CHARGER',
        'input_select.ems_adjustable_primary_load': 'HOME_BATTERY',
        'input_number.ems_adjustable_surplus_activation_w': 2000,
        'input_number.ems_home_battery_min_absorb_w': 100,
        'input_number.ems_max_battery_charge_w': 3700,
        'input_number.ems_max_battery_discharge_w': 4000,
        'input_number.ems_adjustable_surplus_load_priority': 3,
        'input_number.ems_battery_protect_soc': 2,
        'input_number.ems_battery_protect_soc_recovery_margin': 1,
        'input_number.ems_battery_protect_min_cell_voltage_v': 3.03,
        'input_number.ems_battery_protect_charge_floor_w': 0,
        'input_number.ems_surplus_ev_priority': 3,
        'input_number.ems_ev_hard_off_pv_threshold_kw': 1.6,
        'input_number.ems_ev_hard_off_low_pv_cycles': 2,
        'input_number.ems_ev_hard_off_release_cycles': 2,
        'input_number.ems_ev_min_power_w': 1380,
        'input_number.ems_ev_max_power_w': 3680,
        'input_number.ems_ev_current_step_a': 2,
        'input_number.ems_ev_charger_phases': 1,
        'input_number.ems_ev_voltage_v': 230,
        'input_boolean.ems_ev_force_on': False,
        'input_number.ems_surplus_relay1_priority': 2,
        'input_number.ems_relay1_nominal_absorb_w': 2500,
        'input_number.ems_relay1_power_kw': 2500,
        'input_number.ems_surplus_relay2_priority': 1,
        'input_number.ems_relay2_nominal_absorb_w': 5000,
        'input_number.ems_relay2_power_kw': 5000,
    }
    values.update(value_overrides or {})
    return build_core_config_from_grouped_reader(grouped, lambda entity_id, default: values.get(entity_id, default))


def _core_cfg_with_extra_devices(
    project_root,
    *,
    extra_devices=None,
    value_overrides=None,
):
    grouped = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    for device_id, device in (extra_devices or {}).items():
        grouped['ems']['devices'][device_id] = device

    values = {
        'input_number.ems_deadband_w': 50,
        'input_number.ems_ramp_max_w': 5000,
        'input_number.ems_strict_limits_max_w': 4600,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_nz_battery_floor_default_w': 100,
        'input_number.ems_nz_battery_floor_ev_active_w': 0,
        'input_select.ems_adjustable_surplus_load': 'EV_CHARGER',
        'input_select.ems_adjustable_primary_load': 'HOME_BATTERY',
        'input_number.ems_adjustable_surplus_activation_w': 2000,
        'input_number.ems_home_battery_min_absorb_w': 100,
        'input_number.ems_max_battery_charge_w': 3700,
        'input_number.ems_max_battery_discharge_w': 4000,
        'input_number.ems_adjustable_surplus_load_priority': 3,
        'input_number.ems_battery_protect_soc': 2,
        'input_number.ems_battery_protect_soc_recovery_margin': 1,
        'input_number.ems_battery_protect_min_cell_voltage_v': 3.03,
        'input_number.ems_battery_protect_charge_floor_w': 0,
        'input_number.ems_surplus_ev_priority': 3,
        'input_number.ems_ev_hard_off_pv_threshold_kw': 1.6,
        'input_number.ems_ev_hard_off_low_pv_cycles': 2,
        'input_number.ems_ev_hard_off_release_cycles': 2,
        'input_number.ems_ev_min_power_w': 1380,
        'input_number.ems_ev_max_power_w': 3680,
        'input_number.ems_ev_current_step_a': 2,
        'input_number.ems_ev_charger_phases': 1,
        'input_number.ems_ev_voltage_v': 230,
        'input_boolean.ems_ev_force_on': False,
        'input_number.ems_surplus_relay1_priority': 2,
        'input_number.ems_relay1_nominal_absorb_w': 2500,
        'input_number.ems_relay1_power_kw': 2500,
        'input_number.ems_surplus_relay2_priority': 1,
        'input_number.ems_relay2_nominal_absorb_w': 5000,
        'input_number.ems_relay2_power_kw': 5000,
    }
    values.update(value_overrides or {})
    return build_core_config_from_grouped_reader(grouped, lambda entity_id, default: values.get(entity_id, default))


def _core_cfg_without_ev_devices(
    project_root,
    *,
    value_overrides=None,
):
    grouped = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped['ems']['devices'] = {
        device_id: device
        for device_id, device in grouped['ems']['devices'].items()
        if device.get('kind') != 'EV_CHARGER'
    }

    values = {
        'input_number.ems_deadband_w': 50,
        'input_number.ems_ramp_max_w': 5000,
        'input_number.ems_strict_limits_max_w': 4600,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_nz_battery_floor_default_w': 100,
        'input_number.ems_nz_battery_floor_ev_active_w': 0,
        'input_select.ems_adjustable_surplus_load': 'HOME_BATTERY',
        'input_select.ems_adjustable_primary_load': '',
        'input_number.ems_adjustable_surplus_activation_w': 2000,
        'input_number.ems_home_battery_min_absorb_w': 100,
        'input_number.ems_max_battery_charge_w': 3700,
        'input_number.ems_max_battery_discharge_w': 4000,
        'input_number.ems_adjustable_surplus_load_priority': 3,
        'input_number.ems_battery_protect_soc': 2,
        'input_number.ems_battery_protect_soc_recovery_margin': 1,
        'input_number.ems_battery_protect_min_cell_voltage_v': 3.03,
        'input_number.ems_battery_protect_charge_floor_w': 0,
        'input_number.ems_surplus_relay1_priority': 2,
        'input_number.ems_relay1_nominal_absorb_w': 2500,
        'input_number.ems_relay1_power_kw': 2500,
        'input_number.ems_surplus_relay2_priority': 1,
        'input_number.ems_relay2_nominal_absorb_w': 5000,
        'input_number.ems_relay2_power_kw': 5000,
    }
    values.update(value_overrides or {})
    return build_core_config_from_grouped_reader(grouped, lambda entity_id, default: values.get(entity_id, default))


def _core_cfg_view_with_extra_devices(
    project_root,
    *,
    extra_devices=None,
    value_overrides=None,
):
    grouped = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    for device_id, device in (extra_devices or {}).items():
        grouped['ems']['devices'][device_id] = device

    values = {
        'input_number.ems_deadband_w': 50,
        'input_number.ems_ramp_max_w': 5000,
        'input_number.ems_strict_limits_max_w': 4600,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_nz_battery_floor_default_w': 100,
        'input_number.ems_nz_battery_floor_ev_active_w': 0,
        'input_select.ems_adjustable_surplus_load': 'EV_CHARGER',
        'input_select.ems_adjustable_primary_load': 'HOME_BATTERY',
        'input_number.ems_adjustable_surplus_activation_w': 2000,
        'input_number.ems_home_battery_min_absorb_w': 100,
        'input_number.ems_max_battery_charge_w': 3700,
        'input_number.ems_max_battery_discharge_w': 4000,
        'input_number.ems_adjustable_surplus_load_priority': 3,
        'input_number.ems_battery_protect_soc': 2,
        'input_number.ems_battery_protect_soc_recovery_margin': 1,
        'input_number.ems_battery_protect_min_cell_voltage_v': 3.03,
        'input_number.ems_battery_protect_charge_floor_w': 0,
        'input_number.ems_surplus_ev_priority': 3,
        'input_number.ems_ev_hard_off_pv_threshold_kw': 1.6,
        'input_number.ems_ev_hard_off_low_pv_cycles': 2,
        'input_number.ems_ev_hard_off_release_cycles': 2,
        'input_number.ems_ev_min_power_w': 1380,
        'input_number.ems_ev_max_power_w': 3680,
        'input_number.ems_ev_current_step_a': 2,
        'input_number.ems_ev_charger_phases': 1,
        'input_number.ems_ev_voltage_v': 230,
        'input_boolean.ems_ev_force_on': False,
        'input_number.ems_surplus_relay1_priority': 2,
        'input_number.ems_relay1_nominal_absorb_w': 2500,
        'input_number.ems_relay1_power_kw': 2500,
        'input_number.ems_surplus_relay2_priority': 1,
        'input_number.ems_relay2_nominal_absorb_w': 5000,
        'input_number.ems_relay2_power_kw': 5000,
    }
    values.update(value_overrides or {})
    plan = compile_core_config_plan_from_grouped_config(grouped)
    return build_policy_context_view(plan, lambda entity_id, default: values.get(entity_id, default))


def _garage_ev_device_config():
    return {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'min_absorb_w': 'input_number.garage_ev_min_power_w',
            'max_absorb_w': 'input_number.garage_ev_max_power_w',
            'step_w': 'input_number.garage_ev_power_step_w',
        },
        'policy': {
            'priority': 'input_number.garage_ev_priority',
            'surplus_allowed': 'input_boolean.garage_ev_surplus_allowed',
            'force_on': 'input_boolean.garage_ev_force_on',
            'low_pv_threshold_w': 'input_number.garage_ev_low_pv_threshold_w',
            'hard_off_low_pv_cycles': 'input_number.garage_ev_low_pv_cycles',
            'hard_off_release_cycles': 'input_number.garage_ev_release_cycles',
        },
        'adapter': {
            'enabled': 'switch.garage_ev_enabled',
            'current_a': 'number.garage_ev_current_a',
            'current_step_a': 'input_number.garage_ev_current_step_a',
            'phases': 'input_number.garage_ev_phases',
            'voltage_v': 'input_number.garage_ev_voltage_v',
        },
    }


def _garage_ev_value_overrides(*, adjustable_surplus_load='GARAGE_EV', adjustable_primary_load='HOME_BATTERY'):
    return {
        'input_select.ems_adjustable_surplus_load': adjustable_surplus_load,
        'input_select.ems_adjustable_primary_load': adjustable_primary_load,
        'input_number.garage_ev_min_power_w': 1380,
        'input_number.garage_ev_max_power_w': 3680,
        'input_number.garage_ev_power_step_w': 460,
        'input_number.garage_ev_priority': 4,
        'input_boolean.garage_ev_surplus_allowed': True,
        'input_boolean.garage_ev_force_on': False,
        'input_number.garage_ev_low_pv_threshold_w': 1600,
        'input_number.garage_ev_low_pv_cycles': 2,
        'input_number.garage_ev_release_cycles': 2,
        'input_number.garage_ev_current_step_a': 2,
        'input_number.garage_ev_phases': 1,
        'input_number.garage_ev_voltage_v': 230,
        'input_boolean.garage_ev_force_on': False,
    }


@pytest.mark.unit
def test_engine_manual_disables_battery_write_and_keeps_current_battery_setpoint():
    profiles = make_profiles(control=ControlProfile.MANUAL, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=650)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.battery_target_w == 650
    assert out.battery_write_enabled is False
    assert out.dominant_limitation == DominantLimitation.USER_MANUAL_OVERRIDE


@pytest.mark.unit
def test_engine_manual_safe_without_guard_clamp_keeps_current_and_write_disabled():
    profiles = make_profiles(control=ControlProfile.MANUAL_SAFE, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=444)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.battery_target_w == 444
    assert out.battery_write_enabled is False


@pytest.mark.unit
def test_engine_manual_safe_clamps_in_battery_protect():
    profiles = make_profiles(control=ControlProfile.MANUAL_SAFE, guard=GuardProfile.BATTERY_PROTECT)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=-500)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.battery_target_w == 0
    assert out.battery_write_enabled is True


@pytest.mark.unit
def test_engine_battery_protect_applies_configured_charge_floor():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.BATTERY_PROTECT)
    cfg = make_cfg(battery_protect_charge_floor_w=100, deadband_w=0, ramp_max_w=10000)
    m = make_m(grid_power_w=200, current_battery_setpoint_w=-100)
    nz = make_nz(rpnz_w=-1)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )

    assert out.battery_target_w == 100
    assert out.battery_write_enabled is True


@pytest.mark.unit
def test_engine_respects_max_solar_charge_limit_in_net_zero():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(max_solar_charge_w=500, deadband_w=0, ramp_max_w=5000)
    m = make_m(grid_power_w=-3000, current_battery_setpoint_w=0)
    nz = make_nz(rpnz_w=2500)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.battery_target_w <= 500
    assert out.battery_write_enabled is True


@pytest.mark.unit
def test_engine_normal_limits_caps_discharge_with_max_battery_discharge_w():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(max_battery_discharge_w=4600, deadband_w=0, ramp_max_w=10000, max_solar_charge_w=10000)
    m = make_m(grid_power_w=4000, current_battery_setpoint_w=-4500)
    nz = make_nz(rpnz_w=-7000)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )

    assert out.battery_target_w == -4600
    assert out.battery_write_enabled is True


@pytest.mark.unit
def test_engine_normal_limits_caps_discharge_with_negative_canonical_limit():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(max_battery_discharge_w=-4600, deadband_w=0, ramp_max_w=10000, max_solar_charge_w=10000)
    m = make_m(grid_power_w=4000, current_battery_setpoint_w=-4500)
    nz = make_nz(rpnz_w=-7000)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )

    assert out.battery_target_w == -4600
    assert out.attrs['discharge_limit_w'] == 4600
    assert out.attrs['discharge_limit_sign_mode'] == 'canonical_negative'


@pytest.mark.unit
def test_engine_trace_attrs_contain_authority_flag():
    profiles = make_profiles(control=ControlProfile.MANUAL)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=100)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.attrs['battery_write_enabled'] is False


@pytest.mark.unit
def test_engine_trace_attrs_contain_ev_power_normalization():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        ev_min_absorb_w=ev_w(6, phases=3),
        ev_max_absorb_w=ev_w(16, phases=3),
        ev_current_step_a=4,
        ev_charger_phases=3,
    )
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=10)})

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=2000.0), 0.0,
        freeze_until_ts=None,
        ev_burn_active=True,
        **_relay_runtime_args(),
        adjustable_surplus_active=True,
    )

    assert out.attrs['ev_min_power_w'] == 4140
    assert out.attrs['ev_max_power_w'] == 11040
    assert out.attrs['ev_power_step_w'] == 2760
    assert out.attrs['ev_target_w'] == 11040


@pytest.mark.unit
def test_engine_selected_ev_context_uses_normalized_power_step_without_partial_cfg_helper(project_root):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides={
            **_garage_ev_value_overrides(),
            'input_select.ems_adjustable_surplus_load': 'GARAGE_EV',
            'input_number.garage_ev_power_step_w': 0,
            'input_number.garage_ev_current_step_a': 1.0,
            'input_number.garage_ev_phases': 1.0,
            'input_number.garage_ev_voltage_v': 230.0,
        },
    )

    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(ev_states={'GARAGE_EV': ev_state(enabled=True, current_a=6)}),
        make_haeo(),
        make_nz(rpnz_w=2000.0),
        0.0,
        freeze_until_ts=None,
        ev_burn_active=True,
        **_relay_runtime_args(),
        adjustable_surplus_active=True,
    )

    assert out.attrs['selected_ev_device_id'] == 'GARAGE_EV'
    assert out.attrs['ev_power_step_w'] == 230
    assert out.attrs['ev_min_power_w'] == 1380
    assert out.attrs['ev_max_power_w'] == 3680


@pytest.mark.unit
def test_engine_ev_surplus_burn_max_target_does_not_require_measured_current_at_max():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        ev_min_absorb_w=ev_w(6, phases=3),
        ev_max_absorb_w=ev_w(16, phases=3),
        ev_current_step_a=4,
        ev_charger_phases=3,
    )
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=0)})

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=2000.0), 0.0,
        freeze_until_ts=None,
        ev_burn_active=True,
        **_relay_runtime_args(),
        adjustable_surplus_active=True,
    )

    assert out.attrs['ev_target_w'] == 11040


@pytest.mark.unit
def test_engine_trace_attrs_contain_device_policies_with_watt_based_ev_contract():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        ev_min_absorb_w=ev_w(6, phases=3),
        ev_max_absorb_w=ev_w(16, phases=3),
        ev_charger_phases=3,
    )
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=10)})

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=2000.0), 0.0,
        freeze_until_ts=None,
        ev_burn_active=True,
        **_relay_runtime_args(active_device_ids=('RELAY1',)),
        adjustable_surplus_active=True,
    )

    policies = {item['device_id']: item for item in out.attrs['device_policies']}
    policies_from_output = {policy.device_id: policy for policy in out.device_policies}

    assert policies_from_output['HOME_BATTERY'].target_w == out.battery_target_w
    assert policies_from_output['HOME_BATTERY'].enabled is out.battery_write_enabled
    assert policies_from_output['RELAY1'].enabled is True
    assert policies_from_output['RELAY2'].enabled is False
    assert policies['HOME_BATTERY']['target_w'] == out.battery_target_w
    assert policies['HOME_BATTERY']['enabled'] is out.battery_write_enabled
    assert policies['EV_CHARGER']['target_w'] == out.attrs['ev_target_w']
    assert policies['EV_CHARGER']['enabled'] is True
    assert policies['RELAY1']['target_w'] == 2500
    assert policies['RELAY1']['enabled'] is True
    assert policies['RELAY2']['target_w'] == 0
    assert policies['RELAY2']['enabled'] is False


@pytest.mark.unit
def test_engine_relay_policies_include_registry_relays_without_direct_alias_dependency(project_root):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={
            'RELAY3': {
                'kind': 'RELAY',
                'capabilities': {
                    'can_absorb_w': True,
                    'can_produce_w': False,
                    'min_absorb_w': 'input_number.ems_relay3_nominal_absorb_w',
                    'max_absorb_w': 'input_number.ems_relay3_power_w',
                    'step_w': 'input_number.ems_relay3_power_w',
                },
                'policy': {
                    'priority': 'input_number.ems_surplus_relay3_priority',
                    'surplus_allowed': 'input_boolean.ems_relay3_enabled_import_zero',
                    'force_on': 'input_boolean.ems_relay3_force_on',
                },
                'adapter': {
                    'enabled': 'switch.relay_3_2',
                },
            },
        },
        value_overrides={
            'input_number.ems_relay3_nominal_absorb_w': 750,
            'input_number.ems_relay3_power_w': 750,
            'input_number.ems_surplus_relay3_priority': 4,
            'input_boolean.ems_relay3_enabled_import_zero': True,
            'input_boolean.ems_relay3_force_on': False,
        },
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(), make_nz(rpnz_w=100.0, required_power_consumption_kw=0.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(
            surplus_allowed=False,
            relay_device_states={
                'RELAY3': {'surplus_allowed': True, 'force_on': False, 'active': True},
            },
        ),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    targets = {target['device_id']: target for target in out.attrs['surplus_device_targets']}

    assert out.attrs['relay_device_ids'] == ('RELAY1', 'RELAY2', 'RELAY3')
    assert targets['RELAY3']['enabled'] is True
    assert targets['RELAY3']['active'] is True
    assert targets['RELAY3']['threshold_w'] == 750
    assert policies['RELAY1'].enabled is False
    assert policies['RELAY2'].enabled is False
    assert policies['RELAY3'].enabled is True
    assert policies['RELAY3'].target_w == 750
    assert {item['device_id'] for item in out.attrs['device_policies']} >= {'RELAY1', 'RELAY2', 'RELAY3'}


@pytest.mark.unit
def test_engine_surplus_device_trace_matches_current_activation_mapping():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        adjustable_primary_load='HOME_BATTERY',
        adjustable_surplus_activation=2000,
        ev_min_absorb_w=ev_w(4),
        ev_max_absorb_w=ev_w(28),
        ev_charger_phases=1,
    )
    m = make_m()

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500, required_power_consumption_kw=2.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
    )

    assert out.surplus_dispatch_decision == 'ACTIVATE_ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_decision'] == 'ACTIVATE_ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_action'] == 'ACTIVATE'
    assert out.attrs['surplus_device_dispatch_target'] == 'ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_dispatch_contract'] == 'device_id_primary'
    assert out.attrs['surplus_device_next_target'] == 'ADJUSTABLE'
    assert out.attrs['surplus_device_next_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_active_stack'] == 'NONE'
    assert out.attrs['surplus_device_targets'][0]['threshold_w'] == 2000
    assert out.attrs['surplus_device_targets'][0]['threshold_source'] == 'configured_adjustable_surplus_activation_w'


@pytest.mark.unit
def test_engine_cheap_grid_charge_local_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.CHEAP_GRID_CHARGE, forecast=ForecastProfile.NONE)
    cfg = make_cfg()
    m = make_m()
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.battery_target_w == 100
    assert out.explanation == 'Local cheap-charge policy'


@pytest.mark.unit
def test_engine_cheap_grid_charge_haeo_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.CHEAP_GRID_CHARGE, forecast=ForecastProfile.HAEO)
    cfg = make_cfg()
    m = make_m()
    haeo = make_haeo(
        effective_forecast=ForecastProfile.HAEO,
        configured_forecast=ForecastProfile.HAEO,
        fresh=True,
        battery_target_kw=1.234,
    )
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, haeo, make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.battery_target_w == 1234
    assert out.explanation == 'Cheap charge policy with HAEO forecast assistance'


@pytest.mark.unit
def test_engine_max_export_local_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.MAX_EXPORT, forecast=ForecastProfile.NONE)
    cfg = make_cfg()
    m = make_m()
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.battery_target_w == -4000
    assert out.explanation == 'Local export-oriented policy'


@pytest.mark.unit
def test_engine_max_export_force_on_keeps_ev_at_max_power():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.MAX_EXPORT, forecast=ForecastProfile.NONE)
    cfg = make_cfg(
        ev_force_on=True,
        ev_min_absorb_w=ev_w(6),
        ev_max_absorb_w=ev_w(16),
        ev_charger_phases=1,
        ev_voltage_v=230,
    )
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=0)})

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['ev_force_on'] is True
    assert out.attrs['ev_policy_mode'] == 'burn'
    assert out.attrs['ev_target_w'] == 3680
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].target_w == 3680


@pytest.mark.unit
def test_engine_force_on_uses_ev_capability_max_w_not_top_level_current_alias(project_root):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.MAX_EXPORT, forecast=ForecastProfile.NONE)
    cfg = _core_cfg_with_capability_overrides(
        project_root,
        value_overrides={
            'input_boolean.ems_ev_force_on': True,
        },
        EV_CHARGER={'max_absorb_w': 5000, 'step_w': 500},
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=0)}), make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['ev_target_w'] == 5000
    assert policies['EV_CHARGER'].target_w == 5000


@pytest.mark.unit
def test_engine_max_export_haeo_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.MAX_EXPORT, forecast=ForecastProfile.HAEO)
    cfg = make_cfg()
    m = make_m()
    haeo = make_haeo(
        effective_forecast=ForecastProfile.HAEO,
        configured_forecast=ForecastProfile.HAEO,
        fresh=True,
        battery_target_kw=-2.5,
    )
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, haeo, make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    assert out.battery_target_w == -2500
    assert out.explanation == 'Export-oriented policy with HAEO forecast assistance'


@pytest.mark.unit
def test_engine_blocks_max_export_when_battery_cannot_produce(project_root):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.MAX_EXPORT, forecast=ForecastProfile.NONE)
    cfg = _core_cfg_with_capability_overrides(project_root, HOME_BATTERY={'can_produce_w': False})

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.battery_target_w == 0
    assert policies['HOME_BATTERY'].target_w == 0
    assert policies['HOME_BATTERY'].reason == 'capability_blocked_produce'
    assert 'HOME_BATTERY:capability_blocked_produce' in out.attrs['capability_blocked_devices']


@pytest.mark.unit
def test_engine_disables_ev_adjustable_when_ev_cannot_absorb(project_root):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = _core_cfg_with_capability_overrides(project_root, EV_CHARGER={'can_absorb_w': False})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=2.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
    )

    assert out.surplus_dispatch_decision == 'NOOP'
    assert out.attrs['surplus_device_targets'][0]['device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_targets'][0]['enabled'] is False


@pytest.mark.unit
def test_engine_force_rising_edge_sets_freeze_and_blocks_immediate_activation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30)
    m = make_m()
    nz = make_nz(rpnz_w=1000, required_power_consumption_kw=10.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 100.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(forced_device_ids=('RELAY1',)),
    )

    assert out.attrs['surplus_freeze_until_ts'] == 130.0
    assert out.surplus_dispatch_decision == 'NOOP'


@pytest.mark.unit
def test_engine_force_without_rising_edge_allows_activation_without_new_freeze():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30)
    m = make_m()
    nz = make_nz(rpnz_w=1000, required_power_consumption_kw=10.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 100.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(
            forced_device_ids=('RELAY1',),
            previous_force_on_device_ids=('RELAY1',),
        ),
    )

    assert out.attrs['surplus_freeze_until_ts'] == 130.0
    assert out.surplus_dispatch_decision == 'ACTIVATE_ADJUSTABLE'


@pytest.mark.unit
def test_policy_inactive_clear_all_freeze_until_is_stable_across_now_ts():
    profiles = make_profiles(control=ControlProfile.MANUAL, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30)
    m = make_m()
    nz = make_nz(rpnz_w=1000, required_power_consumption_kw=10.0)

    first = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 100.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )
    second = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 105.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
    )

    assert first.attrs['surplus_device_dispatch_action'] == 'CLEAR_ALL'
    assert first.attrs['surplus_device_dispatch_decision'] == 'CLEAR_ALL'
    assert second.attrs['surplus_device_dispatch_action'] == 'CLEAR_ALL'
    assert second.attrs['surplus_device_dispatch_decision'] == 'CLEAR_ALL'
    assert first.attrs['surplus_freeze_until_ts'] is None
    assert second.attrs['surplus_freeze_until_ts'] is None


@pytest.mark.unit
def test_engine_home_battery_adjustable_uses_rpnz_controller_when_not_primary_ev():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(adjustable_surplus_load='HOME_BATTERY', max_solar_charge_w=2000)
    m = make_m(grid_power_w=0, current_battery_setpoint_w=100)
    nz = make_nz(rpnz_w=100, required_power_consumption_kw=0.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=45.0,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=True,
    )

    assert out.surplus_dispatch_decision in ('NOOP', 'ACTIVATE_RELAY1', 'ACTIVATE_RELAY2')
    assert out.battery_target_w == 100


@pytest.mark.unit
def test_engine_net_zero_uses_configurable_default_battery_floor():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        max_solar_charge_w=2000,
        nz_battery_floor_default_w=250,
    )
    m = make_m(grid_power_w=0, current_battery_setpoint_w=100)
    nz = make_nz(rpnz_w=100, required_power_consumption_kw=0.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=45.0,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=True,
    )

    assert out.battery_target_w == 250


@pytest.mark.unit
def test_engine_home_battery_adjustable_release_stops_max_hold():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(adjustable_surplus_load='HOME_BATTERY', max_solar_charge_w=2000)
    m = make_m(grid_power_w=0, current_battery_setpoint_w=100)
    nz = make_nz(rpnz_w=-200, required_power_consumption_kw=0.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=45.0,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=True,
    )

    assert out.surplus_dispatch_decision == 'RELEASE_ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_device_dispatch_target'] == 'ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_device_id'] == 'HOME_BATTERY'
    assert out.battery_target_w < 2000


@pytest.mark.unit
def test_engine_adjustable_surplus_activation_overrides_threshold_source():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        adjustable_primary_load='HOME_BATTERY',
        adjustable_surplus_activation=2000,
        ev_max_absorb_w=ev_w(28),
        ev_min_absorb_w=ev_w(4),
        ev_charger_phases=1,
    )
    m = make_m()

    below = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500, required_power_consumption_kw=1.9), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
    )

    at = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500, required_power_consumption_kw=2.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
    )

    assert below.surplus_dispatch_decision == 'NOOP'
    assert below.surplus_explanation == 'Waiting for EV_CHARGER; raw RPC below threshold'
    assert at.surplus_dispatch_decision == 'ACTIVATE_ADJUSTABLE'
    assert at.surplus_explanation == 'Raw RPC 2.000 kW >= EV_CHARGER threshold 2.000 kW'


@pytest.mark.unit
def test_engine_same_target_combo_emits_fallback_warning_attrs():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        adjustable_primary_load='EV_CHARGER',
    )
    m = make_m()
    nz = make_nz(rpnz_w=200, required_power_consumption_kw=1.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
    )

    assert out.attrs['primary_surplus_combo_valid'] is False
    assert out.attrs['primary_surplus_combo_reason'] == 'fallback_to_cross_combo'
    assert out.attrs['primary_surplus_combo_fallback_active'] is True
    assert 'fallback_to_cross_combo' in out.attrs['primary_surplus_combo_warning']


@pytest.mark.unit
def test_engine_primary_ev_target_w_uses_derived_power_step():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=1380, required_power_consumption_kw=2.0)

    cfg_step_2 = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_charger_phases=1,
        ev_min_absorb_w=ev_w(4),
        ev_max_absorb_w=ev_w(28),
        ev_current_step_a=2,
    )
    out_step_2 = compute_net_zero_engine_outputs(
        profiles, cfg_step_2, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
    )

    cfg_step_4 = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_charger_phases=1,
        ev_min_absorb_w=ev_w(4),
        ev_max_absorb_w=ev_w(28),
        ev_current_step_a=4,
    )
    out_step_4 = compute_net_zero_engine_outputs(
        profiles, cfg_step_4, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
    )

    assert out_step_2.attrs['ev_target_w'] == 1380
    assert out_step_2.attrs['ev_policy_mode'] == 'burn'
    assert out_step_4.attrs['ev_target_w'] == 920


@pytest.mark.unit
def test_engine_primary_ev_low_pv_and_battery_discharge_triggers_hard_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_force_on=False,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
        pv_power_kw=0.0,
        ev_low_pv_cycles=2,
    )

    assert out.attrs['battery_to_ev_loop_risk'] is True
    assert out.attrs['ev_primary_burn_active'] is False
    assert out.attrs['ev_policy_mode'] == 'hard_off'
    assert out.attrs['ev_hard_off_active'] is True
    assert out.attrs['ev_target_w'] == 0


@pytest.mark.unit
def test_engine_primary_ev_low_pv_pre_hard_off_keeps_min_current():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_min_absorb_w=ev_w(4),
        ev_force_on=False,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=1.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
        pv_power_kw=1.5,
        ev_low_pv_cycles=0,
        ev_hard_off_active=False,
    )

    assert out.attrs['battery_to_ev_loop_risk'] is True
    assert out.attrs['ev_policy_mode'] == 'restore_min'
    assert out.attrs['ev_hard_off_active'] is False
    assert out.attrs['ev_target_w'] == 920


@pytest.mark.unit
def test_engine_primary_ev_force_on_does_not_override_low_pv_battery_safety():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_force_on=True,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
        pv_power_kw=0.0,
        ev_low_pv_cycles=2,
    )

    assert out.attrs['ev_force_on'] is True
    assert out.attrs['battery_to_ev_loop_risk'] is True
    assert out.attrs['ev_policy_mode'] == 'hard_off'
    assert out.attrs['ev_target_w'] == 0


@pytest.mark.unit
def test_engine_ev_primary_home_battery_small_positive_rpnz_does_not_release_hard_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        adjustable_surplus_activation=2500,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_release_cycles=2,
    )
    m = make_m(grid_power_w=-10.0, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=1.0, required_power_consumption_kw=0.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 270.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
        pv_power_kw=0.0,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=0,
    )

    assert out.attrs['ev_hard_off_active'] is True
    assert out.attrs['ev_target_w'] == 0
    assert out.attrs['ev_hard_off_release_ready_cycles'] == 0


@pytest.mark.unit
def test_engine_ev_primary_home_battery_releases_hard_off_after_release_cycles():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        adjustable_surplus_activation=2500,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_release_cycles=2,
    )
    m = make_m(grid_power_w=-1100.0, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=cfg_ev_min_a(cfg))})
    release_rpc_kw = ev_min_power_w(cfg) / 1000.0
    nz = make_nz(rpnz_w=2600.0, required_power_consumption_kw=release_rpc_kw)

    first = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 275.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
        pv_power_kw=1.6,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=0,
    )

    assert first.attrs['ev_hard_off_active'] is True
    assert first.attrs['ev_target_w'] == 0
    assert first.attrs['ev_hard_off_release_ready_cycles'] == 1

    second = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 305.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
        pv_power_kw=1.6,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=first.attrs['ev_hard_off_release_ready_cycles'],
    )

    assert second.attrs['ev_hard_off_active'] is False
    assert second.attrs['ev_target_w'] > 0
    assert second.attrs['ev_hard_off_release_ready_cycles'] >= 2


@pytest.mark.unit
def test_engine_ev_primary_home_battery_release_counter_resets_on_condition_break():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        adjustable_surplus_activation=2500,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_release_cycles=2,
    )
    m = make_m(grid_power_w=-1100.0, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=cfg_ev_min_a(cfg))})
    release_rpc_kw = ev_min_power_w(cfg) / 1000.0
    nz = make_nz(rpnz_w=2600.0, required_power_consumption_kw=release_rpc_kw)

    first = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 335.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
        pv_power_kw=1.6,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=0,
    )

    assert first.attrs['ev_hard_off_release_ready_cycles'] == 1
    assert first.attrs['ev_hard_off_active'] is True

    broken = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 365.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
        pv_power_kw=1.5,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=first.attrs['ev_hard_off_release_ready_cycles'],
    )

    assert broken.attrs['ev_hard_off_release_ready_cycles'] == 0
    assert broken.attrs['ev_hard_off_active'] is True


@pytest.mark.unit
def test_engine_preserves_previous_ev_state_per_device_when_selected_ev_changes(project_root):
    cfg_garage = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(),
    )
    previous_ev_device_states = {
        'EV_CHARGER': {
            'device_id': 'EV_CHARGER',
            'mode': 'hard_off',
            'low_pv_cycles': 3,
            'hard_off_release_ready_cycles': 1,
            'hard_off_active': True,
        },
        'GARAGE_EV': {
            'device_id': 'GARAGE_EV',
            'mode': 'restore_min',
            'low_pv_cycles': 0,
            'hard_off_release_ready_cycles': 0,
            'hard_off_active': False,
        },
    }
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    m = make_m()
    out_garage = compute_net_zero_engine_outputs(
        profiles, cfg_garage, m, make_haeo(), make_nz(rpnz_w=500.0, required_power_consumption_kw=2.0), 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
        previous_ev_device_states=previous_ev_device_states,
    )

    assert out_garage.attrs['selected_ev_device_id'] == 'GARAGE_EV'
    assert out_garage.attrs['previous_ev_device_states']['EV_CHARGER']['mode'] == 'hard_off'
    assert out_garage.attrs['previous_ev_device_states']['EV_CHARGER']['hard_off_active'] is True
    assert out_garage.attrs['previous_ev_device_states']['GARAGE_EV']['mode'] == out_garage.attrs['ev_policy_mode']

    cfg_main = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(adjustable_surplus_load='EV_CHARGER'),
    )
    out_main = compute_net_zero_engine_outputs(
        profiles, cfg_main, m, make_haeo(), make_nz(rpnz_w=0.0, required_power_consumption_kw=0.0), 90.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=False,
        previous_ev_device_states=out_garage.attrs['previous_ev_device_states'],
        pv_power_kw=0.0,
    )

    assert out_main.attrs['selected_ev_device_id'] == 'EV_CHARGER'
    assert out_main.attrs['ev_hard_off_active'] is True
    assert out_main.attrs['previous_ev_device_states']['GARAGE_EV']['mode'] == out_garage.attrs['previous_ev_device_states']['GARAGE_EV']['mode']
    assert out_main.attrs['ev_target_w'] == 0


@pytest.mark.unit
def test_engine_targets_selected_second_ev_and_marks_other_evs_inactive(project_root):
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(),
    )
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(), make_nz(rpnz_w=3000.0, required_power_consumption_kw=3.0), 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=True,
        previous_ev_device_states={
            'EV_CHARGER': {
                'device_id': 'EV_CHARGER',
                'mode': 'hard_off',
                'low_pv_cycles': 2,
                'hard_off_release_ready_cycles': 1,
                'hard_off_active': True,
            },
        },
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    payloads = {item['device_id']: item for item in out.attrs['device_policies']}

    assert out.attrs['ev_device_ids'] == ('EV_CHARGER', 'GARAGE_EV')
    assert out.attrs['selected_ev_device_id'] == 'GARAGE_EV'
    assert policies['GARAGE_EV'].enabled is True
    assert policies['GARAGE_EV'].target_w == 3680
    assert policies['EV_CHARGER'].enabled is False
    assert policies['EV_CHARGER'].target_w == 0
    assert payloads['GARAGE_EV']['enabled'] is True
    assert payloads['EV_CHARGER']['reason'] == 'inactive_ev_policy'
    assert out.attrs['previous_ev_device_states']['GARAGE_EV']['mode'] == out.attrs['ev_policy_mode']
    assert out.attrs['previous_ev_device_states']['EV_CHARGER']['mode'] == 'hard_off'


@pytest.mark.unit
def test_engine_core_config_view_hot_path_avoids_legacy_ev_and_relay_materialization(project_root):
    cfg = _core_cfg_view_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(),
    )
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(), make_nz(rpnz_w=3000.0, required_power_consumption_kw=3.0), 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        adjustable_surplus_active=True,
        previous_ev_device_states={
            'EV_CHARGER': {
                'device_id': 'EV_CHARGER',
                'mode': 'hard_off',
                'low_pv_cycles': 2,
                'hard_off_release_ready_cycles': 1,
                'hard_off_active': True,
            },
        },
    )

    assert out.attrs['selected_ev_device_id'] == 'GARAGE_EV'
    assert cfg.legacy_device_bridge_count() == 0
    assert cfg.legacy_device_bridge_counts_by_kind() == {}
    assert out.attrs['legacy_device_bridge_count'] == 0
    assert out.attrs['legacy_device_bridge_counts_by_kind'] == {}


@pytest.mark.unit
def test_engine_without_ev_devices_skips_ev_policy_and_keeps_battery_relay_outputs(project_root):
    cfg = _core_cfg_without_ev_devices(project_root)
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(grid_power_w=-2500.0), make_haeo(), make_nz(rpnz_w=2500.0, required_power_consumption_kw=2.5), 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
        pv_power_kw=3.5,
        previous_ev_device_states={
            'EV_CHARGER': {
                'device_id': 'EV_CHARGER',
                'mode': 'hard_off',
                'low_pv_cycles': 2,
                'hard_off_release_ready_cycles': 1,
                'hard_off_active': True,
            },
        },
    )

    policies = {policy.device_id: policy for policy in out.device_policies}

    assert out.attrs['ev_device_ids'] == ()
    assert out.attrs['selected_ev_device_id'] == ''
    assert out.attrs['ev_policy_mode'] == 'skip'
    assert out.attrs['ev_target_w'] == 0
    assert out.attrs['ev_primary_burn_active'] is False
    assert out.attrs['ev_surplus_burn_active'] is False
    assert out.attrs['previous_ev_device_states']['EV_CHARGER']['mode'] == 'hard_off'
    assert 'EV_CHARGER' not in policies
    assert set(policies) == {'HOME_BATTERY', 'RELAY1', 'RELAY2'}
    assert out.attrs['adjustable_surplus_load'] == 'HOME_BATTERY'
    assert out.attrs['surplus_device_targets'][0]['device_id'] == 'HOME_BATTERY'


@pytest.mark.unit
def test_engine_ev_primary_restore_min_allows_battery_discharge_when_charger_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
    )
    m = make_m(
        current_battery_setpoint_w=-1000,
        grid_power_w=2900.0,
        ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=cfg_ev_min_a(cfg))},
    )
    nz = make_nz(rpnz_w=-15.0, required_power_consumption_kw=-2.49)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
        pv_power_kw=1.7,
        ev_hard_off_active=False,
        ev_low_pv_cycles=0,
    )

    assert out.attrs['ev_policy_mode'] == 'restore_min'
    assert out.attrs['ev_target_w'] == ev_min_power_w(cfg)
    assert out.attrs['ev_hard_off_active'] is False
    assert out.battery_target_w == -2000


@pytest.mark.unit
def test_engine_ev_primary_restore_min_holds_battery_floor_when_charger_on():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
    )
    m = make_m(
        current_battery_setpoint_w=-1000,
        grid_power_w=2900.0,
        ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=cfg_ev_min_a(cfg))},
    )
    nz = make_nz(rpnz_w=-15.0, required_power_consumption_kw=-2.49)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=False,
        pv_power_kw=1.7,
        ev_hard_off_active=False,
        ev_low_pv_cycles=0,
    )

    assert out.attrs['ev_policy_mode'] == 'restore_min'
    assert out.attrs['ev_target_w'] == ev_min_power_w(cfg)
    assert out.attrs['ev_hard_off_active'] is False
    assert out.battery_target_w == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ('rpnz_w', 'expected_floor_hold'),
    [
        (4.0, True),
        (10.0, True),
        (11.0, False),
        (0.0, True),
        (-1.0, True),
    ],
)
def test_engine_ev_primary_treats_tiny_positive_rpnz_as_practical_zero_for_battery_authority(rpnz_w, expected_floor_hold):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
    )
    m = make_m(
        current_battery_setpoint_w=-1000,
        grid_power_w=2900.0,
        ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=cfg_ev_min_a(cfg))},
    )
    nz = make_nz(rpnz_w=rpnz_w, required_power_consumption_kw=0.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        adjustable_surplus_active=True,
        pv_power_kw=1.7,
        ev_hard_off_active=False,
        ev_low_pv_cycles=0,
    )

    assert out.battery_target_w == 0
    assert out.attrs['surplus_adjustable_active'] is (not expected_floor_hold)
