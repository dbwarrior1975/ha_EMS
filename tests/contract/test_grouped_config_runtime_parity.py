import pytest
import yaml
import time

from ems_adapter.config_loader import (
    build_core_config_from_grouped_config,
    build_core_config_from_grouped_reader,
    load_grouped_ems_config,
    validate_grouped_ems_config,
)
from ems_adapter import config_loader as config_loader_mod
from ems_adapter.device_read_model import build_device_configs
from ems_adapter import runtime_context as runtime_context_mod
from ems_adapter.runtime_context import (
    build_runtime_entities_from_grouped_config,
    read_runtime_context,
    runtime_context_dynamic_read_audit,
)
from tests.entity_ids import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
from tests.helpers import ev_w


@pytest.fixture(autouse=True)
def _enable_runtime_context_detailed_metrics_for_contract_tests():
    previous = runtime_context_mod.runtime_context_detailed_metrics_enabled()
    runtime_context_mod.set_runtime_context_detailed_metrics_enabled(True)
    try:
        yield
    finally:
        runtime_context_mod.set_runtime_context_detailed_metrics_enabled(previous)

def _write_grouped_config_with_override(project_root, tmp_path, dotted_path, value):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    node = config
    parts = dotted_path.split('.')
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value
    path = tmp_path / 'grouped_override.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path


def _write_grouped_config_with_overrides(project_root, tmp_path, overrides):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    for dotted_path, value in overrides.items():
        node = config
        parts = dotted_path.split('.')
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    path = tmp_path / 'grouped_overrides.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path


def _write_grouped_config_with_second_ev(project_root, tmp_path):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices']['EV_GARAGE'] = {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_regulation': True,
            'supports_residual_regulation': False,
            'uses_hard_off_lifecycle': True,
            'min_absorb_w': 'input_number.ems_ev_garage_min_power_w',
            'max_absorb_w': 'input_number.ems_ev_garage_max_power_w',
            'step_w': 'input_number.ems_ev_garage_power_step_w',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_ev_garage_priority',
            'surplus_allowed': 'input_boolean.ems_ev_garage_surplus_allowed',
            'force_on': 'input_boolean.ems_ev_garage_force_on',
            'low_pv_threshold_w': 'input_number.ems_ev_garage_low_pv_threshold_w',
            'hard_off_low_pv_cycles': 'input_number.ems_ev_garage_low_pv_cycles',
            'hard_off_release_cycles': 'input_number.ems_ev_garage_release_cycles',
        },
        'adapter': {
            'enabled': 'switch.ev_garage_enabled',
            'current_a': 'number.ev_garage_current_a',
            'current_step_a': 'input_number.ems_ev_garage_current_step_a',
            'phases': 'input_number.ems_ev_garage_phases',
            'voltage_v': 'input_number.ems_ev_garage_voltage_v',
        },
    }
    path = tmp_path / 'grouped_two_ev.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path, config


def _write_grouped_config_without_ev(project_root, tmp_path):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices'] = {
        device_id: device
        for device_id, device in config['ems']['devices'].items()
        if device.get('kind') != 'EV_CHARGER'
    }
    role_constraints = config['ems'].get('role_constraints', {})
    if isinstance(role_constraints, dict):
        home_battery_primary = role_constraints.get('HOME_BATTERY_PRIMARY')
        if isinstance(home_battery_primary, dict):
            home_battery_primary.pop('EV_CHARGER', None)
    config['ems']['global_config']['adjustable_surplus_load'] = 'input_select.ems_adjustable_surplus_load'
    config['ems']['global_config']['adjustable_primary_load'] = 'input_select.ems_adjustable_primary_load'
    path = tmp_path / 'grouped_no_ev.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path, config


def _stub_entity_readers():
    return (
        lambda _entity_id: False,
        lambda _entity_id, default=0.0: default,
        lambda _entity_id, default=0: default,
        lambda _entity_id, default='': default,
    )


def _mutable_entity_readers(values):
    return (
        lambda entity_id: bool(values.get(entity_id, False)),
        lambda entity_id, default=0.0: values.get(entity_id, default),
        lambda entity_id, default=0: values.get(entity_id, default),
        lambda entity_id, default='': values.get(entity_id, default),
    )


def _assert_dynamic_value_updates_on_static_cache_hit(project_root, monkeypatch, values, update_fn, extract_fn):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    read_bool, read_float, read_int, read_str = _mutable_entity_readers(values)

    first_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    update_fn(values)
    second_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert metrics['policy_engine_static_context_cache_hit'] is True
    assert extract_fn(first_cfg) != extract_fn(second_cfg)
    return first_cfg, second_cfg


@pytest.mark.unit
def test_grouped_config_builds_same_core_config_and_device_configs_as_runtime_view(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    validation = validate_grouped_ems_config(grouped_config)
    assert validation.ok is True

    grouped_config_path = project_root / 'example_EMS_config.yaml'
    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_config_path)
    harness.set_entities(
        {
            ENT['deadband_w']: 25,
            ENT['ramp_max_w']: 750,
            ENT['strict_limits_max_w']: 4100,
            ENT['max_battery_discharge_w']: 5200,
            ENT['max_solar_charge_w']: 4300,
            ENT['battery_protect_soc']: 7,
            ENT['battery_protect_soc_recovery_margin']: 2,
            ENT['battery_protect_min_cell_voltage_v']: 3.12,
            ENT['battery_protect_charge_floor_w']: 350,
            ENT['ev_min_absorb_w']: ev_w(6, phases=3),
            ENT['ev_max_absorb_w']: ev_w(20, phases=3),
            ENT['ev_charger_phases']: 3,
            ENT['ev_force_on']: False,
            ENT['ev_hard_off_pv_threshold_kw']: 1.4,
            ENT['ev_hard_off_low_pv_cycles']: 3,
            ENT['ev_hard_off_release_cycles']: 4,
            ENT['ev_current_step_a']: 2,
            ENT['nz_battery_floor_default_w']: 125,
            ENT['nz_battery_floor_ev_active_w']: 75,
            ENT['adjustable_surplus_load']: 'EV_CHARGER',
            ENT['adjustable_primary_load']: 'HOME_BATTERY',
            ENT['adjustable_surplus_activation']: 650,
            ENT['haeo_stale_timeout_s']: 240,
            ENT['devices']['RELAY1']['max_absorb_w']: 2300,
            ENT['devices']['RELAY2']['max_absorb_w']: 4800,
            ENT['surplus_freeze_s']: 45,
            ENT['devices']['EV_CHARGER']['priority']: 5,
            ENT['devices']['RELAY1']['priority']: 3,
            ENT['devices']['RELAY2']['priority']: 1,
        }
    )

    core_config = harness.policy_mod['read_config']()
    grouped_config_view = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )

    assert set(grouped_config_view.devices) == set(core_config.devices)
    assert build_device_configs(grouped_config_view) == build_device_configs(core_config)


