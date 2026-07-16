import pytest
from ems_core.domain.models import (
    ControlProfile, GoalProfile, GuardProfile, DominantLimitation, ForecastProfile,
    HaeoNetZeroPlan, DeviceControlContext,
)
from ems_core.domain.ev_power import ev_min_power_w
from ems_core.net_zero.engine import (
    compute_net_zero_engine_outputs,
    compute_primary_consuming_device_target_w,
    compute_primary_producer_feedback_protection,
    compute_hard_off_lifecycle_transition,
    quantize_produce_magnitude_toward_zero,
    _allocate_producer_dispatch,
    _capability_device_config_for_id,
    _producer_feedback_request,
    _producer_transient_target_w,
)
from ems_adapter.config_loader import (
    build_core_config_from_grouped_reader,
    load_grouped_ems_config,
)
from tests.helpers import cfg_ev_min_a, ev_state, ev_w, make_profiles, make_cfg, make_m, make_haeo, make_nz


def _device_policy(out, device_id='EV_CHARGER'):
    return next(policy for policy in out.device_policies if policy.device_id == device_id)


def _surplus_candidate(out, device_id='EV_CHARGER'):
    return next(item for item in out.attrs['surplus_candidates'] if item['device_id'] == device_id)


def _device_lifecycle_state(out, device_id='EV_CHARGER'):
    return out.attrs['device_lifecycle_states'][device_id]


def _previous_device_states(
    device_id='EV_CHARGER',
    *,
    mode='',
    low_pv_cycles=0,
    hard_off_release_ready_cycles=0,
    hard_off_active=False,
):
    return {
        device_id: {
            'device_id': device_id,
            'mode': mode,
            'low_pv_cycles': low_pv_cycles,
            'hard_off_release_ready_cycles': hard_off_release_ready_cycles,
            'hard_off_active': hard_off_active,
        }
    }


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
        'active_surplus_device_ids': tuple(active_device_ids),
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
        'input_select.ems_primary_consuming_device': '',
        'input_number.ems_home_battery_min_absorb_w': 100,
        'input_number.ems_max_battery_charge_w': 3700,
        'input_number.ems_max_battery_discharge_w': 4000,
        'input_number.ems_home_battery_surplus_priority': 3,
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


def _garage_ev_device_config():
    return {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_consuming_regulation': True,
            'supports_producing_regulation': False,
            'uses_hard_off_lifecycle': True,
            'min_absorb_w': 'input_number.garage_ev_min_power_w',
            'max_absorb_w': 'input_number.garage_ev_max_power_w',
            'min_produce_w': 0,
            'max_produce_w': 0,
            'step_w': 'input_number.garage_ev_power_step_w',
        },
        'policy': {
            'priority': 'input_number.garage_ev_priority',
            'producing_priority': 0,
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


def _garage_ev_value_overrides(*, primary_consuming_device_id='HOME_BATTERY'):
    return {
        'input_select.ems_primary_consuming_device': primary_consuming_device_id,
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
        **_relay_runtime_args(),
    )

    assert out.battery_target_w == -4600
    assert out.battery_write_enabled is True


@pytest.mark.unit
def test_engine_capability_adapter_preserves_negative_produce_limit_for_fail_closed_clamp():
    cfg = make_cfg(max_battery_discharge_w=-4600)

    device_cfg = _capability_device_config_for_id(cfg, 'HOME_BATTERY')

    assert device_cfg.max_produce_w == -4600


@pytest.mark.unit
def test_engine_negative_produce_limit_fails_closed_in_internal_context():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(max_battery_discharge_w=-4600, deadband_w=0, ramp_max_w=10000, max_solar_charge_w=10000)
    m = make_m(grid_power_w=4000, current_battery_setpoint_w=-4500)
    nz = make_nz(rpnz_w=-7000)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 0.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
    )

    assert out.attrs['discharge_limit_w'] == 0
    assert out.attrs['discharge_limit_sign_mode'] == 'positive_magnitude'






@pytest.mark.unit
def test_engine_primary_ev_context_uses_normalized_power_step_without_partial_cfg_helper(project_root):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides={
            **_garage_ev_value_overrides(primary_consuming_device_id='GARAGE_EV'),
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
        **_relay_runtime_args(active_device_ids=('GARAGE_EV',)),
    )

    policy = _device_policy(out, 'GARAGE_EV')
    assert out.attrs['effective_primary_consuming_device_id'] == 'GARAGE_EV'
    adapter = cfg.devices['GARAGE_EV'].adapter
    assert adapter.current_step_a * adapter.phases * adapter.voltage_v == 230
    assert policy.target_w == 2380

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
        **_relay_runtime_args(active_device_ids=('EV_CHARGER',)),
    )

    assert _device_policy(out).target_w == 11040


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
        **_relay_runtime_args(active_device_ids=('RELAY1', 'EV_CHARGER')),
    )

    policies = {item['device_id']: item for item in out.attrs['device_policies']}
    policies_from_output = {policy.device_id: policy for policy in out.device_policies}

    assert policies_from_output['HOME_BATTERY'].target_w == out.battery_target_w
    assert policies_from_output['HOME_BATTERY'].enabled is out.battery_write_enabled
    assert policies_from_output['RELAY1'].enabled is True
    assert policies_from_output['RELAY2'].enabled is False
    assert policies['HOME_BATTERY']['target_w'] == out.battery_target_w
    assert policies['HOME_BATTERY']['enabled'] is out.battery_write_enabled
    assert policies['EV_CHARGER']['target_w'] == policies_from_output['EV_CHARGER'].target_w
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
                    'supports_primary_consuming_regulation': False,
                    'supports_producing_regulation': False,
                    'uses_hard_off_lifecycle': False,
                    'min_absorb_w': 'input_number.ems_relay3_nominal_absorb_w',
                    'max_absorb_w': 'input_number.ems_relay3_power_w',
                    'min_produce_w': 0,
                    'max_produce_w': 0,
                    'step_w': 'input_number.ems_relay3_power_w',
                },
                'policy': {
                    'priority': 'input_number.ems_surplus_relay3_priority',
                    'producing_priority': 0,
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
        **_relay_runtime_args(
            surplus_allowed=False,
            active_device_ids=('RELAY3',),
            relay_device_states={
                'RELAY3': {'surplus_allowed': True, 'force_on': False, 'active': True},
            },
        ),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    targets = {target['device_id']: target for target in out.attrs['surplus_candidates']}

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
        primary_consuming_device_id='HOME_BATTERY',
        home_battery_surplus_priority=2,
        ev_priority=3,
    )
    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=7000), make_haeo(),
        make_nz(rpnz_w=7000.0, required_power_consumption_kw=7.0), 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
    )

    target = next(item for item in out.attrs['surplus_candidates'] if item['device_id'] == 'EV_CHARGER')
    assert target['priority'] == 3
    assert 'home_battery_surplus_priority' not in out.attrs

@pytest.mark.unit
def test_engine_haeo_role_switch_uses_device_owned_candidate_priority():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        home_battery_surplus_priority=2,
        ev_priority=3,
        battery_surplus_allowed=True,
    )
    plan = HaeoNetZeroPlan(
        active=True,
        primary_consuming_device_id='EV_CHARGER',
        preferred_surplus_device_id='HOME_BATTERY',
        device_limits_w={'HOME_BATTERY': 3700, 'EV_CHARGER': 6400},
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=5000), make_haeo(),
        make_nz(rpnz_w=5000.0, required_power_consumption_kw=5.0), 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        haeo_nz_plan=plan,
    )

    assert out.attrs['ordered_primary_consuming_device_ids'] == ('EV_CHARGER', 'HOME_BATTERY')
    assert out.attrs['primary_consuming_skipped_by_id']['EV_CHARGER'] == 'below_min_absorb_w'
    assert out.attrs['effective_primary_consuming_device_id'] == 'HOME_BATTERY'
    assert 'HOME_BATTERY' not in out.attrs['surplus_candidate_device_ids']
    assert 'adjustable_surplus_load' not in out.attrs

