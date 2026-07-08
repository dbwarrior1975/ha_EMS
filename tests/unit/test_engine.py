import pytest
from ems_core.domain.models import (
    ControlProfile, GoalProfile, GuardProfile, DominantLimitation, ForecastProfile,
    HaeoNetZeroPlan, DeviceControlContext,
)
from ems_core.domain.ev_power import ev_min_power_w
from ems_core.net_zero.engine import (
    compute_net_zero_engine_outputs,
    compute_primary_device_target_w,
    compute_primary_residual_feedback_protection,
)
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
        'input_select.ems_adjustable_primary_load': 'HOME_BATTERY',
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
        'input_select.ems_adjustable_primary_load': 'HOME_BATTERY',
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
    grouped['ems']['devices']['HOME_BATTERY']['policy']['surplus_allowed'] = True

    values = {
        'input_number.ems_deadband_w': 50,
        'input_number.ems_ramp_max_w': 5000,
        'input_number.ems_strict_limits_max_w': 4600,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_nz_battery_floor_default_w': 100,
        'input_number.ems_nz_battery_floor_ev_active_w': 0,
        'input_select.ems_adjustable_primary_load': '',
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
        'input_select.ems_adjustable_primary_load': 'HOME_BATTERY',
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
            'supports_primary_regulation': True,
            'supports_residual_regulation': False,
            'uses_hard_off_lifecycle': True,
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
            'surplus_dispatch_mode': 'max_absorb',
        },
        'adapter': {
            'enabled': 'switch.garage_ev_enabled',
            'current_a': 'number.garage_ev_current_a',
            'current_step_a': 'input_number.garage_ev_current_step_a',
            'phases': 'input_number.garage_ev_phases',
            'voltage_v': 'input_number.garage_ev_voltage_v',
        },
    }


def _garage_ev_value_overrides(*, adjustable_primary_load='HOME_BATTERY'):
    return {
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
def test_engine_selected_ev_context_uses_normalized_power_step_without_partial_cfg_helper(project_root):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides={
            **_garage_ev_value_overrides(adjustable_primary_load='GARAGE_EV'),
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
        selected_ev_surplus_active=True,
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
        selected_ev_surplus_active=True,
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
        selected_ev_surplus_active=True,
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
                    'supports_primary_regulation': False,
                    'supports_residual_regulation': False,
                    'uses_hard_off_lifecycle': False,
                    'min_absorb_w': 'input_number.ems_relay3_nominal_absorb_w',
                    'max_absorb_w': 'input_number.ems_relay3_power_w',
                    'step_w': 'input_number.ems_relay3_power_w',
                },
                'policy': {
                    'priority': 'input_number.ems_surplus_relay3_priority',
                    'surplus_allowed': 'input_boolean.ems_relay3_enabled_import_zero',
                    'force_on': 'input_boolean.ems_relay3_force_on',
                    'surplus_dispatch_mode': 'fixed',
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
def test_engine_uses_device_owned_priority_without_legacy_role_scalar():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_primary_load='HOME_BATTERY',
        adjustable_surplus_load_priority=2,
        ev_priority=3,
    )
    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=7000), make_haeo(),
        make_nz(rpnz_w=7000.0, required_power_consumption_kw=7.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
    )

    target = next(item for item in out.attrs['surplus_device_targets'] if item['device_id'] == 'EV_CHARGER')
    assert target['priority'] == 3
    assert 'adjustable_surplus_load_priority' not in out.attrs

@pytest.mark.unit
def test_engine_haeo_role_switch_uses_device_owned_candidate_priority():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_primary_load='HOME_BATTERY',
        adjustable_surplus_load_priority=2,
        ev_priority=3,
        battery_surplus_allowed=True,
    )
    plan = HaeoNetZeroPlan(
        active=True,
        primary_device_id='EV_CHARGER',
        preferred_surplus_device_id='HOME_BATTERY',
        device_limits_w={'HOME_BATTERY': 3700, 'EV_CHARGER': 6400},
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=5000), make_haeo(),
        make_nz(rpnz_w=5000.0, required_power_consumption_kw=5.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
        haeo_nz_plan=plan,
    )

    target = next(item for item in out.attrs['surplus_device_targets'] if item['device_id'] == 'HOME_BATTERY')
    assert target['priority'] == 2
    assert target['threshold_w'] == 3700
    assert target['threshold_source'] == 'device_capabilities.max_absorb_w'
    assert 'adjustable_surplus_load' not in out.attrs

