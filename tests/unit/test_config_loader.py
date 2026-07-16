import os
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
    compile_core_config_plan_from_grouped_config,
    materialize_core_config_from_plan,
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
def test_validate_requires_at_least_one_battery_device(project_root):
    config = _load_example(project_root)
    del config['ems']['devices']['HOME_BATTERY']

    result = validate_grouped_ems_config(config)
    assert result.ok is False
    assert 'ems.devices' in _error_paths(result)


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
def test_validate_rejects_battery_with_both_directions_disabled(project_root):
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
def test_build_core_config_from_grouped_config_uses_canonical_grouped_values(project_root):
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
        'input_select.ems_primary_consuming_device': 'HOME_BATTERY',
        'input_number.ems_adjustable_surplus_activation_w': 2000,
        'input_number.ems_home_battery_surplus_priority': 3,
        'input_number.ems_haeo_stale_timeout_s': 300,
        'input_number.ems_relay1_power_kw': 2.5,
        'input_number.ems_relay2_power_kw': 5.0,
        'input_number.ems_surplus_freeze_s': 30,
        'input_number.ems_surplus_ev_priority': 3,
        'input_number.ems_surplus_relay1_priority': 2,
        'input_number.ems_surplus_relay2_priority': 1,
    }

    cfg = build_core_config_from_grouped_config(config, entity_values)

    assert cfg.global_config.deadband_w == 75
    assert cfg.device_by_id('HOME_BATTERY').capabilities.max_absorb_w == 3700
    assert cfg.device_by_id('HOME_BATTERY').capabilities.max_produce_w == 4600
    assert cfg.device_by_id('EV_CHARGER').policy.low_pv_threshold_w == 1.8
    assert not hasattr(cfg, 'adjustable_surplus_load')
    assert cfg.global_config.primary_consuming_device_ids == ('HOME_BATTERY',)


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

    assert cfg.global_config.deadband_w == 80
    assert cfg.global_config.ramp_w == 900


















@pytest.mark.unit
def test_compile_core_config_plan_contains_dynamic_refs_with_metadata(project_root):
    config = _load_example(project_root)

    plan = compile_core_config_plan_from_grouped_config(config)
    deadband_ref = plan.grouped_config_plan['ems']['global_config']['deadband_w']
    primary_refs = plan.grouped_config_plan['ems']['global_config']['primary_consuming_device_ids']
    ev_force_on_ref = plan.grouped_config_plan['ems']['devices']['EV_CHARGER']['policy']['force_on']

    assert isinstance(deadband_ref, DynamicConfigRef)
    assert deadband_ref.path == 'ems.global_config.deadband_w'
    assert deadband_ref.entity_id == 'input_number.ems_deadband_w'
    assert deadband_ref.value_type == 'int'
    assert deadband_ref.default == 50

    assert isinstance(primary_refs, tuple)
    assert isinstance(primary_refs[0], DynamicConfigRef)
    assert primary_refs[0].value_type == 'str'
    assert primary_refs[0].default == ''
    assert primary_refs[1] == 'HOME_BATTERY'

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
        'tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_surplus/EMS_config.yaml',
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
                'input_number.ems_home_battery_surplus_priority': 3,
                'input_number.ems_surplus_ev_priority': 8,
            }
        ),
    )

    assert cfg.device_by_id('HOME_BATTERY').policy.priority == 3
    assert cfg.device_by_id('EV_CHARGER').policy.priority == 8


@pytest.mark.unit
def test_device_priorities_are_independent_of_removed_surplus_selector(project_root):
    config = _load_example(project_root)

    cfg = build_core_config_from_grouped_reader(
        config,
        _plan_reader_from_values(
            {
                'input_number.ems_home_battery_surplus_priority': 2,
                'input_number.ems_surplus_ev_priority': 3,
            }
        ),
    )

    assert cfg.device_by_id('HOME_BATTERY').policy.priority == 2
    assert cfg.device_by_id('EV_CHARGER').policy.priority == 3
    assert not hasattr(cfg, 'adjustable_surplus_load')


@pytest.mark.unit
def test_dynamic_default_override_battery_priority_uses_explicit_ha_value_when_present(project_root):
    config = _load_example(project_root)

    cfg = build_core_config_from_grouped_reader(
        config,
        _plan_reader_from_values(
            {
                'input_number.ems_home_battery_surplus_priority': 11,
                'input_number.ems_surplus_ev_priority': 5,
            }
        ),
    )

    assert cfg.device_by_id('HOME_BATTERY').policy.priority == 11


@pytest.mark.unit
def test_materialized_core_config_does_not_expose_mutable_cached_plan_objects(project_root):
    config = _load_example(project_root)
    plan = compile_core_config_plan_from_grouped_config(config)
    reader = lambda _entity_id, default: default
    first_cfg = materialize_core_config_from_plan(plan, reader)

    first_cfg.role_constraints.default['mutated'] = 123
    first_cfg.devices['BROKEN'] = first_cfg.device_by_id('HOME_BATTERY')

    second_cfg = materialize_core_config_from_plan(plan, reader)

    assert 'mutated' not in second_cfg.role_constraints.default
    assert 'BROKEN' not in second_cfg.devices
    assert 'mutated' not in plan.grouped_config_plan['ems']['role_constraints'].get('default', {})
    assert 'BROKEN' not in plan.grouped_config_plan['ems']['devices']



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
def test_runtime_packet_config_allows_multiple_generic_battery_devices(project_root):
    config = load_grouped_ems_config(project_root / 'EMS_config.yaml')
    devices = config['ems']['devices']
    battery = devices.pop('HOME_BATTERY')
    devices['BATTERY_30KWH'] = battery
    devices['BATTERY_60KWH'] = {
        'kind': 'BATTERY',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': True,
            'supports_primary_consuming_regulation': True,
            'supports_producing_regulation': True,
        },
    }
    config['ems']['role_constraints']['default']['primary'] = 'BATTERY_30KWH'

    result = validate_grouped_ems_config(config)

    assert result.ok is True
    assert not _error_paths(result)
