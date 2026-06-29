from ems_core.domain import ev_power as _ev_power
from ems_core.domain.models import (
    ControlProfile,
    CoreBatteryAdapterConfig,
    CoreBatteryDeviceConfig,
    CoreBatteryGuardConfig,
    CoreBatteryPolicyConfig,
    CoreConfig,
    CoreDeviceCapabilitiesConfig,
    CoreEvAdapterConfig,
    CoreEvChargerDeviceConfig,
    CoreEvPolicyConfig,
    CoreGlobalConfig,
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
        adjustable_surplus_load='HOME_BATTERY',
        adjustable_primary_load='',
        adjustable_surplus_activation=0.0,
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

    home_battery = CoreBatteryDeviceConfig(
        device_id='HOME_BATTERY',
        kind='BATTERY',
        capabilities=CoreDeviceCapabilitiesConfig(
            can_absorb_w=True,
            can_produce_w=True,
            min_absorb_w=0,
            max_absorb_w=float(data['max_solar_charge_w']),
            step_w=float(data['deadband_w']),
            max_produce_w=float(data['max_battery_discharge_w']),
        ),
        policy=CoreBatteryPolicyConfig(
            priority=int(data['adjustable_surplus_load_priority']),
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
            measured_power_w='sensor.battery_power_w',
        ),
    )
    ev_charger = CoreEvChargerDeviceConfig(
        device_id='EV_CHARGER',
        kind='EV_CHARGER',
        capabilities=CoreDeviceCapabilitiesConfig(
            can_absorb_w=True,
            can_produce_w=False,
            min_absorb_w=float(data['ev_min_absorb_w']),
            max_absorb_w=float(data['ev_max_absorb_w']),
            step_w=float(_ev_power.ev_current_a_to_power_w(data['ev_current_step_a'], data['ev_charger_phases'], data['ev_voltage_v'])),
            max_produce_w=None,
        ),
        policy=CoreEvPolicyConfig(
            priority=ev_priority,
            surplus_allowed=bool(overrides.get('ev_surplus_allowed', True)),
            force_on=bool(data['ev_force_on']),
            low_pv_threshold_w=float(data['ev_hard_off_pv_threshold_kw']),
            hard_off_low_pv_cycles=int(data['ev_hard_off_low_pv_cycles']),
            hard_off_release_cycles=int(data['ev_hard_off_release_cycles']),
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
            min_absorb_w=int(relay_thresholds_w['RELAY1']),
            max_absorb_w=int(relay_thresholds_w['RELAY1']),
            step_w=int(relay_thresholds_w['RELAY1']),
            max_produce_w=None,
        ),
        policy=CoreRelayPolicyConfig(
            priority=int(relay_priorities['RELAY1']),
            surplus_allowed=bool(relay_policies['RELAY1'].get('surplus_allowed', True)),
            force_on=bool(relay_policies['RELAY1'].get('force_on', False)),
        ),
        adapter=CoreRelayAdapterConfig(enabled='switch.relay1'),
    )
    relay2 = CoreRelayDeviceConfig(
        device_id='RELAY2',
        kind='RELAY',
        capabilities=CoreDeviceCapabilitiesConfig(
            can_absorb_w=True,
            can_produce_w=False,
            min_absorb_w=int(relay_thresholds_w['RELAY2']),
            max_absorb_w=int(relay_thresholds_w['RELAY2']),
            step_w=int(relay_thresholds_w['RELAY2']),
            max_produce_w=None,
        ),
        policy=CoreRelayPolicyConfig(
            priority=int(relay_priorities['RELAY2']),
            surplus_allowed=bool(relay_policies['RELAY2'].get('surplus_allowed', True)),
            force_on=bool(relay_policies['RELAY2'].get('force_on', False)),
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
            adjustable_surplus_load=str(data['adjustable_surplus_load']),
            adjustable_primary_load=str(data['adjustable_primary_load']),
            adjustable_surplus_activation_w=float(data['adjustable_surplus_activation']),
        ),
        home_battery=home_battery,
        runtime=CoreRuntimeConfig(
            grid_power_w='sensor.grid_power_w',
            hourly_energy_balance_kwh='sensor.hourly_energy_balance_kwh',
            required_power_w='sensor.required_power_w',
            rpnz_w='sensor.rpnz_w',
            pv_power_w='sensor.pv_power_w',
        ),
        state=CoreStateConfig(
            surplus_freeze_until='input_datetime.surplus_freeze_until',
            active_surplus_devices='sensor.active_surplus_devices',
        ),
        policy_outputs=CorePolicyOutputsConfig(
            decision_trace='sensor.decision_trace',
            device_policies='sensor.device_policies',
            surplus_policy_active='binary_sensor.surplus_policy_active',
            surplus_dispatch_decision='sensor.surplus_dispatch_decision',
        ),
        devices={
            'HOME_BATTERY': home_battery,
            'EV_CHARGER': ev_charger,
            'RELAY1': relay1,
            'RELAY2': relay2,
        },
    )
    cfg.ev_charger_phases = int(data['ev_charger_phases'])
    cfg.ev_current_step_a = int(data['ev_current_step_a'])
    cfg.ev_voltage_v = float(data['ev_voltage_v'])
    cfg.ev_min_absorb_w = float(data['ev_min_absorb_w'])
    cfg.ev_max_absorb_w = float(data['ev_max_absorb_w'])
    cfg.ev_power_step_w = float(_ev_power.ev_power_step_w(cfg))
    cfg.min_absorb_w = float(data['ev_min_absorb_w'])
    cfg.max_absorb_w = float(data['ev_max_absorb_w'])
    cfg.step_w = float(cfg.ev_power_step_w)
    cfg.ev_force_on = bool(data['ev_force_on'])
    return cfg


def ev_w(current_a, phases=1, voltage_v=230):
    return _ev_power.ev_current_a_to_power_w(current_a, phases, voltage_v)


def cfg_ev_min_a(cfg):
    return getattr(_ev_power, 'ev_min_' 'current_a_from_min_absorb_w')(
        cfg.ev_min_absorb_w,
        phases=cfg.ev_charger_phases,
        voltage_v=cfg.ev_voltage_v,
        current_step_a=cfg.ev_current_step_a,
    )


def cfg_ev_max_a(cfg):
    return getattr(_ev_power, 'ev_max_' 'current_a_from_max_absorb_w')(
        cfg.ev_max_absorb_w,
        phases=cfg.ev_charger_phases,
        voltage_v=cfg.ev_voltage_v,
        current_step_a=cfg.ev_current_step_a,
    )


def make_m(**overrides):
    data = dict(
        now_ts=0.0,
        soc=50.0,
        min_cell_voltage_v=3.2,
        battery_heartbeat_age_s=0.0,
        grid_power_w=0.0,
        current_battery_setpoint_w=100.0,
        hourly_energy_balance_kwh=0.0,
        charger_on=False,
        charger_current_a=4,
        relay1_on=False,
        relay2_on=False,
    )
    data.update(overrides)
    return RuntimeMeasurements(**data)


def make_haeo(**overrides):
    data = dict(
        effective_forecast=ForecastProfile.NONE,
        configured_forecast=ForecastProfile.NONE,
        fresh=True,
        battery_target_kw=0.0,
        ev_target_kw=0.0,
    )
    data.update(overrides)
    return HaeoTargets(**data)


def make_nz(**overrides):
    data = dict(rpnz_w=0.0, required_power_consumption_kw=0.0)
    data.update(overrides)
    return NetZeroState(**data)
