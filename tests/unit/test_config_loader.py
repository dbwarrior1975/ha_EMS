import os
import inspect
import subprocess
import sys

import pytest

from ems_adapter.config_loader import (
    DynamicConfigRef,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    _materialize_core_config_via_resolved_config_for_tests,
    _parse_policy_engine_diagnostics_interval_seconds,
    _parse_policy_engine_interval_seconds,
    build_core_config_from_grouped_config,
    build_core_config_from_grouped_reader,
    build_policy_context_view,
    compile_core_config_plan_from_grouped_config,
    compile_dynamic_runtime_read_plan,
    materialize_core_config_from_plan,
    runtime_alias_index,
    load_grouped_ems_config,
    load_and_validate_grouped_ems_config,
    validate_grouped_ems_config,
)
from ems_core.domain.constants import (
    CANONICAL_DIAGNOSTICS_OUTPUTS,
    CANONICAL_POLICY_OUTPUTS,
)


def _load_example(project_root):
    return load_grouped_ems_config(project_root / 'example_EMS_config.yaml')


def _plan_reader_from_values(values):
    return lambda entity_id, default: values.get(entity_id, default)


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
@pytest.mark.parametrize('value', ('true', 1, 0, None, 'unknown'))
def test_validate_rejects_non_boolean_surplus_allowed(project_root, value):
    config = _load_example(project_root)
    config['ems']['devices']['EV_CHARGER']['policy']['surplus_allowed'] = value

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.devices.EV_CHARGER.policy.surplus_allowed' in _error_paths(result)


@pytest.mark.unit
@pytest.mark.parametrize('value', (0, -1, -0.5, 4400))
def test_validate_rejects_removed_surplus_activation_threshold_field(project_root, value):
    config = _load_example(project_root)
    config['ems']['devices']['EV_CHARGER']['policy']['activation_threshold_w'] = value

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.devices.EV_CHARGER.policy.activation_threshold_w' in _error_paths(result)


@pytest.mark.unit
def test_validate_rejects_unknown_surplus_dispatch_mode(project_root):
    config = _load_example(project_root)
    config['ems']['devices']['EV_CHARGER']['policy']['surplus_dispatch_mode'] = 'stepped'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.devices.EV_CHARGER.policy.surplus_dispatch_mode' in _error_paths(result)


@pytest.mark.unit
@pytest.mark.parametrize('field', ('surplus_allowed', 'surplus_dispatch_mode'))
def test_validate_rejects_missing_required_ev_surplus_policy_field(project_root, field):
    config = _load_example(project_root)
    del config['ems']['devices']['EV_CHARGER']['policy'][field]

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert f'ems.devices.EV_CHARGER.policy.{field}' in _error_paths(result)


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
    config['ems']['policy_outputs'] = {'unexpected_output': 'sensor.foo'}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_outputs'] == (
        'ems.policy_outputs is no longer user config. EMS canonical policy output entity IDs are fixed in code.'
    )


@pytest.mark.unit
def test_policy_outputs_defaults_to_canonical_values_if_missing(project_root):
    config = _load_example(project_root)
    config['ems'].pop('policy_outputs', None)
    config['ems'].pop('diagnostics_outputs', None)

    result = validate_grouped_ems_config(config)
    core = build_core_config_from_grouped_config(config, {})

    assert result.ok is True
    assert core.policy_outputs.device_policies == CANONICAL_POLICY_OUTPUTS['device_policies']
    assert core.policy_outputs.dispatch_command == CANONICAL_POLICY_OUTPUTS['dispatch_command']
    assert core.policy_outputs.policy_state == CANONICAL_POLICY_OUTPUTS['policy_state']
    assert core.diagnostics_outputs.policy_diagnostics == CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics']
    assert core.diagnostics_outputs.actuator_writer_trace == CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace']
    assert core.diagnostics_outputs.dispatch_state_applier_trace == CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace']


