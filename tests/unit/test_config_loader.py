import os
import subprocess
import sys

import pytest

from ems_adapter.config_loader import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    build_ems_config_from_grouped_config,
    build_ems_config_from_grouped_reader,
    runtime_alias_index,
    load_grouped_ems_config,
    load_and_validate_grouped_ems_config,
    validate_grouped_ems_config,
)


def _load_example(project_root):
    return load_grouped_ems_config(project_root / 'example_EMS_config.yaml')


def _error_paths(result):
    return {issue.path for issue in result.issues if issue.severity == SEVERITY_ERROR}


@pytest.mark.unit
def test_example_grouped_config_loads_and_validates(project_root):
    config, result = load_and_validate_grouped_ems_config(project_root / 'example_EMS_config.yaml')

    assert 'ems' in config
    assert result.ok is True
    assert any(issue.severity == SEVERITY_WARNING for issue in result.issues)


@pytest.mark.unit
def test_config_loader_import_does_not_require_yaml(project_root):
    script = """
import builtins
real_import = builtins.__import__

def blocked_import(name, *args, **kwargs):
    if name == 'yaml':
        raise ModuleNotFoundError("No module named 'yaml'")
    return real_import(name, *args, **kwargs)

builtins.__import__ = blocked_import
import ems_adapter.config_loader
print('ok')
"""
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root / 'modules')
    result = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'


@pytest.mark.unit
def test_load_grouped_config_missing_file_raises_clear_error(tmp_path):
    missing = tmp_path / 'missing.yaml'
    with pytest.raises(FileNotFoundError, match='Grouped EMS config not found'):
        load_grouped_ems_config(missing)


@pytest.mark.unit
def test_load_grouped_config_invalid_yaml_raises_clear_error(tmp_path):
    path = tmp_path / 'broken.yaml'
    path.write_text('ems: [', encoding='utf-8')

    with pytest.raises(ValueError, match='Invalid YAML'):
        load_grouped_ems_config(path)


@pytest.mark.unit
def test_validate_requires_top_level_ems_mapping():
    result = validate_grouped_ems_config({})
    assert result.ok is False
    assert 'ems' in _error_paths(result)


@pytest.mark.unit
def test_validate_requires_all_supported_devices(project_root):
    config = _load_example(project_root)
    del config['ems']['devices']['EV_CHARGER']

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.devices.EV_CHARGER' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_wrong_device_kind(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['RELAY1']['kind'] = 'BATTERY'

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.devices.RELAY1.kind' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_invalid_entity_id(project_root):
    config = _load_example(project_root)
    config['ems']['profiles']['control'] = 'not_an_entity'

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.profiles.control' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_unknown_role_constraint_device(project_root):
    config = _load_example(project_root)
    config['ems']['role_constraints']['EV_PRIMARY']['UNKNOWN_DEVICE'] = {
        'min_absorb_w': 0,
    }

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.role_constraints.EV_PRIMARY.UNKNOWN_DEVICE' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_invalid_ev_phases_numeric_constant(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['EV_CHARGER']['adapter']['phases'] = 2

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.devices.EV_CHARGER.adapter.phases' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_relay_can_produce(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['RELAY1']['capabilities']['can_produce_w'] = True

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.devices.RELAY1.capabilities.can_produce_w' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_negative_step_numeric_constant(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['RELAY2']['capabilities']['step_w'] = -1

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.devices.RELAY2.capabilities.step_w' in _error_paths(result)


@pytest.mark.unit
def test_runtime_alias_index_exposes_unit_transform_metadata(project_root):
    config = _load_example(project_root)
    aliases = runtime_alias_index(config)

    assert aliases['required_power_consumption_kw'].config_path == 'ems.runtime.required_power_w'
    assert aliases['required_power_consumption_kw'].unit_transform == 'W_TO_KW'
    assert aliases['pv_power_kw'].unit_transform == 'W_TO_KW'
    assert aliases['ev_hard_off_pv_threshold_kw'].unit_transform == 'W_TO_KW'