@pytest.mark.unit
def test_grouped_config_runtime_reader_matches_dict_core_view(project_root):
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    validation = validate_grouped_ems_config(grouped_config)
    assert validation.ok is True

    grouped_config_path = project_root / 'example_EMS_config.yaml'
    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_config_path)
    harness.set_entities(
        {
            ENT['deadband_w']: 20,
            ENT['ramp_max_w']: 900,
            ENT['strict_limits_max_w']: 4200,
            ENT['max_battery_discharge_w']: 5000,
            ENT['max_solar_charge_w']: 4400,
            ENT['battery_protect_soc']: 8,
            ENT['battery_protect_soc_recovery_margin']: 3,
            ENT['battery_protect_min_cell_voltage_v']: 3.11,
            ENT['battery_protect_charge_floor_w']: 250,
            ENT['ev_min_absorb_w']: ev_w(7),
            ENT['ev_max_absorb_w']: ev_w(21),
            ENT['ev_charger_phases']: 1,
            ENT['ev_force_on']: False,
            ENT['ev_hard_off_pv_threshold_kw']: 1.5,
            ENT['ev_hard_off_low_pv_cycles']: 4,
            ENT['ev_hard_off_release_cycles']: 5,
            ENT['ev_current_step_a']: 1,
            ENT['nz_battery_floor_default_w']: 175,
            ENT['nz_battery_floor_ev_active_w']: 25,
            ENT['adjustable_surplus_load']: 'EV_CHARGER',
            ENT['adjustable_primary_load']: 'HOME_BATTERY',
            ENT['adjustable_surplus_activation']: 550,
            ENT['haeo_stale_timeout_s']: 180,
            ENT['devices']['RELAY1']['max_absorb_w']: 2100,
            ENT['devices']['RELAY2']['max_absorb_w']: 4400,
            ENT['surplus_freeze_s']: 60,
            ENT['devices']['EV_CHARGER']['priority']: 4,
            ENT['devices']['RELAY1']['priority']: 2,
            ENT['devices']['RELAY2']['priority']: 1,
        }
    )

    dict_view = build_core_config_from_grouped_config(grouped_config, harness.store.values)
    reader_view = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )
    core_view = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )
    runtime_core_view = harness.policy_mod['read_config']()

    assert reader_view == dict_view
    assert set(runtime_core_view.devices) == set(core_view.devices)
    assert build_device_configs(runtime_core_view) == build_device_configs(core_view)


@pytest.mark.unit
def test_policy_read_config_uses_grouped_config_as_default_source_when_available(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    grouped_config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')

    harness = QuarterScenarioHarness(project_root)
    harness.set_entities(
        {
            ENT['deadband_w']: 30,
            ENT['ramp_max_w']: 800,
            ENT['strict_limits_max_w']: 4300,
            ENT['max_battery_discharge_w']: 5100,
            ENT['max_solar_charge_w']: 4500,
            ENT['battery_protect_soc']: 6,
            ENT['battery_protect_soc_recovery_margin']: 2,
            ENT['battery_protect_min_cell_voltage_v']: 3.10,
            ENT['battery_protect_charge_floor_w']: 300,
            ENT['ev_min_absorb_w']: ev_w(6, phases=3),
            ENT['ev_max_absorb_w']: ev_w(22, phases=3),
            ENT['ev_charger_phases']: 3,
            ENT['ev_force_on']: False,
            ENT['ev_hard_off_pv_threshold_kw']: 1.3,
            ENT['ev_hard_off_low_pv_cycles']: 3,
            ENT['ev_hard_off_release_cycles']: 4,
            ENT['ev_current_step_a']: 2,
            ENT['nz_battery_floor_default_w']: 150,
            ENT['nz_battery_floor_ev_active_w']: 50,
            ENT['adjustable_surplus_load']: 'EV_CHARGER',
            ENT['adjustable_primary_load']: 'HOME_BATTERY',
            ENT['adjustable_surplus_activation']: 700,
            ENT['haeo_stale_timeout_s']: 210,
            ENT['devices']['RELAY1']['max_absorb_w']: 2200,
            ENT['devices']['RELAY2']['max_absorb_w']: 4600,
            ENT['surplus_freeze_s']: 55,
            ENT['devices']['EV_CHARGER']['priority']: 5,
            ENT['devices']['RELAY1']['priority']: 3,
            ENT['devices']['RELAY2']['priority']: 1,
        }
    )

    returned_config = harness.policy_mod['read_config']()
    status = harness.policy_mod['_GROUPED_CONFIG_DUAL_READ_STATUS']

    expected_core_config = build_core_config_from_grouped_reader(
        grouped_config,
        lambda entity_id, default: harness.store.get_value(entity_id, default),
    )
    assert set(returned_config.devices) == set(expected_core_config.devices)
    assert build_device_configs(returned_config) == build_device_configs(expected_core_config)
    assert status['enabled'] is True
    assert status['ok'] is True
    assert status['source'] == 'grouped_config'
    assert status['reason'] == 'loaded'


@pytest.mark.unit
def test_grouped_config_resolution_prefers_explicit_path_over_env_and_scenario(tmp_path, monkeypatch):
    explicit_path = tmp_path / 'explicit.yaml'
    env_path = tmp_path / 'env.yaml'
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    (scenario_dir / 'EMS_config.yaml').write_text('scenario: true\n', encoding='utf-8')
    explicit_path.write_text('explicit: true\n', encoding='utf-8')
    env_path.write_text('env: true\n', encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(env_path))

    resolved = QuarterScenarioHarness._resolve_grouped_config_path(
        project_root=tmp_path,
        grouped_config_path=explicit_path,
        scenario_dir=scenario_dir,
    )

    assert resolved == explicit_path


@pytest.mark.unit
def test_grouped_config_resolution_prefers_scenario_config_over_root_fallbacks(tmp_path, monkeypatch):
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    scenario_path = scenario_dir / 'EMS_config.yaml'
    scenario_path.write_text('scenario: true\n', encoding='utf-8')
    (tmp_path / 'example_EMS_config.yaml').write_text('root_example: true\n', encoding='utf-8')
    (tmp_path / 'EMS_config.yaml').write_text('root_ems: true\n', encoding='utf-8')
    monkeypatch.delenv('EMS_GROUPED_CONFIG_PATH', raising=False)

    resolved = QuarterScenarioHarness._resolve_grouped_config_path(
        project_root=tmp_path,
        scenario_dir=scenario_dir,
    )

    assert resolved == scenario_path


@pytest.mark.unit
def test_grouped_config_resolution_prefers_scenario_config_over_env(tmp_path, monkeypatch):
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    scenario_path = scenario_dir / 'EMS_config.yaml'
    env_path = tmp_path / 'env.yaml'
    scenario_path.write_text('scenario: true\n', encoding='utf-8')
    env_path.write_text('env: true\n', encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(env_path))

    resolved = QuarterScenarioHarness._resolve_grouped_config_path(
        project_root=tmp_path,
        scenario_dir=scenario_dir,
    )

    assert resolved == scenario_path


@pytest.mark.unit
def test_grouped_config_resolution_fails_when_scenario_dir_has_no_ems_config(tmp_path, monkeypatch):
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    (scenario_dir / 'example_EMS_config.yaml').write_text('scenario_example: true\n', encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(tmp_path / 'env.yaml'))

    with pytest.raises(FileNotFoundError) as exc:
        QuarterScenarioHarness._resolve_grouped_config_path(
            project_root=tmp_path,
            scenario_dir=scenario_dir,
        )

    assert str(scenario_dir) in str(exc.value)
    assert 'EMS_config.yaml' in str(exc.value)


@pytest.mark.unit
def test_grouped_config_resolution_prefers_root_example_before_root_ems(tmp_path, monkeypatch):
    root_example = tmp_path / 'example_EMS_config.yaml'
    root_ems = tmp_path / 'EMS_config.yaml'
    root_example.write_text('root_example: true\n', encoding='utf-8')
    root_ems.write_text('root_ems: true\n', encoding='utf-8')
    monkeypatch.delenv('EMS_GROUPED_CONFIG_PATH', raising=False)

    resolved = QuarterScenarioHarness._resolve_grouped_config_path(project_root=tmp_path)

    assert resolved == root_example


@pytest.mark.unit
def test_all_e2e_scenario_dirs_define_ems_config(project_root):
    scenario_root = project_root / 'tests' / 'e2e_entity'
    scenario_dirs = sorted(
        path for path in scenario_root.iterdir()
        if path.is_dir() and not path.name.startswith('__')
    )

    missing = [
        path.name
        for path in scenario_dirs
        if not (path / 'EMS_config.yaml').exists()
    ]

    assert missing == []


@pytest.mark.unit
def test_policy_loop_publishes_grouped_config_default_source_trace_attrs(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))

    harness = QuarterScenarioHarness(project_root)
    harness.step(note='dual-read trace')

    attrs = harness.getattrs(ENT['policy_diagnostics'])
    assert attrs['config_source'] == 'grouped_config'
    assert attrs['config_dual_read_enabled'] is True
    assert attrs['config_dual_read_ok'] is True
    assert attrs['config_dual_read_reason'] == 'loaded'
    assert attrs['config_grouped_path'] == str(project_root / 'example_EMS_config.yaml')


