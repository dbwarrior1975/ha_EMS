import os
import subprocess
import sys

import pytest

from ems_adapter.config_loader import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    build_core_config_from_grouped_config,
    build_core_config_from_grouped_reader,
    runtime_alias_index,
    load_grouped_ems_config,
    load_and_validate_grouped_ems_config,
    validate_grouped_ems_config,
)


def _load_example(project_root):
    return load_grouped_ems_config(project_root / 'example_EMS_config.yaml')


def _error_paths(result):
    return {issue.path for issue in result.issues if issue.severity == SEVERITY_ERROR}


def _error_messages(result):
    return {issue.path: issue.message for issue in result.issues if issue.severity == SEVERITY_ERROR}


@pytest.mark.unit
def test_example_grouped_config_loads_and_validates(project_root):
    config, result = load_and_validate_grouped_ems_config(project_root / 'example_EMS_config.yaml')

    assert 'ems' in config
    assert result.ok is True
    assert not any(issue.severity == SEVERITY_ERROR for issue in result.issues)


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
def test_validate_requires_home_battery_device(project_root):
    config = _load_example(project_root)
    del config['ems']['devices']['HOME_BATTERY']

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.devices.HOME_BATTERY' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_wrong_device_kind(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['RELAY1']['kind'] = 'UNSUPPORTED'

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
    config['ems']['devices']['EV_CHARGER']['adapter']['phases'] = 0

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
def test_validate_rejects_home_battery_with_both_directions_disabled(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['HOME_BATTERY']['capabilities']['can_absorb_w'] = False
    config['ems']['devices']['HOME_BATTERY']['capabilities']['can_produce_w'] = False

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.devices.HOME_BATTERY.capabilities' in _error_paths(result)


@pytest.mark.unit
def test_validate_warns_when_disabled_absorb_direction_keeps_positive_limit(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['EV_CHARGER']['capabilities']['can_absorb_w'] = False

    result = validate_grouped_ems_config(config)

    warning_paths = {issue.path for issue in result.issues if issue.severity == SEVERITY_WARNING}
    assert 'ems.devices.EV_CHARGER.capabilities.max_absorb_w' in warning_paths


@pytest.mark.unit
def test_validate_rejects_ev_limits_that_cannot_be_represented_by_current_step(project_root):
    config = _load_example(project_root)
    ev = config['ems']['devices']['EV_CHARGER']
    ev['capabilities']['min_absorb_w'] = 100
    ev['capabilities']['max_absorb_w'] = 200
    ev['adapter']['current_step_a'] = 4
    ev['adapter']['phases'] = 1
    ev['adapter']['voltage_v'] = 230

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.devices.EV_CHARGER.adapter.current_step_a' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_unknown_ev_adapter_field_generically(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['EV_CHARGER']['adapter']['unexpected_field'] = 'input_number.foo'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.devices.EV_CHARGER.adapter.unexpected_field'] == (
        'Unknown config field: ems.devices.EV_CHARGER.adapter.unexpected_field'
    )


@pytest.mark.unit
def test_validate_rejects_unknown_relay_policy_field_generically(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['RELAY1']['policy']['extra_policy_flag'] = 'input_boolean.foo'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.devices.RELAY1.policy.extra_policy_flag'] == (
        'Unknown config field: ems.devices.RELAY1.policy.extra_policy_flag'
    )


@pytest.mark.unit
def test_validate_rejects_unknown_policy_output_field_generically(project_root):
    config = _load_example(project_root)
    config['ems']['policy_outputs']['unexpected_output'] = 'sensor.foo'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_outputs.unexpected_output'] == (
        'Unknown config field: ems.policy_outputs.unexpected_output'
    )


@pytest.mark.unit
def test_validate_accepts_diagnostics_outputs_section(project_root):
    config = _load_example(project_root)

    result = validate_grouped_ems_config(config)

    assert result.ok is True


@pytest.mark.unit
def test_validate_rejects_legacy_policy_decision_trace_with_guidance(project_root):
    config = _load_example(project_root)
    config['ems']['policy_outputs']['decision_trace'] = 'sensor.legacy_trace'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_outputs.decision_trace'] == (
        'Unsupported legacy policy_outputs field: decision_trace. '
        'Use diagnostics_outputs.policy_diagnostics instead.'
    )


@pytest.mark.unit
def test_validate_rejects_legacy_actuator_writer_trace_with_guidance(project_root):
    config = _load_example(project_root)
    config['ems']['policy_outputs']['actuator_writer_trace'] = 'sensor.legacy_writer_trace'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_outputs.actuator_writer_trace'] == (
        'Unsupported legacy policy_outputs field: actuator_writer_trace. '
        'Use diagnostics_outputs.actuator_writer_trace instead.'
    )