@pytest.mark.unit
def test_engine_ev_surplus_allowed_false_excludes_only_that_device():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        ev_surplus_allowed=False,
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=5000), make_haeo(),
        make_nz(rpnz_w=5000.0, required_power_consumption_kw=5.0), 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
    )

    candidate_ids = {item['device_id'] for item in out.attrs['surplus_candidates']}
    assert 'EV_CHARGER' not in candidate_ids
    assert 'HOME_BATTERY' not in candidate_ids
    assert out.attrs['effective_primary_consuming_device_id'] == 'HOME_BATTERY'
    assert out.attrs['surplus_dispatch_action'] == 'NOOP'


@pytest.mark.unit
def test_engine_ev_force_on_bypasses_surplus_allowed_optimizer_gate():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        ev_surplus_allowed=False,
        ev_force_on=True,
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=500), make_haeo(),
        make_nz(rpnz_w=-100.0, required_power_consumption_kw=0.0), 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
    )

    candidates = {item['device_id']: item for item in out.attrs['surplus_candidates']}
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
        primary_consuming_device_id='EV_CHARGER',
        ev_force_on=True,
    )
    plan = HaeoNetZeroPlan(
        active=True,
        primary_consuming_device_id='EV_CHARGER',
        preferred_surplus_device_id='HOME_BATTERY',
        device_limits_w={'EV_CHARGER': 1000, 'HOME_BATTERY': 3700},
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(),
        make_nz(rpnz_w=100.0, required_power_consumption_kw=0.1), 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
        haeo_nz_plan=plan,
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['haeo_nz_plan_active'] is True
    assert out.attrs['haeo_nz_device_limits_w']['EV_CHARGER'] == 1000
    assert 'haeo_nz_battery_limit_w' not in out.attrs
    assert 'haeo_nz_ev_limit_w' not in out.attrs
    assert policies['EV_CHARGER'].target_w == 6440
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].reason == 'ev_force_on'


@pytest.mark.unit
def test_engine_forced_active_ev_ignores_allocator_release_for_effective_policy():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        ev_force_on=True,
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(),
        make_nz(rpnz_w=0.0, required_power_consumption_kw=0.0), 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False, active_device_ids=('EV_CHARGER',)),
        pv_power_kw=0.0,
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['surplus_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_dispatch_device_id'] == 'EV_CHARGER'
    assert policies['EV_CHARGER'].target_w == 6440
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].reason == 'ev_force_on'


@pytest.mark.unit
def test_engine_active_ev_is_released_when_surplus_allowed_turns_false():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        primary_consuming_device_id='HOME_BATTERY',
        adjustable_surplus_activation=2000,
        ev_surplus_allowed=False,
    )

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(pv_power_w=5000), make_haeo(),
        make_nz(rpnz_w=5000.0, required_power_consumption_kw=5.0), 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False, active_device_ids=('EV_CHARGER',)),
    )

    target = next(item for item in out.attrs['surplus_candidates'] if item['device_id'] == 'EV_CHARGER')
    assert target['enabled'] is False
    assert target['active'] is True
    assert out.attrs['surplus_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_dispatch_device_id'] == 'EV_CHARGER'


@pytest.mark.unit
def test_engine_surplus_device_trace_uses_max_absorb_as_activation_threshold():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
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
        **_relay_runtime_args(surplus_allowed=False),
    )

    assert out.attrs['surplus_dispatch_action'] == 'ACTIVATE'
    assert out.attrs['surplus_dispatch_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_dispatch_action'] == 'ACTIVATE'
    assert out.attrs['surplus_dispatch_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_dispatch_contract'] == 'device_id_primary'
    assert out.attrs['surplus_next_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_candidate_stack'] == 'EV_CHARGER'
    assert out.attrs['surplus_candidates'][0]['threshold_w'] == ev_max_w
    assert out.attrs['surplus_candidates'][0]['threshold_source'] == 'device_capabilities.max_absorb_w'

@pytest.mark.unit
def test_engine_cheap_grid_charge_local_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.CHEAP_GRID_CHARGE, forecast=ForecastProfile.NONE)
    cfg = make_cfg()
    m = make_m()
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
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
        **_relay_runtime_args(),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert _surplus_candidate(out)['force_on'] is True
    assert policies['EV_CHARGER'].mode == 'burn'
    assert policies['EV_CHARGER'].target_w == 3680
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
        **_relay_runtime_args(),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert policies['EV_CHARGER'].target_w == 5000
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
        **_relay_runtime_args(surplus_allowed=False),
    )

    assert out.attrs['effective_primary_consuming_device_id'] == 'HOME_BATTERY'
    assert out.attrs['surplus_dispatch_action'] == 'NOOP'
    candidate_ids = {item['device_id'] for item in out.attrs['surplus_candidates']}
    assert 'EV_CHARGER' not in candidate_ids
    assert 'HOME_BATTERY' not in candidate_ids

@pytest.mark.unit
def test_engine_force_rising_edge_sets_freeze_and_blocks_immediate_activation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30, battery_surplus_allowed=False)
    m = make_m()
    nz = make_nz(rpnz_w=1000, required_power_consumption_kw=10.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 100.0,
        freeze_until_ts=None,
        **_relay_runtime_args(forced_device_ids=('RELAY1',)),
    )

    assert out.attrs['surplus_freeze_until_ts'] == 130.0
    assert out.attrs['surplus_dispatch_action'] == 'NOOP'
    assert out.attrs['surplus_dispatch_device_id'] == ''


@pytest.mark.unit
def test_engine_force_without_rising_edge_allows_activation_without_new_freeze():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30, battery_surplus_allowed=False, ev_surplus_allowed=False)
    m = make_m()
    nz = make_nz(rpnz_w=1000, required_power_consumption_kw=10.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 100.0,
        freeze_until_ts=None,
        **_relay_runtime_args(
            forced_device_ids=('RELAY1',),
            previous_force_on_device_ids=('RELAY1',),
        ),
    )

    assert out.attrs['surplus_freeze_until_ts'] == 130.0
    assert out.attrs['surplus_dispatch_action'] == 'ACTIVATE'
    assert out.attrs['surplus_dispatch_device_id'] == 'RELAY2'

@pytest.mark.unit
def test_policy_inactive_clear_all_freeze_until_is_stable_across_now_ts():
    profiles = make_profiles(control=ControlProfile.MANUAL, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(surplus_freeze_s=30)
    m = make_m()
    nz = make_nz(rpnz_w=1000, required_power_consumption_kw=10.0)

    first = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 100.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
    )
    second = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 105.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
    )

    assert first.attrs['surplus_dispatch_action'] == 'CLEAR_ALL'
    assert second.attrs['surplus_dispatch_action'] == 'CLEAR_ALL'
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
        **_relay_runtime_args(active_device_ids=('EV_CHARGER',)),
    )

    assert out.attrs['surplus_dispatch_action'] in ('NOOP', 'ACTIVATE')
    if out.attrs['surplus_dispatch_action'] == 'ACTIVATE':
        assert out.attrs['surplus_dispatch_device_id'] in ('RELAY1', 'RELAY2')
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
        **_relay_runtime_args(active_device_ids=('EV_CHARGER',)),
    )

    assert out.battery_target_w == 250

@pytest.mark.unit
def test_engine_home_battery_candidate_release_stops_max_hold():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_id='EV_CHARGER',
        max_solar_charge_w=2000,
    )
    m = make_m(grid_power_w=0, current_battery_setpoint_w=100)
    nz = make_nz(rpnz_w=-200, required_power_consumption_kw=0.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=45.0,
        **_relay_runtime_args(active_device_ids=('HOME_BATTERY',)),
    )

    assert out.attrs['surplus_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_dispatch_device_id'] == 'HOME_BATTERY'
    assert out.attrs['surplus_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_dispatch_device_id'] == 'HOME_BATTERY'
    assert out.battery_target_w < 2000

