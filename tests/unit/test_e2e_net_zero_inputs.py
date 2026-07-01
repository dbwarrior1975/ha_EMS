import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness
from tests.e2e_entity.scenario_runner import run_scenario_steps
from tests.entity_ids import ENT


@pytest.mark.unit
def test_runtime_inputs_helper_generates_raw_values_matching_expected_derived(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')
    values = runtime_inputs_for_net_zero_intent(
        harness.ent,
        rpnz_w=-10,
        required_power_consumption_kw=-3.4,
        at_s=135,
        pv_power_kw=1.7,
    )

    run_scenario_steps(
        harness,
        [
            {
                'at_s': 135,
                'note': 'raw helper smoke',
                'set': values,
                'expect_derived': {
                    **expect_derived_for_net_zero_intent(
                        rpnz_w=-10,
                        required_power_consumption_kw=-3.4,
                        at_s=135,
                    ),
                    'required_power_consumption_kw': {'value': -3.4, 'tolerance': 0.001},
                },
            },
        ],
    )

    assert harness._legacy_derived_override_active is False
    assert harness.policy_mod['derive_net_zero_inputs'] is harness._real_derive_net_zero_inputs


@pytest.mark.unit
def test_runtime_inputs_helper_rejects_nonzero_required_power_above_export_stop_threshold(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')

    with pytest.raises(AssertionError, match='cannot encode nonzero NET_ZERO required_power above export stop threshold'):
        runtime_inputs_for_net_zero_intent(
            harness.ent,
            rpnz_w=-1000,
            required_power_consumption_kw=1.0,
            at_s=0,
        )


@pytest.mark.unit
def test_legacy_keys_keep_derived_override_active(project_root):
    harness = QuarterScenarioHarness(project_root, grouped_config_path=project_root / 'example_EMS_config.yaml')

    harness.step(
        at_s=135,
        note='legacy override still supported',
        set_values={
            ENT['required_power_consumption_kw']: -3.4,
            ENT['rpnz_w']: -10.0,
            ENT['grid_power_w']: 3290.0,
        },
    )

    assert harness._legacy_derived_override_active is True
    assert harness.policy_mod['derive_net_zero_inputs'].__func__ is harness._derive_net_zero_inputs_for_test.__func__
