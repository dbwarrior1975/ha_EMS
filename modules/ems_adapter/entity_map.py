ENT = {
    'control_profile': 'input_select.ems_control_profile',
    'goal_profile': 'input_select.ems_goal_profile',
    'forecast_profile': 'input_select.ems_forecast_profile',
    'guard_profile': 'input_select.ems_guard_profile',

    'battery_protect_soc': 'input_number.ems_battery_protect_soc',
    'battery_protect_soc_recovery_margin': 'input_number.ems_battery_protect_soc_recovery_margin',
    'battery_protect_min_cell_voltage_v': 'input_number.ems_battery_protect_min_cell_voltage_v',

    'deadband_w': 'input_number.ems_deadband_w',
    'ramp_max_w': 'input_number.ems_ramp_max_w',
    'strict_limits_max_w': 'input_number.ems_strict_limits_max_w',
    'max_solar_charge_w': 'input_number.victron_maksimi_auringon_latausteho',

    'ev_min_current_a': 'input_number.ems_ev_min_current_a',
    'ev_max_current_a': 'input_number.ems_ev_max_current_a',
    'ev_charger_phases': 'input_number.ems_ev_charger_phases',
    'ev_force_current_a': 'input_number.ems_ev_force_current_a',
    'ev_hard_off_pv_threshold_kw': 'input_number.ems_ev_hard_off_pv_threshold_kw',
    'ev_hard_off_low_pv_cycles': 'input_number.ems_ev_hard_off_low_pv_cycles',
    'pv_power_kw': 'sensor.pv_instant_power_2',

    'haeo_stale_timeout_s': 'input_number.ems_haeo_stale_timeout_s',

    'relay1_power_kw': 'input_number.ems_relay1_power_kw',
    'relay2_power_kw': 'input_number.ems_relay2_power_kw',
    'surplus_freeze_s': 'input_number.ems_surplus_freeze_s',
    'relay1_priority': 'input_number.ems_surplus_relay1_priority',
    'relay2_priority': 'input_number.ems_surplus_relay2_priority',
    'ev_priority': 'input_number.ems_surplus_ev_priority',

    'soc': 'sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc',
    'min_cell_voltage_v': 'sensor.victron_mqtt_b827eb48c929_battery_1_battery_min_cell_voltage',
    'victron_heartbeat': 'sensor.victron_mqtt_b827eb48c929_battery_1_battery_power',
    'grid_power_w': 'sensor.average_active_power_2',
    'current_battery_sp': 'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point',
    'hourly_energy_balance': 'sensor.hourly_energy_balance',

    'charger_control': 'switch.charger_control',
    'charger_current': 'number.charger_current_level',
    'relay1': 'switch.relay_1_2',
    'relay2': 'switch.relay_2_2',

    'haeo_battery_power_active': 'sensor.haeo_battery_power_active',
    'haeo_ev_battery_power_active': 'sensor.haeo_ev_battery_power_active',
    'haeo_battery_active_power_fresh_source': 'sensor.battery_active_power',
    'haeo_ev_active_power_fresh_source': 'sensor.ev_akut_active_power',

    'required_power_consumption_kw': 'sensor.required_power_consumption',
    'rpnz_w': 'sensor.ems_calculated_required_power_for_net_zero',

    'surplus_freeze_until': 'input_datetime.ems_surplus_freeze_until',
    'surplus_ev_active': 'input_boolean.ems_surplus_ev_active',
    'surplus_r1_active': 'input_boolean.ems_surplus_relay1_active',
    'surplus_r2_active': 'input_boolean.ems_surplus_relay2_active',

    'relay1_enabled_import_zero': 'input_boolean.ems_relay1_enabled_import_zero',
    'relay2_enabled_import_zero': 'input_boolean.ems_relay2_enabled_import_zero',
    'relay1_force_on': 'input_boolean.ems_relay1_force_on',
    'relay2_force_on': 'input_boolean.ems_relay2_force_on',

    'policy_battery_target_w': 'sensor.ems_policy_battery_target_w_pyscript',
    'policy_ev_current_a': 'sensor.ems_policy_ev_current_a_pyscript',
    'policy_relay1_command': 'sensor.ems_policy_relay1_command_pyscript',
    'policy_relay2_command': 'sensor.ems_policy_relay2_command_pyscript',
    'policy_decision_trace': 'sensor.ems_policy_decision_trace_pyscript',

    'surplus_policy_active_pys': 'binary_sensor.ems_net_zero_surplus_policy_active_pyscript',
    'surplus_next_target_pys': 'sensor.ems_net_zero_surplus_next_target_pyscript',
    'surplus_next_threshold_pys': 'sensor.ems_net_zero_surplus_next_threshold_kw_pyscript',
    'surplus_release_candidate_pys': 'sensor.ems_net_zero_surplus_release_candidate_pyscript',
    'surplus_explanation_pys': 'sensor.ems_net_zero_surplus_explanation_pyscript',
    'surplus_dispatch_decision_pys': 'sensor.ems_net_zero_surplus_dispatch_decision_pyscript',

    'actuator_victron_setpoint_w': 'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point',
    'actuator_ev_current_a': 'number.charger_current_level',
    'actuator_ev_enabled': 'switch.charger_control',
    'actuator_relay1': 'switch.relay_1_2',
    'actuator_relay2': 'switch.relay_2_2',
}
