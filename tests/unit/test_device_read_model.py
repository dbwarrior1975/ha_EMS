import pytest

from ems_adapter.config_loader import build_core_config_from_grouped_reader, load_grouped_ems_config
from ems_adapter.device_read_model import build_device_configs, build_devices, build_device_states
from tests.helpers import ev_state, ev_w, make_cfg, make_m, relay_state


def _config_by_id(cfg):
    return {item.device_id: item for item in build_device_configs(cfg)}


def _state_by_id(cfg, m):
    return {item.device_id: item for item in build_device_states(cfg, m)}


def _device_by_id(cfg, m):
    return {item.config.device_id: item for item in build_devices(cfg, m)}


@pytest.mark.unit
def test_battery_device_mapping_uses_current_limits_and_runtime_state():
    cfg = make_cfg(
        max_solar_charge_w=4200,
        max_battery_discharge_w=5100,
        deadband_w=25,
        adjustable_surplus_load_priority=7,
        battery_heartbeat_timeout_s=120,
    )
    m = make_m(
        soc=55.0,
        battery_heartbeat_age_s=15.0,
        current_battery_setpoint_w=-900.0,
    )

    battery_cfg = _config_by_id(cfg)['HOME_BATTERY']
    battery_state = _state_by_id(cfg, m)['HOME_BATTERY']
    battery_device = _device_by_id(cfg, m)['HOME_BATTERY']

    assert battery_cfg.kind == 'BATTERY'
    assert battery_cfg.response_kind == 'continuous'
    assert battery_cfg.can_absorb_w is True
    assert battery_cfg.can_produce_w is True
    assert battery_cfg.min_absorb_w == 0
    assert battery_cfg.max_absorb_w == 4200
    assert battery_cfg.max_produce_w == 5100
    assert battery_cfg.step_w == 25
    assert battery_cfg.priority == 7

    assert battery_state.available is True
    assert battery_state.active is True
    assert battery_state.measured_power_w == -900
    assert battery_state.current_target_w == -900
    assert battery_state.guard_state == 'OK'

    assert battery_device.config == battery_cfg
    assert battery_device.state == battery_state


@pytest.mark.unit
def test_ev_device_mapping_converts_current_to_power():
    cfg = make_cfg(
        ev_min_absorb_w=ev_w(6, phases=3),
        ev_max_absorb_w=ev_w(16, phases=3),
        ev_current_step_a=4,
        ev_charger_phases=3,
        ev_priority=8,
    )
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=10)})

    ev_cfg = _config_by_id(cfg)['EV_CHARGER']
    ev_runtime_state = _state_by_id(cfg, m)['EV_CHARGER']

    assert ev_cfg.kind == 'EV_CHARGER'
    assert ev_cfg.response_kind == 'selector'
    assert ev_cfg.can_absorb_w is True
    assert ev_cfg.can_produce_w is False
    assert ev_cfg.min_absorb_w == 4140
    assert ev_cfg.max_absorb_w == 11040
    assert ev_cfg.max_produce_w == 0
    assert ev_cfg.step_w == 2760
    assert ev_cfg.priority == 8

    assert ev_runtime_state.available is True
    assert ev_runtime_state.active is True
    assert ev_runtime_state.measured_power_w == 6900
    assert ev_runtime_state.current_target_w == 6900
    assert ev_runtime_state.guard_state == 'OK'