@pytest.mark.unit
def test_policy_engine_interval_defaults_to_5(project_root):
    config = _load_example(project_root)
    config['ems'].pop('policy_engine', None)

    result = validate_grouped_ems_config(config)
    core = build_core_config_from_grouped_config(config, {})

    assert result.ok is True
    assert core.policy_engine.interval_seconds == 5.0
    assert core.policy_engine.diagnostics_interval_seconds == 30.0


@pytest.mark.unit
def test_policy_engine_interval_accepts_minimum_2(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'interval_seconds': 2}

    result = validate_grouped_ems_config(config)
    core = build_core_config_from_grouped_config(config, {})

    assert result.ok is True
    assert core.policy_engine.interval_seconds == 2.0


@pytest.mark.unit
def test_policy_engine_interval_rejects_values_below_2(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'interval_seconds': 1}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.interval_seconds'] == (
        'policy_engine.interval_seconds must be >= 2 seconds'
    )


@pytest.mark.unit
def test_policy_engine_interval_rejects_non_numeric(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'interval_seconds': '5'}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.interval_seconds'] == (
        'policy_engine.interval_seconds must be numeric'
    )


@pytest.mark.unit
def test_policy_engine_interval_rejects_bool(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'interval_seconds': True}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.interval_seconds'] == (
        'policy_engine.interval_seconds must be numeric'
    )


@pytest.mark.unit
def test_policy_engine_interval_rejects_entity_ref(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'interval_seconds': 'input_number.ems_interval'}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.interval_seconds'] == (
        'policy_engine.interval_seconds must be numeric'
    )


@pytest.mark.unit
def test_policy_engine_interval_rejects_unknown_field(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {
        'interval_seconds': 5,
        'diagnostics_interval_seconds': 30,
        'unexpected': 1,
    }

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.unexpected'] == (
        'Unknown config field: ems.policy_engine.unexpected'
    )


@pytest.mark.unit
def test_parse_policy_engine_interval_seconds_accepts_int_and_float():
    assert _parse_policy_engine_interval_seconds(5) == 5.0
    assert _parse_policy_engine_interval_seconds(2.5) == 2.5


@pytest.mark.unit
def test_policy_engine_diagnostics_interval_defaults_to_30(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'interval_seconds': 5}

    result = validate_grouped_ems_config(config)
    core = build_core_config_from_grouped_config(config, {})

    assert result.ok is True
    assert core.policy_engine.diagnostics_interval_seconds == 30.0


@pytest.mark.unit
def test_policy_engine_diagnostics_interval_accepts_30(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'interval_seconds': 5, 'diagnostics_interval_seconds': 30}

    result = validate_grouped_ems_config(config)
    core = build_core_config_from_grouped_config(config, {})

    assert result.ok is True
    assert core.policy_engine.diagnostics_interval_seconds == 30.0


@pytest.mark.unit
def test_policy_engine_diagnostics_interval_accepts_minimum_5(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'diagnostics_interval_seconds': 5}

    result = validate_grouped_ems_config(config)
    core = build_core_config_from_grouped_config(config, {})

    assert result.ok is True
    assert core.policy_engine.diagnostics_interval_seconds == 5.0


@pytest.mark.unit
@pytest.mark.parametrize('value', [2, 0, -1])
def test_policy_engine_diagnostics_interval_rejects_values_below_5(project_root, value):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'diagnostics_interval_seconds': value}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.diagnostics_interval_seconds'] == (
        'policy_engine.diagnostics_interval_seconds must be >= 5 seconds'
    )


@pytest.mark.unit
def test_policy_engine_diagnostics_interval_rejects_non_numeric(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'diagnostics_interval_seconds': '30'}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.diagnostics_interval_seconds'] == (
        'policy_engine.diagnostics_interval_seconds must be a numeric config constant'
    )


@pytest.mark.unit
def test_policy_engine_diagnostics_interval_rejects_bool(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'diagnostics_interval_seconds': True}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.diagnostics_interval_seconds'] == (
        'policy_engine.diagnostics_interval_seconds must be a numeric config constant'
    )