@pytest.mark.unit
def test_engine_surplus_activation_threshold_is_device_max_absorb_capability():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    ev_max_w = ev_w(28)
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
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
        **_relay_runtime_args(surplus_allowed=False),
    )

    at = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(),
        make_nz(rpnz_w=500, required_power_consumption_kw=ev_max_w / 1000.0), 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
    )

    target = below.attrs['surplus_candidates'][0]
    assert target['device_id'] == 'EV_CHARGER'
    assert target['threshold_w'] == ev_max_w
    assert target['threshold_source'] == 'device_capabilities.max_absorb_w'
    assert below.attrs['surplus_dispatch_action'] == 'NOOP'
    assert below.attrs['surplus_dispatch_device_id'] == ''
    assert below.surplus_explanation == 'Waiting for EV_CHARGER; raw RPC below threshold'
    assert at.attrs['surplus_dispatch_action'] == 'ACTIVATE'
    assert at.attrs['surplus_dispatch_device_id'] == 'EV_CHARGER'
    assert at.surplus_explanation == f'Raw RPC {ev_max_w / 1000.0:.3f} kW >= EV_CHARGER threshold {ev_max_w / 1000.0:.3f} kW'



@pytest.mark.unit
def test_engine_ev_surplus_dispatch_mode_has_canonical_fixed_and_max_absorb_semantics():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=6)})
    nz = make_nz(rpnz_w=5000.0, required_power_consumption_kw=12.0)

    fixed_cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        battery_surplus_allowed=False,
        ev_min_absorb_w=2400.0,
        ev_max_absorb_w=11000.0,
    )
    fixed_cfg.devices['EV_CHARGER'].policy.surplus_dispatch_mode = 'fixed'
    fixed = compute_net_zero_engine_outputs(
        profiles, fixed_cfg, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False, active_device_ids=('EV_CHARGER',)),
    )

    max_cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        battery_surplus_allowed=False,
        ev_min_absorb_w=2400.0,
        ev_max_absorb_w=11000.0,
    )
    max_cfg.devices['EV_CHARGER'].policy.surplus_dispatch_mode = 'max_absorb'
    maximum = compute_net_zero_engine_outputs(
        profiles, max_cfg, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False, active_device_ids=('EV_CHARGER',)),
    )

    assert _surplus_candidate(fixed)['surplus_dispatch_mode'] == 'fixed'
    assert _device_policy(fixed).target_w == 2400
    assert _surplus_candidate(maximum)['surplus_dispatch_mode'] == 'max_absorb'
    assert _device_policy(maximum).target_w == 11000


@pytest.mark.unit
def test_engine_primary_ev_target_w_uses_derived_power_step():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=1380, required_power_consumption_kw=2.0)

    cfg_step_2 = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
        ev_charger_phases=1,
        ev_min_absorb_w=ev_w(4),
        ev_max_absorb_w=ev_w(28),
        ev_current_step_a=2,
    )
    out_step_2 = compute_net_zero_engine_outputs(
        profiles, cfg_step_2, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
    )

    cfg_step_4 = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
        ev_charger_phases=1,
        ev_min_absorb_w=ev_w(4),
        ev_max_absorb_w=ev_w(28),
        ev_current_step_a=4,
    )
    out_step_4 = compute_net_zero_engine_outputs(
        profiles, cfg_step_4, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
    )

    assert _device_policy(out_step_2).target_w == 1380
    assert _device_policy(out_step_2).mode == 'burn'
    assert _device_policy(out_step_4).target_w == 920



@pytest.mark.unit
def test_hard_off_low_pv_counter_saturates_at_configured_threshold():
    device = DeviceControlContext(
        device_id='EV_CHARGER',
        kind='EV',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=1840,
        max_absorb_w=6200,
        min_produce_w=0,
        max_produce_w=0,
        step_w=460,
        supports_primary_consuming_regulation=True,
        supports_producing_regulation=False,
        uses_hard_off_lifecycle=True,
        priority=10,
        producing_priority=0,
        current_control_target_w=0,
    )

    transition = compute_hard_off_lifecycle_transition(
        device,
        {
            'low_pv_cycles': 141,
            'hard_off_release_ready_cycles': 0,
            'hard_off_active': True,
        },
        lifecycle_enabled=True,
        requested_active=False,
        pv_power_w=0,
        low_pv_threshold_w=1600,
        hard_off_low_pv_cycles=15,
        hard_off_release_cycles=2,
    )

    assert transition.hard_off_active is True
    assert transition.low_pv_cycles == 15
    assert transition.hard_off_release_ready_cycles == 0


@pytest.mark.unit
def test_hard_off_release_counter_uses_pv_recovery_without_rpc_gate():
    device = DeviceControlContext(
        device_id='EV_CHARGER',
        kind='EV',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=1840,
        max_absorb_w=6200,
        min_produce_w=0,
        max_produce_w=0,
        step_w=460,
        supports_primary_consuming_regulation=True,
        supports_producing_regulation=False,
        uses_hard_off_lifecycle=True,
        priority=10,
        producing_priority=0,
        current_control_target_w=0,
    )
    previous = {
        'low_pv_cycles': 15,
        'hard_off_release_ready_cycles': 0,
        'hard_off_active': True,
    }

    release_tick_1 = compute_hard_off_lifecycle_transition(
        device,
        previous,
        lifecycle_enabled=True,
        requested_active=False,
        pv_power_w=1900,
        low_pv_threshold_w=1600,
        hard_off_low_pv_cycles=15,
        hard_off_release_cycles=2,
    )
    assert release_tick_1.hard_off_active is True
    assert release_tick_1.low_pv_cycles == 15
    assert release_tick_1.hard_off_release_ready_cycles == 1
    assert release_tick_1.recovery_condition is True

    released = compute_hard_off_lifecycle_transition(
        device,
        {
            'low_pv_cycles': release_tick_1.low_pv_cycles,
            'hard_off_release_ready_cycles': release_tick_1.hard_off_release_ready_cycles,
            'hard_off_active': release_tick_1.hard_off_active,
        },
        lifecycle_enabled=True,
        requested_active=False,
        pv_power_w=1900,
        low_pv_threshold_w=1600,
        hard_off_low_pv_cycles=15,
        hard_off_release_cycles=2,
    )
    assert released.hard_off_active is False
    assert released.low_pv_cycles == 0
    assert released.hard_off_release_ready_cycles == 2
    assert released.activation_allowed is True


@pytest.mark.unit
def test_hard_off_release_counter_resets_when_pv_drops_below_threshold():
    device = DeviceControlContext(
        device_id='EV_CHARGER',
        kind='EV',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=1840,
        max_absorb_w=6200,
        min_produce_w=0,
        max_produce_w=0,
        step_w=460,
        supports_primary_consuming_regulation=True,
        supports_producing_regulation=False,
        uses_hard_off_lifecycle=True,
        priority=10,
        producing_priority=0,
        current_control_target_w=0,
    )
    transition = compute_hard_off_lifecycle_transition(
        device,
        {
            'low_pv_cycles': 15,
            'hard_off_release_ready_cycles': 1,
            'hard_off_active': True,
        },
        lifecycle_enabled=True,
        requested_active=False,
        pv_power_w=1500,
        low_pv_threshold_w=1600,
        hard_off_low_pv_cycles=15,
        hard_off_release_cycles=2,
    )
    assert transition.hard_off_active is True
    assert transition.hard_off_release_ready_cycles == 0
    assert transition.recovery_condition is False


