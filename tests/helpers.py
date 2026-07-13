from ems_core.domain import ev_power as _ev_power
from ems_core.domain.models import (
    ControlProfile,
    CoreBatteryAdapterConfig,
    CoreBatteryDeviceConfig,
    CoreBatteryGuardConfig,
    CoreBatteryPolicyConfig,
    CoreConfig,
    CoreDiagnosticsOutputsConfig,
    CoreDeviceCapabilitiesConfig,
    CoreEvAdapterConfig,
    CoreEvChargerDeviceConfig,
    CoreEvPolicyConfig,
    CoreGlobalConfig,
    CorePolicyEngineConfig,
    CorePolicyOutputsConfig,
    CoreProfilesConfig,
    CoreRelayAdapterConfig,
    CoreRelayDeviceConfig,
    CoreRelayPolicyConfig,
    CoreRuntimeConfig,
    CoreStateConfig,
    ForecastProfile,
    GoalProfile,
    GuardProfile,
    HaeoTargets,
    NetZeroState,
    Profiles,
    RuntimeMeasurements,
)


def make_profiles(**overrides):
    data = dict(
        control=ControlProfile.AUTOMATIC,
        goal=GoalProfile.NET_ZERO,
        forecast=ForecastProfile.NONE,
        guard=GuardProfile.NORMAL_LIMITS,
    )
    data.update(overrides)
    return Profiles(**data)


