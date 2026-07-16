import pytest
import yaml

from ems_adapter.config_loader import load_grouped_ems_config
from tests.e2e_entity.entity_registry import build_scenario_entity_registry
from tests.entity_ids import ENT
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness







def _write_scenario_config_with_second_ev(project_root, tmp_path):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices']['EV_GARAGE'] = {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_consuming_regulation': True,
            'supports_producing_regulation': False,
            'uses_hard_off_lifecycle': True,
            'min_absorb_w': 'input_number.ems_ev_garage_min_power_w',
            'max_absorb_w': 'input_number.ems_ev_garage_max_power_w',
            'min_produce_w': 0,
            'max_produce_w': 0,
            'step_w': 'input_number.ems_ev_garage_power_step_w',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_ev_garage_priority',
            'producing_priority': 0,
            'surplus_allowed': 'input_boolean.ems_ev_garage_surplus_allowed',
            'surplus_dispatch_mode': 'max_absorb',
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
    path = tmp_path / 'scenario_two_ev.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path, config


def _write_scenario_config_without_ev(project_root, tmp_path):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices'] = {
        device_id: device
        for device_id, device in config['ems']['devices'].items()
        if device.get('kind') != 'EV_CHARGER'
    }
    config['ems']['global_config']['primary_consuming_device_id'] = 'input_select.ems_primary_consuming_device'
    haeo_devices = config['ems'].get('haeo', {}).get('devices', {})
    if isinstance(haeo_devices, dict):
        haeo_devices.pop('EV_CHARGER', None)
    path = tmp_path / 'scenario_no_ev.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path, config












@pytest.mark.unit
def test_scenario_config_resolution_prefers_explicit_path_over_scenario(tmp_path, monkeypatch):
    explicit_path = tmp_path / 'explicit.yaml'
    env_path = tmp_path / 'env.yaml'
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    (scenario_dir / 'EMS_config.yaml').write_text('scenario: true\n', encoding='utf-8')
    explicit_path.write_text('explicit: true\n', encoding='utf-8')
    env_path.write_text('env: true\n', encoding='utf-8')

    resolved = QuarterScenarioHarness._resolve_scenario_config_path(
        project_root=tmp_path,
        scenario_config_path=explicit_path,
        scenario_dir=scenario_dir,
    )

    assert resolved == explicit_path


@pytest.mark.unit
def test_scenario_config_resolution_prefers_scenario_config_over_root_fallbacks(tmp_path, monkeypatch):
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    scenario_path = scenario_dir / 'EMS_config.yaml'
    scenario_path.write_text('scenario: true\n', encoding='utf-8')
    (tmp_path / 'example_EMS_config.yaml').write_text('root_example: true\n', encoding='utf-8')
    (tmp_path / 'EMS_config.yaml').write_text('root_ems: true\n', encoding='utf-8')

    resolved = QuarterScenarioHarness._resolve_scenario_config_path(
        project_root=tmp_path,
        scenario_dir=scenario_dir,
    )

    assert resolved == scenario_path




@pytest.mark.unit
def test_scenario_config_resolution_fails_when_scenario_dir_has_no_ems_config(tmp_path, monkeypatch):
    scenario_dir = tmp_path / 'scenario'
    scenario_dir.mkdir()
    (scenario_dir / 'example_EMS_config.yaml').write_text('scenario_example: true\n', encoding='utf-8')

    with pytest.raises(FileNotFoundError) as exc:
        QuarterScenarioHarness._resolve_scenario_config_path(
            project_root=tmp_path,
            scenario_dir=scenario_dir,
        )

    assert str(scenario_dir) in str(exc.value)
    assert 'EMS_config.yaml' in str(exc.value)