@pytest.mark.unit
def test_grouped_config_default_source_marks_production_ready(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))

    harness = QuarterScenarioHarness(project_root)
    harness.step(note='strict grouped production preflight')

    attrs = harness.getattrs(ENT['policy_diagnostics'])
    assert attrs['config_source'] == 'grouped_config'
    assert attrs['config_dual_read_ok'] is True
    assert attrs['config_grouped_production_ready'] is True
    assert attrs['config_grouped_production_ready_reason'] == 'ready'


@pytest.mark.unit
def test_policy_loop_requires_grouped_config_path_to_exist(project_root, monkeypatch):
    missing_path = project_root / 'missing_grouped_config.yaml'
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(missing_path))

    harness = QuarterScenarioHarness(project_root)
    with pytest.raises(FileNotFoundError):
        harness.step(note='invalid grouped path')

    status = harness.policy_mod['_GROUPED_CONFIG_DUAL_READ_STATUS']
    assert status['source'] == 'grouped_config'
    assert status['ok'] is False
    assert status['reason'] == 'FileNotFoundError'
    assert status['path'] == str(missing_path)


@pytest.mark.unit
def test_read_runtime_context_validation_error_lists_failing_paths(project_root, tmp_path, monkeypatch):
    grouped_path = _write_grouped_config_with_override(
        project_root,
        tmp_path,
        'ems.state.previous_device_state',
        None,
    )
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    with pytest.raises(ValueError, match='ems.state.previous_device_state: must be a non-empty entity id string'):
        read_runtime_context(read_bool, read_float, read_int, read_str)


@pytest.mark.unit
def test_read_runtime_context_caches_grouped_config_until_file_signature_changes(project_root, tmp_path, monkeypatch):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped_path = tmp_path / 'grouped_cache.yaml'
    grouped_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    runtime_context_mod._reset_runtime_context_config_cache()

    calls = []
    real_loader = runtime_context_mod.load_and_validate_grouped_ems_config

    def counting_loader(path):
        calls.append(path)
        return real_loader(path)

    signatures = iter(((1, 100), (1, 100), (2, 100)))

    def controlled_signature(_path):
        return next(signatures)

    monkeypatch.setattr(runtime_context_mod, 'load_and_validate_grouped_ems_config', counting_loader)
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', controlled_signature)
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    read_runtime_context(read_bool, read_float, read_int, read_str)
    read_runtime_context(read_bool, read_float, read_int, read_str)
    read_runtime_context(read_bool, read_float, read_int, read_str)

    assert calls == [str(grouped_path), str(grouped_path)]


@pytest.mark.unit
def test_runtime_context_production_path_does_not_call_eager_materializers(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))

    def _fail(*_args, **_kwargs):
        raise AssertionError('production runtime path must not call eager core-config materializer')

    monkeypatch.setattr(config_loader_mod, 'materialize_core_config_from_plan', _fail)
    monkeypatch.setattr(config_loader_mod, '_materialize_core_config_direct', _fail)
    monkeypatch.setattr(config_loader_mod, '_materialize_core_devices_from_plan', _fail)
    monkeypatch.setattr(config_loader_mod, '_materialize_home_battery_from_plan', _fail)
    monkeypatch.setattr(config_loader_mod, '_populate_core_config_derived_fields', _fail)

    cfg, _entities = read_runtime_context(*_stub_entity_readers())

    assert cfg is not None
    assert cfg.ev_charger is not None