@pytest.mark.unit
def test_policy_engine_diagnostics_interval_rejects_entity_ref(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'diagnostics_interval_seconds': 'input_number.ems_diagnostics_interval'}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_engine.diagnostics_interval_seconds'] == (
        'policy_engine.diagnostics_interval_seconds must be a numeric config constant'
    )


@pytest.mark.unit
def test_diagnostics_interval_invalid_yaml_does_not_default_silently(project_root):
    config = _load_example(project_root)
    config['ems']['policy_engine'] = {'diagnostics_interval_seconds': 'bad-yaml-value'}

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.policy_engine.diagnostics_interval_seconds' in _error_paths(result)


@pytest.mark.unit
def test_parse_policy_engine_diagnostics_interval_seconds_accepts_int_and_float():
    assert _parse_policy_engine_diagnostics_interval_seconds(30) == 30.0
    assert _parse_policy_engine_diagnostics_interval_seconds(7.5) == 7.5


@pytest.mark.unit
def test_policy_outputs_section_is_rejected_even_with_canonical_values(project_root):
    config = _load_example(project_root)
    config['ems']['policy_outputs'] = dict(CANONICAL_POLICY_OUTPUTS)

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_outputs'] == (
        'ems.policy_outputs is no longer user config. EMS canonical policy output entity IDs are fixed in code.'
    )


@pytest.mark.unit
def test_policy_outputs_section_is_rejected_with_custom_values(project_root):
    config = _load_example(project_root)
    config['ems']['policy_outputs'] = {
        'device_policies': 'sensor.custom_device_policies',
    }

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_outputs'] == (
        'ems.policy_outputs is no longer user config. EMS canonical policy output entity IDs are fixed in code.'
    )


@pytest.mark.unit
def test_policy_outputs_section_is_rejected_with_unknown_key(project_root):
    config = _load_example(project_root)
    config['ems']['policy_outputs'] = {
        'unexpected': 'sensor.foo',
    }

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.policy_outputs'] == (
        'ems.policy_outputs is no longer user config. EMS canonical policy output entity IDs are fixed in code.'
    )


@pytest.mark.unit
def test_diagnostics_outputs_defaults_to_canonical_values_if_missing(project_root):
    config = _load_example(project_root)
    config['ems'].pop('diagnostics_outputs', None)
    config['ems'].pop('policy_outputs', None)

    result = validate_grouped_ems_config(config)
    core = build_core_config_from_grouped_config(config, {})

    assert result.ok is True
    assert core.diagnostics_outputs.policy_diagnostics == CANONICAL_DIAGNOSTICS_OUTPUTS['policy_diagnostics']
    assert core.diagnostics_outputs.actuator_writer_trace == CANONICAL_DIAGNOSTICS_OUTPUTS['actuator_writer_trace']
    assert core.diagnostics_outputs.dispatch_state_applier_trace == CANONICAL_DIAGNOSTICS_OUTPUTS['dispatch_state_applier_trace']


@pytest.mark.unit
def test_diagnostics_outputs_section_is_rejected_even_with_canonical_values(project_root):
    config = _load_example(project_root)
    config['ems']['diagnostics_outputs'] = dict(CANONICAL_DIAGNOSTICS_OUTPUTS)

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.diagnostics_outputs'] == (
        'ems.diagnostics_outputs is no longer user config. EMS diagnostics output entity IDs are fixed in code.'
    )


@pytest.mark.unit
def test_diagnostics_outputs_section_is_rejected_with_custom_values(project_root):
    config = _load_example(project_root)
    config['ems']['diagnostics_outputs'] = {
        'policy_diagnostics': 'sensor.custom_policy_diagnostics',
    }

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.diagnostics_outputs'] == (
        'ems.diagnostics_outputs is no longer user config. EMS diagnostics output entity IDs are fixed in code.'
    )