@pytest.mark.unit
def test_scenario_config_resolution_prefers_root_example_before_root_ems(tmp_path, monkeypatch):
    root_example = tmp_path / 'example_EMS_config.yaml'
    root_ems = tmp_path / 'EMS_config.yaml'
    root_example.write_text('root_example: true\n', encoding='utf-8')
    root_ems.write_text('root_ems: true\n', encoding='utf-8')

    resolved = QuarterScenarioHarness._resolve_scenario_config_path(project_root=tmp_path)

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
def test_harness_builds_scenario_entity_registry_from_scenario_yaml(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'

    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    assert harness.scenario_config_path == scenario_dir / 'EMS_config.yaml'
    assert harness.scenario_config is not None
    assert harness.ent['devices']['RELAY3']['enabled'] == 'switch.relay_3_2'
    assert harness.dev('RELAY3', 'enabled') == 'switch.relay_3_2'
    assert harness.dev('RELAY3', 'enabled') == 'switch.relay_3_2'
    assert 'ENT' not in harness.policy_mod


@pytest.mark.unit
def test_scenario_harness_registry_is_isolated_from_root_ent(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'

    assert 'RELAY3' not in ((ENT.get('devices') or {}))

    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    assert harness.scenario_config_path == scenario_dir / 'EMS_config.yaml'
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
def test_direct_runtime_v5_two_ev_candidate_pool_uses_canonical_device_id_routing(project_root, tmp_path, monkeypatch):
    scenario_path, scenario_config = _write_scenario_config_with_second_ev(project_root, tmp_path)

    entities = build_scenario_entity_registry(scenario_config)
    assert entities['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert entities['devices']['EV_GARAGE']['enabled'] == 'switch.ev_garage_enabled'
    assert entities['devices']['EV_GARAGE']['current_a'] == 'number.ev_garage_current_a'

    harness = QuarterScenarioHarness(project_root, scenario_config_path=scenario_path)
    harness.set_entities(
        {
            ENT['primary_consuming_device_selector']: 'HOME_BATTERY',
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=4000,
                required_power_consumption_kw=4.0,
                at_s=harness.now,
            ),
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
    harness.step(note='activate higher-priority garage ev')
    snap = harness.step(note='generic two-ev pool writes garage ev')
    trace_attrs = snap['attrs'][ENT['policy_diagnostics']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']
    policies = {item['device_id']: item for item in trace_attrs['device_policies']}

    assert set(harness.policy_mod['read_config']().devices) >= {'EV_CHARGER', 'EV_GARAGE'}
    assert trace_attrs['ev_device_ids'] == ('EV_CHARGER', 'EV_GARAGE')
    assert {'EV_CHARGER', 'EV_GARAGE'} <= set(trace_attrs['surplus_candidate_device_ids'])
    assert policies['EV_GARAGE']['enabled'] is True
    assert policies['EV_GARAGE']['target_w'] == 3680
    assert policies['EV_CHARGER']['enabled'] is False
    assert policies['EV_CHARGER']['target_w'] == 0
    assert trace_attrs['previous_device_states']['EV_GARAGE']['mode'] == policies['EV_GARAGE']['mode']
    assert writer_attrs['devices']['EV_CHARGER']['device_policy_contract'] == 'canonical'
    assert writer_attrs['devices']['EV_GARAGE']['device_policy_contract'] == 'canonical'
    assert writer_attrs['devices']['EV_GARAGE']['target_current_a'] == 16
    assert snap['values']['switch.ev_garage_enabled'] is True
    assert snap['values']['number.ev_garage_current_a'] == 16


@pytest.mark.unit
def test_direct_runtime_v5_zero_ev_config_runs_policy_without_ev_policy(project_root, tmp_path, monkeypatch):
    scenario_path, scenario_config = _write_scenario_config_without_ev(project_root, tmp_path)

    entities = build_scenario_entity_registry(scenario_config)
    assert entities['ev_device_ids'] == ()

    harness = QuarterScenarioHarness(project_root, scenario_config_path=scenario_path)
    harness.set_entities(
        {
            ENT['primary_consuming_device_selector']: '',
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=2400,
                required_power_consumption_kw=2.4,
                at_s=harness.now,
                pv_power_kw=3.5,
            ),
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        }
    )

    snap = harness.step(note='direct v3 no ev policy run')
    trace_attrs = snap['attrs'][ENT['policy_diagnostics']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']
    policies = {item['device_id']: item for item in trace_attrs['device_policies']}

    assert trace_attrs['ev_device_ids'] == ()
    assert 'EV_CHARGER' not in policies
    assert set(policies) == {'HOME_BATTERY', 'RELAY1', 'RELAY2'}
    assert 'EV_CHARGER' not in writer_attrs['devices']
    assert set(writer_attrs['devices']) == {'RELAY1', 'RELAY2'}


@pytest.mark.unit
def test_canonical_tuple_key_is_stable_for_semantically_equal_payloads(project_root):
    harness = QuarterScenarioHarness(project_root, scenario_config_path=project_root / 'example_EMS_config.yaml')
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
    harness = QuarterScenarioHarness(project_root, scenario_config_path=project_root / 'example_EMS_config.yaml')
    device_policies_entity = ENT['device_policies']

    harness.set_entities(
        {
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=2200,
                required_power_consumption_kw=2.2,
                at_s=harness.now,
            ),
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
    harness = QuarterScenarioHarness(project_root, scenario_config_path=project_root / 'example_EMS_config.yaml')
    dispatch_entity = ENT['dispatch_command']

    harness.set_entities(
        {
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=2200,
                required_power_consumption_kw=2.2,
                at_s=harness.now,
            ),
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
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=3000,
                required_power_consumption_kw=2.4,
                at_s=harness.now,
            ),
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
    assert 'surplus_dispatch_action' in third_attrs
    assert 'surplus_dispatch_device_id' in third_attrs
    assert 'surplus_dispatch_contract' in third_attrs
    assert 'surplus_candidates' not in third_attrs
    assert 'surplus_freeze_until_ts' in third_attrs


@pytest.mark.unit
def test_policy_state_sensor_uses_monotonic_version_and_carries_previous_state_fields(project_root):
    harness = QuarterScenarioHarness(project_root, scenario_config_path=project_root / 'example_EMS_config.yaml')
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
    assert 'haeo_nz_primary_consuming_device_id' in second_attrs
    assert 'prev_force_on_device_ids' in second_attrs


@pytest.mark.unit
def test_policy_state_helpers_prefer_canonical_sensor_over_trace(project_root):
    harness = QuarterScenarioHarness(project_root, scenario_config_path=project_root / 'example_EMS_config.yaml')
    harness.set_attrs(
        ENT['policy_state'],
        {
            'haeo_nz_quarter_key': 'canonical-quarter',
            'haeo_nz_primary_consuming_device_id': 'HOME_BATTERY',
            'prev_force_on_device_ids': ('RELAY2',),
        },
    )
    harness.set_attrs(
        ENT['policy_diagnostics'],
        {
            'haeo_nz_quarter_key': 'trace-quarter',
            'haeo_nz_primary_consuming_device_id': 'EV_CHARGER',
            'prev_force_on_device_ids': ('RELAY1',),
        },
    )

    assert harness.policy_mod['_policy_state_attr'](harness.ent, 'haeo_nz_quarter_key', '') == 'canonical-quarter'
    assert harness.policy_mod['_policy_state_attr'](harness.ent, 'haeo_nz_primary_consuming_device_id', '') == 'HOME_BATTERY'
    assert harness.policy_mod['_read_previous_force_on_device_ids'](harness.ent) == ('RELAY2',)


@pytest.mark.unit
def test_e2e_harness_executes_strict_direct_tick_frame_v5_contract(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'
    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    snap = harness.step(
        set_values=runtime_inputs_for_net_zero_intent(
            harness.ent,
            rpnz_w=500,
            required_power_consumption_kw=3.5,
            at_s=0,
        ),
        note='direct v3 contract probe',
        at_s=0,
    )

    diagnostics = snap['attrs'][ENT['policy_diagnostics']]
    assert diagnostics['config_source'] == 'direct_tick_frame_v5_e2e'
    assert diagnostics['runtime_input_contract'] == 'direct_tick_frame_v5'
    packet_snapshot = harness.direct_runtime.snapshot()
    assert packet_snapshot.policy_config['schema_version'] == 5
    assert packet_snapshot.measurements['schema_version'] == 5
    assert packet_snapshot.policy_state['schema_version'] == 5
    assert packet_snapshot.tick_frame.policy_config_revision == packet_snapshot.policy_config['revision']


@pytest.mark.unit
def test_direct_runtime_v5_third_relay_routes_from_packet_entity_registry(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'
    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)

    policy_packet = harness.direct_runtime.build_policy_config_packet()
    assert policy_packet['entity_registry']['devices']['RELAY3']['enabled'] == 'switch.relay_3_2'

    harness.set_attrs(
        ENT['device_policies'],
        {
            'device_policies': [
                {
                    'device_id': 'RELAY3',
                    'target_w': 7500,
                    'enabled': True,
                    'mode': 'relay',
                    'reason': 'relay_policy',
                }
            ]
        },
    )
    harness.set_entities({'switch.relay_3_2': False})
    harness._run_writer_loop()

    trace = harness.getattrs(ENT['actuator_writer_trace'])
    assert trace['devices']['RELAY3']['written'] is True
    assert trace['devices']['RELAY3']['action'] == 'turn_on'
    assert harness.get('switch.relay_3_2') is True


@pytest.mark.unit
def test_direct_runtime_v5_third_relay_missing_packet_mapping_fails_closed(project_root):
    scenario_dir = project_root / 'tests' / 'e2e_entity' / 'net_zero_priority_order_quarter_3_relays'
    harness = QuarterScenarioHarness(project_root, scenario_dir=scenario_dir)
    original_registry = harness.direct_runtime._entity_registry

    def registry_without_relay3():
        registry = original_registry()
        registry['devices']['RELAY3'] = {}
        return registry

    harness.direct_runtime._entity_registry = registry_without_relay3
    harness.set_attrs(
        ENT['device_policies'],
        {
            'device_policies': [
                {
                    'device_id': 'RELAY3',
                    'target_w': 7500,
                    'enabled': True,
                    'mode': 'relay',
                    'reason': 'relay_policy',
                }
            ]
        },
    )
    harness.set_entities({'switch.relay_3_2': False})
    harness._run_writer_loop()

    trace = harness.getattrs(ENT['actuator_writer_trace'])
    assert trace['devices']['RELAY3']['written'] is False
    assert trace['devices']['RELAY3']['reason'] == 'missing_actuator_entity'
    assert harness.get('switch.relay_3_2') is False