@pytest.mark.unit
def test_engine_ev_surplus_allowed_false_excludes_only_that_device():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_primary_load='HOME_BATTERY',
        ev_surplus_allowed=False,
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=5000), make_haeo(),
        make_nz(rpnz_w=5000.0, required_power_consumption_kw=5.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
    )

    candidate_ids = {item['device_id'] for item in out.attrs['surplus_device_targets']}
    assert 'EV_CHARGER' not in candidate_ids
    assert 'HOME_BATTERY' in candidate_ids
    assert out.attrs['surplus_device_next_device_id'] == 'HOME_BATTERY'
    assert out.surplus_dispatch_decision == 'ACTIVATE_HOME_BATTERY'


@pytest.mark.unit
def test_engine_ev_force_on_bypasses_surplus_allowed_optimizer_gate():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_primary_load='HOME_BATTERY',
        ev_surplus_allowed=False,
        ev_force_on=True,
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=500), make_haeo(),
        make_nz(rpnz_w=-100.0, required_power_consumption_kw=0.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
    )

    candidates = {item['device_id']: item for item in out.attrs['surplus_device_targets']}
    policies = {policy.device_id: policy for policy in out.device_policies}
    assert candidates['EV_CHARGER']['force_on'] is True
    assert candidates['EV_CHARGER']['enabled'] is True
    assert candidates['EV_CHARGER']['activation_allowed'] is True
    assert policies['EV_CHARGER'].target_w == 6440
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].reason == 'ev_force_on'


@pytest.mark.unit
def test_engine_ev_force_on_bypasses_haeo_net_zero_plan_limit():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_primary_load='EV_CHARGER',
        ev_force_on=True,
    )
    plan = HaeoNetZeroPlan(
        active=True,
        primary_device_id='EV_CHARGER',
        preferred_surplus_device_id='HOME_BATTERY',
        device_limits_w={'EV_CHARGER': 1000, 'HOME_BATTERY': 3700},
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(),
        make_nz(rpnz_w=100.0, required_power_consumption_kw=0.1), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
        pv_power_kw=0.0,
        haeo_nz_plan=plan,
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['haeo_nz_plan_active'] is True
    assert out.attrs['haeo_nz_device_limits_w']['EV_CHARGER'] == 1000
    assert policies['EV_CHARGER'].target_w == 6440
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].reason == 'ev_force_on'


@pytest.mark.unit
def test_engine_forced_active_ev_ignores_allocator_release_for_effective_policy():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_primary_load='HOME_BATTERY',
        ev_force_on=True,
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(),
        make_nz(rpnz_w=0.0, required_power_consumption_kw=0.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=True,
        pv_power_kw=0.0,
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['surplus_device_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_device_dispatch_device_id'] == 'EV_CHARGER'
    assert policies['EV_CHARGER'].target_w == 6440
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].reason == 'ev_force_on'


@pytest.mark.unit
def test_engine_active_ev_is_released_when_surplus_allowed_turns_false():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        adjustable_primary_load='HOME_BATTERY',
        adjustable_surplus_activation=2000,
        ev_surplus_allowed=False,
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=5000), make_haeo(),
        make_nz(rpnz_w=5000.0, required_power_consumption_kw=5.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=True,
    )

    target = next(item for item in out.attrs['surplus_device_targets'] if item['device_id'] == 'EV_CHARGER')
    assert target['enabled'] is False
    assert target['active'] is True
    assert out.attrs['surplus_device_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_device_dispatch_device_id'] == 'EV_CHARGER'