@pytest.mark.unit
def test_diagnostics_outputs_section_is_rejected_with_unknown_key(project_root):
    config = _load_example(project_root)
    config['ems']['diagnostics_outputs'] = {
        'unexpected': 'sensor.foo',
    }

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert _error_messages(result)['ems.diagnostics_outputs'] == (
        'ems.diagnostics_outputs is no longer user config. EMS diagnostics output entity IDs are fixed in code.'
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
    assert not hasattr(cfg, 'adjustable_surplus_load')
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


@pytest.mark.unit
def test_core_config_view_uses_plain_methods_not_partial_callables(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)

    cfg = build_policy_context_view(plan, lambda _entity_id, default: default)

    assert inspect.ismethod(cfg.device_by_id)
    assert inspect.ismethod(cfg.first_device_by_kind)
    assert inspect.ismethod(cfg.devices_by_kind)
    assert not hasattr(cfg.device_by_id, 'func')
    assert not hasattr(cfg.first_device_by_kind, 'func')
    assert not hasattr(cfg.devices_by_kind, 'func')
    assert cfg.legacy_device_bridge_count() == 0
    assert cfg.ev_charger == cfg.first_device_by_kind('EV_CHARGER')


@pytest.mark.unit
def test_core_config_view_device_lookup_methods_return_plain_tuples(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)

    cfg = build_policy_context_view(plan, lambda _entity_id, default: default)

    relay_devices = cfg.devices_by_kind('RELAY')
    ev_devices = cfg.devices_by_kind('EV_CHARGER')

    assert type(relay_devices) is tuple
    assert type(ev_devices) is tuple
    assert relay_devices
    assert ev_devices
    assert cfg.device_by_id('RELAY1').device_id == 'RELAY1'
    assert cfg.device_by_id('EV_CHARGER').device_id == 'EV_CHARGER'


@pytest.mark.unit
def test_core_config_view_builds_relay_devices_lazily(project_root, monkeypatch):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)
    call_counts = {
        'relay': 0,
        'ev': 0,
    }
    real_build_relay = sys.modules['ems_adapter.config_loader']._build_view_relay_device
    real_build_ev = sys.modules['ems_adapter.config_loader']._build_view_ev_device

    def counting_build_relay(*args, **kwargs):
        call_counts['relay'] += 1
        return real_build_relay(*args, **kwargs)

    def counting_build_ev(*args, **kwargs):
        call_counts['ev'] += 1
        return real_build_ev(*args, **kwargs)

    monkeypatch.setattr('ems_adapter.config_loader._build_view_relay_device', counting_build_relay)
    monkeypatch.setattr('ems_adapter.config_loader._build_view_ev_device', counting_build_ev)

    cfg = build_policy_context_view(plan, lambda _entity_id, default: default)

    assert call_counts['relay'] == 0
    assert call_counts['ev'] == 0

    _relay = cfg.device_by_id('RELAY1')
    assert _relay.device_id == 'RELAY1'
    assert call_counts['relay'] == 1


@pytest.mark.unit
def test_core_config_devices_view_values_items_do_not_return_coroutines(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)

    cfg = build_policy_context_view(plan, lambda _entity_id, default: default)
    values = cfg.devices.values()
    items = cfg.devices.items()

    assert type(values) is tuple
    assert type(items) is tuple
    assert values
    assert items
    for device in values:
        assert inspect.isawaitable(device) is False
        assert inspect.isawaitable(device.device_id) is False
        assert isinstance(device.device_id, str)
    for device_id, device in items:
        assert inspect.isawaitable(device) is False
        assert isinstance(device_id, str)
        assert device.device_id == device_id


