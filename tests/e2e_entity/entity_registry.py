from ems_core.domain.constants import CANONICAL_DIAGNOSTICS_OUTPUTS, CANONICAL_POLICY_OUTPUTS


def _scenario_fixture_ev(devices):
    """Resolve the fixture EV without priority/order-based selection."""
    explicit = (devices or {}).get('EV_CHARGER')
    if isinstance(explicit, dict) and str(explicit.get('kind')) == 'EV_CHARGER':
        return 'EV_CHARGER', explicit
    evs = []
    for device_id, device in (devices or {}).items():
        if isinstance(device, dict) and str(device.get('kind')) == 'EV_CHARGER':
            evs.append((str(device_id), device))
    if len(evs) == 1:
        return evs[0]
    return '', {}


def _scenario_fixture_relay(devices, device_id):
    relay = (devices or {}).get(str(device_id))
    if isinstance(relay, dict) and str(relay.get('kind')) == 'RELAY':
        return relay
    return {}


def build_scenario_entity_registry(config):
    """Test-harness entity registry for scenario YAML.

    This intentionally lives under tests: production runtime execution is packet-only
    and does not participate in policy runtime execution.
    """
    ems = config.get('ems', {}) if isinstance(config, dict) else {}
    profiles = ems.get('profiles', {}) if isinstance(ems.get('profiles'), dict) else {}
    global_cfg = ems.get('global_config', {}) if isinstance(ems.get('global_config'), dict) else {}
    runtime = ems.get('runtime', {}) if isinstance(ems.get('runtime'), dict) else {}
    state = ems.get('state', {}) if isinstance(ems.get('state'), dict) else {}
    haeo = ems.get('haeo', {}) if isinstance(ems.get('haeo'), dict) else {}
    haeo_devices = haeo.get('devices', {}) if isinstance(haeo.get('devices'), dict) else {}
    haeo_home_battery = haeo_devices.get('HOME_BATTERY', {}) if isinstance(haeo_devices.get('HOME_BATTERY'), dict) else {}
    haeo_ev_charger = haeo_devices.get('EV_CHARGER', {}) if isinstance(haeo_devices.get('EV_CHARGER'), dict) else {}
    devices = ems.get('devices', {}) if isinstance(ems.get('devices'), dict) else {}
    battery = devices.get('HOME_BATTERY', {}) if isinstance(devices.get('HOME_BATTERY'), dict) else {}
    battery_caps = battery.get('capabilities', {}) if isinstance(battery.get('capabilities'), dict) else {}
    battery_policy = battery.get('policy', {}) if isinstance(battery.get('policy'), dict) else {}
    battery_guard = battery.get('guard', {}) if isinstance(battery.get('guard'), dict) else {}
    battery_adapter = battery.get('adapter', {}) if isinstance(battery.get('adapter'), dict) else {}
    _ev_id, ev = _scenario_fixture_ev(devices)
    ev_caps = ev.get('capabilities', {}) if isinstance(ev.get('capabilities'), dict) else {}
    ev_policy = ev.get('policy', {}) if isinstance(ev.get('policy'), dict) else {}
    ev_adapter = ev.get('adapter', {}) if isinstance(ev.get('adapter'), dict) else {}
    relay1 = _scenario_fixture_relay(devices, 'RELAY1')
    relay2 = _scenario_fixture_relay(devices, 'RELAY2')
    relay1_adapter = relay1.get('adapter', {}) if isinstance(relay1.get('adapter'), dict) else {}
    relay2_adapter = relay2.get('adapter', {}) if isinstance(relay2.get('adapter'), dict) else {}

    primary_consuming_device_ids = global_cfg.get('primary_consuming_device_ids') or ()
    primary_consuming_device_id_entity = ''
    if isinstance(primary_consuming_device_ids, (list, tuple)) and primary_consuming_device_ids:
        primary_consuming_device_id_entity = primary_consuming_device_ids[0]

    ent = {
        'control_profile': profiles.get('control'),
        'goal_profile': profiles.get('goal'),
        'forecast_profile': profiles.get('forecast'),
        'guard_profile': profiles.get('guard'),
        'deadband_w': global_cfg.get('deadband_w'),
        'ramp_max_w': global_cfg.get('ramp_w'),
        'strict_limits_max_w': global_cfg.get('strict_limit_w'),
        'surplus_freeze_s': global_cfg.get('surplus_freeze_s'),
        'haeo_stale_timeout_s': global_cfg.get('haeo_stale_timeout_s'),
        'nz_battery_floor_default_w': global_cfg.get('nz_battery_floor_default_w'),
        'nz_battery_floor_ev_active_w': global_cfg.get('nz_battery_floor_ev_active_w'),
        'primary_consuming_device_id': primary_consuming_device_id_entity,
        'primary_consuming_device_ids': tuple(primary_consuming_device_ids),
        'max_solar_charge_w': battery_caps.get('max_absorb_w'),
        'max_battery_discharge_w': battery_caps.get('max_produce_w'),
        'battery_protect_soc': battery_guard.get('protect_soc'),
        'battery_protect_soc_recovery_margin': battery_guard.get('protect_soc_recovery_margin'),
        'battery_protect_min_cell_voltage_v': battery_guard.get('protect_min_cell_voltage_v'),
        'battery_protect_charge_floor_w': battery_guard.get('protect_min_absorb_w'),
        'soc': battery_guard.get('soc'),
        'min_cell_voltage_v': battery_guard.get('min_cell_voltage_v'),
        'battery_heartbeat': battery_guard.get('heartbeat'),
        'current_battery_sp': battery_adapter.get('target_w'),
        'actuator_battery_setpoint_w': battery_adapter.get('target_w'),
        'ev_hard_off_pv_threshold_kw': ev_policy.get('low_pv_threshold_w'),
        'ev_hard_off_low_pv_cycles': ev_policy.get('hard_off_low_pv_cycles'),
        'ev_hard_off_release_cycles': ev_policy.get('hard_off_release_cycles'),
        'charger_control': ev_adapter.get('enabled'),
        'actuator_ev_enabled': ev_adapter.get('enabled'),
        'charger_current': ev_adapter.get('current_a'),
        'actuator_ev_current_a': ev_adapter.get('current_a'),
        'ev_min_absorb_w': ev_caps.get('min_absorb_w'),
        'ev_max_absorb_w': ev_caps.get('max_absorb_w'),
        'ev_current_step_a': ev_adapter.get('current_step_a'),
        'ev_charger_phases': ev_adapter.get('phases'),
        'ev_voltage_v': ev_adapter.get('voltage_v'),
        'ev_force_on': ev_policy.get('force_on'),
        'actuator_relay1': relay1_adapter.get('enabled'),
        'actuator_relay2': relay2_adapter.get('enabled'),
        'grid_power_w': runtime.get('grid_power_w'),
        'quarter_energy_balance': runtime.get('quarter_energy_balance_kwh'),
        'quarter_energy_balance_kwh': runtime.get('quarter_energy_balance_kwh'),
        'pv_power_w': runtime.get('pv_power_w'),
        'surplus_freeze_until': state.get('surplus_freeze_until'),
        'active_surplus_devices': state.get('active_surplus_devices'),
        'haeo_battery_power_active': haeo_home_battery.get('power_active'),
        'haeo_ev_battery_power_active': haeo_ev_charger.get('power_active'),
        'haeo_battery_active_power_fresh_source': haeo_home_battery.get('fresh_source'),
        'haeo_ev_active_power_fresh_source': haeo_ev_charger.get('fresh_source'),
        'haeo_device_power_active_by_id': {
            str(device_id): mapping.get('power_active')
            for device_id, mapping in haeo_devices.items()
            if isinstance(mapping, dict)
        },
        'haeo_device_fresh_source_by_id': {
            str(device_id): mapping.get('fresh_source')
            for device_id, mapping in haeo_devices.items()
            if isinstance(mapping, dict)
        },
        'device_policies': CANONICAL_POLICY_OUTPUTS['device_policies'],
        'dispatch_command': CANONICAL_POLICY_OUTPUTS['dispatch_command'],
        'policy_state': CANONICAL_POLICY_OUTPUTS['policy_state'],
        'policy_diagnostics': CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics'],
        'actuator_writer_trace': CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace'],
        'dispatch_state_applier_trace': CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace'],
    }

    device_entities = {}
    relay_ids = []
    ev_ids = []
    for device_id, device in devices.items():
        if not isinstance(device, dict):
            continue
        device_id = str(device_id)
        kind = str(device.get('kind') or '')
        caps = device.get('capabilities', {}) if isinstance(device.get('capabilities'), dict) else {}
        policy = device.get('policy', {}) if isinstance(device.get('policy'), dict) else {}
        adapter = device.get('adapter', {}) if isinstance(device.get('adapter'), dict) else {}
        entry = {'device_id': device_id, 'kind': kind}
        if kind == 'BATTERY':
            entry.update({
                'target_w': adapter.get('target_w'),
                'measured_power_w': adapter.get('measured_power_w'),
                'priority': policy.get('priority'),
            })
        elif kind == 'EV_CHARGER':
            ev_ids.append(device_id)
            entry.update({
                'enabled': adapter.get('enabled'),
                'current_a': adapter.get('current_a'),
                'current_step_a': adapter.get('current_step_a'),
                'phases': adapter.get('phases'),
                'voltage_v': adapter.get('voltage_v'),
                'min_absorb_w': caps.get('min_absorb_w'),
                'max_absorb_w': caps.get('max_absorb_w'),
                'surplus_allowed': policy.get('surplus_allowed'),
                'force_on': policy.get('force_on'),
                'priority': policy.get('priority'),
            })
        elif kind == 'RELAY':
            relay_ids.append(device_id)
            entry.update({
                'enabled': adapter.get('enabled'),
                'surplus_allowed': policy.get('surplus_allowed'),
                'force_on': policy.get('force_on'),
                'priority': policy.get('priority'),
                'max_absorb_w': caps.get('max_absorb_w'),
            })
        device_entities[device_id] = {k: v for k, v in entry.items() if v not in (None, '')}
    ent['devices'] = device_entities
    ent['relay_device_ids'] = tuple(relay_ids)
    ent['ev_device_ids'] = tuple(ev_ids)
    return {key: value for key, value in ent.items() if value not in (None, '') or key in {'devices', 'relay_device_ids', 'ev_device_ids'}}