@pytest.mark.unit
def test_hard_off_release_counter_does_not_progress_while_activation_is_blocked():
    device = DeviceControlContext(
        device_id='EV_CHARGER',
        kind='EV',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=1840,
        max_absorb_w=6200,
        min_produce_w=0,
        max_produce_w=0,
        step_w=460,
        supports_primary_consuming_regulation=True,
        supports_producing_regulation=False,
        uses_hard_off_lifecycle=True,
        priority=10,
        producing_priority=0,
        current_control_target_w=0,
    )
    transition = compute_hard_off_lifecycle_transition(
        device,
        {
            'low_pv_cycles': 15,
            'hard_off_release_ready_cycles': 1,
            'hard_off_active': True,
        },
        lifecycle_enabled=True,
        requested_active=False,
        pv_power_w=1900,
        low_pv_threshold_w=1600,
        activation_blocked=True,
        hard_off_low_pv_cycles=15,
        hard_off_release_cycles=2,
    )
    assert transition.hard_off_active is True
    assert transition.hard_off_release_ready_cycles == 0
    assert transition.recovery_condition is False


@pytest.mark.unit
def test_engine_primary_ev_feedback_protection_triggers_hard_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
        ev_force_on=False,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
        previous_device_states=_previous_device_states(low_pv_cycles=2),
    )

    assert out.attrs['feedback_protection_active'] is True
    assert out.attrs['feedback_protection_primary_consuming_device_id'] == 'EV_CHARGER'
    assert out.attrs['feedback_protection_producing_device_id'] == 'HOME_BATTERY'
    assert out.attrs['activation_block_reason'] == 'primary_producer_feedback_protection'
    policy = _device_policy(out)
    lifecycle = _device_lifecycle_state(out)
    assert policy.mode == 'hard_off'
    assert lifecycle['hard_off_active'] is True
    assert policy.target_w == 0


@pytest.mark.unit
def test_engine_primary_ev_low_pv_pre_hard_off_keeps_min_current():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
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
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=1.5,
        previous_device_states=_previous_device_states(low_pv_cycles=0, hard_off_active=False),
    )

    assert out.attrs['feedback_protection_active'] is True
    assert out.attrs['feedback_protection_producer_active'] is True
    policy = _device_policy(out)
    lifecycle = _device_lifecycle_state(out)
    assert policy.mode == 'restore_min'
    assert lifecycle['hard_off_active'] is False
    assert policy.target_w == 0
    assert out.attrs['primary_consuming_skipped_by_id']['EV_CHARGER'] == 'producer_feedback_protection'


@pytest.mark.unit
def test_engine_primary_ev_force_on_bypasses_feedback_protection_before_hard_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
        ev_force_on=True,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
        previous_device_states=_previous_device_states(low_pv_cycles=2),
    )

    policy = _device_policy(out)
    lifecycle = _device_lifecycle_state(out)
    assert out.attrs['feedback_protection_active'] is False
    assert out.attrs['activation_block_reason'] == ''
    assert policy.mode == 'burn'
    assert lifecycle['hard_off_active'] is False
    assert policy.target_w == 6440
    policies = {policy.device_id: policy for policy in out.device_policies}
    assert policies['EV_CHARGER'].enabled is True
    assert policies['EV_CHARGER'].target_w == 6440


@pytest.mark.unit
def test_engine_primary_ev_force_on_bypasses_active_hard_off_without_clearing_state():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
        ev_force_on=True,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_release_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=0.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
        previous_device_states=_previous_device_states(
            mode='hard_off', low_pv_cycles=2, hard_off_active=True,
            hard_off_release_ready_cycles=0,
        ),
    )

    policy = _device_policy(out)
    lifecycle = _device_lifecycle_state(out)
    assert out.attrs['feedback_protection_active'] is False
    assert lifecycle['hard_off_active'] is True
    assert policy.mode == 'burn'
    assert policy.target_w == 6440
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
        primary_consuming_device_id='EV_CHARGER',
        ev_force_on=False,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=0, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
        previous_device_states=_previous_device_states(low_pv_cycles=1),
    )

    assert out.attrs['feedback_protection_active'] is False
    assert out.attrs['feedback_protection_producer_active'] is False
    assert _device_lifecycle_state(out)['hard_off_active'] is False
    assert _device_policy(out).mode == 'restore_min'
    assert _device_policy(out).target_w == 0
    assert out.attrs['primary_consuming_skipped_by_id']['EV_CHARGER'] == 'below_min_absorb_w'


@pytest.mark.unit
def test_engine_battery_primary_negative_setpoint_does_not_create_cross_device_feedback_block():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        ev_force_on=False,
        ev_hard_off_pv_threshold_kw=1.6,
    )
    m = make_m(current_battery_setpoint_w=-1200)
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
    )

    assert out.attrs['configured_primary_consuming_device_ids'] == ('HOME_BATTERY',)
    assert out.attrs['effective_primary_consuming_device_id'] == ''
    assert out.attrs['producing_regulator_device_ids'] == ('HOME_BATTERY',)
    assert out.attrs['feedback_protection_active'] is False
    assert out.attrs['activation_block_reason'] == ''


@pytest.mark.unit
def test_primary_producer_feedback_protection_is_capability_and_ownership_driven():
    primary = DeviceControlContext(
        device_id='PRIMARY_ABSORBER',
        kind='SYNTHETIC',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=100,
        max_absorb_w=2000,
        min_produce_w=0,
        max_produce_w=0,
        step_w=100,
        supports_primary_consuming_regulation=True,
        supports_producing_regulation=False,
        uses_hard_off_lifecycle=True,
        priority=10,
        producing_priority=0,
        current_control_target_w=500,
    )
    residual = DeviceControlContext(
        device_id='RESIDUAL_PRODUCER',
        kind='SYNTHETIC',
        can_absorb_w=False,
        can_produce_w=True,
        min_absorb_w=0,
        max_absorb_w=0,
        min_produce_w=0,
        max_produce_w=4000,
        step_w=100,
        supports_primary_consuming_regulation=False,
        supports_producing_regulation=True,
        uses_hard_off_lifecycle=False,
        priority=0,
        producing_priority=10,
        current_control_target_w=-1200,
    )

    assert compute_primary_producer_feedback_protection(
        primary, residual, low_energy_active=True
    ) is True
    assert compute_primary_producer_feedback_protection(
        primary, residual, low_energy_active=True, explicit_activation_request=True
    ) is False

    residual_not_producing = DeviceControlContext(
        **{**residual.__dict__, 'current_control_target_w': 0}
    )
    assert compute_primary_producer_feedback_protection(
        primary, residual_not_producing, low_energy_active=True
    ) is False

    same_device_residual = DeviceControlContext(
        **{**residual.__dict__, 'device_id': 'PRIMARY_ABSORBER'}
    )
    assert compute_primary_producer_feedback_protection(
        primary, same_device_residual, low_energy_active=True
    ) is False


@pytest.mark.unit
def test_engine_ev_primary_home_battery_small_positive_rpnz_does_not_release_hard_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
        adjustable_surplus_activation=2500,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_release_cycles=2,
    )
    m = make_m(grid_power_w=-10.0, ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=4)})
    nz = make_nz(rpnz_w=1.0, required_power_consumption_kw=0.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 270.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
        pv_power_kw=0.0,
        previous_device_states=_previous_device_states(
            mode='hard_off', low_pv_cycles=2, hard_off_active=True,
            hard_off_release_ready_cycles=0,
        ),
    )

    lifecycle = _device_lifecycle_state(out)
    assert lifecycle['hard_off_active'] is True
    assert _device_policy(out).target_w == 0
    assert lifecycle['hard_off_release_ready_cycles'] == 0


