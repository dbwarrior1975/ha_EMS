import pytest

from ems_adapter.config_loader import load_grouped_ems_config, validate_grouped_ems_config
from tests.e2e_entity.entity_registry import build_scenario_entity_registry
from tests.entity_ids import ENT
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.smoke
def test_release_example_config_loads_and_runs_direct_v3_smoke_step(project_root):
    grouped_config_path = project_root / 'example_EMS_config.yaml'
    grouped_config = load_grouped_ems_config(grouped_config_path)
    validation = validate_grouped_ems_config(grouped_config)
    runtime_entities = build_scenario_entity_registry(grouped_config)

    assert validation.ok is True
    assert 'HOME_BATTERY' in runtime_entities['devices']
    assert runtime_entities['ev_device_ids'] == ('EV_CHARGER',)
    assert runtime_entities['relay_device_ids'] == ('RELAY1', 'RELAY2')

    harness = QuarterScenarioHarness(project_root, scenario_config_path=grouped_config_path)
    snap = harness.step(
        {
            **runtime_inputs_for_net_zero_intent(
                harness.ent,
                rpnz_w=1800,
                required_power_consumption_kw=1.8,
                at_s=harness.now,
            ),
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        },
        note='release example smoke',
    )

    trace_attrs = snap['attrs'][ENT['policy_diagnostics']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']

    assert trace_attrs['config_source'] == 'direct_tick_frame_v3_e2e'
    assert trace_attrs['runtime_input_contract'] == 'direct_tick_frame_v3'
    assert writer_attrs['writer_trace_canonical_contract'] == 'devices'
    assert 'EV_CHARGER' in writer_attrs['devices']
    assert 'RELAY1' in writer_attrs['devices']
    assert 'RELAY2' in writer_attrs['devices']