@pytest.mark.unit
def test_runtime_context_metrics_are_numeric_and_non_negative(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    numeric_fields = (
        'policy_engine_config_signature_ms',
        'policy_engine_static_context_cache_hits',
        'policy_engine_static_context_cache_misses',
        'policy_engine_static_context_build_ms',
        'policy_engine_dynamic_config_reads_ms',
        'policy_engine_dynamic_config_logical_reads',
        'policy_engine_dynamic_config_reader_total_ms',
        'policy_engine_dynamic_config_reader_overhead_ms',
        'policy_engine_dynamic_config_audit_overhead_ms',
        'policy_engine_runtime_entity_registry_ms',
        'policy_engine_core_config_build_ms',
    )
    for field in numeric_fields:
        assert isinstance(metrics[field], int)
        assert metrics[field] >= 0
    assert isinstance(metrics['policy_engine_static_context_cache_hit'], bool)
    assert isinstance(metrics['policy_engine_dynamic_config_full_audit_collected'], bool)


@pytest.mark.unit
def test_runtime_context_dynamic_read_audit_collapses_duplicate_reads_within_single_run(project_root, tmp_path, monkeypatch):
    grouped_path = _write_grouped_config_with_overrides(
        project_root,
        tmp_path,
        {
            'ems.profiles.control': 'input_select.ems_shared_profile',
            'ems.profiles.goal': 'input_select.ems_shared_profile',
        },
    )
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))

    read_counts = {'shared': 0}

    def read_bool(_entity_id):
        return False

    def read_float(_entity_id, default=0.0):
        return default

    def read_int(_entity_id, default=0):
        return default

    def read_str(entity_id, default=''):
        if entity_id == 'input_select.ems_shared_profile':
            read_counts['shared'] += 1
            return 'AUTOMATIC'
        return default

    cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    audit = runtime_context_dynamic_read_audit()

    assert cfg.profiles.control == 'AUTOMATIC'
    assert cfg.profiles.goal == 'AUTOMATIC'
    assert read_counts['shared'] == 1
    assert audit['total_reads'] >= audit['underlying_reads']
    assert audit['cache_hits'] >= 1
    assert audit['full_audit_collected'] is True
    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    shared_entries = [
        entry for entry in audit['entries']
        if entry['entity_id'] == 'input_select.ems_shared_profile'
    ]
    assert len(shared_entries) == 1
    assert shared_entries[0]['count'] == 2
    assert shared_entries[0]['underlying_reads'] == 1
    assert shared_entries[0]['cache_hits'] == 1
    assert metrics['policy_engine_dynamic_config_unique_reads'] >= 1
    assert metrics['policy_engine_dynamic_config_audit_entries'] >= 1
    assert metrics['policy_engine_dynamic_config_full_audit_collected'] is True


@pytest.mark.unit
def test_runtime_context_dynamic_read_audit_cache_is_per_run_and_values_refresh_next_run(project_root, tmp_path, monkeypatch):
    grouped_path = _write_grouped_config_with_overrides(
        project_root,
        tmp_path,
        {
            'ems.profiles.control': 'input_select.ems_shared_profile',
            'ems.profiles.goal': 'input_select.ems_shared_profile',
        },
    )
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))

    values = {'shared': 'AUTOMATIC'}
    read_counts = {'shared': 0}

    def read_bool(_entity_id):
        return False

    def read_float(_entity_id, default=0.0):
        return default

    def read_int(_entity_id, default=0):
        return default

    def read_str(entity_id, default=''):
        if entity_id == 'input_select.ems_shared_profile':
            read_counts['shared'] += 1
            return values['shared']
        return default

    first_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    values['shared'] = 'MANUAL_SAFE'
    second_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    audit = runtime_context_dynamic_read_audit()

    assert first_cfg.profiles.control == 'AUTOMATIC'
    assert second_cfg.profiles.control == 'MANUAL_SAFE'
    assert second_cfg.profiles.goal == 'MANUAL_SAFE'
    assert read_counts['shared'] == 2
    shared_entries = [
        entry for entry in audit['entries']
        if entry['entity_id'] == 'input_select.ems_shared_profile'
    ]
    assert len(shared_entries) == 1
    assert shared_entries[0]['count'] == 2
    assert shared_entries[0]['underlying_reads'] == 1
    assert shared_entries[0]['cache_hits'] == 1


@pytest.mark.unit
def test_runtime_context_dynamic_read_audit_sort_is_pyscript_safe(project_root, tmp_path, monkeypatch):
    grouped_path = _write_grouped_config_with_overrides(
        project_root,
        tmp_path,
        {
            'ems.profiles.control': 'input_select.ems_shared_profile',
            'ems.profiles.goal': 'input_select.ems_shared_profile',
            'ems.profiles.forecast': 'input_select.ems_forecast_profile',
        },
    )
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))

    def read_bool(_entity_id):
        return False

    def read_float(_entity_id, default=0.0):
        return default

    def read_int(_entity_id, default=0):
        return default

    def read_str(entity_id, default=''):
        if entity_id == 'input_select.ems_shared_profile':
            return 'AUTOMATIC'
        if entity_id == 'input_select.ems_forecast_profile':
            return 'NONE'
        return default

    read_runtime_context(read_bool, read_float, read_int, read_str)
    audit = runtime_context_dynamic_read_audit()
    source = (project_root / 'modules' / 'ems_adapter' / 'runtime_context.py').read_text(encoding='utf-8')

    assert hasattr(runtime_context_mod, '_dynamic_read_audit_sort_key') is False
    assert 'sort(key=' not in source
    assert audit['entries']
    shared_entries = [
        entry for entry in audit['entries']
        if entry['entity_id'] == 'input_select.ems_shared_profile'
    ]
    assert len(shared_entries) == 1
    assert shared_entries[0]['count'] == 2
    previous_sort_key = None
    for entry in audit['entries']:
        sort_key = (
            -int(entry['count']),
            -int(entry['cache_hits']),
            str(entry['entity_id']),
            str(entry['default_repr']),
        )
        if previous_sort_key is not None:
            assert previous_sort_key <= sort_key
        previous_sort_key = sort_key


@pytest.mark.unit
def test_runtime_context_metrics_report_cache_hit_and_miss(project_root, tmp_path, monkeypatch):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped_path = tmp_path / 'grouped_metrics_cache.yaml'
    grouped_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    read_runtime_context(read_bool, read_float, read_int, read_str)
    first_metrics = runtime_context_mod.runtime_context_metrics_attrs()
    read_runtime_context(read_bool, read_float, read_int, read_str)
    second_metrics = runtime_context_mod.runtime_context_metrics_attrs()

    assert first_metrics['policy_engine_static_context_cache_hit'] is False
    assert first_metrics['policy_engine_static_context_cache_misses'] == 1
    assert second_metrics['policy_engine_static_context_cache_hit'] is True
    assert second_metrics['policy_engine_static_context_cache_hits'] == 1


@pytest.mark.unit
def test_runtime_context_static_cache_miss_on_first_read(project_root, tmp_path, monkeypatch):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped_path = tmp_path / 'grouped_static_cache.yaml'
    grouped_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert metrics['policy_engine_static_context_cache_hit'] is False
    assert metrics['policy_engine_static_context_cache_misses'] == 1


@pytest.mark.unit
def test_runtime_context_static_cache_hit_when_config_signature_unchanged(project_root, tmp_path, monkeypatch):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped_path = tmp_path / 'grouped_static_cache_hit.yaml'
    grouped_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    read_runtime_context(read_bool, read_float, read_int, read_str)
    _cfg, entities = read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert metrics['policy_engine_static_context_cache_hit'] is True
    assert metrics['policy_engine_static_context_cache_hits'] == 1
    assert str(entities['device_policies']).startswith('sensor.ems_device_policies')