@pytest.mark.unit
def test_ev_device_states_use_each_ev_adapter_for_measured_power(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped_config['ems']['devices']['EV_A'] = grouped_config['ems']['devices'].pop('EV_CHARGER')
    grouped_config['ems']['devices']['EV_A']['adapter']['phases'] = 'input_number.ev_a_phases'
    grouped_config['ems']['devices']['EV_A']['adapter']['voltage_v'] = 'input_number.ev_a_voltage_v'
    grouped_config['ems']['devices']['EV_A']['adapter']['current_step_a'] = 'input_number.ev_a_current_step_a'
    grouped_config['ems']['devices']['EV_A']['capabilities']['min_absorb_w'] = 'input_number.ev_a_min_power_w'
    grouped_config['ems']['devices']['EV_A']['capabilities']['max_absorb_w'] = 'input_number.ev_a_max_power_w'
    grouped_config['ems']['devices']['EV_A']['capabilities']['step_w'] = 'input_number.ev_a_power_step_w'
    grouped_config['ems']['devices']['EV_A']['policy']['priority'] = 'input_number.ev_a_priority'
    grouped_config['ems']['devices']['EV_A']['policy']['surplus_allowed'] = 'input_boolean.ev_a_surplus_allowed'
    grouped_config['ems']['devices']['EV_A']['policy']['force_on'] = 'input_boolean.ev_a_force_on'
    grouped_config['ems']['devices']['EV_A']['policy']['low_pv_threshold_w'] = 'input_number.ev_a_low_pv_threshold_w'
    grouped_config['ems']['devices']['EV_A']['policy']['hard_off_low_pv_cycles'] = 'input_number.ev_a_low_pv_cycles'
    grouped_config['ems']['devices']['EV_A']['policy']['hard_off_release_cycles'] = 'input_number.ev_a_release_cycles'
    grouped_config['ems']['devices']['EV_A']['adapter']['enabled'] = 'switch.ev_a_enabled'
    grouped_config['ems']['devices']['EV_A']['adapter']['current_a'] = 'number.ev_a_current_a'
    grouped_config['ems']['devices']['EV_B'] = {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_regulation': True,
            'supports_residual_regulation': False,
            'uses_hard_off_lifecycle': True,
            'min_absorb_w': 'input_number.ev_b_min_power_w',
            'max_absorb_w': 'input_number.ev_b_max_power_w',
            'step_w': 'input_number.ev_b_power_step_w',
        },
        'policy': {
            'priority': 'input_number.ev_b_priority',
            'surplus_allowed': 'input_boolean.ev_b_surplus_allowed',
            'force_on': 'input_boolean.ev_b_force_on',
            'low_pv_threshold_w': 'input_number.ev_b_low_pv_threshold_w',
            'hard_off_low_pv_cycles': 'input_number.ev_b_low_pv_cycles',
            'hard_off_release_cycles': 'input_number.ev_b_release_cycles',
        },
        'adapter': {
            'enabled': 'switch.ev_b_enabled',
            'current_a': 'number.ev_b_current_a',
            'current_step_a': 'input_number.ev_b_current_step_a',
            'phases': 'input_number.ev_b_phases',
            'voltage_v': 'input_number.ev_b_voltage_v',
        },
    }
    values = {
        'input_number.ems_home_battery_min_absorb_w': 125,
        'input_number.ems_max_battery_charge_w': 4300,
        'input_number.ems_max_battery_discharge_w': 5100,
        'input_number.ems_deadband_w': 25,
        'input_number.ems_adjustable_surplus_load_priority': 7,
        'input_number.ev_a_min_power_w': 1380,
        'input_number.ev_a_max_power_w': 3680,
        'input_number.ev_a_power_step_w': 230,
        'input_number.ev_a_priority': 8,
        'input_boolean.ev_a_surplus_allowed': True,
        'input_boolean.ev_a_force_on': False,
        'input_number.ev_a_low_pv_threshold_w': 1600,
        'input_number.ev_a_low_pv_cycles': 2,
        'input_number.ev_a_release_cycles': 2,
        'input_number.ev_a_current_step_a': 1,
        'input_number.ev_a_phases': 1,
        'input_number.ev_a_voltage_v': 230,
        'switch.ev_a_enabled': True,
        'number.ev_a_current_a': 10,
        'input_number.ev_b_min_power_w': 4140,
        'input_number.ev_b_max_power_w': 11040,
        'input_number.ev_b_power_step_w': 690,
        'input_number.ev_b_priority': 6,
        'input_boolean.ev_b_surplus_allowed': True,
        'input_boolean.ev_b_force_on': False,
        'input_number.ev_b_low_pv_threshold_w': 1600,
        'input_number.ev_b_low_pv_cycles': 2,
        'input_number.ev_b_release_cycles': 2,
        'input_number.ev_b_current_step_a': 1,
        'input_number.ev_b_phases': 3,
        'input_number.ev_b_voltage_v': 230,
        'switch.ev_b_enabled': True,
        'number.ev_b_current_a': 10,
    }
    core_cfg = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: values.get(entity_id, default),
    )
    m = make_m(
        ev_states={
            'EV_A': ev_state(enabled=True, current_a=10),
            'EV_B': ev_state(enabled=True, current_a=10),
        }
    )

    states = _state_by_id(core_cfg, m)

    assert states['EV_A'].measured_power_w == 2300
    assert states['EV_B'].measured_power_w == 6900