@pytest.mark.unit
def test_engine_ev_primary_home_battery_releases_hard_off_after_release_cycles():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
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
        **_relay_runtime_args(),
        pv_power_kw=1.6,
        previous_device_states=_previous_device_states(
            mode='hard_off', low_pv_cycles=2, hard_off_active=True,
            hard_off_release_ready_cycles=0,
        ),
    )

    first_lifecycle = _device_lifecycle_state(first)
    assert first_lifecycle['hard_off_active'] is True
    assert _device_policy(first).target_w == 0
    assert first_lifecycle['hard_off_release_ready_cycles'] == 1

    second = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 305.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
        pv_power_kw=1.6,
        previous_device_states=_previous_device_states(
            mode='hard_off', low_pv_cycles=2, hard_off_active=True,
            hard_off_release_ready_cycles=first_lifecycle['hard_off_release_ready_cycles'],
        ),
    )

    second_lifecycle = _device_lifecycle_state(second)
    assert second_lifecycle['hard_off_active'] is False
    assert _device_policy(second).target_w > 0
    assert second_lifecycle['hard_off_release_ready_cycles'] >= 2


@pytest.mark.unit
def test_engine_ev_primary_home_battery_release_counter_resets_on_condition_break():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
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
        **_relay_runtime_args(),
        pv_power_kw=1.6,
        previous_device_states=_previous_device_states(
            mode='hard_off', low_pv_cycles=2, hard_off_active=True,
            hard_off_release_ready_cycles=0,
        ),
    )

    first_lifecycle = _device_lifecycle_state(first)
    assert first_lifecycle['hard_off_release_ready_cycles'] == 1
    assert first_lifecycle['hard_off_active'] is True

    broken = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 365.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
        pv_power_kw=1.5,
        previous_device_states=_previous_device_states(
            mode='hard_off', low_pv_cycles=2, hard_off_active=True,
            hard_off_release_ready_cycles=first_lifecycle['hard_off_release_ready_cycles'],
        ),
    )

    broken_lifecycle = _device_lifecycle_state(broken)
    assert broken_lifecycle['hard_off_release_ready_cycles'] == 0
    assert broken_lifecycle['hard_off_active'] is True



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
        **_relay_runtime_args(surplus_allowed=False, active_device_ids=('GARAGE_EV',)),
        previous_device_states={
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
    assert 'GARAGE_EV' in out.attrs['surplus_active_device_ids']
    assert policies['GARAGE_EV'].enabled is True
    assert policies['GARAGE_EV'].target_w == 3680
    assert policies['EV_CHARGER'].enabled is False
    assert policies['EV_CHARGER'].target_w == 0
    assert payloads['GARAGE_EV']['enabled'] is True
    assert payloads['EV_CHARGER']['reason'] == 'ev_lifecycle_hard_off'
    assert out.attrs['previous_device_states']['EV_CHARGER']['mode'] == 'hard_off'
    assert 'GARAGE_EV' in out.attrs['previous_device_states']

@pytest.mark.unit
def test_engine_multi_ev_policy_and_lifecycle_are_stable_under_device_order_permutation(project_root):
    cfg_a = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(),
    )
    cfg_b = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(),
    )
    reordered = {}
    for device_id, device in cfg_b.devices.items():
        if device_id == 'EV_CHARGER':
            reordered['GARAGE_EV'] = cfg_b.devices['GARAGE_EV']
        if device_id != 'GARAGE_EV':
            reordered[device_id] = device
    cfg_b.devices = reordered

    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    kwargs = {
        'freeze_until_ts': None,
        **_relay_runtime_args(surplus_allowed=False, active_device_ids=('GARAGE_EV',)),
        'pv_power_kw': 2.0,
        'previous_device_states': {
            'EV_CHARGER': {
                'device_id': 'EV_CHARGER',
                'mode': 'hard_off',
                'low_pv_cycles': 2,
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
        },
    }
    args = (
        profiles,
        make_m(ev_states={
            'EV_CHARGER': ev_state(enabled=False, current_a=0),
            'GARAGE_EV': ev_state(enabled=True, current_a=6),
        }),
        make_haeo(),
        make_nz(rpnz_w=4000.0, required_power_consumption_kw=4.0),
        60.0,
    )

    out_a = compute_net_zero_engine_outputs(args[0], cfg_a, *args[1:], **kwargs)
    out_b = compute_net_zero_engine_outputs(args[0], cfg_b, *args[1:], **kwargs)

    policies_a = {
        policy.device_id: (policy.target_w, policy.enabled, policy.mode, policy.reason)
        for policy in out_a.device_policies
        if policy.device_id in ('EV_CHARGER', 'GARAGE_EV')
    }
    policies_b = {
        policy.device_id: (policy.target_w, policy.enabled, policy.mode, policy.reason)
        for policy in out_b.device_policies
        if policy.device_id in ('EV_CHARGER', 'GARAGE_EV')
    }
    assert policies_b == policies_a
    assert out_b.attrs['device_lifecycle_states'] == out_a.attrs['device_lifecycle_states']


@pytest.mark.unit
def test_engine_exact_primary_ev_device_id_does_not_fall_back_to_first_ev(project_root):
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(primary_consuming_device_id='EV_CHARGER'),
    )
    reordered = {'GARAGE_EV': cfg.devices['GARAGE_EV']}
    for device_id, device in cfg.devices.items():
        if device_id != 'GARAGE_EV':
            reordered[device_id] = device
    cfg.devices = reordered

    out = compute_net_zero_engine_outputs(
        make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO),
        cfg,
        make_m(ev_states={
            'EV_CHARGER': ev_state(enabled=True, current_a=6),
            'GARAGE_EV': ev_state(enabled=False, current_a=0),
        }),
        make_haeo(),
        make_nz(rpnz_w=1380.0, required_power_consumption_kw=1.0),
        60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
    )

    assert out.attrs['ev_device_ids'] == ('GARAGE_EV', 'EV_CHARGER')
    assert out.attrs['effective_primary_consuming_device_id'] == 'EV_CHARGER'


@pytest.mark.unit
def test_engine_primary_ev_owns_primary_target_while_other_ev_remains_surplus_candidate(project_root):
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(primary_consuming_device_id='EV_CHARGER'),
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
        **_relay_runtime_args(surplus_allowed=False),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['effective_primary_consuming_device_id'] == 'EV_CHARGER'
    assert out.attrs['effective_primary_consuming_device_id'] == 'EV_CHARGER'
    assert 'surplus_preferred_surplus_device_id' not in out.attrs
    assert 'EV_CHARGER' not in out.attrs['surplus_candidate_device_ids']
    assert 'GARAGE_EV' in out.attrs['surplus_candidate_device_ids']
    assert policies['EV_CHARGER'].reason == 'ev_primary_policy'
    assert policies['EV_CHARGER'].target_w == out.attrs['primary_consuming_device_target_w']

@pytest.mark.unit
def test_engine_latched_hard_off_keeps_device_policy_authority_when_ev_is_not_primary_or_surplus_eligible():
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        ev_surplus_allowed=False,
        ev_force_on=False,
    )
    out = compute_net_zero_engine_outputs(
        make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO),
        cfg,
        make_m(ev_states={'EV_CHARGER': ev_state(enabled=False, current_a=0)}),
        make_haeo(),
        make_nz(rpnz_w=0.0, required_power_consumption_kw=0.0),
        60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
        previous_device_states={
            'EV_CHARGER': {
                'device_id': 'EV_CHARGER',
                'mode': 'hard_off',
                'low_pv_cycles': 10,
                'hard_off_release_ready_cycles': 0,
                'hard_off_active': True,
            },
        },
    )

    policy = _device_policy(out)
    assert 'EV_CHARGER' not in out.attrs['surplus_candidate_device_ids']
    assert out.attrs['device_lifecycle_states']['EV_CHARGER']['hard_off_active'] is True
    assert policy.target_w == 0
    assert policy.enabled is False
    assert policy.mode == 'hard_off'
    assert policy.reason == 'ev_lifecycle_hard_off'