def make_cfg(**overrides):
    data = dict(
        deadband_w=50.0,
        ramp_max_w=1000.0,
        strict_limits_max_w=4600.0,
        max_battery_discharge_w=4600.0,
        default_sp_w=100.0,
        max_solar_charge_w=3700.0,
        battery_protect_soc=2.0,
        battery_protect_soc_recovery_margin=1.0,
        battery_protect_min_cell_voltage_v=3.03,
        battery_protect_charge_floor_w=0.0,
        battery_heartbeat_timeout_s=360.0,
        haeo_stale_timeout_s=300.0,
        ev_min_absorb_w=1380.0,
        ev_max_absorb_w=6440.0,
        ev_charger_phases=1,
        ev_voltage_v=230.0,
        ev_force_on=False,
        ev_hard_off_pv_threshold_kw=1.6,
        ev_hard_off_low_pv_cycles=2,
        ev_hard_off_release_cycles=2,
        ev_current_step_a=4,
        nz_battery_floor_default_w=100.0,
        nz_battery_floor_ev_active_w=0.0,
        primary_consuming_device_id='',
        primary_consuming_device_ids=None,
        adjustable_surplus_load_priority=3,
        ev_priority=3,
        surplus_freeze_s=30,
    )
    data.update(overrides)

    relay_thresholds_w = {
        'RELAY1': 2500,
        'RELAY2': 5000,
    }
    relay_thresholds_w.update(data.pop('relay_thresholds_w', {}) or {})
    relay_priorities = {
        'RELAY1': 2,
        'RELAY2': 1,
    }
    relay_priorities.update(data.pop('relay_priorities', {}) or {})
    relay_policies = {
        'RELAY1': {'surplus_allowed': True, 'force_on': False},
        'RELAY2': {'surplus_allowed': True, 'force_on': False},
    }
    for device_id, policy_overrides in (data.pop('relay_policies', {}) or {}).items():
        relay_policies.setdefault(str(device_id), {}).update(policy_overrides or {})
    ev_priority = int(data.pop('ev_priority'))
    battery_surplus_allowed = bool(overrides.get('battery_surplus_allowed', True))
    ev_surplus_allowed = bool(overrides.get('ev_surplus_allowed', True))

    home_battery = CoreBatteryDeviceConfig(
        device_id='HOME_BATTERY',
        kind='BATTERY',
        capabilities=CoreDeviceCapabilitiesConfig(
            can_absorb_w=True,
            can_produce_w=True,
            supports_primary_consuming_regulation=True,
            supports_producing_regulation=True,
            min_absorb_w=0,
            max_absorb_w=float(data['max_solar_charge_w']),
            step_w=float(data['deadband_w']),
            min_produce_w=0,
            max_produce_w=float(data['max_battery_discharge_w']),
            uses_hard_off_lifecycle=False,
        ),
        policy=CoreBatteryPolicyConfig(
            priority=int(data['adjustable_surplus_load_priority']),
            producing_priority=100,
            surplus_allowed=battery_surplus_allowed,
            surplus_dispatch_mode='max_absorb',
            default_min_absorb_w=None,
        ),
        guard=CoreBatteryGuardConfig(
            soc='sensor.soc',
            min_cell_voltage_v='sensor.min_cell_voltage_v',
            heartbeat='sensor.battery_heartbeat',
            protect_soc=float(data['battery_protect_soc']),
            protect_soc_recovery_margin=float(data['battery_protect_soc_recovery_margin']),
            protect_min_cell_voltage_v=float(data['battery_protect_min_cell_voltage_v']),
            protect_min_absorb_w=float(data['battery_protect_charge_floor_w']),
        ),
        adapter=CoreBatteryAdapterConfig(
            target_w='number.battery_target_w',
        ),
    )
    ev_charger = CoreEvChargerDeviceConfig(
        device_id='EV_CHARGER',
        kind='EV_CHARGER',
        capabilities=CoreDeviceCapabilitiesConfig(
            can_absorb_w=True,
            can_produce_w=False,
            supports_primary_consuming_regulation=True,
            supports_producing_regulation=False,
            min_absorb_w=float(data['ev_min_absorb_w']),
            max_absorb_w=float(data['ev_max_absorb_w']),
            step_w=float(_ev_power.ev_current_a_to_power_w(data['ev_current_step_a'], data['ev_charger_phases'], data['ev_voltage_v'])),
            min_produce_w=0,
            max_produce_w=None,
            uses_hard_off_lifecycle=True,
        ),
        policy=CoreEvPolicyConfig(
            priority=ev_priority,
            producing_priority=0,
            surplus_allowed=ev_surplus_allowed,
            force_on=bool(data['ev_force_on']),
            low_pv_threshold_w=float(data['ev_hard_off_pv_threshold_kw']),
            hard_off_low_pv_cycles=int(data['ev_hard_off_low_pv_cycles']),
            hard_off_release_cycles=int(data['ev_hard_off_release_cycles']),
            surplus_dispatch_mode='max_absorb',
        ),
        adapter=CoreEvAdapterConfig(
            enabled='switch.ev_enabled',
            current_a='number.ev_current_a',
            current_step_a=int(data['ev_current_step_a']),
            phases=int(data['ev_charger_phases']),
            voltage_v=float(data['ev_voltage_v']),
        ),
    )
    relay1 = CoreRelayDeviceConfig(
        device_id='RELAY1',
        kind='RELAY',
        capabilities=CoreDeviceCapabilitiesConfig(
            can_absorb_w=True,
            can_produce_w=False,
            supports_primary_consuming_regulation=False,
            supports_producing_regulation=False,
            min_absorb_w=int(relay_thresholds_w['RELAY1']),
            max_absorb_w=int(relay_thresholds_w['RELAY1']),
            step_w=int(relay_thresholds_w['RELAY1']),
            min_produce_w=0,
            max_produce_w=None,
            uses_hard_off_lifecycle=False,
        ),
        policy=CoreRelayPolicyConfig(
            priority=int(relay_priorities['RELAY1']),
            producing_priority=0,
            surplus_allowed=bool(relay_policies['RELAY1'].get('surplus_allowed', True)),
            force_on=bool(relay_policies['RELAY1'].get('force_on', False)),
            surplus_dispatch_mode='fixed',
        ),
        adapter=CoreRelayAdapterConfig(enabled='switch.relay1'),
    )
    relay2 = CoreRelayDeviceConfig(
        device_id='RELAY2',
        kind='RELAY',
        capabilities=CoreDeviceCapabilitiesConfig(
            can_absorb_w=True,
            can_produce_w=False,
            supports_primary_consuming_regulation=False,
            supports_producing_regulation=False,
            min_absorb_w=int(relay_thresholds_w['RELAY2']),
            max_absorb_w=int(relay_thresholds_w['RELAY2']),
            step_w=int(relay_thresholds_w['RELAY2']),
            min_produce_w=0,
            max_produce_w=None,
            uses_hard_off_lifecycle=False,
        ),
        policy=CoreRelayPolicyConfig(
            priority=int(relay_priorities['RELAY2']),
            producing_priority=0,
            surplus_allowed=bool(relay_policies['RELAY2'].get('surplus_allowed', True)),
            force_on=bool(relay_policies['RELAY2'].get('force_on', False)),
            surplus_dispatch_mode='fixed',
        ),
        adapter=CoreRelayAdapterConfig(enabled='switch.relay2'),
    )

    cfg = CoreConfig(
        profiles=CoreProfilesConfig(
            control=ControlProfile.AUTOMATIC,
            goal=GoalProfile.NET_ZERO,
            forecast=ForecastProfile.NONE,
            guard=GuardProfile.NORMAL_LIMITS,
        ),
        policy_engine=CorePolicyEngineConfig(interval_seconds=5.0),
        global_config=CoreGlobalConfig(
            deadband_w=float(data['deadband_w']),
            ramp_w=float(data['ramp_max_w']),
            strict_limit_w=float(data['strict_limits_max_w']),
            default_sp_w=float(data['default_sp_w']),
            surplus_freeze_s=int(data['surplus_freeze_s']),
            battery_heartbeat_timeout_s=float(data['battery_heartbeat_timeout_s']),
            haeo_stale_timeout_s=float(data['haeo_stale_timeout_s']),
            nz_battery_floor_default_w=float(data['nz_battery_floor_default_w']),
            nz_battery_floor_ev_active_w=float(data['nz_battery_floor_ev_active_w']),
            primary_consuming_device_ids=tuple(
                data['primary_consuming_device_ids']
                if data.get('primary_consuming_device_ids') is not None
                else ((str(data['primary_consuming_device_id']),) if str(data['primary_consuming_device_id']) else ())
            ),
        ),
        runtime=CoreRuntimeConfig(
            grid_power_w='sensor.grid_power_w',
            quarter_energy_balance_kwh='sensor.hourly_energy_balance',
            pv_power_w='sensor.pv_power_w',
        ),
        state=CoreStateConfig(
            surplus_freeze_until='input_datetime.surplus_freeze_until',
            active_surplus_devices='sensor.active_surplus_devices',
        ),
        policy_outputs=CorePolicyOutputsConfig(
            device_policies='sensor.device_policies',
            dispatch_command='sensor.dispatch_command',
            policy_state='sensor.policy_state',
        ),
        diagnostics_outputs=CoreDiagnosticsOutputsConfig(
            policy_diagnostics='sensor.policy_diagnostics',
            actuator_writer_trace='sensor.actuator_writer_trace',
            dispatch_state_applier_trace='sensor.dispatch_state_applier_trace',
        ),
        devices={
            'HOME_BATTERY': home_battery,
            'EV_CHARGER': ev_charger,
            'RELAY1': relay1,
            'RELAY2': relay2,
        },
    )
    cfg.ev_min_absorb_w = float(data['ev_min_absorb_w'])
    cfg.ev_max_absorb_w = float(data['ev_max_absorb_w'])
    cfg.ev_power_step_w = float(_ev_power.ev_power_step_w(ev_charger))
    cfg.min_absorb_w = float(data['ev_min_absorb_w'])
    cfg.max_absorb_w = float(data['ev_max_absorb_w'])
    cfg.step_w = float(cfg.ev_power_step_w)
    return cfg


