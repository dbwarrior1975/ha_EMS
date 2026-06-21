import pytest
from ems_core.domain.models import ControlProfile, GoalProfile, GuardProfile, DominantLimitation, ForecastProfile
from ems_core.net_zero.engine import compute_net_zero_engine_outputs
from tests.helpers import make_profiles, make_cfg, make_m, make_haeo, make_nz


@pytest.mark.unit
def test_engine_manual_disables_battery_write_and_keeps_current_battery_setpoint():
    profiles = make_profiles(control=ControlProfile.MANUAL, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg()
    m = make_m(current_battery_setpoint_w=650)
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.attrs['battery_write_enabled'] is False


@pytest.mark.unit
def test_engine_trace_attrs_contain_ev_power_normalization():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        ev_min_current_a=6,
        ev_max_current_a=16,
        ev_current_step_a=4,
        ev_charger_phases=3,
    )
    m = make_m(charger_on=True, charger_current_a=10)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=2000.0), 0.0,
        freeze_until_ts=None,
        ev_burn_active=True,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=True,
    )

    assert out.ev_current_a == 16
    assert out.attrs['ev_min_power_w'] == 4140
    assert out.attrs['ev_max_power_w'] == 11040
    assert out.attrs['ev_power_step_w'] == 2760
    assert out.attrs['ev_target_w'] == 11040


@pytest.mark.unit
def test_engine_trace_attrs_contain_device_policies_with_watt_based_ev_contract():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        ev_min_current_a=6,
        ev_max_current_a=16,
        ev_charger_phases=3,
        relay1_power_kw=2.5,
        relay2_power_kw=5.0,
    )
    m = make_m(charger_on=True, charger_current_a=10)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=2000.0), 0.0,
        freeze_until_ts=None,
        ev_burn_active=True,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=True,
        relay2_net_zero_active=False,
        adjustable_surplus_active=True,
    )

    policies = {item['device_id']: item for item in out.attrs['device_policies']}
    policies_from_output = {policy.device_id: policy for policy in out.device_policies}

    assert out.attrs['device_policy_parity_ok'] is True
    assert out.attrs['device_policy_parity_mismatch'] == ''
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
def test_engine_surplus_device_trace_matches_current_activation_mapping():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        adjustable_primary_load='HOME_BATTERY',
        adjustable_surplus_activation=2000,
        ev_min_current_a=4,
        ev_max_current_a=28,
        ev_charger_phases=1,
    )
    m = make_m()

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500, required_power_consumption_kw=2.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=False,
        relay2_surplus_allowed=False,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
    )

    assert out.surplus_dispatch_decision == 'ACTIVATE_ADJUSTABLE'
    assert out.attrs['surplus_device_parity_ok'] is True
    assert out.attrs['surplus_device_parity_mismatch'] == ''
    assert out.attrs['surplus_device_dispatch_decision'] == 'ACTIVATE_ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_action'] == 'ACTIVATE'
    assert out.attrs['surplus_device_dispatch_target'] == 'ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_dispatch_contract'] == 'device_id_primary'
    assert out.attrs['surplus_dispatch_decision_role'] == 'ha_compatibility_mirror'
    assert out.attrs['surplus_device_next_target'] == 'ADJUSTABLE'
    assert out.attrs['surplus_device_next_device_id'] == 'EV_CHARGER'
    assert out.attrs['surplus_device_active_stack'] == 'NONE'
    assert out.attrs['surplus_device_targets'][0]['threshold_w'] == 2000


@pytest.mark.unit
def test_engine_cheap_grid_charge_local_battery_target_and_explanation():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.CHEAP_GRID_CHARGE, forecast=ForecastProfile.NONE)
    cfg = make_cfg()
    m = make_m()
    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(effective_forecast=ForecastProfile.NONE, configured_forecast=ForecastProfile.NONE), make_nz(), 0.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == -4000
    assert out.explanation == 'Local export-oriented policy'


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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
    )
    assert out.battery_target_w == -2500
    assert out.explanation == 'Export-oriented policy with HAEO forecast assistance'


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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=True,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        prev_relay1_force_on=False,
        prev_relay2_force_on=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=True,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        prev_relay1_force_on=True,
        prev_relay2_force_on=False,
    )

    assert out.attrs['surplus_freeze_until_ts'] == 130.0
    assert out.surplus_dispatch_decision == 'ACTIVATE_ADJUSTABLE'


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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=True,
    )

    assert out.surplus_dispatch_decision == 'RELEASE_ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_action'] == 'RELEASE'
    assert out.attrs['surplus_device_dispatch_target'] == 'ADJUSTABLE'
    assert out.attrs['surplus_device_dispatch_device_id'] == 'HOME_BATTERY'
    assert out.attrs['surplus_device_parity_ok'] is True
    assert out.battery_target_w < 2000