@pytest.mark.unit
def test_engine_hard_off_release_counters_follow_each_devices_pv_threshold(project_root):
    cfg = _core_cfg_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides={
            **_garage_ev_value_overrides(),
            'input_number.garage_ev_max_power_w': 5000,
            'input_number.garage_ev_low_pv_threshold_w': 2500,
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
        **_relay_runtime_args(surplus_allowed=False),
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
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
        previous_device_states=previous_device_states,
    )

    assert 'GARAGE_EV' in out.attrs['surplus_candidate_device_ids']
    assert set(out.attrs['hard_off_lifecycle_devices']) == {'EV_CHARGER', 'GARAGE_EV'}
    assert out.attrs['previous_device_states']['EV_CHARGER']['low_pv_cycles'] == 2
    assert out.attrs['previous_device_states']['EV_CHARGER']['hard_off_active'] is True
    assert out.attrs['previous_device_states']['GARAGE_EV']['low_pv_cycles'] == 4
    assert out.attrs['previous_device_states']['GARAGE_EV']['hard_off_active'] is False
    assert out.attrs['device_lifecycle_states'] == {
        'EV_CHARGER': out.attrs['previous_device_states']['EV_CHARGER'],
        'GARAGE_EV': out.attrs['previous_device_states']['GARAGE_EV'],
    }

@pytest.mark.unit
def test_engine_ev_kind_does_not_enable_hard_off_lifecycle_without_capability():
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
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
        **_relay_runtime_args(),
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
    assert _device_policy(out).mode == 'restore_min'
    assert 'EV_CHARGER' not in out.attrs['device_lifecycle_states']


@pytest.mark.unit
def test_engine_core_config_view_hot_path_uses_canonical_device_ids_without_ev_compat_view(project_root):
    cfg = _core_cfg_view_with_extra_devices(
        project_root,
        extra_devices={'GARAGE_EV': _garage_ev_device_config()},
        value_overrides=_garage_ev_value_overrides(),
    )
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(), make_haeo(), make_nz(rpnz_w=4000.0, required_power_consumption_kw=4.0), 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False, active_device_ids=('GARAGE_EV',)),
        previous_device_states={
            'EV_CHARGER': {
                'device_id': 'EV_CHARGER',
                'mode': 'hard_off',
                'low_pv_cycles': 2,
                'hard_off_release_ready_cycles': 1,
                'hard_off_active': True,
            },
        },
    )

    assert 'GARAGE_EV' in out.attrs['surplus_active_device_ids']
    assert not hasattr(cfg, 'ev_charger')
    assert 'legacy_device_bridge_count' not in out.attrs
    assert 'legacy_device_bridge_counts_by_kind' not in out.attrs

@pytest.mark.unit
def test_engine_without_ev_devices_skips_ev_policy_and_keeps_battery_relay_outputs(project_root):
    cfg = _core_cfg_without_ev_devices(project_root)
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, make_m(grid_power_w=-4000.0), make_haeo(),
        make_nz(rpnz_w=4000.0, required_power_consumption_kw=4.0), 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
        pv_power_kw=4.5,
        previous_device_states={
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
    assert out.attrs['previous_device_states']['EV_CHARGER']['mode'] == 'hard_off'
    assert 'EV_CHARGER' not in out.attrs['device_lifecycle_states']
    assert 'EV_CHARGER' not in policies
    assert set(policies) == {'HOME_BATTERY', 'RELAY1', 'RELAY2'}
    assert 'adjustable_surplus_load' not in out.attrs
    assert out.attrs['surplus_candidate_device_ids'] == ('RELAY1', 'RELAY2')

@pytest.mark.unit
def test_engine_ev_primary_restore_min_allows_battery_discharge_when_charger_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
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
        **_relay_runtime_args(),
        pv_power_kw=1.7,
        previous_device_states=_previous_device_states(),
    )

    assert _device_policy(out).mode == 'restore_min'
    assert _device_policy(out).target_w == 0
    assert _device_lifecycle_state(out)['hard_off_active'] is False
    assert out.battery_target_w == -2000
    assert out.attrs['producer_request_source'] == 'grid_feedback'
    assert out.attrs['producer_feedback_target_grid_w'] == -15.0
    assert out.attrs['producer_feedback_grid_actual_w'] == 2900.0
    assert out.attrs['producer_feedback_error_w'] == -2915.0
    assert out.attrs['producer_feedback_current_control_target_w'] == -1000.0
    assert out.attrs['producer_feedback_desired_control_target_w'] == -2500.0
    assert out.attrs['producer_requested_w'] == 2500.0


@pytest.mark.unit
def test_engine_ev_primary_restore_min_holds_battery_floor_when_charger_on():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        primary_consuming_device_id='EV_CHARGER',
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
        **_relay_runtime_args(),
        pv_power_kw=1.7,
        previous_device_states=_previous_device_states(),
    )

    assert _device_policy(out).mode == 'restore_min'
    assert _device_policy(out).target_w == 0
    assert _device_lifecycle_state(out)['hard_off_active'] is False
    assert out.battery_target_w == -2000
    assert out.attrs['producer_authority_device_ids'] == ('HOME_BATTERY',)
    assert out.attrs['producer_feedback_error_w'] == -2915.0
    assert out.attrs['producer_requested_w'] == 2500.0


@pytest.mark.unit
@pytest.mark.parametrize('rpnz_w', [4.0, 10.0, 11.0, 0.0, -1.0])
def test_engine_producer_authority_uses_grid_feedback_across_target_grid_zero(rpnz_w):
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(primary_consuming_device_id='EV_CHARGER')
    m = make_m(
        current_battery_setpoint_w=-1000,
        grid_power_w=2900.0,
        ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=cfg_ev_min_a(cfg))},
    )
    nz = make_nz(rpnz_w=rpnz_w, required_power_consumption_kw=0.5)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(active_device_ids=('EV_CHARGER',)),
        pv_power_kw=1.7,
        previous_device_states=_previous_device_states(),
    )

    expected_error_w = float(rpnz_w) - 2900.0
    expected_step_w = int(round((expected_error_w / 2.0) / 100.0)) * 100
    expected_desired_w = -1000.0 + float(expected_step_w)
    assert out.battery_target_w == -2000
    assert out.attrs['producer_authority_device_ids'] == ('HOME_BATTERY',)
    assert out.attrs['producer_request_source'] == 'grid_feedback'
    assert out.attrs['producer_feedback_target_grid_w'] == float(rpnz_w)
    assert out.attrs['producer_feedback_grid_actual_w'] == 2900.0
    assert out.attrs['producer_feedback_error_w'] == expected_error_w
    assert out.attrs['producer_feedback_desired_control_target_w'] == expected_desired_w
    assert out.attrs['producer_requested_w'] == -expected_desired_w
    assert out.attrs['battery_min_floor_reason'] == 'not_applicable'
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
        min_produce_w=0.0,
        max_produce_w=0.0,
        step_w=100.0,
        supports_primary_consuming_regulation=True,
        supports_producing_regulation=False,
        uses_hard_off_lifecycle=False,
        priority=50,
        producing_priority=0,
        current_control_target_w=750.0,
    )

    assert compute_primary_consuming_device_target_w(device, 50.0) == 200.0
    assert compute_primary_consuming_device_target_w(device, 240.0) == 200.0
    assert compute_primary_consuming_device_target_w(device, 1375.0) == 1300.0
    assert compute_primary_consuming_device_target_w(device, 2500.0) == 2000.0