@pytest.mark.unit
def test_core_config_devices_view_materializes_each_device_at_most_once_per_view(project_root, monkeypatch):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)
    call_counts = {}
    config_loader_mod = sys.modules['ems_adapter.config_loader']
    real_build_battery = config_loader_mod._build_view_battery_device
    real_build_ev = config_loader_mod._build_view_ev_device
    real_build_relay = config_loader_mod._build_view_relay_device

    def _count(key):
        call_counts[key] = int(call_counts.get(key, 0) or 0) + 1

    def counting_build_battery(plan_arg, values_arg):
        _count(str(plan_arg.device_id))
        return real_build_battery(plan_arg, values_arg)

    def counting_build_ev(plan_arg, values_arg):
        _count(str(plan_arg.device_id))
        return real_build_ev(plan_arg, values_arg)

    def counting_build_relay(plan_arg, values_arg):
        _count(str(plan_arg.device_id))
        return real_build_relay(plan_arg, values_arg)

    monkeypatch.setattr('ems_adapter.config_loader._build_view_battery_device', counting_build_battery)
    monkeypatch.setattr('ems_adapter.config_loader._build_view_ev_device', counting_build_ev)
    monkeypatch.setattr('ems_adapter.config_loader._build_view_relay_device', counting_build_relay)

    cfg = build_policy_context_view(plan, lambda _entity_id, default: default)
    assert cfg.legacy_device_bridge_count() == 0

    assert cfg.home_battery.device_id == 'HOME_BATTERY'
    assert cfg.ev_charger.device_id == 'EV_CHARGER'
    assert cfg.device_by_id('RELAY1').device_id == 'RELAY1'
    assert cfg.device_by_id('RELAY2').device_id == 'RELAY2'
    assert cfg.devices['HOME_BATTERY'] is cfg.home_battery
    assert cfg.devices['EV_CHARGER'] is cfg.ev_charger
    assert cfg.devices['RELAY1'] is cfg.device_by_id('RELAY1')
    assert cfg.devices['RELAY2'] is cfg.device_by_id('RELAY2')
    assert len(cfg.devices.values()) == 4
    assert len(cfg.devices.items()) == 4

    assert call_counts['HOME_BATTERY'] == 1
    assert call_counts['EV_CHARGER'] == 1
    assert call_counts['RELAY1'] == 1
    assert call_counts['RELAY2'] == 1
    assert cfg.legacy_device_bridge_count() == 4


@pytest.mark.unit
def test_core_config_view_hot_path_starts_without_legacy_device_bridge(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)

    cfg = build_policy_context_view(plan, lambda _entity_id, default: default)

    assert cfg.legacy_device_bridge_count() == 0
    assert cfg.legacy_device_bridge_counts_by_kind() == {}


@pytest.mark.unit
def test_dynamic_runtime_snapshot_keeps_only_dynamic_device_leaf_values(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)
    config_loader_mod = sys.modules['ems_adapter.config_loader']

    snapshot = config_loader_mod.build_dynamic_runtime_snapshot(plan, lambda _entity_id, default: default)

    assert 'can_absorb_w' not in ((snapshot.device_values['EV_CHARGER'].get('capabilities') or {}))
    assert 'can_produce_w' not in ((snapshot.device_values['EV_CHARGER'].get('capabilities') or {}))
    assert 'priority' in ((snapshot.device_values['EV_CHARGER'].get('policy') or {}))
    assert 'enabled' in ((snapshot.device_values['EV_CHARGER'].get('adapter') or {}))
    assert 'policy' in snapshot.home_battery_values
    assert 'priority' in snapshot.home_battery_values['policy']


@pytest.mark.unit
def test_home_battery_access_paths_share_same_per_view_object(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)

    cfg = build_policy_context_view(plan, lambda _entity_id, default: default)
    values_by_id = {device.device_id: device for device in cfg.devices.values()}
    items_by_id = {device_id: device for device_id, device in cfg.devices.items()}

    assert cfg.home_battery is cfg.device_by_id('HOME_BATTERY')
    assert cfg.home_battery is cfg.devices['HOME_BATTERY']
    assert cfg.home_battery is values_by_id['HOME_BATTERY']
    assert cfg.home_battery is items_by_id['HOME_BATTERY']


