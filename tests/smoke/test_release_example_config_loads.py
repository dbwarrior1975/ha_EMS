import pytest

from ems_adapter.config_loader import load_grouped_ems_config, validate_grouped_ems_config
from ems_adapter.runtime_context import build_runtime_entities_from_grouped_config
from tests.entity_ids import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.smoke
def test_release_example_grouped_config_loads_and_runs_smoke_step(project_root):
    grouped_config_path = project_root / 'example_EMS_config.yaml'
    grouped_config = load_grouped_ems_config(grouped_config_path)
    validation = validate_grouped_ems_config(grouped_config)
    runtime_entities = build_runtime_entities_from_grouped_config(grouped_config)

    assert validation.ok is True
    assert 'HOME_BATTERY' in runtime_entities['devices']
    assert runtime_entities['ev_device_ids'] == ('EV_CHARGER',)
    assert runtime_entities['relay_device_ids'] == ('RELAY1', 'RELAY2')

    harness = QuarterScenarioHarness(project_root, grouped_config_path=grouped_config_path)
    snap = harness.step(
        {
            ENT['grid_power_w']: -2600,
            ENT['hourly_energy_balance']: -0.6,
            ENT['rpnz_w']: 1800,
            ENT['required_power_consumption_kw']: 1.8,
            ENT['soc']: 55,
            ENT['min_cell_voltage_v']: 3.2,
            ENT['haeo_battery_active_power_fresh_source']: 0,
            ENT['haeo_ev_active_power_fresh_source']: 0,
        },
        note='release example smoke',
    )

    trace_attrs = snap['attrs'][ENT['policy_decision_trace']]
    writer_attrs = snap['attrs']['sensor.ems_actuator_writer_trace']

    assert trace_attrs['config_source'] == 'grouped_config'
    assert trace_attrs['config_grouped_path'] == str(grouped_config_path)
    assert trace_attrs['policy_output_contract'] == 'device_policy_primary'
    assert writer_attrs['writer_trace_canonical_contract'] == 'devices'
    assert 'EV_CHARGER' in writer_attrs['devices']
    assert 'RELAY1' in writer_attrs['devices']
    assert 'RELAY2' in writer_attrs['devices']