@pytest.mark.unit
def test_engine_surplus_device_trace_uses_max_absorb_as_activation_threshold():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_primary_load='HOME_BATTERY',
        battery_surplus_allowed=False,
        ev_min_absorb_w=ev_w(4),
        ev_max_absorb_w=ev_w(28),
        ev_charger_phases=1,
    )
    m = make_m()
    ev_max_w = ev_w(28)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(),
        make_nz(rpnz_w=500, required_power_consumption_kw=ev_max_w / 1000.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
    )

    assert out.surplus_dispatch_decision == 'ACTIVATE_EV_CHARGER'
    assert out.attrs['surplus_device_dispatch_decision'] == 'ACTIVATE_EV_CHARGER'
    assert out.attrs['surplus_device_dispatch_action'] == 'ACTIVATE'
    assert out.attrs['surplus_device_dispatch_target'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_dispatch_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_dispatch_contract'] == 'device_id_primary'
    assert out.attrs['surplus_device_next_target'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_next_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_active_stack'] == 'NONE'
    assert out.attrs['surplus_device_targets'][0]['threshold_w'] == ev_max_w
    assert out.attrs['surplus_device_targets'][0]['threshold_source'] == 'device_capabilities.max_absorb_w'

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
def test_engine_excludes_ev_when_ev_cannot_absorb_and_keeps_battery_candidate(project_root):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = _core_cfg_with_capability_overrides(project_root, EV_CHARGER={'can_absorb_w': False})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=4.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
    )

    assert out.surplus_dispatch_decision == 'ACTIVATE_HOME_BATTERY'
    candidate_ids = {item['device_id'] for item in out.attrs['surplus_device_targets']}
    assert 'EV_CHARGER' not in candidate_ids
    assert 'HOME_BATTERY' in candidate_ids

@pytest.mark.unit
def test_engine_force_rising_edge_sets_freeze_and_blocks_immediate_activation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30, battery_surplus_allowed=False)
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
    cfg = make_cfg(surplus_freeze_s=30, battery_surplus_allowed=False, ev_surplus_allowed=False)
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
    assert out.surplus_dispatch_decision == 'ACTIVATE_RELAY2'

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
        selected_ev_surplus_active=True,
    )

    assert out.surplus_dispatch_decision in ('NOOP', 'ACTIVATE_RELAY1', 'ACTIVATE_RELAY2')
    assert out.battery_target_w == 100


@pytest.mark.unit
def test_engine_net_zero_uses_configurable_default_battery_floor():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        max_solar_charge_w=2000,
        nz_battery_floor_default_w=250,
        battery_surplus_allowed=False,
    )
    m = make_m(grid_power_w=0, current_battery_setpoint_w=100)
    nz = make_nz(rpnz_w=100, required_power_consumption_kw=0.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=45.0,
        ev_burn_active=False,
        **_relay_runtime_args(),
        selected_ev_surplus_active=True,
    )

    assert out.battery_target_w == 250

@pytest.mark.unit
def test_engine_home_battery_candidate_release_stops_max_hold():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_primary_load='EV_CHARGER',
        max_solar_charge_w=2000,
    )
    m = make_m(grid_power_w=0, current_battery_setpoint_w=100)
    nz = make_nz(rpnz_w=-200, required_power_consumption_kw=0.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=45.0,
        ev_burn_active=False,
        **_relay_runtime_args(),
        active_surplus_device_ids=('HOME_BATTERY',),
    )

    assert out.surplus_dispatch_decision == 'RELEASE_HOME_BATTERY'
    assert out.attrs['surplus_device_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_device_dispatch_target'] == 'HOME_BATTERY'
    assert out.attrs['surplus_device_dispatch_device_id'] == 'HOME_BATTERY'
    assert out.battery_target_w < 2000