@pytest.mark.unit
def test_runtime_context_reuses_static_plan_object_on_cache_hit_while_refreshing_dynamic_values(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))

    values = {
        ENT['devices']['EV_CHARGER']['priority']: 4,
    }

    def read_bool(_entity_id):
        return False

    def read_float(_entity_id, default=0.0):
        return values.get(_entity_id, default)

    def read_int(entity_id, default=0):
        return values.get(entity_id, default)

    def read_str(_entity_id, default=''):
        return values.get(_entity_id, default)

    first_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    first_plan = runtime_context_mod._RUNTIME_CONTEXT_CONFIG_CACHE['core_config_plan']
    values[ENT['devices']['EV_CHARGER']['priority']] = 9
    second_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    second_plan = runtime_context_mod._RUNTIME_CONTEXT_CONFIG_CACHE['core_config_plan']

    assert first_plan is second_plan
    assert first_cfg.ev_charger.policy.priority == 4
    assert second_cfg.ev_charger.policy.priority == 9
    assert runtime_context_mod.runtime_context_metrics_attrs()['policy_engine_static_context_cache_hit'] is True


@pytest.mark.unit
def test_runtime_context_static_cache_invalidates_when_config_signature_changes(project_root, tmp_path, monkeypatch):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped_path = tmp_path / 'grouped_static_cache_invalidate.yaml'
    grouped_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))
    runtime_context_mod._reset_runtime_context_config_cache()
    signatures = iter(((1, 100), (1, 100), (2, 100)))
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: next(signatures))
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    read_runtime_context(read_bool, read_float, read_int, read_str)
    read_runtime_context(read_bool, read_float, read_int, read_str)
    read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert metrics['policy_engine_static_context_cache_hit'] is False
    assert metrics['policy_engine_static_context_cache_hits'] == 1
    assert metrics['policy_engine_static_context_cache_misses'] == 2


