import pytest

from ems_adapter.config_loader import build_core_config_from_grouped_reader, load_grouped_ems_config
from ems_adapter.device_read_model import build_device_configs, build_devices, build_device_states
from tests.helpers import make_cfg, make_m


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
        ev_min_current_a=6,
        ev_max_current_a=16,
        ev_current_step_a=4,
        ev_charger_phases=3,
        ev_priority=8,
    )
    m = make_m(charger_on=True, charger_current_a=10)

    ev_cfg = _config_by_id(cfg)['EV_CHARGER']
    ev_state = _state_by_id(cfg, m)['EV_CHARGER']

    assert ev_cfg.kind == 'EV_CHARGER'
    assert ev_cfg.response_kind == 'selector'
    assert ev_cfg.can_absorb_w is True
    assert ev_cfg.can_produce_w is False
    assert ev_cfg.min_absorb_w == 4140
    assert ev_cfg.max_absorb_w == 11040
    assert ev_cfg.max_produce_w == 0
    assert ev_cfg.step_w == 2760
    assert ev_cfg.priority == 8

    assert ev_state.available is True
    assert ev_state.active is True
    assert ev_state.measured_power_w == 6900
    assert ev_state.current_target_w == 6900
    assert ev_state.guard_state == 'OK'


@pytest.mark.unit
def test_relay1_device_mapping_is_constant_power_when_active():
    cfg = make_cfg(relay1_power_kw=2.5, relay1_priority=2)
    m = make_m(relay1_on=True)

    relay_cfg = _config_by_id(cfg)['RELAY1']
    relay_state = _state_by_id(cfg, m)['RELAY1']

    assert relay_cfg.kind == 'RELAY'
    assert relay_cfg.response_kind == 'relay'
    assert relay_cfg.can_absorb_w is True
    assert relay_cfg.can_produce_w is False
    assert relay_cfg.min_absorb_w == 2500
    assert relay_cfg.max_absorb_w == 2500
    assert relay_cfg.step_w == 2500
    assert relay_cfg.priority == 2

    assert relay_state.available is True
    assert relay_state.active is True
    assert relay_state.measured_power_w == 2500
    assert relay_state.current_target_w == 2500


@pytest.mark.unit
def test_relay2_device_mapping_is_zero_when_inactive():
    cfg = make_cfg(relay2_power_kw=5.0, relay2_priority=1)
    m = make_m(relay2_on=False)

    relay_cfg = _config_by_id(cfg)['RELAY2']
    relay_state = _state_by_id(cfg, m)['RELAY2']

    assert relay_cfg.kind == 'RELAY'
    assert relay_cfg.response_kind == 'relay'
    assert relay_cfg.min_absorb_w == 5000
    assert relay_cfg.max_absorb_w == 5000
    assert relay_cfg.step_w == 5000
    assert relay_cfg.priority == 1

    assert relay_state.available is True
    assert relay_state.active is False
    assert relay_state.measured_power_w == 0
    assert relay_state.current_target_w == 0


@pytest.mark.unit
def test_core_config_device_mapping_uses_yaml_capabilities_directly(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'EMS_config.yaml')
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
    m = make_m(relay1_on=True, relay2_on=True, charger_on=True, charger_current_a=10)

    states = _state_by_id(core_cfg, m)

    assert states['RELAY1'].measured_power_w == 2500
    assert states['RELAY2'].measured_power_w == 5000
    assert states['EV_CHARGER'].measured_power_w == 2300