@pytest.mark.unit
def test_runtime_alias_index_contains_expected_core_aliases(project_root):
    config = _load_example(project_root)
    aliases = runtime_alias_index(config)

    assert aliases['control_profile'].config_path == 'ems.profiles.control'
    assert aliases['ramp_max_w'].config_path == 'ems.global_config.ramp_w'
    assert aliases['battery_protect_charge_floor_w'].config_path == 'ems.devices.HOME_BATTERY.guard.protect_min_absorb_w'
    assert aliases['actuator_ev_current_a'].config_path == 'ems.devices.EV_CHARGER.adapter.current_a'


@pytest.mark.unit
def test_build_ems_config_from_grouped_config_no_longer_depends_on_runtime_alias_runtime(project_root, monkeypatch):
    config = _load_example(project_root)
    entity_values = {
        'input_number.ems_deadband_w': 75,
        'input_number.ems_ramp_max_w': 1200,
        'input_number.ems_strict_limits_max_w': 5000,
        'input_number.ems_max_battery_discharge_w': 4600,
        'input_number.ems_max_battery_charge_w': 3700,
        'input_number.ems_battery_protect_soc': 3,
        'input_number.ems_battery_protect_soc_recovery_margin': 2,
        'input_number.ems_battery_protect_min_cell_voltage_v': 3.04,
        'input_number.ems_battery_protect_charge_floor_w': 150,
        'input_number.ems_ev_min_current_a': 6,
        'input_number.ems_ev_max_current_a': 16,
        'input_number.ems_ev_charger_phases': 3,
        'input_number.ems_ev_force_current_a': 0,
        'input_number.ems_ev_hard_off_pv_threshold_kw': 1.8,
        'input_number.ems_ev_hard_off_low_pv_cycles': 2,
        'input_number.ems_ev_hard_off_release_cycles': 3,
        'input_number.ems_ev_current_step_a': 4,
        'input_number.ems_nz_battery_floor_default_w': 100,
        'input_number.ems_nz_battery_floor_ev_active_w': 0,
        'input_select.ems_adjustable_surplus_load': 'EV_CHARGER',
        'input_select.ems_adjustable_primary_load': 'HOME_BATTERY',
        'input_number.ems_adjustable_surplus_activation_w': 2000,
        'input_number.ems_adjustable_surplus_load_priority': 3,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_relay1_power_kw': 2.5,
        'input_number.ems_relay2_power_kw': 5.0,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_surplus_ev_priority': 3,
        'input_number.ems_surplus_relay1_priority': 2,
        'input_number.ems_surplus_relay2_priority': 1,
    }

    def _fail_runtime_alias_runtime(_config):
        raise AssertionError('runtime alias index must not be used by grouped runtime reader')

    monkeypatch.setattr('ems_adapter.config_loader.runtime_alias_index', _fail_runtime_alias_runtime)

    cfg = build_ems_config_from_grouped_config(config, entity_values)

    assert cfg.deadband_w == 75
    assert cfg.max_solar_charge_w == 3700
    assert cfg.max_battery_discharge_w == 4600
    assert cfg.ev_hard_off_pv_threshold_kw == 1.8
    assert cfg.adjustable_surplus_load == 'EV_CHARGER'
    assert cfg.adjustable_primary_load == 'HOME_BATTERY'


@pytest.mark.unit
def test_build_ems_config_from_grouped_reader_uses_core_config_builder(project_root, monkeypatch):
    config = _load_example(project_root)
    called = {'value': False}

    real_builder = build_ems_config_from_grouped_reader.__globals__['build_core_config_from_grouped_reader']

    def _tracking_builder(grouped_config, read_entity):
        called['value'] = True
        return real_builder(grouped_config, read_entity)

    monkeypatch.setitem(
        build_ems_config_from_grouped_reader.__globals__,
        'build_core_config_from_grouped_reader',
        _tracking_builder,
    )

    cfg = build_ems_config_from_grouped_reader(
        config,
        lambda entity_id, default: {
            'input_number.ems_deadband_w': 80,
            'input_number.ems_ramp_max_w': 900,
            'input_number.ems_ev_max_current_a': 16,
        }.get(entity_id, default),
    )

    assert called['value'] is True
    assert cfg.deadband_w == 80
    assert cfg.ramp_max_w == 900