def ev_w(current_a, phases=1, voltage_v=230):
    return _ev_power.ev_current_a_to_power_w(current_a, phases, voltage_v)


def cfg_ev_min_a(cfg):
    ev_adapter = cfg.device_by_id('EV_CHARGER').adapter
    return getattr(_ev_power, 'ev_min_' 'current_a_from_min_absorb_w')(
        cfg.ev_min_absorb_w,
        phases=ev_adapter.phases,
        voltage_v=ev_adapter.voltage_v,
        current_step_a=ev_adapter.current_step_a,
    )


def cfg_ev_max_a(cfg):
    ev_adapter = cfg.device_by_id('EV_CHARGER').adapter
    return getattr(_ev_power, 'ev_max_' 'current_a_from_max_absorb_w')(
        cfg.ev_max_absorb_w,
        phases=ev_adapter.phases,
        voltage_v=ev_adapter.voltage_v,
        current_step_a=ev_adapter.current_step_a,
    )


def ev_state(*, enabled=False, active=None, current_a=0):
    enabled = bool(enabled)
    current_a = int(current_a)
    if active is None:
        active = enabled and current_a > 0
    return {
        'enabled': enabled,
        'current_a': current_a,
        'active': bool(active),
    }


def relay_state(*, active=False, surplus_allowed=None, force_on=None):
    state = {
        'active': bool(active),
    }
    if surplus_allowed is not None:
        state['surplus_allowed'] = bool(surplus_allowed)
    if force_on is not None:
        state['force_on'] = bool(force_on)
    return state