@pytest.mark.unit
def test_engine_surplus_activation_threshold_is_device_max_absorb_capability():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    ev_max_w = ev_w(28)
    cfg = make_cfg(
        adjustable_primary_load='HOME_BATTERY',
        battery_surplus_allowed=False,
        ev_max_absorb_w=ev_max_w,
        ev_min_absorb_w=ev_w(4),
        ev_charger_phases=1,
    )
    m = make_m()

    below = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(),
        make_nz(rpnz_w=500, required_power_consumption_kw=(ev_max_w - 1) / 1000.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
    )

    at = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(),
        make_nz(rpnz_w=500, required_power_consumption_kw=ev_max_w / 1000.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
    )

    target = below.attrs['surplus_device_targets'][0]
    assert target['device_id'] == 'EV_CHARGER'
    assert target['threshold_w'] == ev_max_w
    assert target['threshold_source'] == 'device_capabilities.max_absorb_w'
    assert below.surplus_dispatch_decision == 'NOOP'
    assert below.surplus_explanation == 'Waiting for EV_CHARGER; raw RPC below threshold'
    assert at.surplus_dispatch_decision == 'ACTIVATE_EV_CHARGER'
    assert at.surplus_explanation == f'Raw RPC {ev_max_w / 1000.0:.3f} kW >= EV_CHARGER threshold {ev_max_w / 1000.0:.3f} kW'



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
        selected_ev_surplus_active=False,
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
        selected_ev_surplus_active=False,
    )

    assert out_step_2.attrs['ev_target_w'] == 1380
    assert out_step_2.attrs['ev_policy_mode'] == 'burn'
    assert out_step_4.attrs['ev_target_w'] == 920


@pytest.mark.unit
def test_engine_primary_ev_feedback_protection_triggers_hard_off():
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
        selected_ev_surplus_active=False,
        pv_power_kw=0.0,
        ev_low_pv_cycles=2,
    )

    assert out.attrs['feedback_protection_active'] is True
    assert out.attrs['feedback_protection_primary_device_id'] == 'EV_CHARGER'
    assert out.attrs['feedback_protection_residual_device_id'] == 'HOME_BATTERY'
    assert out.attrs['activation_block_reason'] == 'primary_residual_feedback_protection'
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
        selected_ev_surplus_active=False,
        pv_power_kw=1.5,
        ev_low_pv_cycles=0,
        ev_hard_off_active=False,
    )

    assert out.attrs['feedback_protection_active'] is True
    assert out.attrs['feedback_protection_residual_producing'] is True
    assert out.attrs['ev_policy_mode'] == 'restore_min'
    assert out.attrs['ev_hard_off_active'] is False
    assert out.attrs['ev_target_w'] == 920


@pytest.mark.unit
def test_engine_primary_ev_force_on_bypasses_feedback_protection_before_hard_off():
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
        selected_ev_surplus_active=False,
        pv_power_kw=0.0,
        ev_low_pv_cycles=2,
    )

    assert out.attrs['ev_force_on'] is True
    assert out.attrs['feedback_protection_active'] is False
    assert out.attrs['activation_block_reason'] == ''
    assert out.attrs['ev_policy_mode'] == 'burn'
    assert out.attrs['ev_hard_off_active'] is False
    assert out.attrs['ev_target_w'] == 6440
    policies = {policy.device_id: policy for policy in out.device_policies}
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].target_w == 6440


@pytest.mark.unit
def test_engine_primary_ev_force_on_bypasses_active_hard_off_without_clearing_state():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_force_on=True,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_release_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=0.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
        pv_power_kw=0.0,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=0,
    )

    assert out.attrs['ev_force_on'] is True
    assert out.attrs['feedback_protection_active'] is False
    assert out.attrs['ev_hard_off_active'] is True
    assert out.attrs['ev_policy_mode'] == 'burn'
    assert out.attrs['ev_target_w'] == 6440
    assert out.attrs['force_on_active_device_ids'] == ('EV_CHARGER',)
    assert out.attrs['force_on_hard_off_bypass_device_ids'] == ('EV_CHARGER',)
    policies = {policy.device_id: policy for policy in out.device_policies}
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].target_w == 6440
    assert policies['EV_CHARGER'].reason == 'ev_force_on'