@pytest.mark.unit
def test_device_view_memoization_is_per_view_not_cross_run(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)

    first_cfg = build_policy_context_view(
        plan,
        _plan_reader_from_values(
            {
                'input_number.ems_surplus_ev_priority': 4,
                'input_boolean.ems_ev_force_on': False,
            }
        ),
    )
    second_cfg = build_policy_context_view(
        plan,
        _plan_reader_from_values(
            {
                'input_number.ems_surplus_ev_priority': 9,
                'input_boolean.ems_ev_force_on': True,
            }
        ),
    )

    assert first_cfg is not second_cfg
    assert first_cfg.home_battery is not second_cfg.home_battery
    assert first_cfg.ev_charger is not second_cfg.ev_charger
    assert first_cfg.device_by_id('RELAY1') is not second_cfg.device_by_id('RELAY1')
    assert first_cfg.ev_charger.policy.priority == 4
    assert second_cfg.ev_charger.policy.priority == 9
    assert first_cfg.ev_charger.policy.force_on is False
    assert second_cfg.ev_charger.policy.force_on is True


@pytest.mark.unit
def test_compile_core_config_plan_contains_dynamic_refs_with_metadata(project_root):
    config = _load_example(project_root)

    plan = compile_core_config_plan_from_grouped_config(config)
    deadband_ref = plan.grouped_config_plan['ems']['global_config']['deadband_w']
    primary_ref = plan.grouped_config_plan['ems']['global_config']['adjustable_primary_load']
    ev_force_on_ref = plan.grouped_config_plan['ems']['devices']['EV_CHARGER']['policy']['force_on']

    assert isinstance(deadband_ref, DynamicConfigRef)
    assert deadband_ref.path == 'ems.global_config.deadband_w'
    assert deadband_ref.entity_id == 'input_number.ems_deadband_w'
    assert deadband_ref.value_type == 'int'
    assert deadband_ref.default == 50

    assert isinstance(primary_ref, DynamicConfigRef)
    assert primary_ref.value_type == 'str'
    assert primary_ref.default == ''

    assert isinstance(ev_force_on_ref, DynamicConfigRef)
    assert ev_force_on_ref.path == 'ems.devices.EV_CHARGER.policy.force_on'
    assert ev_force_on_ref.value_type == 'str'


@pytest.mark.unit
@pytest.mark.parametrize(
    'config_relpath',
    (
        'example_EMS_config.yaml',
        'tests/e2e_entity/net_zero_priority_order_quarter_3_relays/EMS_config.yaml',
        'tests/e2e_entity/net_zero_two_ev_one_relay/EMS_config.yaml',
        'tests/e2e_entity/net_zero_no_ev_relays_only/EMS_config.yaml',
        'tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/EMS_config.yaml',
    ),
)
def test_materialize_core_config_from_plan_matches_resolved_config_path_across_real_configs(project_root, config_relpath):
    config = load_grouped_ems_config(project_root / config_relpath)
    plan = compile_core_config_plan_from_grouped_config(config)
    reader = lambda _entity_id, default: default

    direct_cfg = build_core_config_from_grouped_reader(config, reader)
    resolved_cfg = _materialize_core_config_via_resolved_config_for_tests(plan, reader)

    assert direct_cfg == resolved_cfg


@pytest.mark.unit
def test_materialize_core_config_from_plan_matches_resolved_config_path_with_dynamic_non_default_values(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)
    values = {
        'input_select.ems_control_profile': 'MANUAL_SAFE',
        'input_select.ems_goal_profile': 'MAX_EXPORT',
        'input_number.ems_deadband_w': 77,
        'input_number.ems_surplus_ev_priority': 6,
        'input_boolean.ems_ev_force_on': True,
        'input_number.ems_battery_protect_soc': 9,
        'input_number.ems_surplus_relay1_priority': 4,
    }
    reader = _plan_reader_from_values(values)

    direct_cfg = build_core_config_from_grouped_reader(config, reader)
    resolved_cfg = _materialize_core_config_via_resolved_config_for_tests(plan, reader)

    assert direct_cfg == resolved_cfg