@pytest.mark.unit
def test_ev_device_states_fall_back_to_default_adapter_power_values():
    cfg = make_cfg()
    cfg.devices['EV_CHARGER'].adapter.phases = None
    cfg.devices['EV_CHARGER'].adapter.voltage_v = None
    m = make_m(ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=10)})

    states = _state_by_id(cfg, m)

    assert states['EV_CHARGER'].measured_power_w == 2300


@pytest.mark.unit
def test_relay1_device_mapping_is_constant_power_when_active():
    cfg = make_cfg()
    m = make_m(relay_states={'RELAY1': relay_state(active=True)})

    relay_cfg = _config_by_id(cfg)['RELAY1']
    relay_runtime_state = _state_by_id(cfg, m)['RELAY1']

    assert relay_cfg.kind == 'RELAY'
    assert relay_cfg.response_kind == 'relay'
    assert relay_cfg.can_absorb_w is True
    assert relay_cfg.can_produce_w is False
    assert relay_cfg.min_absorb_w == 2500
    assert relay_cfg.max_absorb_w == 2500
    assert relay_cfg.step_w == 2500
    assert relay_cfg.priority == 2

    assert relay_runtime_state.available is True
    assert relay_runtime_state.active is True
    assert relay_runtime_state.measured_power_w == 2500
    assert relay_runtime_state.current_target_w == 2500


@pytest.mark.unit
def test_relay2_device_mapping_is_zero_when_inactive():
    cfg = make_cfg()
    m = make_m(relay_states={'RELAY2': relay_state(active=False)})

    relay_cfg = _config_by_id(cfg)['RELAY2']
    relay_runtime_state = _state_by_id(cfg, m)['RELAY2']

    assert relay_cfg.kind == 'RELAY'
    assert relay_cfg.response_kind == 'relay'
    assert relay_cfg.min_absorb_w == 5000
    assert relay_cfg.max_absorb_w == 5000
    assert relay_cfg.step_w == 5000
    assert relay_cfg.priority == 1

    assert relay_runtime_state.available is True
    assert relay_runtime_state.active is False
    assert relay_runtime_state.measured_power_w == 0
    assert relay_runtime_state.current_target_w == 0


@pytest.mark.unit
def test_core_config_device_mapping_uses_yaml_capabilities_directly(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    values = {
        'input_number.ems_home_battery_min_absorb_w': 125,
        'input_number.ems_max_battery_charge_w': 4300,
        'input_number.ems_max_battery_discharge_w': 5100,
        'input_number.ems_deadband_w': 25,
        'input_number.ems_adjustable_surplus_load_priority': 7,
        'input_number.ems_ev_min_power_w': 1380,
        'input_number.ems_ev_max_power_w': 6440,
        'input_number.ems_ev_power_step_w': 920,
        'input_number.ems_surplus_ev_priority': 8,
    }
    core_cfg = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: values.get(entity_id, default),
    )

    configs = _config_by_id(core_cfg)

    battery_cfg = configs['HOME_BATTERY']
    assert battery_cfg.can_absorb_w is True
    assert battery_cfg.can_produce_w is True
    assert battery_cfg.min_absorb_w == 125
    assert battery_cfg.max_absorb_w == 4300
    assert battery_cfg.max_produce_w == 5100
    assert battery_cfg.step_w == 25
    assert battery_cfg.priority == 7

    ev_cfg = configs['EV_CHARGER']
    assert ev_cfg.can_absorb_w is True
    assert ev_cfg.can_produce_w is False
    assert ev_cfg.min_absorb_w == 1380
    assert ev_cfg.max_absorb_w == 6440
    assert ev_cfg.step_w == 920
    assert ev_cfg.priority == 8