@pytest.mark.unit
def test_engine_primary_ev_feedback_protection_requires_actual_residual_production():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_force_on=False,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=0, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
        pv_power_kw=0.0,
        ev_low_pv_cycles=1,
    )

    assert out.attrs['feedback_protection_active'] is False
    assert out.attrs['feedback_protection_residual_producing'] is False
    assert out.attrs['ev_hard_off_active'] is False
    assert out.attrs['ev_policy_mode'] == 'burn'


@pytest.mark.unit
def test_engine_battery_primary_negative_setpoint_does_not_create_cross_device_feedback_block():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_primary_load='HOME_BATTERY',
        ev_force_on=False,
        ev_hard_off_pv_threshold_kw=1.6,
    )
    m = make_m(current_battery_setpoint_w=-1200)
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
        pv_power_kw=0.0,
    )

    assert out.attrs['primary_device_id'] == 'HOME_BATTERY'
    assert out.attrs['residual_regulator_device_id'] == 'HOME_BATTERY'
    assert out.attrs['feedback_protection_active'] is False
    assert out.attrs['activation_block_reason'] == ''


@pytest.mark.unit
def test_primary_residual_feedback_protection_is_capability_and_ownership_driven():
    primary = DeviceControlContext(
        device_id='PRIMARY_ABSORBER',
        kind='SYNTHETIC',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=100,
        max_absorb_w=2000,
        max_produce_w=0,
        step_w=100,
        supports_primary_regulation=True,
        supports_residual_regulation=False,
        uses_hard_off_lifecycle=True,
        priority=10,
        current_measured_power_w=500,
    )
    residual = DeviceControlContext(
        device_id='RESIDUAL_PRODUCER',
        kind='SYNTHETIC',
        can_absorb_w=False,
        can_produce_w=True,
        min_absorb_w=0,
        max_absorb_w=0,
        max_produce_w=4000,
        step_w=100,
        supports_primary_regulation=False,
        supports_residual_regulation=True,
        uses_hard_off_lifecycle=False,
        priority=0,
        current_measured_power_w=-1200,
    )

    assert compute_primary_residual_feedback_protection(
        primary, residual, low_energy_active=True
    ) is True
    assert compute_primary_residual_feedback_protection(
        primary, residual, low_energy_active=True, explicit_activation_request=True
    ) is False

    residual_not_producing = DeviceControlContext(
        **{**residual.__dict__, 'current_measured_power_w': 0}
    )
    assert compute_primary_residual_feedback_protection(
        primary, residual_not_producing, low_energy_active=True
    ) is False

    same_device_residual = DeviceControlContext(
        **{**residual.__dict__, 'device_id': 'PRIMARY_ABSORBER'}
    )
    assert compute_primary_residual_feedback_protection(
        primary, same_device_residual, low_energy_active=True
    ) is False


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
        selected_ev_surplus_active=False,
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
        selected_ev_surplus_active=False,
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
        selected_ev_surplus_active=False,
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
        selected_ev_surplus_active=False,
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
        selected_ev_surplus_active=False,
        pv_power_kw=1.5,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=first.attrs['ev_hard_off_release_ready_cycles'],
    )

    assert broken.attrs['ev_hard_off_release_ready_cycles'] == 0
    assert broken.attrs['ev_hard_off_active'] is True



@pytest.mark.unit
def test_engine_two_ev_policies_are_derived_independently_from_candidate_and_lifecycle_state(project_root):
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(),
    )
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(), make_nz(rpnz_w=4000.0, required_power_consumption_kw=4.0), 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
        active_surplus_device_ids=('GARAGE_EV',),
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
    assert payloads['EV_CHARGER']['reason'] == 'ev_lifecycle_hard_off'
    assert out.attrs['previous_ev_device_states']['EV_CHARGER']['mode'] == 'hard_off'
    assert 'GARAGE_EV' in out.attrs['previous_ev_device_states']