@pytest.mark.unit
def test_battery_priority_does_not_inherit_ev_priority_when_battery_value_equals_default(project_root):
    config = _load_example(project_root)

    cfg = build_core_config_from_grouped_reader(
        config,
        _plan_reader_from_values(
            {
                'input_number.ems_adjustable_surplus_load_priority': 3,
                'input_number.ems_surplus_ev_priority': 8,
            }
        ),
    )

    assert cfg.home_battery.policy.priority == 3
    assert cfg.ev_charger.policy.priority == 8


@pytest.mark.unit
def test_device_priorities_are_independent_of_removed_surplus_selector(project_root):
    config = _load_example(project_root)

    cfg = build_core_config_from_grouped_reader(
        config,
        _plan_reader_from_values(
            {
                'input_number.ems_adjustable_surplus_load_priority': 2,
                'input_number.ems_surplus_ev_priority': 3,
            }
        ),
    )

    assert cfg.home_battery.policy.priority == 2
    assert cfg.ev_charger.policy.priority == 3
    assert not hasattr(cfg, 'adjustable_surplus_load')


@pytest.mark.unit
def test_dynamic_default_override_battery_priority_uses_explicit_ha_value_when_present(project_root):
    config = _load_example(project_root)

    cfg = build_core_config_from_grouped_reader(
        config,
        _plan_reader_from_values(
            {
                'input_number.ems_adjustable_surplus_load_priority': 11,
                'input_number.ems_surplus_ev_priority': 5,
            }
        ),
    )

    assert cfg.home_battery.policy.priority == 11


@pytest.mark.unit
def test_materialized_core_config_does_not_expose_mutable_cached_plan_objects(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)
    reader = lambda _entity_id, default: default
    first_cfg = materialize_core_config_from_plan(plan, reader)

    first_cfg.role_constraints.default['mutated'] = 123
    first_cfg.devices['BROKEN'] = first_cfg.home_battery

    second_cfg = materialize_core_config_from_plan(plan, reader)

    assert 'mutated' not in second_cfg.role_constraints.default
    assert 'BROKEN' not in second_cfg.devices
    assert 'mutated' not in plan.grouped_config_plan['ems']['role_constraints'].get('default', {})
    assert 'BROKEN' not in plan.grouped_config_plan['ems']['devices']


@pytest.mark.unit
def test_grouped_config_rejects_removed_legacy_adjustable_surplus_alias(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['global_config']['adjustable_surplus_load'] = 'RELAY1'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.global_config.adjustable_surplus_load' in _error_paths(result)


@pytest.mark.unit
def test_runtime_packet_config_rejects_duplicate_runtime_owned_device_fields(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_runtime_packet_config.yaml')
    config['ems']['devices']['EV_CHARGER']['policy'] = {'priority': 2}
    config['ems']['devices']['RELAY1']['capabilities']['max_absorb_w'] = 2700

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    paths = {issue.path for issue in result.errors}
    assert 'ems.devices.EV_CHARGER.policy' in paths
    assert 'ems.devices.RELAY1.capabilities.max_absorb_w' in paths

@pytest.mark.unit
def test_runtime_packet_config_rejects_static_global_config(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_runtime_packet_config.yaml')
    config['ems']['global_config'] = {
        'deadband_w': 50,
        'ramp_w': 1000,
        'strict_limit_w': 8000,
    }

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert any(issue.path == 'ems.global_config' for issue in result.errors)


@pytest.mark.unit
def test_runtime_packet_global_config_is_not_in_individual_dynamic_read_plan(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_runtime_packet_config.yaml')
    plan = compile_core_config_plan_from_grouped_config(config)
    read_plan = compile_dynamic_runtime_read_plan(plan)

    assert read_plan['global_config_fields'] == ()
    assert all('global_config' not in str(entry.get('path', '')) for entry in read_plan['unique_reads'])