@pytest.mark.unit
def test_core_config_device_states_use_core_capability_power_for_relays(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    values = {
        'input_number.ems_relay1_power_kw': 2500,
        'input_number.ems_relay2_power_kw': 5000,
        'input_number.ems_ev_charger_phases': 1,
    }
    core_cfg = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: values.get(entity_id, default),
    )
    m = make_m(
        relay_states={
            'RELAY1': relay_state(active=True),
            'RELAY2': relay_state(active=True),
        },
        ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=10)},
    )

    states = _state_by_id(core_cfg, m)

    assert states['RELAY1'].measured_power_w == 2500
    assert states['RELAY2'].measured_power_w == 5000
    assert states['EV_CHARGER'].measured_power_w == 2300


@pytest.mark.unit
def test_core_config_device_registry_exposes_extra_relay_without_fixed_dataclass_field(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped_config['ems']['devices']['RELAY3'] = {
        'kind': 'RELAY',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_regulation': False,
            'supports_residual_regulation': False,
            'uses_hard_off_lifecycle': False,
            'min_absorb_w': 'input_number.ems_relay3_power_kw',
            'max_absorb_w': 'input_number.ems_relay3_power_kw',
            'step_w': 'input_number.ems_relay3_power_kw',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_relay3_priority',
            'surplus_allowed': 'input_boolean.ems_relay3_enabled_import_zero',
            'force_on': 'input_boolean.ems_relay3_force_on',
        },
        'adapter': {
            'enabled': 'switch.relay_3_2',
        },
    }
    values = {
        'input_number.ems_relay3_power_kw': 7500,
        'input_number.ems_surplus_relay3_priority': 4,
        'input_boolean.ems_relay3_enabled_import_zero': True,
        'input_boolean.ems_relay3_force_on': False,
        'switch.relay_3_2': False,
    }
    core_cfg = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: values.get(entity_id, default),
    )
    m = make_m()

    configs = _config_by_id(core_cfg)
    states = _state_by_id(core_cfg, m)
    devices = _device_by_id(core_cfg, m)

    assert configs['RELAY3'].kind == 'RELAY'
    assert configs['RELAY3'].max_absorb_w == 7500
    assert states['RELAY3'].available is False
    assert states['RELAY3'].guard_state == 'UNWIRED'
    assert devices['RELAY3'].state.device_id == 'RELAY3'


@pytest.mark.unit
def test_core_config_device_states_map_custom_relay_ids_without_fixed_relay_names(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped_config['ems']['devices']['POOL_PUMP'] = grouped_config['ems']['devices'].pop('RELAY1')
    grouped_config['ems']['devices']['BOILER'] = grouped_config['ems']['devices'].pop('RELAY2')
    values = {
        'input_number.ems_relay1_power_kw': 2500,
        'input_number.ems_relay2_power_kw': 5000,
        'input_number.ems_ev_charger_phases': 1,
    }
    core_cfg = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: values.get(entity_id, default),
    )
    m = make_m(
        relay_states={
            'RELAY1': relay_state(active=True),
            'RELAY2': relay_state(active=False),
            'POOL_PUMP': relay_state(active=True),
            'BOILER': relay_state(active=False),
        },
    )

    states = _state_by_id(core_cfg, m)

    assert states['POOL_PUMP'].active is True
    assert states['POOL_PUMP'].measured_power_w == 2500
    assert states['BOILER'].active is False
    assert states['BOILER'].measured_power_w == 0