@pytest.mark.unit
def test_validate_rejects_legacy_dispatch_state_applier_trace_with_guidance(project_root):
    config = _load_example(project_root)
    config['ems']['policy_outputs']['dispatch_state_applier_trace'] = 'sensor.legacy_dispatch_trace'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_outputs.dispatch_state_applier_trace'] == (
        'Unsupported legacy policy_outputs field: dispatch_state_applier_trace. '
        'Use diagnostics_outputs.dispatch_state_applier_trace instead.'
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ('field_name', 'entity_id'),
    (
        ('surplus_policy_active', 'binary_sensor.legacy_surplus_policy_active'),
        ('surplus_next_target', 'sensor.legacy_surplus_next_target'),
        ('surplus_next_threshold', 'sensor.legacy_surplus_next_threshold'),
        ('surplus_release_candidate', 'sensor.legacy_surplus_release_candidate'),
        ('surplus_explanation', 'sensor.legacy_surplus_explanation'),
    ),
)
def test_validate_rejects_removed_standalone_surplus_summary_outputs(project_root, field_name, entity_id):
    config = _load_example(project_root)
    config['ems']['policy_outputs'][field_name] = entity_id

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)[f'ems.policy_outputs.{field_name}'] == (
        f'Unsupported legacy policy_outputs field: {field_name}. '
        'Standalone surplus summary sensors were removed.'
    )


@pytest.mark.unit
def test_runtime_alias_index_exposes_unit_transform_metadata(project_root):
    config = _load_example(project_root)
    aliases = runtime_alias_index(config)

    assert aliases['ev_hard_off_pv_threshold_kw'].unit_transform == 'W_TO_KW'


@pytest.mark.unit
def test_validate_rejects_legacy_runtime_fields_with_explicit_messages(project_root):
    config = _load_example(project_root)
    runtime = config['ems']['runtime']
    runtime['required_power_w'] = 'sensor.required_power_consumption'
    runtime['rpnz_w'] = 'sensor.ems_calculated_required_power_for_net_zero'
    runtime['pv_power_kw'] = 'sensor.pv_kw'

    result = validate_grouped_ems_config(config)

    messages = _error_messages(result)
    assert messages['ems.runtime.required_power_w'] == (
        'runtime.required_power_w is no longer accepted; required power is derived inside EMS '
        'from grid_power_w, quarter_energy_balance_kwh, and current quarter time.'
    )
    assert messages['ems.runtime.rpnz_w'] == (
        'runtime.rpnz_w is no longer accepted; RPNZ is derived inside EMS from '
        'quarter_energy_balance_kwh and current quarter time.'
    )
    assert messages['ems.runtime.pv_power_kw'] == (
        'runtime.pv_power_kw is no longer accepted; use runtime.pv_power_w.'
    )


@pytest.mark.unit
def test_runtime_alias_index_contains_expected_core_aliases(project_root):
    config = _load_example(project_root)
    aliases = runtime_alias_index(config)

    assert aliases['control_profile'].config_path == 'ems.profiles.control'
    assert aliases['ramp_max_w'].config_path == 'ems.global_config.ramp_w'
    assert aliases['battery_protect_charge_floor_w'].config_path == 'ems.devices.HOME_BATTERY.guard.protect_min_absorb_w'
    assert aliases['actuator_ev_current_a'].config_path == 'ems.devices.EV_CHARGER.adapter.current_a'


@pytest.mark.unit
def test_runtime_alias_index_uses_kind_based_fallback_for_custom_device_ids(project_root):
    config = _load_example(project_root)
    devices = config['ems']['devices']
    devices['GARAGE_EV'] = devices.pop('EV_CHARGER')
    devices['POOL_PUMP'] = devices.pop('RELAY1')
    devices['BOILER'] = devices.pop('RELAY2')

    aliases = runtime_alias_index(config)

    assert aliases['actuator_ev_current_a'].config_path == 'ems.devices.GARAGE_EV.adapter.current_a'
    assert aliases['actuator_relay1'].config_path == 'ems.devices.POOL_PUMP.adapter.enabled'
    assert aliases['actuator_relay2'].config_path == 'ems.devices.BOILER.adapter.enabled'


@pytest.mark.unit
def test_build_core_config_from_grouped_config_no_longer_depends_on_runtime_alias_runtime(project_root, monkeypatch):
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
        'input_number.ems_ev_min_power_w': 4140,
        'input_number.ems_ev_max_power_w': 11040,
        'input_number.ems_ev_charger_phases': 3,
        'input_boolean.ems_ev_force_on': False,
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

    cfg = build_core_config_from_grouped_config(config, entity_values)

    assert cfg.deadband_w == 75
    assert cfg.max_solar_charge_w == 3700
    assert cfg.max_battery_discharge_w == 4600
    assert cfg.device_by_id('EV_CHARGER').policy.low_pv_threshold_w == 1.8
    assert cfg.adjustable_surplus_load == 'EV_CHARGER'
    assert cfg.adjustable_primary_load == 'HOME_BATTERY'


@pytest.mark.unit
def test_build_core_config_from_grouped_reader_builds_core_config(project_root):
    config = _load_example(project_root)

    cfg = build_core_config_from_grouped_reader(
        config,
        lambda entity_id, default: {
            'input_number.ems_deadband_w': 80,
            'input_number.ems_ramp_max_w': 900,
            'input_number.ems_ev_max_power_w': 3680,
        }.get(entity_id, default),
    )

    assert cfg.deadband_w == 80
    assert cfg.ramp_max_w == 900