@pytest.mark.unit
def test_engine_primary_ev_owns_primary_target_while_other_ev_remains_surplus_candidate(project_root):
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(adjustable_primary_load='EV_CHARGER'),
    )
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)

    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(ev_states={
            'EV_CHARGER': ev_state(enabled=True, current_a=6),
            'GARAGE_EV': ev_state(enabled=False, current_a=0),
        }),
        make_haeo(),
        make_nz(rpnz_w=1380.0, required_power_consumption_kw=1.0),
        60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['primary_device_id'] == 'EV_CHARGER'
    assert out.attrs['selected_ev_device_id'] == 'EV_CHARGER'
    assert 'surplus_preferred_surplus_device_id' not in out.attrs
    assert 'EV_CHARGER' not in out.attrs['surplus_candidate_device_ids']
    assert 'GARAGE_EV' in out.attrs['surplus_candidate_device_ids']
    assert policies['EV_CHARGER'].reason == 'ev_primary_policy'
    assert policies['EV_CHARGER'].target_w == out.attrs['primary_device_target_w']

@pytest.mark.unit
def test_engine_hard_off_release_counters_progress_and_reset_independently_per_ev(project_root):
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides={
            **_garage_ev_value_overrides(),
            'input_number.garage_ev_max_power_w': 5000,
        },
    )
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    previous_device_states = {
        'EV_CHARGER': {
            'device_id': 'EV_CHARGER',
            'mode': 'hard_off',
            'low_pv_cycles': 0,
            'hard_off_release_ready_cycles': 1,
            'hard_off_active': True,
        },
        'GARAGE_EV': {
            'device_id': 'GARAGE_EV',
            'mode': 'hard_off',
            'low_pv_cycles': 0,
            'hard_off_release_ready_cycles': 1,
            'hard_off_active': True,
        },
    }

    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(),
        make_haeo(),
        make_nz(rpnz_w=0.0, required_power_consumption_kw=4.0),
        60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
        pv_power_kw=2.0,
        previous_device_states=previous_device_states,
    )

    ev_state_next = out.attrs['previous_device_states']['EV_CHARGER']
    garage_state_next = out.attrs['previous_device_states']['GARAGE_EV']
    assert ev_state_next['hard_off_release_ready_cycles'] == 2
    assert ev_state_next['hard_off_active'] is False
    assert garage_state_next['hard_off_release_ready_cycles'] == 0
    assert garage_state_next['hard_off_active'] is True

@pytest.mark.unit
def test_engine_hard_off_lifecycle_state_is_device_owned_for_two_capable_evs(project_root):
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides={
            **_garage_ev_value_overrides(),
            'input_number.garage_ev_low_pv_cycles': 100,
        },
    )
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    previous_device_states = {
        'EV_CHARGER': {
            'device_id': 'EV_CHARGER',
            'mode': 'hard_off',
            'low_pv_cycles': 50,
            'hard_off_release_ready_cycles': 7,
            'hard_off_active': True,
        },
        'GARAGE_EV': {
            'device_id': 'GARAGE_EV',
            'mode': 'restore_min',
            'low_pv_cycles': 3,
            'hard_off_release_ready_cycles': 0,
            'hard_off_active': False,
        },
    }

    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(),
        make_haeo(),
        make_nz(rpnz_w=0.0, required_power_consumption_kw=0.0),
        60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=False,
        pv_power_kw=0.0,
        previous_device_states=previous_device_states,
    )

    assert out.attrs['selected_ev_device_id'] == 'GARAGE_EV'
    assert set(out.attrs['hard_off_lifecycle_devices']) == {'EV_CHARGER', 'GARAGE_EV'}
    assert out.attrs['previous_device_states']['EV_CHARGER']['low_pv_cycles'] == 51
    assert out.attrs['previous_device_states']['EV_CHARGER']['hard_off_active'] is True
    assert out.attrs['previous_device_states']['GARAGE_EV']['low_pv_cycles'] == 4
    assert out.attrs['previous_device_states']['GARAGE_EV']['hard_off_active'] is False
    assert out.attrs['device_lifecycle_states'] == {
        'EV_CHARGER': out.attrs['previous_device_states']['EV_CHARGER'],
        'GARAGE_EV': out.attrs['previous_device_states']['GARAGE_EV'],
    }
    assert out.attrs['previous_ev_device_states'] == out.attrs['previous_device_states']