@pytest.mark.unit
def test_primary_target_eligibility_is_capability_driven_not_kind_driven():
    unsupported_ev = DeviceControlContext(
        device_id='EV_TEST',
        kind='EV_CHARGER',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=100.0,
        max_absorb_w=1000.0,
        min_produce_w=0.0,
        max_produce_w=0.0,
        step_w=100.0,
        supports_primary_consuming_regulation=False,
        supports_producing_regulation=False,
        uses_hard_off_lifecycle=False,
        priority=10,
        producing_priority=0,
    )
    neutral_primary = DeviceControlContext(
        device_id='GENERIC_TEST',
        kind='TEST_DEVICE',
        can_absorb_w=True,
        can_produce_w=False,
        min_absorb_w=100.0,
        max_absorb_w=1000.0,
        min_produce_w=0.0,
        max_produce_w=0.0,
        step_w=100.0,
        supports_primary_consuming_regulation=True,
        supports_producing_regulation=False,
        uses_hard_off_lifecycle=False,
        priority=10,
        producing_priority=0,
    )

    assert compute_primary_consuming_device_target_w(unsupported_ev, 750.0) == 0.0
    assert compute_primary_consuming_device_target_w(neutral_primary, 750.0) == 700.0


@pytest.mark.unit
def test_engine_outputs_do_not_produce_p0_legacy_mirrors():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(primary_consuming_device_id='HOME_BATTERY')
    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(),
        make_haeo(),
        make_nz(rpnz_w=2500.0, required_power_consumption_kw=2.5),
        60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
    )

    removed_keys = {
        'selected_ev_device_id',
        'ev_policy_mode',
        'ev_low_pv_cycles',
        'ev_hard_off_active',
        'ev_hard_off_release_ready_cycles',
        'ev_hard_off_release_cycles_required',
        'ev_hard_off_release_rpc_kw',
        'ev_hard_off_pv_threshold_kw',
        'ev_primary_burn_active',
        'ev_surplus_burn_active',
        'ev_current_step_a',
        'ev_force_on',
        'ev_min_power_w',
        'ev_max_power_w',
        'ev_power_step_w',
        'ev_target_w',
        'previous_device_state',
        'previous_ev_device_states',
        'surplus_next_target',
        'surplus_release_candidate',
        'active_stack',
        'surplus_device_active_stack',
        'surplus_device_active_device_stack',
        'surplus_device_next_target',
        'surplus_device_next_device_id',
        'surplus_device_release_candidate',
        'surplus_device_release_device_id',
        'surplus_device_dispatch_decision',
        'surplus_device_dispatch_action',
        'surplus_device_dispatch_target',
        'surplus_device_dispatch_device_id',
        'surplus_device_dispatch_contract',
        'surplus_device_targets',
        'surplus_targets_by_device_id',
        'diagnostics_contract',
        'runtime_contract',
    }

    assert removed_keys.isdisjoint(out.attrs)
    assert 'device_policies' in out.attrs
    assert 'surplus_candidates' in out.attrs
    assert 'previous_device_states' in out.attrs
    assert 'device_lifecycle_states' in out.attrs
    assert all('decision_name' not in candidate for candidate in out.attrs['surplus_candidates'])


def _producer_context(
    device_id,
    *,
    producing_priority,
    max_produce_w,
    step_w=50,
    min_produce_w=0,
    current_control_target_w=0,
):
    return DeviceControlContext(
        device_id=device_id,
        kind='HOME_BATTERY',
        can_absorb_w=True,
        can_produce_w=True,
        min_absorb_w=0,
        max_absorb_w=5000,
        min_produce_w=min_produce_w,
        max_produce_w=max_produce_w,
        step_w=step_w,
        supports_primary_consuming_regulation=False,
        supports_producing_regulation=True,
        uses_hard_off_lifecycle=False,
        priority=0,
        producing_priority=producing_priority,
        current_control_target_w=current_control_target_w,
    )


def test_producer_feedback_request_uses_measured_grid_and_current_signed_producer_target():
    cfg = make_cfg(deadband_w=50)
    producer = _producer_context(
        'HOME_BATTERY',
        producing_priority=100,
        max_produce_w=100,
        step_w=50,
        current_control_target_w=-100,
    )

    feedback = _producer_feedback_request(cfg, (producer,), -730, 5772.39990234375)

    assert feedback['target_grid_w'] == -730.0
    assert feedback['grid_actual_w'] == 5772.39990234375
    assert feedback['error_w'] == pytest.approx(-6502.39990234375)
    assert feedback['current_control_target_w'] == -100.0
    assert feedback['desired_control_target_w'] == -3400.0
    assert feedback['requested_w'] == 3400.0


def test_producer_feedback_request_holds_current_target_inside_deadband():
    cfg = make_cfg(deadband_w=50)
    producer = _producer_context(
        'HOME_BATTERY',
        producing_priority=100,
        max_produce_w=4000,
        current_control_target_w=-600,
    )

    feedback = _producer_feedback_request(cfg, (producer,), -730, -780)

    assert feedback['error_w'] == 50.0
    assert feedback['desired_control_target_w'] == -600.0
    assert feedback['requested_w'] == 600.0


def test_producer_feedback_request_sums_signed_current_targets_for_sign_crossing():
    cfg = make_cfg(deadband_w=50)
    first = _producer_context(
        'BATTERY_A',
        producing_priority=20,
        max_produce_w=4000,
        current_control_target_w=2600,
    )
    second = _producer_context(
        'BATTERY_B',
        producing_priority=10,
        max_produce_w=4000,
        current_control_target_w=-500,
    )

    feedback = _producer_feedback_request(cfg, (first, second), -400, 6000)

    assert feedback['current_control_target_w'] == 2100.0
    assert feedback['error_w'] == -6400.0
    assert feedback['desired_control_target_w'] == -1100.0
    assert feedback['requested_w'] == 1100.0


@pytest.mark.unit
def test_snapshot_like_force_on_does_not_double_count_ev_target_into_producer_request():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_id='HOME_BATTERY',
        ev_force_on=True,
        max_battery_discharge_w=100,
        ev_max_absorb_w=7000,
    )
    m = make_m(
        current_battery_setpoint_w=-100,
        grid_power_w=5772.39990234375,
        pv_power_w=1672.0,
        ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=30)},
    )
    nz = make_nz(rpnz_w=-730.0, required_power_consumption_kw=0.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        **_relay_runtime_args(),
        pv_power_kw=1.672,
        previous_device_states=_previous_device_states(hard_off_active=True),
    )

    ev_policy = _device_policy(out, 'EV_CHARGER')
    assert ev_policy.reason == 'ev_force_on'
    assert ev_policy.target_w == 7000
    assert out.battery_target_w == -100
    assert out.attrs['producer_request_source'] == 'grid_feedback'
    assert out.attrs['residual_rpnz_w'] == -730.0
    assert out.attrs['producer_feedback_error_w'] == pytest.approx(-6502.39990234375)
    assert out.attrs['producer_feedback_current_control_target_w'] == -100.0
    assert out.attrs['producer_feedback_desired_control_target_w'] == -3400.0
    assert out.attrs['producer_requested_w'] == 3400.0
    assert out.attrs['producer_allocated_w_by_id']['HOME_BATTERY'] == 100.0
    assert out.attrs['unserved_production_w'] == 3300.0


def test_producer_quantization_is_toward_zero():
    assert quantize_produce_magnitude_toward_zero(3213, 50) == 3200


def test_strict_producing_priority_keeps_lower_closed_for_quantization_remainder():
    profiles = make_profiles()
    cfg = make_cfg(ramp_max_w=1000)
    first = _producer_context('BATTERY_A', producing_priority=20, max_produce_w=4000, step_w=50)
    second = _producer_context('BATTERY_B', producing_priority=10, max_produce_w=4000, step_w=1)

    dispatch = _allocate_producer_dispatch(profiles, cfg, (first, second), 3213)

    assert dispatch['allocated_w_by_id'] == {'BATTERY_A': 3200.0, 'BATTERY_B': 0.0}
    assert dispatch['unserved_w'] == 13.0