@pytest.mark.unit
def test_engine_adjustable_surplus_activation_overrides_threshold_source():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='EV_CHARGER',
        adjustable_primary_load='HOME_BATTERY',
        adjustable_surplus_activation=2000,
        ev_max_current_a=28,
        ev_min_current_a=4,
        ev_charger_phases=1,
    )
    m = make_m()

    below = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500, required_power_consumption_kw=1.9), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=False,
        relay2_surplus_allowed=False,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
    )

    at = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), make_nz(rpnz_w=500, required_power_consumption_kw=2.0), 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=False,
        relay2_surplus_allowed=False,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
    )

    assert below.surplus_dispatch_decision == 'NOOP'
    assert below.surplus_explanation == 'Waiting for ADJUSTABLE; raw RPC below threshold'
    assert at.surplus_dispatch_decision == 'ACTIVATE_ADJUSTABLE'
    assert at.surplus_explanation == 'Raw RPC 2.000 kW >= ADJUSTABLE threshold 2.000 kW'


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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
    )

    assert out.attrs['primary_surplus_combo_valid'] is False
    assert out.attrs['primary_surplus_combo_reason'] == 'fallback_to_cross_combo'
    assert out.attrs['primary_surplus_combo_fallback_active'] is True
    assert 'fallback_to_cross_combo' in out.attrs['primary_surplus_combo_warning']


@pytest.mark.unit
def test_engine_primary_ev_current_uses_configurable_step_size():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    m = make_m(charger_current_a=4)
    nz = make_nz(rpnz_w=1380, required_power_consumption_kw=2.0)

    cfg_step_2 = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_charger_phases=1,
        ev_min_current_a=4,
        ev_max_current_a=28,
        ev_current_step_a=2,
    )
    out_step_2 = compute_net_zero_engine_outputs(
        profiles, cfg_step_2, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=False,
        relay2_surplus_allowed=False,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
    )

    cfg_step_4 = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_charger_phases=1,
        ev_min_current_a=4,
        ev_max_current_a=28,
        ev_current_step_a=4,
    )
    out_step_4 = compute_net_zero_engine_outputs(
        profiles, cfg_step_4, m, make_haeo(), nz, 30.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=False,
        relay2_surplus_allowed=False,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
    )

    assert out_step_2.ev_current_a == 6
    assert out_step_2.attrs['ev_policy_mode'] == 'burn'
    assert out_step_4.ev_current_a == 4


@pytest.mark.unit
def test_engine_primary_ev_low_pv_and_battery_discharge_triggers_hard_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_force_current_a=0,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, charger_current_a=4)
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=3.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=False,
        relay2_surplus_allowed=False,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
        pv_power_kw=0.0,
        ev_low_pv_cycles=2,
    )

    assert out.attrs['battery_to_ev_loop_risk'] is True
    assert out.attrs['ev_primary_burn_active'] is False
    assert out.attrs['ev_policy_mode'] == 'hard_off'
    assert out.attrs['ev_hard_off_active'] is True
    assert out.ev_current_a == 0