@pytest.mark.unit
def test_runtime_context_cache_reset_for_tests(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    read_bool, read_float, read_int, read_str = _stub_entity_readers()

    read_runtime_context(read_bool, read_float, read_int, read_str)
    runtime_context_mod._reset_runtime_context_config_cache()

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    cache = runtime_context_mod._RUNTIME_CONTEXT_CONFIG_CACHE
    assert cache['config'] is None
    assert cache['grouped_entities'] is None
    assert cache['hits'] == 0
    assert cache['misses'] == 0
    assert metrics['policy_engine_static_context_cache_hits'] == 0
    assert metrics['policy_engine_static_context_cache_misses'] == 0


@pytest.mark.unit
def test_dynamic_control_profile_value_updates_with_static_context_cache_hit(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    values = {
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
    }
    read_bool, read_float, read_int, read_str = _mutable_entity_readers(values)

    first_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    values[ENT['adjustable_surplus_load']] = 'HOME_BATTERY'
    second_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert first_cfg.adjustable_surplus_load == 'EV_CHARGER'
    assert second_cfg.adjustable_surplus_load == 'HOME_BATTERY'
    assert metrics['policy_engine_static_context_cache_hit'] is True


@pytest.mark.unit
def test_dynamic_input_number_threshold_updates_with_static_context_cache_hit(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    values = {
        ENT['battery_protect_soc']: 7,
    }
    read_bool, read_float, read_int, read_str = _mutable_entity_readers(values)

    first_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    values[ENT['battery_protect_soc']] = 11
    second_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert first_cfg.battery_protect_soc == 7
    assert second_cfg.battery_protect_soc == 11
    assert metrics['policy_engine_static_context_cache_hit'] is True


@pytest.mark.unit
def test_dynamic_input_boolean_force_on_updates_with_static_context_cache_hit(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    values = {
        ENT['ev_force_on']: False,
    }
    read_bool, read_float, read_int, read_str = _mutable_entity_readers(values)

    first_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    values[ENT['ev_force_on']] = True
    second_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert first_cfg.ev_charger.policy.force_on is False
    assert second_cfg.ev_charger.policy.force_on is True
    assert metrics['policy_engine_static_context_cache_hit'] is True


@pytest.mark.unit
def test_dynamic_priority_value_updates_with_static_context_cache_hit(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    values = {
        ENT['devices']['EV_CHARGER']['priority']: 4,
    }
    read_bool, read_float, read_int, read_str = _mutable_entity_readers(values)

    first_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)
    values[ENT['devices']['EV_CHARGER']['priority']] = 9
    second_cfg, _entities = read_runtime_context(read_bool, read_float, read_int, read_str)

    metrics = runtime_context_mod.runtime_context_metrics_attrs()
    assert first_cfg.ev_charger.policy.priority == 4
    assert second_cfg.ev_charger.policy.priority == 9
    assert metrics['policy_engine_static_context_cache_hit'] is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ('initial_values', 'update_fn', 'extract_fn', 'expected_first', 'expected_second'),
    (
        (
            {'input_select.ems_control_profile': 'AUTOMATIC'},
            lambda values: values.__setitem__('input_select.ems_control_profile', 'MANUAL'),
            lambda cfg: cfg.profiles.control,
            'AUTOMATIC',
            'MANUAL',
        ),
        (
            {'input_select.ems_goal_profile': 'NET_ZERO'},
            lambda values: values.__setitem__('input_select.ems_goal_profile', 'MAX_EXPORT'),
            lambda cfg: cfg.profiles.goal,
            'NET_ZERO',
            'MAX_EXPORT',
        ),
        (
            {'input_select.ems_forecast_profile': 'NONE'},
            lambda values: values.__setitem__('input_select.ems_forecast_profile', 'HAEO'),
            lambda cfg: cfg.profiles.forecast,
            'NONE',
            'HAEO',
        ),
        (
            {'input_select.ems_guard_profile': 'NORMAL_LIMITS'},
            lambda values: values.__setitem__('input_select.ems_guard_profile', 'STRICT_LIMITS'),
            lambda cfg: cfg.profiles.guard,
            'NORMAL_LIMITS',
            'STRICT_LIMITS',
        ),
        (
            {ENT['deadband_w']: 25},
            lambda values: values.__setitem__(ENT['deadband_w'], 60),
            lambda cfg: cfg.deadband_w,
            25,
            60,
        ),
        (
            {'switch.charger_control': False},
            lambda values: values.__setitem__('switch.charger_control', True),
            lambda cfg: cfg.ev_charger.adapter.enabled,
            False,
            True,
        ),
        (
            {ENT['devices']['RELAY1']['force_on']: False},
            lambda values: values.__setitem__(ENT['devices']['RELAY1']['force_on'], True),
            lambda cfg: cfg.devices['RELAY1'].policy.force_on,
            False,
            True,
        ),
    ),
)
def test_dynamic_fields_refresh_with_static_context_cache_hit(
    project_root,
    monkeypatch,
    initial_values,
    update_fn,
    extract_fn,
    expected_first,
    expected_second,
):
    first_cfg, second_cfg = _assert_dynamic_value_updates_on_static_cache_hit(
        project_root,
        monkeypatch,
        dict(initial_values),
        update_fn,
        extract_fn,
    )

    assert extract_fn(first_cfg) == expected_first
    assert extract_fn(second_cfg) == expected_second


@pytest.mark.unit
def test_ev_priority_change_does_not_mutate_battery_priority_on_cache_hit(project_root, monkeypatch):
    first_cfg, second_cfg = _assert_dynamic_value_updates_on_static_cache_hit(
        project_root,
        monkeypatch,
        {
            'input_number.ems_adjustable_surplus_load_priority': 3,
            ENT['devices']['EV_CHARGER']['priority']: 4,
        },
        lambda values: values.__setitem__(ENT['devices']['EV_CHARGER']['priority'], 9),
        lambda cfg: cfg.ev_charger.policy.priority,
    )

    assert first_cfg.home_battery.policy.priority == 3
    assert second_cfg.home_battery.policy.priority == 3
    assert first_cfg.ev_charger.policy.priority == 4
    assert second_cfg.ev_charger.policy.priority == 9


@pytest.mark.unit
def test_runtime_context_metrics_measure_dynamic_reads_separately_from_core_config_build(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))
    values = {
        ENT['battery_protect_soc']: 7,
        ENT['adjustable_surplus_load']: 'EV_CHARGER',
        ENT['devices']['EV_CHARGER']['priority']: 4,
        ENT['ev_force_on']: False,
    }

    def slow_bool(entity_id):
        time.sleep(0.002)
        return bool(values.get(entity_id, False))

    def slow_float(entity_id, default=0.0):
        time.sleep(0.002)
        return values.get(entity_id, default)

    def slow_int(entity_id, default=0):
        time.sleep(0.002)
        return values.get(entity_id, default)

    def slow_str(entity_id, default=''):
        time.sleep(0.002)
        return values.get(entity_id, default)

    read_runtime_context(slow_bool, slow_float, slow_int, slow_str)
    metrics = runtime_context_mod.runtime_context_metrics_attrs()

    assert metrics['policy_engine_dynamic_config_reads_ms'] > 0
    assert metrics['policy_engine_core_config_build_ms'] >= 0
    assert metrics['policy_engine_core_config_materialize_total_ms'] >= metrics['policy_engine_dynamic_config_reads_ms']
    assert abs(
        (
            metrics['policy_engine_core_config_build_ms']
            + metrics['policy_engine_dynamic_config_reads_ms']
        )
        - metrics['policy_engine_core_config_materialize_total_ms']
    ) <= 5


@pytest.mark.unit
def test_core_config_materialization_submetrics_are_numeric_and_non_negative(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))
    runtime_context_mod._reset_runtime_context_config_cache()
    monkeypatch.setattr(runtime_context_mod, '_grouped_config_file_signature', lambda _path: (1, 100))

    read_runtime_context(*_stub_entity_readers())
    metrics = runtime_context_mod.runtime_context_metrics_attrs()

    metric_keys = (
        'policy_engine_core_config_materialize_total_ms',
        'policy_engine_core_config_profiles_global_runtime_state_ms',
        'policy_engine_core_config_devices_ms',
        'policy_engine_core_config_home_battery_ms',
        'policy_engine_core_config_haeo_ms',
        'policy_engine_core_config_role_constraints_ms',
        'policy_engine_core_config_derived_fields_ms',
        'policy_engine_dynamic_runtime_snapshot_ms',
        'policy_engine_policy_context_view_ms',
        'policy_engine_dynamic_config_unique_reads',
        'policy_engine_dynamic_config_audit_entries',
        'policy_engine_dynamic_config_logical_reads',
        'policy_engine_dynamic_config_reader_total_ms',
        'policy_engine_dynamic_config_reader_overhead_ms',
        'policy_engine_dynamic_config_audit_overhead_ms',
        'policy_engine_dynamic_runtime_snapshot_dict_nodes',
        'policy_engine_dynamic_runtime_snapshot_tuple_nodes',
        'policy_engine_dynamic_runtime_snapshot_dynamic_refs_seen',
        'policy_engine_dynamic_runtime_snapshot_dynamic_refs_unique',
        'policy_engine_dynamic_runtime_snapshot_dynamic_ref_cache_hits',
    )

    for key in metric_keys:
        assert isinstance(metrics[key], int)
        assert metrics[key] >= 0
    assert isinstance(metrics['policy_engine_dynamic_config_full_audit_collected'], bool)


@pytest.mark.unit
def test_harness_builds_scenario_entity_registry_from_scenario_yaml(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'

    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    assert harness.grouped_config_path == scenario_dir / 'EMS_config.yaml'
    assert harness.grouped_config is not None
    assert harness.ent['devices']['RELAY3']['enabled'] == 'switch.relay_3_2'
    assert harness.dev('RELAY3', 'enabled') == 'switch.relay_3_2'
    assert harness.dev('RELAY3', 'enabled') == 'switch.relay_3_2'
    assert harness.policy_mod['ENT'] is harness.ent


@pytest.mark.unit
def test_scenario_harness_registry_is_isolated_from_root_ent(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'

    assert 'RELAY3' not in ((ENT.get('devices') or {}))

    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    assert harness.grouped_config_path == scenario_dir / 'EMS_config.yaml'
    assert 'RELAY3' in harness.ent['devices']
    assert harness.dev('RELAY3', 'enabled') == 'switch.relay_3_2'


@pytest.mark.unit
def test_seed_active_surplus_devices_uses_harness_registry_for_scenario_only_relay(project_root):
    from tests.e2e_entity.scenario_runner import seed_active_surplus_devices

    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'
    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    harness.set_entities({
        harness.ent['devices']['RELAY1']['priority']: 4,
        harness.ent['devices']['EV_CHARGER']['priority']: 3,
        harness.ent['devices']['RELAY2']['priority']: 2,
        harness.dev('RELAY3', 'priority'): 1,
    })

    seed_active_surplus_devices(
        harness,
        active_device_ids=('RELAY3', 'RELAY1', 'EV_CHARGER', 'RELAY2'),
        relay_states={'RELAY3': True},
    )

    assert harness.get(harness.dev('RELAY3', 'enabled')) is True
    assert harness.get(harness.ent['active_surplus_devices']) == 'RELAY1,EV_CHARGER,RELAY2,RELAY3'


@pytest.mark.unit
def test_harness_device_entity_error_includes_scenario_config_path(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'
    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    with pytest.raises(KeyError) as exc:
        harness.device_entity('RELAY3', 'missing_field')

    message = str(exc.value)
    assert 'device_id=RELAY3' in message
    assert 'field=missing_field' in message
    assert str(scenario_dir / 'EMS_config.yaml') in message


@pytest.mark.unit
def test_grouped_config_dual_read_accepts_grouped_specific_entity_ids(project_root, tmp_path, monkeypatch):
    grouped_path = _write_grouped_config_with_override(
        project_root,
        tmp_path,
        'ems.global_config.deadband_w',
        'input_number.grouped_deadband_w',
    )
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))

    harness = QuarterScenarioHarness(project_root)
    harness.set_entities(
        {
            ENT['deadband_w']: 30,
            'input_number.grouped_deadband_w': 35,
        }
    )

    returned_config = harness.policy_mod['read_config']()
    status = harness.policy_mod['_GROUPED_CONFIG_DUAL_READ_STATUS']

    assert returned_config.deadband_w == 35
    assert status['source'] == 'grouped_config'
    assert status['ok'] is True
    assert status['reason'] == 'loaded'
    assert status['mismatches'] == ()
    harness.step(note='parity mismatch trace')
    attrs = harness.getattrs(ENT['policy_diagnostics'])
    assert attrs['config_grouped_production_ready'] is True
    assert attrs['config_grouped_production_ready_reason'] == 'ready'


@pytest.mark.unit
def test_grouped_config_source_runs_full_policy_dispatch_writer_chain(project_root, monkeypatch):
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(project_root / 'example_EMS_config.yaml'))

    harness = QuarterScenarioHarness(project_root)
    snap = harness.step(
        {
            ENT['grid_power_w']: -2600,
            ENT['quarter_energy_balance']: -0.6,
            ENT['rpnz_w']: 1800,
            ENT['required_power_consumption_kw']: 1.8,
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        },
        note='grouped source e2e',
    )

    trace_attrs = snap['attrs'][ENT['policy_diagnostics']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']

    assert trace_attrs['config_source'] == 'grouped_config'
    assert trace_attrs['config_dual_read_enabled'] is True
    assert trace_attrs['config_dual_read_ok'] is True
    assert trace_attrs['config_dual_read_reason'] == 'loaded'
    assert writer_attrs['writer_trace_canonical_contract'] == 'devices'
    assert writer_attrs['victron']['policy_source'] == 'canonical'
    assert writer_attrs['devices']['EV_CHARGER']['policy_source'] == 'canonical'
    assert writer_attrs['devices']['RELAY1']['policy_source'] == 'canonical'
    assert writer_attrs['devices']['RELAY2']['policy_source'] == 'canonical'


@pytest.mark.unit
def test_grouped_config_two_ev_boundary_targets_selected_ev(project_root, tmp_path, monkeypatch):
    grouped_path, grouped_config = _write_grouped_config_with_second_ev(project_root, tmp_path)
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))

    entities = build_runtime_entities_from_grouped_config(grouped_config)
    assert entities['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert entities['devices']['EV_GARAGE']['enabled'] == 'switch.ev_garage_enabled'
    assert entities['devices']['EV_GARAGE']['current_a'] == 'number.ev_garage_current_a'

    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_path)
    harness.set_entities(
        {
            ENT['adjustable_surplus_load']: 'EV_GARAGE',
            ENT['adjustable_primary_load']: 'HOME_BATTERY',
            ENT['adjustable_surplus_activation']: 2000,
            ENT['grid_power_w']: -3200,
            ENT['quarter_energy_balance']: -0.8,
            ENT['rpnz_w']: 3200,
            ENT['required_power_consumption_kw']: 3.2,
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
            'input_number.ems_ev_garage_min_power_w': 1380,
            'input_number.ems_ev_garage_max_power_w': 3680,
            'input_number.ems_ev_garage_power_step_w': 460,
            'input_number.ems_surplus_ev_garage_priority': 4,
            'input_boolean.ems_ev_garage_surplus_allowed': True,
            'input_number.ems_ev_garage_low_pv_threshold_w': 1600,
            'input_number.ems_ev_garage_low_pv_cycles': 2,
            'input_number.ems_ev_garage_release_cycles': 2,
            'input_number.ems_ev_garage_current_step_a': 2,
            'input_number.ems_ev_garage_phases': 1,
            'input_number.ems_ev_garage_voltage_v': 230,
            'input_boolean.ems_ev_garage_force_on': False,
            'switch.ev_garage_enabled': False,
            'number.ev_garage_current_a': 6,
        }
    )

    harness.step(note='activate first surplus device')
    harness.step(note='activate selected garage ev')
    snap = harness.step(note='selected garage ev writes')
    trace_attrs = snap['attrs'][ENT['policy_diagnostics']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']
    policies = {item['device_id']: item for item in trace_attrs['device_policies']}

    assert set(harness.policy_mod['read_config']().devices) >= {'EV_CHARGER', 'EV_GARAGE'}
    assert trace_attrs['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert trace_attrs['selected_ev_device_id'] == 'EV_GARAGE'
    assert policies['EV_GARAGE']['enabled'] is True
    assert policies['EV_GARAGE']['target_w'] == 3680
    assert policies['EV_CHARGER']['enabled'] is False
    assert policies['EV_CHARGER']['target_w'] == 0
    assert trace_attrs['previous_ev_device_states']['EV_GARAGE']['mode'] == trace_attrs['ev_policy_mode']
    assert writer_attrs['devices']['EV_CHARGER']['policy_source'] == 'canonical'
    assert writer_attrs['devices']['EV_GARAGE']['policy_source'] == 'canonical'
    assert writer_attrs['devices']['EV_GARAGE']['target_current_a'] == 16
    assert snap['values']['switch.ev_garage_enabled'] is True
    assert snap['values']['number.ev_garage_current_a'] == 16


@pytest.mark.unit
def test_zero_ev_config_runs_policy_without_ev_policy(project_root, tmp_path, monkeypatch):
    grouped_path, grouped_config = _write_grouped_config_without_ev(project_root, tmp_path)
    monkeypatch.setenv('EMS_GROUPED_CONFIG_PATH', str(grouped_path))

    entities = build_runtime_entities_from_grouped_config(grouped_config)
    assert entities['ev_device_ids'] == ()

    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_path)
    harness.set_entities(
        {
            ENT['adjustable_surplus_load']: 'HOME_BATTERY',
            ENT['adjustable_primary_load']: '',
            ENT['adjustable_surplus_activation']: 2000,
            ENT['grid_power_w']: -2400,
            ENT['quarter_energy_balance']: -0.5,
            ENT['rpnz_w']: 2400,
            ENT['required_power_consumption_kw']: 2.4,
            ENT['pv_power_kw']: 3.5,
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        }
    )

    snap = harness.step(note='grouped config no ev policy run')
    trace_attrs = snap['attrs'][ENT['policy_diagnostics']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']
    policies = {item['device_id']: item for item in trace_attrs['device_policies']}

    assert trace_attrs['ev_device_ids'] == ()
    assert trace_attrs['selected_ev_device_id'] == ''
    assert trace_attrs['ev_policy_mode'] == 'skip'
    assert trace_attrs['ev_target_w'] == 0
    assert 'EV_CHARGER' not in policies
    assert set(policies) == {'HOME_BATTERY', 'RELAY1', 'RELAY2'}
    assert 'EV_CHARGER' not in writer_attrs['devices']
    assert set(writer_attrs['devices']) == {'RELAY1', 'RELAY2'}


@pytest.mark.unit
def test_policy_outputs_publish_device_policy_contract_and_payloads(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    harness.step(note='policy output contract attrs')

    attrs = harness.getattrs(ENT['policy_diagnostics'])
    assert attrs['policy_output_contract'] == 'device_policy_primary'
    assert attrs['device_policies']


@pytest.mark.unit
def test_canonical_tuple_key_is_stable_for_semantically_equal_payloads(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    stable_key = harness.policy_mod['_stable_key']

    left = {
        'device_policies': (
            {'device_id': 'RELAY1', 'enabled': True, 'targets': ('a', 'b')},
            {'device_id': 'RELAY2', 'enabled': False, 'meta': {'priority': 2, 'mode': 'off'}},
        ),
        'flags': {'alpha', 'beta'},
    }
    right = {
        'flags': {'beta', 'alpha'},
        'device_policies': [
            {'targets': ['a', 'b'], 'enabled': True, 'device_id': 'RELAY1'},
            {'meta': {'mode': 'off', 'priority': 2}, 'enabled': False, 'device_id': 'RELAY2'},
        ],
    }
    changed = {
        'device_policies': [
            {'targets': ['a', 'b'], 'enabled': True, 'device_id': 'RELAY1'},
            {'meta': {'mode': 'off', 'priority': 2}, 'enabled': True, 'device_id': 'RELAY2'},
        ],
        'flags': {'beta', 'alpha'},
    }

    assert stable_key(left) == stable_key(right)
    assert stable_key(left) != stable_key(changed)


@pytest.mark.unit
def test_device_policies_sensor_uses_monotonic_version_and_only_advances_on_change(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    device_policies_entity = ENT['device_policies']

    harness.set_entities(
        {
            ENT['grid_power_w']: -2200,
            ENT['quarter_energy_balance']: -0.4,
            ENT['rpnz_w']: 2200,
            ENT['required_power_consumption_kw']: 2.2,
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        }
    )
    harness._run_policy_loop()
    first_state = harness.get(device_policies_entity)
    first_attrs = harness.getattrs(device_policies_entity)

    harness._run_policy_loop()
    second_state = harness.get(device_policies_entity)
    second_attrs = harness.getattrs(device_policies_entity)

    harness.set_entities({ENT['control_profile']: 'MANUAL'})
    harness._run_policy_loop()
    third_state = harness.get(device_policies_entity)
    third_attrs = harness.getattrs(device_policies_entity)

    assert first_state == first_attrs['device_policies_version']
    assert first_attrs['device_policies_state_kind'] == 'monotonic_version'
    assert second_state == first_state
    assert second_attrs['device_policies'] == first_attrs['device_policies']
    assert third_state == third_attrs['device_policies_version']
    assert third_state > second_state
    assert third_attrs['device_policies'] != second_attrs['device_policies']


@pytest.mark.unit
def test_dispatch_command_sensor_uses_monotonic_version_and_carries_dispatch_attrs(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    dispatch_entity = ENT['dispatch_command']

    harness.set_entities(
        {
            ENT['grid_power_w']: -2200,
            ENT['quarter_energy_balance']: -0.4,
            ENT['rpnz_w']: 2200,
            ENT['required_power_consumption_kw']: 2.2,
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        }
    )
    harness._run_policy_loop()
    first_state = harness.get(dispatch_entity)
    first_attrs = harness.getattrs(dispatch_entity)

    harness._run_policy_loop()
    second_state = harness.get(dispatch_entity)
    second_attrs = harness.getattrs(dispatch_entity)

    harness.set_entities(
        {
            ENT['grid_power_w']: -3000,
            ENT['quarter_energy_balance']: -0.7,
            ENT['rpnz_w']: 3000,
            ENT['required_power_consumption_kw']: 2.4,
        }
    )
    harness._run_policy_loop()
    third_state = harness.get(dispatch_entity)
    third_attrs = harness.getattrs(dispatch_entity)

    assert first_state == first_attrs['dispatch_command_version']
    assert first_attrs['dispatch_command_state_kind'] == 'monotonic_version'
    assert second_state == first_state
    # The changed measurements do not alter the dispatch command in this scenario.
    assert third_state == second_state
    assert third_attrs == second_attrs
    assert 'surplus_device_dispatch_action' in third_attrs
    assert 'surplus_device_targets' in third_attrs
    assert 'surplus_freeze_until_ts' in third_attrs


@pytest.mark.unit
def test_policy_state_sensor_uses_monotonic_version_and_carries_previous_state_fields(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    policy_state_entity = ENT['policy_state']

    harness._run_policy_loop()
    first_state = harness.get(policy_state_entity)
    first_attrs = harness.getattrs(policy_state_entity)
    harness._run_policy_loop()
    second_state = harness.get(policy_state_entity)
    second_attrs = harness.getattrs(policy_state_entity)
    harness.set_entities({ENT['devices']['RELAY1']['force_on']: True})
    harness._run_policy_loop()
    third_state = harness.get(policy_state_entity)
    third_attrs = harness.getattrs(policy_state_entity)

    assert first_state == first_attrs['policy_state_version']
    assert first_attrs['policy_state_state_kind'] == 'monotonic_version'
    assert second_state == first_state
    assert third_state == third_attrs['policy_state_version']
    assert third_state > second_state
    assert 'haeo_nz_quarter_key' in second_attrs
    assert 'haeo_nz_primary_device_id' in second_attrs
    assert 'prev_force_on_device_ids' in second_attrs


@pytest.mark.unit
def test_policy_state_helpers_prefer_canonical_sensor_over_trace(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    harness.set_attrs(
        ENT['policy_state'],
        {
            'haeo_nz_quarter_key': 'canonical-quarter',
            'haeo_nz_primary_device_id': 'HOME_BATTERY',
            'prev_force_on_device_ids': ('RELAY2',),
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'haeo_nz_quarter_key': 'trace-quarter',
            'haeo_nz_primary_device_id': 'EV_CHARGER',
            'prev_force_on_device_ids': ('RELAY1',),
        },
    )

    assert harness.policy_mod['_policy_state_attr'](harness.ent, 'haeo_nz_quarter_key', '') == 'canonical-quarter'
    assert harness.policy_mod['_policy_state_attr'](harness.ent, 'haeo_nz_primary_device_id', '') == 'HOME_BATTERY'
    assert harness.policy_mod['_read_previous_force_on_device_ids'](harness.ent) == ('RELAY2',)