@pytest.mark.unit
def test_engine_ev_kind_does_not_enable_hard_off_lifecycle_without_capability():
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=1,
    )
    cfg.devices['EV_CHARGER'].capabilities.uses_hard_off_lifecycle = False
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)

    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=0)}),
        make_haeo(),
        make_nz(rpnz_w=0.0, required_power_consumption_kw=0.0),
        60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        selected_ev_surplus_active=False,
        pv_power_kw=0.0,
        previous_device_states={
            'EV_CHARGER': {
                'device_id': 'EV_CHARGER',
                'mode': 'hard_off',
                'low_pv_cycles': 50,
                'hard_off_release_ready_cycles': 3,
                'hard_off_active': True,
            },
        },
    )

    assert out.attrs['hard_off_lifecycle_devices'] == ()
    assert out.attrs['ev_policy_mode'] == 'restore_min'
    assert out.attrs['ev_low_pv_cycles'] == 0
    assert out.attrs['ev_hard_off_active'] is False


@pytest.mark.unit
def test_engine_core_config_view_hot_path_avoids_legacy_ev_and_relay_materialization(project_root):
    cfg = _core_cfg_view_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(),
    )
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(), make_nz(rpnz_w=4000.0, required_power_consumption_kw=4.0), 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(surplus_allowed=False),
        selected_ev_surplus_active=True,
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
        profiles, cfg, make_m(grid_power_w=-4000.0), make_haeo(),
        make_nz(rpnz_w=4000.0, required_power_consumption_kw=4.0), 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        **_relay_runtime_args(),
        selected_ev_surplus_active=False,
        pv_power_kw=4.5,
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
    assert 'adjustable_surplus_load' not in out.attrs
    assert out.attrs['surplus_candidate_device_ids'] == ('HOME_BATTERY', 'RELAY1', 'RELAY2')

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
        selected_ev_surplus_active=False,
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
        selected_ev_surplus_active=False,
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
        selected_ev_surplus_active=True,
        pv_power_kw=1.7,
        ev_hard_off_active=False,
        ev_low_pv_cycles=0,
    )

    assert out.battery_target_w == 0
    assert out.attrs['battery_min_floor_reason'] == 'ev_active_floor_override'
    assert 'surplus_adjustable_active' not in out.attrs


@pytest.mark.unit
def test_generic_primary_target_supports_heat_pump_like_context_without_ev_adapter_fields():
    device = DeviceControlContext(
        device_id='SYNTHETIC_HEAT_PUMP',
        kind='HEAT_PUMP',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=200.0,
        max_absorb_w=2000.0,
        max_produce_w=0.0,
        step_w=100.0,
        supports_primary_regulation=True,
        supports_residual_regulation=False,
        uses_hard_off_lifecycle=False,
        priority=50,
        current_measured_power_w=750.0,
    )

    assert compute_primary_device_target_w(device, 50.0) == 200.0
    assert compute_primary_device_target_w(device, 240.0) == 200.0
    assert compute_primary_device_target_w(device, 1375.0) == 1300.0
    assert compute_primary_device_target_w(device, 2500.0) == 2000.0


@pytest.mark.unit
def test_primary_target_eligibility_is_capability_driven_not_kind_driven():
    unsupported_ev = DeviceControlContext(
        device_id='EV_TEST',
        kind='EV_CHARGER',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=100.0,
        max_absorb_w=1000.0,
        max_produce_w=0.0,
        step_w=100.0,
        supports_primary_regulation=False,
        supports_residual_regulation=False,
        uses_hard_off_lifecycle=False,
        priority=10,
    )
    neutral_primary = DeviceControlContext(
        device_id='GENERIC_TEST',
        kind='TEST_DEVICE',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=100.0,
        max_absorb_w=1000.0,
        max_produce_w=0.0,
        step_w=100.0,
        supports_primary_regulation=True,
        supports_residual_regulation=False,
        uses_hard_off_lifecycle=False,
        priority=10,
    )

    assert compute_primary_device_target_w(unsupported_ev, 750.0) == 0.0
    assert compute_primary_device_target_w(neutral_primary, 750.0) == 700.0