@pytest.mark.unit
def test_engine_primary_ev_low_pv_pre_hard_off_keeps_min_current():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO, guard=GuardProfile.NORMAL_LIMITS)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
        ev_min_current_a=4,
        ev_force_current_a=0,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
    )
    m = make_m(current_battery_setpoint_w=-1200, charger_current_a=4)
    nz = make_nz(rpnz_w=500, required_power_consumption_kw=1.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=False,
        relay2_surplus_allowed=False,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
        pv_power_kw=1.5,
        ev_low_pv_cycles=0,
        ev_hard_off_active=False,
    )

    assert out.attrs['battery_to_ev_loop_risk'] is True
    assert out.attrs['ev_policy_mode'] == 'restore_min'
    assert out.attrs['ev_hard_off_active'] is False
    assert out.ev_current_a == 4


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
    m = make_m(grid_power_w=-10.0, charger_current_a=4)
    nz = make_nz(rpnz_w=1.0, required_power_consumption_kw=0.0)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 270.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
        pv_power_kw=0.0,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=0,
    )

    assert out.attrs['ev_hard_off_active'] is True
    assert out.ev_current_a == 0
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
    m = make_m(grid_power_w=-1100.0, charger_current_a=cfg.ev_min_current_a)
    release_rpc_kw = (cfg.ev_min_current_a * max(cfg.ev_charger_phases, 1) * 230) / 1000.0
    nz = make_nz(rpnz_w=2600.0, required_power_consumption_kw=release_rpc_kw)

    first = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 275.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
        pv_power_kw=1.6,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=0,
    )

    assert first.attrs['ev_hard_off_active'] is True
    assert first.ev_current_a == 0
    assert first.attrs['ev_hard_off_release_ready_cycles'] == 1

    second = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 305.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
        pv_power_kw=1.6,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=first.attrs['ev_hard_off_release_ready_cycles'],
    )

    assert second.attrs['ev_hard_off_active'] is False
    assert second.ev_current_a > 0
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
    m = make_m(grid_power_w=-1100.0, charger_current_a=cfg.ev_min_current_a)
    release_rpc_kw = (cfg.ev_min_current_a * max(cfg.ev_charger_phases, 1) * 230) / 1000.0
    nz = make_nz(rpnz_w=2600.0, required_power_consumption_kw=release_rpc_kw)

    first = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 335.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
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
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
        pv_power_kw=1.5,
        ev_hard_off_active=True,
        ev_low_pv_cycles=2,
        ev_hard_off_release_ready_cycles=first.attrs['ev_hard_off_release_ready_cycles'],
    )

    assert broken.attrs['ev_hard_off_release_ready_cycles'] == 0
    assert broken.attrs['ev_hard_off_active'] is True
    assert broken.ev_current_a == 0


@pytest.mark.unit
def test_engine_ev_primary_restore_min_allows_battery_discharge_when_charger_off():
    profiles = make_profiles(control=ControlProfile.AUTOMATIC, goal=GoalProfile.NET_ZERO)
    cfg = make_cfg(
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='EV_CHARGER',
    )
    m = make_m(
        charger_on=False,
        charger_current_a=cfg.ev_min_current_a,
        current_battery_setpoint_w=-1000,
        grid_power_w=2900.0,
    )
    nz = make_nz(rpnz_w=-15.0, required_power_consumption_kw=-2.49)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
        pv_power_kw=1.7,
        ev_hard_off_active=False,
        ev_low_pv_cycles=0,
    )

    assert out.attrs['ev_policy_mode'] == 'restore_min'
    assert out.ev_current_a == cfg.ev_min_current_a
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
        charger_on=True,
        charger_current_a=cfg.ev_min_current_a,
        current_battery_setpoint_w=-1000,
        grid_power_w=2900.0,
    )
    nz = make_nz(rpnz_w=-15.0, required_power_consumption_kw=-2.49)

    out = compute_net_zero_engine_outputs(
        profiles, cfg, m, make_haeo(), nz, 60.0,
        freeze_until_ts=None,
        ev_burn_active=False,
        relay1_surplus_allowed=True,
        relay2_surplus_allowed=True,
        relay1_force_on=False,
        relay2_force_on=False,
        relay1_net_zero_active=False,
        relay2_net_zero_active=False,
        adjustable_surplus_active=False,
        pv_power_kw=1.7,
        ev_hard_off_active=False,
        ev_low_pv_cycles=0,
    )

    assert out.attrs['ev_policy_mode'] == 'restore_min'
    assert out.ev_current_a == cfg.ev_min_current_a
    assert out.attrs['ev_hard_off_active'] is False
    assert out.battery_target_w == 0