def make_m(**overrides):
    ev_states = dict(overrides.pop('ev_states', {}) or {})
    relay_states = dict(overrides.pop('relay_states', {}) or {})
    battery_states = dict(overrides.pop('battery_states', {}) or {})

    # Scalar convenience inputs are translated only in this test helper. The
    # production RuntimeMeasurements contract is device-owned.
    scalar_soc = overrides.pop('soc', 50.0)
    scalar_min_cell = overrides.pop('min_cell_voltage_v', 3.2)
    scalar_heartbeat_age = overrides.pop('battery_heartbeat_age_s', 0.0)
    scalar_setpoint = overrides.pop('current_battery_setpoint_w', 100.0)
    battery_states.setdefault(
        'HOME_BATTERY',
        {
            'soc': scalar_soc,
            'min_cell_voltage_v': scalar_min_cell,
            'heartbeat_age_s': scalar_heartbeat_age,
            'current_setpoint_w': scalar_setpoint,
            'heartbeat': 0.0,
        },
    )
    ev_states.setdefault('EV_CHARGER', ev_state())
    relay_states.setdefault('RELAY1', relay_state())
    relay_states.setdefault('RELAY2', relay_state())

    data = dict(
        now_ts=0.0,
        grid_power_w=0.0,
        quarter_energy_balance_kwh=0.0,
        pv_power_w=None,
        battery_states=battery_states,
        ev_states=ev_states,
        relay_states=relay_states,
    )
    data.update(overrides)
    return RuntimeMeasurements(**data)


def make_haeo(**overrides):
    # Scalar convenience inputs remain test-only; production HAEO ownership is
    # explicit by device_id.
    battery_target_kw = overrides.pop('battery_target_kw', None)
    ev_target_kw = overrides.pop('ev_target_kw', None)
    data = dict(
        effective_forecast=ForecastProfile.NONE,
        configured_forecast=ForecastProfile.NONE,
        fresh=True,
        device_target_kw_by_id={},
        device_age_s_by_id={},
    )
    if battery_target_kw is not None:
        data['device_target_kw_by_id']['HOME_BATTERY'] = float(battery_target_kw)
        data['device_age_s_by_id']['HOME_BATTERY'] = 0.0
    if ev_target_kw is not None:
        data['device_target_kw_by_id']['EV_CHARGER'] = float(ev_target_kw)
        data['device_age_s_by_id']['EV_CHARGER'] = 0.0
    data.update(overrides)
    return HaeoTargets(**data)


def make_nz(**overrides):
    data = dict(rpnz_w=0.0, required_power_consumption_kw=0.0)
    data.update(overrides)
    return NetZeroState(**data)


def balance_for_rpnz_w(rpnz_w, remaining_s=900.0):
    horizon_s = max(float(remaining_s), 30.0)
    return -(float(rpnz_w) / 1000.0) * horizon_s / 3600.0


def runtime_inputs_for_net_zero(
    entity_ids,
    *,
    rpnz_w,
    required_power_consumption_kw,
    remaining_s=900.0,
    pv_power_kw=None,
):
    quarter_energy_balance_kwh = balance_for_rpnz_w(rpnz_w, remaining_s=remaining_s)
    required_power_w = float(required_power_consumption_kw) * 1000.0
    target_grid_w = -(quarter_energy_balance_kwh * 3_600_000.0 / max(float(remaining_s), 30.0))
    grid_power_w = target_grid_w - required_power_w
    values = {
        entity_ids['quarter_energy_balance_kwh']: quarter_energy_balance_kwh,
        entity_ids['grid_power_w']: grid_power_w,
    }
    if pv_power_kw is not None:
        values[entity_ids['pv_power_w']] = float(pv_power_kw) * 1000.0
    return values