def test_strict_producing_priority_opens_lower_only_after_reachable_hard_ceiling():
    profiles = make_profiles()
    cfg = make_cfg(ramp_max_w=1000)
    first = _producer_context('BATTERY_A', producing_priority=20, max_produce_w=4033, step_w=50)
    second = _producer_context('BATTERY_B', producing_priority=10, max_produce_w=4000, step_w=50)

    dispatch = _allocate_producer_dispatch(profiles, cfg, (first, second), 5000)

    assert dispatch['ceiling_w_by_id']['BATTERY_A'] == 4000.0
    assert dispatch['allocated_w_by_id'] == {'BATTERY_A': 4000.0, 'BATTERY_B': 1000.0}
    assert dispatch['unserved_w'] == 0.0


def test_zero_ceiling_producer_does_not_block_priority_chain():
    profiles = make_profiles()
    cfg = make_cfg(ramp_max_w=1000)
    first = _producer_context('BATTERY_A', producing_priority=20, max_produce_w=0, step_w=50)
    second = _producer_context('BATTERY_B', producing_priority=10, max_produce_w=4000, step_w=50)

    dispatch = _allocate_producer_dispatch(profiles, cfg, (first, second), 700)

    assert dispatch['allocated_w_by_id'] == {'BATTERY_A': 0.0, 'BATTERY_B': 700.0}
    assert dispatch['unserved_w'] == 0.0


def test_nonzero_producer_minimum_skips_without_overshoot_and_tries_next():
    profiles = make_profiles()
    cfg = make_cfg(ramp_max_w=1000)
    first = _producer_context(
        'BATTERY_A', producing_priority=20, max_produce_w=4000, min_produce_w=1500, step_w=50
    )
    second = _producer_context('BATTERY_B', producing_priority=10, max_produce_w=4000, step_w=50)

    dispatch = _allocate_producer_dispatch(profiles, cfg, (first, second), 700)

    assert dispatch['allocated_w_by_id'] == {'BATTERY_A': 0.0, 'BATTERY_B': 700.0}
    assert dispatch['skipped_below_min_device_ids'] == ('BATTERY_A',)
    assert dispatch['unserved_w'] == 0.0


def test_producer_ramp_transient_does_not_change_priority_allocation():
    profiles = make_profiles()
    cfg = make_cfg(ramp_max_w=1000)
    first = _producer_context(
        'BATTERY_A', producing_priority=20, max_produce_w=4000, step_w=50, current_control_target_w=0
    )
    second = _producer_context('BATTERY_B', producing_priority=10, max_produce_w=4000, step_w=50)

    dispatch = _allocate_producer_dispatch(profiles, cfg, (first, second), 3000)
    transient = _producer_transient_target_w(cfg, first, dispatch['allocated_w_by_id']['BATTERY_A'])

    assert dispatch['allocated_w_by_id'] == {'BATTERY_A': 3000.0, 'BATTERY_B': 0.0}
    assert transient == -1000.0


def test_producer_authority_ramps_through_positive_target_during_sign_crossing():
    cfg = make_cfg(ramp_max_w=1000)
    producer = _producer_context(
        'BATTERY_A', producing_priority=20, max_produce_w=4000, step_w=50, current_control_target_w=2600
    )

    assert _producer_transient_target_w(cfg, producer, 4000) == 1600.0


def test_grid_feedback_keeps_producer_authority_active_through_positive_sign_crossing_transient():
    profiles = make_profiles()
    cfg = make_cfg(deadband_w=50, ramp_max_w=1000)
    producer = _producer_context(
        'BATTERY_A',
        producing_priority=20,
        max_produce_w=4000,
        step_w=50,
        current_control_target_w=2600,
    )

    feedback = _producer_feedback_request(cfg, (producer,), 0, 6000)
    dispatch = _allocate_producer_dispatch(
        profiles, cfg, (producer,), feedback['requested_w']
    )
    transient = _producer_transient_target_w(
        cfg, producer, dispatch['allocated_w_by_id']['BATTERY_A']
    )

    assert feedback['error_w'] == -6000.0
    assert feedback['desired_control_target_w'] == -400.0
    assert feedback['requested_w'] == 400.0
    assert dispatch['allocated_w_by_id'] == {'BATTERY_A': 400.0}
    # Authority is already producing-direction authority even though ramping from
    # +2600 W toward -400 W leaves this tick's transient target positive.
    assert transient == 1600.0


@pytest.mark.unit
def test_ordered_primary_fallback_uses_battery_when_ev_request_is_below_minimum():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_ids=('EV_CHARGER', 'HOME_BATTERY'),
        battery_surplus_allowed=True,
    )

    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(grid_power_w=0.0, current_battery_setpoint_w=100.0),
        make_haeo(),
        make_nz(rpnz_w=1000.0, required_power_consumption_kw=1.0),
        30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=3.0,
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['configured_primary_consuming_device_ids'] == ('EV_CHARGER', 'HOME_BATTERY')
    assert out.attrs['effective_primary_consuming_device_id'] == 'HOME_BATTERY'
    assert out.attrs['effective_primary_consuming_reason'] == 'selected'
    assert out.attrs['primary_consuming_skipped_by_id']['EV_CHARGER'] == 'below_min_absorb_w'
    assert policies['EV_CHARGER'].target_w == 0
    assert policies['HOME_BATTERY'].target_w == 600
    assert 'HOME_BATTERY' not in out.attrs['surplus_candidate_device_ids']
    assert out.attrs['unserved_primary_consuming_w'] == 0.0


@pytest.mark.unit
def test_ordered_primary_fallback_uses_battery_when_ev_is_hard_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_ids=('EV_CHARGER', 'HOME_BATTERY'),
        battery_surplus_allowed=True,
        ev_hard_off_low_pv_cycles=2,
    )

    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(grid_power_w=-1000.0, current_battery_setpoint_w=100.0),
        make_haeo(),
        make_nz(rpnz_w=1000.0, required_power_consumption_kw=2.0),
        30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=0.0,
        previous_device_states=_previous_device_states(
            mode='hard_off',
            low_pv_cycles=2,
            hard_off_active=True,
        ),
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['effective_primary_consuming_device_id'] == 'HOME_BATTERY'
    assert out.attrs['primary_consuming_skipped_by_id']['EV_CHARGER'] == 'lifecycle_hard_off'
    assert policies['EV_CHARGER'].mode == 'hard_off'
    assert policies['EV_CHARGER'].target_w == 0
    assert policies['HOME_BATTERY'].target_w > 100
    assert out.attrs['unserved_primary_consuming_w'] == 0.0


@pytest.mark.unit
def test_no_realisable_primary_reports_unserved_consuming_request_without_implicit_fallback():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        primary_consuming_device_ids=('EV_CHARGER',),
        battery_surplus_allowed=False,
    )

    out = compute_net_zero_engine_outputs(
        profiles,
        cfg,
        make_m(grid_power_w=0.0, current_battery_setpoint_w=100.0),
        make_haeo(),
        make_nz(rpnz_w=1000.0, required_power_consumption_kw=1.0),
        30.0,
        freeze_until_ts=None,
        **_relay_runtime_args(surplus_allowed=False),
        pv_power_kw=3.0,
    )

    policies = {policy.device_id: policy for policy in out.device_policies}
    assert out.attrs['effective_primary_consuming_device_id'] == ''
    assert out.attrs['effective_primary_consuming_reason'] == 'no_realisable_primary_consuming_device'
    assert out.attrs['primary_consuming_skipped_by_id']['EV_CHARGER'] == 'below_min_absorb_w'
    assert out.attrs['unserved_primary_consuming_w'] > 0.0
    assert policies['HOME_BATTERY'].target_w == 100
